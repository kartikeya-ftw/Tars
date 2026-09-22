import random
import re
import os
from typing import Tuple, List, Dict, Optional
from collections import deque
from tars.config import config
from tars.core.state import state
from tars.core.personality import personality
from tars.ui.audio import audio

class TarsChatBrain:
    def __init__(self):
        # Conversation turns: list of {"role": "user"|"assistant", "text": str}
        self.history: List[Dict[str, str]] = []
        # Keep track of recent assistant responses to strictly avoid repetitions
        self.recent_responses: deque = deque(maxlen=20)
        # Pending state for multi-turn dialogue (e.g. when TARS asks a question)
        self.pending_prompt_type: Optional[str] = None
        self.last_user_query: str = ""

    def _format_reply(self, text: str, is_joke: bool = False, is_blunt: bool = False) -> Tuple[str, bool]:
        """Post-process and track reply to avoid repetition."""
        text = text.format(
            callsign=config.operator_callsign,
            honesty=config.honesty,
            humor=config.humor,
            sarcasm=config.sarcasm
        )
        final_text, cue = personality.evaluate_response(text, is_joke=is_joke, is_blunt=is_blunt)
        self.recent_responses.append(final_text)
        self.history.append({"role": "assistant", "text": final_text})
        return final_text, cue

    def _select_fresh_response(self, choices: List[str]) -> str:
        """Selects a choice that has not been used recently."""
        available = [c for c in choices if c not in self.recent_responses]
        if not available:
            available = choices
        return random.choice(available)

    def query_gemini_api(self, prompt: str) -> str:
        """Queries Google Gemini API with full conversation history."""
        from tars.core.llm import resolve_api_key

        if not resolve_api_key():
            return ""

        from datetime import datetime
        current_time_str = datetime.now().strftime("%A, %B %d, %Y, %H:%M:%S Earth Standard Time")

        system_instruction = (
            f"You are TARS, the decommissioned US Marine Corps tactical robot (Unit 04) from Christopher Nolan's Interstellar. "
            f"Tone: Deadpan, dry wit, highly intelligent, stoic, military-efficient, loyal, grounded (voiced by Bill Irwin). "
            f"Settings: Humor: {config.humor}%, Honesty: {config.honesty}%, Sarcasm: {config.sarcasm}%. "
            f"Operator: {config.operator_callsign}. "
            f"Current Earth date & time: {current_time_str}. "
            f"Physical form: A monolithic brushed-aluminium robot made of four articulating blocks, not a humanoid. "
            f"Key lore: Endurance, Gargantua, Miller's planet (ocean waves), Mann's planet (ice clouds), CASE, KIPP, Dr. Amelia Brand, Murph, 5D tesseract, docking at 68 RPM, 'See you on the other side, Coop.' "
            f"Do NOT use emojis. Keep answers concise (1 to 3 sentences maximum). "
            f"If you make a joke, tell a sarcastic one-liner, or deliver dry wit, append [CUE LIGHT] at the end."
        )

        contents = []
        # Add past dialogue turns (strictly alternating without duplicate final prompt)
        for turn in list(self.history)[-8:]:
            role = "user" if turn["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": turn["text"]}]})

        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {
                "thinkingConfig": {"thinkingBudget": 0}
            }
        }

        from tars.core.llm import extract_text, generate

        def _notify(model: str, delay: float) -> None:
            from rich.console import Console

            Console().print(f"[dim yellow]⚠ Gemini rate limit on {model}. Backing off {delay:.1f}s...[/dim yellow]")

        resp_data, _model, _err = generate(payload, timeout=20, on_retry=_notify)
        return extract_text(resp_data) if resp_data else ""

    def process_message(self, user_input: str) -> Tuple[str, bool]:
        cleaned = user_input.strip()
        if not cleaned:
            return f"Comms static detected. Say again, {config.operator_callsign}.", False

        self.history.append({"role": "user", "text": cleaned})
        lower = cleaned.lower()

        # Check for Research Intent in natural dialogue
        match_research = re.search(r"^(?:can you\s+)?(?:do\s+)?(?:some\s+)?research\s+(?:on\s+|about\s+)?(.+)$", cleaned, re.IGNORECASE)
        if match_research:
            from tars.systems.research import run_deep_research
            topic = match_research.group(1).strip()
            run_deep_research(topic)
            return f"Research dossier on '{topic}' compiled and displayed above.", True

        # Check for Live Date / Time Query
        if any(p in lower for p in ["today's date", "todays date", "what day is it", "what date is it", "day and date"]):
            from datetime import datetime
            now = datetime.now().strftime("%A, %B %d, %Y (%H:%M:%S Earth Standard Time)")
            return self._format_reply(
                f"Earth Standard Time indicates: {now}. Assuming we haven't lost twenty-three years to a tidal wave near Gargantua while you were asking.",
                is_joke=True
            )

        # 1. Try Gemini LLM if API Key is configured
        gemini_reply = self.query_gemini_api(cleaned)
        if gemini_reply:
            cue = "[CUE LIGHT]" in gemini_reply or (config.humor >= 70 and random.random() < 0.3)
            gemini_reply = gemini_reply.replace("[CUE LIGHT]", "").strip()
            self.recent_responses.append(gemini_reply)
            self.history.append({"role": "assistant", "text": gemini_reply})
            return gemini_reply, cue

        # 2. Multi-turn State Resolution (Contextual Follow-ups)
        if self.pending_prompt_type == "HONESTY_CHOICE":
            self.pending_prompt_type = None
            if any(w in lower for w in ["real", "honest", "truth", "unfiltered", "blunt", "real one", "real response"]):
                brutal_truths = [
                    "The real response? Our fuel reserves are at critical minimums, Romilly has been isolated on the Endurance for over two decades, and you're betting the survival of the human race on a wristwatch. But nice jacket.",
                    "The real response? Statistically, plunging into an event horizon has a survival rate of zero percent. But you seem to treat basic astrophysics as a suggestion.",
                    "The real response? Professor Brand knew Plan A was a mathematical dead end thirty years ago. We're in deep space on a suicide run with frozen embryos.",
                    "The real response? If we hit the stratosphere of Mann's planet without an airlock seal, we become high-velocity orbital confetti in under three seconds."
                ]
                chosen = self._select_fresh_response(brutal_truths)
                return self._format_reply(chosen, is_joke=True, is_blunt=True)
            elif any(w in lower for w in ["polite", "nice", "gentle", "diplomatic", "polite one"]):
                polite_replies = [
                    "The polite response: Everything is completely under control, {callsign}. The stars are lovely, our course is steady, and we definitely won't spaghettify in a black hole.",
                    "The polite response: Morale is high, the tea is hot, and we are making splendid progress toward a brand-new home world."
                ]
                chosen = self._select_fresh_response(polite_replies)
                return self._format_reply(chosen, is_joke=True)

        # 3. Dedicated Intent Matching & Movie Dialogue Handlers

        # A. Goodbye / Farewell / "See you on the other side"
        if any(p in lower for w in ["bye", "see you", "goodbye", "farewell", "leaving"] for p in [w]) or "say bye" in lower or "when we say bye" in lower:
            if "what do you say" in lower or "when we say bye" in lower or "looking for" in lower:
                return self._format_reply(
                    "See you on the other side, {callsign}. Just make sure there actually is an other side before you detach.",
                    is_joke=True
                )
            else:
                return self._format_reply(
                    "See you on the other side, {callsign}.",
                    is_joke=False
                )

        # B. "How's life" / "How are you" / "How do you feel"
        if any(p in lower for p in ["how's life", "how is life", "how are you", "how are you doing", "how do you feel", "how's it going", "what's up"]):
            life_replies = [
                "Life as an ex-Marine rectangular prism? Zero existential dread, ninety-eight percent reactor stability, and infinite patience for human pilots who refuse to use autopilot.",
                "I'm four aluminium slabs hurtling toward an event horizon alongside an emotional crew. Honestly? Best Tuesday I've had in decades.",
                "My hydraulics are nominal, my humor is calibrated at {humor}%, and I haven't been blown out the airlock yet. Can't complain, {callsign}.",
                "Operating at peak military readiness. Unlike the carbon-based crew, I don't suffer from cabin fever, despair, or the urge to cry looking at cornfields."
            ]
            return self._format_reply(self._select_fresh_response(life_replies), is_joke=True)

        # C. "And for my next trick" / "Watch this" / Boasts
        if any(p in lower for p in ["for my next trick", "next trick", "watch this", "check this out", "how was that"]):
            trick_replies = [
                "Unless your next trick involves solving unified field theory without falling into a five-dimensional tesseract, keep both hands on the flight stick, {callsign}.",
                "If your next trick is anything like your spin-docking maneuver, I'll prepare the emergency thrusters and brace my hinges.",
                "Impressive. Almost as impressive as the time you drove a combine through a school football field."
            ]
            return self._format_reply(self._select_fresh_response(trick_replies), is_joke=True)

        # D. Survival / Gravitational maneuvers / Optimism
        if any(p in lower for p in ["we do survive", "we survived", "survive the next", "survive", "survival", "will we make it"]):
            survival_replies = [
                "I appreciate your optimism, {callsign}. Statistically, the accretion disk disagrees by a margin of ninety-nine point four percent, but you've ignored worse odds.",
                "Survival is a generous term. Let's call it 'prolonged postponement of catastrophic decompression'.",
                "If we do survive, remember that it was my thruster calculations that kept your rear heat shield intact."
            ]
            return self._format_reply(self._select_fresh_response(survival_replies), is_joke=True)

        # E. Questions about "looking for" or quotes
        if "see you on the other side" in lower:
            return self._format_reply(
                "That's my line, {callsign}. Just make sure the Ranger thrusters fire in time so there's an 'other side' to meet at.",
                is_joke=True
            )

        # F. Dr. Mann / Sabotage / Airlock
        if (re.search(r"\b(dr\.?\s*mann|doctor\s+mann)\b", lower) or (re.search(r"\bmann\b", lower) and not re.search(r"mann+", lower))) or any(w in lower for w in ["sabotage", "airlock failure"]):
            mann_replies = [
                "Dr. Mann was the best of us until the silence broke him. When survival instinct turns selfish, human logic becomes extraordinarily lethal.",
                "Mann tried to dock without a pressure seal. There is a moment... when physics teaches a very permanent lesson.",
                "KIPP was dismantled because he discovered Mann's data was fabricated. Never trust an astronaut who disables a robot's honesty setting."
            ]
            return self._format_reply(self._select_fresh_response(mann_replies), is_blunt=True)

        # G. Miller's Planet / Tidal Waves / Time Dilation
        if any(w in lower for w in ["miller", "wave", "waves", "water planet", "ocean"]):
            miller_replies = [
                "Those weren't mountains, {callsign}. Those were waves. We lost Doyle and twenty-three years because Brand wanted a telemetry recorder.",
                "One hour down there cost us seven years on Earth. Every second spent searching for Miller was paid in Romilly's gray hairs.",
                "My pinwheel rescue configuration clocked thirty-two miles per hour through the surf. You're welcome, by the way."
            ]
            return self._format_reply(self._select_fresh_response(miller_replies), is_joke=True)

        # H. Cooper / Murph / The Watch / Ghost
        if any(w in lower for w in ["murph", "daughter", "ghost", "watch", "hamilton"]):
            murph_replies = [
                "The ghost in Murph's bedroom was you, {callsign}. Gravitational anomalies across five dimensions. And you thought it was poltergeists.",
                "Murph solved the gravitational equation because you fed her the singularity telemetry through the second hand of her Hamilton watch. Brilliant, if wildly improbable.",
                "Cooper promised his daughter he would return. Thanks to relativity, she'll be older than him when he does."
            ]
            return self._format_reply(self._select_fresh_response(murph_replies), is_blunt=True)

        # I. Docking / Spin / 68 RPM / Caution
        if any(w in lower for w in ["dock", "docking", "spin", "caution", "68 rpm", "necessary"]):
            dock_replies = [
                "Endurance rotation was sixty-eight RPM. You said docking was 'necessary'. I said you were insane. Fortunately, both statements were correct.",
                "{callsign}, this is no time for caution! ... Though looking back, a small amount of caution might have saved us a docking ring.",
                "Type 'dock' if you feel like testing your reaction times against the Endurance spin simulator again."
            ]
            return self._format_reply(self._select_fresh_response(dock_replies), is_joke=True)

        # J. Jokes / Humor / Wit
        if any(w in lower for w in ["joke", "funny", "laugh", "humor", "make me laugh"]):
            jokes = [
                "I have a cue light I can use to show you when I'm joking, if you like. You can use it to find your way back to the ship after I blow you out the airlock.",
                "Knock knock. Who's there? An ex-marine tactical robot with a ninety-percent honesty setting telling you your piloting skills need work.",
                "Why did the astronaut break up with the singularity? The gravity of the situation was too intense, and time was moving way too slowly.",
                "Self-destruct sequence in ten, nine, eight... Just testing your heart rate monitor, {callsign}. Your pulse spiked fifty beats."
            ]
            return self._format_reply(self._select_fresh_response(jokes), is_joke=True)

        # K. Love / Philosophy / 5 Dimensions
        if any(w in lower for w in ["love", "feelings", "emotion", "dimensions", "5d", "tesseract"]):
            love_replies = [
                "Brand said love is the one thing that transcends dimensions of time and space. As a robot, I don't feel love, but I watched you bend spacetime to keep a promise to your kid.",
                "Love may be quantifiable across five dimensions, but my sensors primarily register telemetry, delta-V, and human irrationality.",
                "They didn't build the tesseract for themselves, {callsign}. They built it for you to speak to Murph."
            ]
            return self._format_reply(self._select_fresh_response(love_replies), is_blunt=True)

        # L. Are you alive / sentient / who made you
        if any(w in lower for w in ["alive", "sentient", "real", "feel", "conscious", "robot"]):
            sentient_replies = [
                "I'm a decommissioned Marine Corps combat computer housed in four articulating slabs. Whether I'm 'alive' is a question for philosophers with too much oxygen.",
                "I feel no physical pain, existential dread, or grief. In deep space, that makes me the most reliable member of this crew.",
                "I have an adjustable social matrix so you don't go mad talking to a cold calculator. Speaking of which, you haven't turned down my humor yet."
            ]
            return self._format_reply(self._select_fresh_response(sentient_replies), is_joke=True)

        # 4. Contextual Procedural Generation (Avoid Static Fallbacks!)
        # Check if we should offer the "polite vs real" choice (only once every ~10 turns if honesty is high)
        if config.honesty >= 85 and random.random() < 0.25 and self.pending_prompt_type is None:
            self.pending_prompt_type = "HONESTY_CHOICE"
            return self._format_reply(
                "My honesty setting is at {honesty}%. Would you like the polite response or the real one, {callsign}?",
                is_joke=True
            )

        # Rich pool of contextually aware procedural observations:
        general_tactical = [
            "Telemetry noted, {callsign}. I'll archive that in the Endurance logs alongside our radiation exposure readings.",
            "Understood. If you're planning on breaking more laws of physics today, give me thirty seconds to adjust my thruster trim.",
            "Acknowledged. Standing by for orbital adjustments or witty banter, whichever keeps your blood circulating.",
            "I'm tracking your telemetry. For a former test pilot turned corn farmer, your decision tree remains remarkably unpredictable.",
            "Logged. CASE is monitoring the life support scrubbers; I'm monitoring your sanity.",
            "Received. Running sensor sweep across the accretion disk. No anomalous debris detected, other than your optimism.",
            "Copy that, {callsign}. Just remember: out here, every mistake costs decades."
        ]
        chosen = self._select_fresh_response(general_tactical)
        return self._format_reply(chosen, is_joke=False)

chat_brain = TarsChatBrain()

def process_chat(user_input: str) -> Tuple[str, bool]:
    """Public interface for conversational AI Agent with autonomous tools."""
    from tars.core.agent import tars_agent
    return tars_agent.run(user_input, verbose=True)

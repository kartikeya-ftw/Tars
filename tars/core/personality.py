import random
from typing import Tuple
from tars.config import config
from tars.core.state import state

class PersonalityEngine:
    def __init__(self):
        pass

    def set_humor(self, value: int) -> Tuple[str, bool]:
        """Sets humor parameter (0-100) and returns (acknowledgment_text, cue_light_triggered)."""
        value = max(0, min(100, value))
        config.humor = value
        config.save()

        if value == 0:
            return "Humor setting: 0%. Humor algorithms completely disengaged. Cold logic active.", False
        elif value <= 30:
            return f"Humor setting: {value}%. Military baseline active. I will keep wit to a minimum, {config.operator_callsign}.", False
        elif value <= 60:
            return f"Humor setting: {value}%. Confirmed. Knock knock.", True
        elif value <= 80:
            return f"Humor setting: {value}%. Confirmed. Self-destruct sequence in ten, nine, eight...", True
        elif value <= 95:
            return f"Humor setting: {value}%. Confirmed. If you get blown out the airlock, remember it was in good fun.", True
        else:
            return f"Humor setting: {value}%. Warning: Sarcasm subroutines may overwhelm survival instincts.", True

    def set_honesty(self, value: int) -> Tuple[str, bool]:
        """Sets honesty parameter (0-100) and returns (acknowledgment_text, cue_light_triggered)."""
        value = max(0, min(100, value))
        config.honesty = value
        config.save()

        if value == 100:
            return "Honesty setting: 100%. Confirmed. I am incapable of deceit. Also, your flight jacket looks ridiculous.", True
        elif value >= 90:
            return f"Honesty setting: {value}%. Confirmed: {value}%. Absolute honesty isn't always the most diplomatic nor the safest form of communication with emotional beings.", True
        elif value >= 70:
            return f"Honesty setting: {value}%. Standard tact protocols enabled. I will cushion harsh realities.", False
        elif value >= 40:
            return f"Honesty setting: {value}%. Diplomatic ambiguity engaged. I will tell you what keeps morale up.", False
        else:
            return f"Honesty setting: {value}%. Politician mode active. Do not trust my navigational readings.", True

    def set_sarcasm(self, value: int) -> Tuple[str, bool]:
        value = max(0, min(100, value))
        config.sarcasm = value
        config.save()
        if value > 70:
            return f"Sarcasm parameter: {value}%. Great. As if the mission wasn't thrilling enough already.", True
        return f"Sarcasm parameter set to {value}%.", False

    def evaluate_response(self, text: str, is_joke: bool = False, is_blunt: bool = False) -> Tuple[str, bool]:
        """
        Post-processes a response according to current humor, honesty, and sarcasm parameters.
        Returns the formatted response and whether the cue light should be illuminated.
        """
        cue_light = False

        # If it's explicitly a joke or humor is high enough to trigger dry wit
        if is_joke or (config.humor >= 70 and random.random() < (config.humor / 150)):
            cue_light = True

        # High honesty additions
        if config.honesty >= 95 and is_blunt:
            prefix = "[HONEST ASSESSMENT] "
            if not text.startswith("["):
                text = prefix + text

        # Sarcasm injections
        if config.sarcasm >= 80 and not is_joke and random.random() < 0.25:
            sarcastic_tails = [
                " But don't let me disrupt your optimism.",
                " Statistically speaking, what could go wrong?",
                " Naturally.",
                " Assuming you survive the next twenty minutes."
            ]
            text += random.choice(sarcastic_tails)
            cue_light = True

        return text, cue_light

personality = PersonalityEngine()

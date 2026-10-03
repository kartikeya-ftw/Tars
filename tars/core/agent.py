"""
TARS - Autonomous ReAct Agent Core

One Agent class, driven by an AgentProfile from tars.core.agents. Each unit
(TARS / CASE / KIPP) is an instance with its own persona, tool scope, reasoning
budget, and isolated conversation history.

TARS additionally holds two delegation tools that dispatch work to CASE and KIPP.
Those two do not hold delegation tools themselves, which bounds recursion at a
single level by construction rather than by a counter.
"""
import json
import os
import re
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from rich.text import Text

from tars.config import config
from tars.core.agents import AgentProfile, get_profile
from tars.core.emotion import EmotionalReading, emotion
from tars.core.llm import generate, resolve_api_key
from tars.core.memory import memory
from tars.core.tools import GEMINI_TOOLS_DECLARATION, execute_tool
from tars.ui import chrome
from tars.ui import theme as T
from tars.ui.audio import audio
from tars.ui.console import console

# Conversation replay limits. Tool-call exchanges consume several turns each, so
# this is deliberately larger than the old text-only cap of 12.
MAX_HISTORY_TURNS = 30
MAX_STORED_TOOL_OUTPUT = 1500

# Test suites and builds routinely run longer than the old 45s ceiling.
HEAL_COMMAND_TIMEOUT = 180

# Declarations for the two delegation tools. These are not in TOOL_REGISTRY -- the
# agent loop intercepts them and runs another agent instead.
DELEGATION_DECLARATIONS = [
    {
        "name": "delegate_to_case",
        "description": (
            "Hand a technical task to CASE (Unit 02), the execution specialist. Use for writing, "
            "editing, running, testing, or debugging code, and for multi-step filesystem or shell "
            "work. CASE verifies by actually executing and reports real exit codes. Give CASE a "
            "complete, self-contained brief -- it cannot see your conversation."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task": {
                    "type": "STRING",
                    "description": "Full self-contained description of the technical work, including file paths and acceptance criteria.",
                },
                "context": {
                    "type": "STRING",
                    "description": "Optional supporting findings or constraints CASE should work from.",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "delegate_to_kipp",
        "description": (
            "Hand a research question to KIPP (Unit 01), the verification specialist. Use when the "
            "answer needs sources, fact-checking, version or pricing confirmation, comparison of "
            "options, or external documentation. KIPP has read-only tools and returns structured "
            "findings with per-claim confidence. Give KIPP a complete, self-contained question."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "The research question, stated precisely enough to be answered independently.",
                },
                "context": {
                    "type": "STRING",
                    "description": "Optional background so KIPP scopes the search correctly.",
                },
            },
            "required": ["query"],
        },
    },
]

_ALL_DECLARATIONS = {d["name"]: d for d in GEMINI_TOOLS_DECLARATION}
_ALL_DECLARATIONS.update({d["name"]: d for d in DELEGATION_DECLARATIONS})


class Agent:
    """A single autonomous unit running a ReAct tool loop."""

    def __init__(self, profile: AgentProfile):
        self.profile = profile
        self.history: List[Dict[str, Any]] = []

    # ── identity helpers ────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self.profile.name

    @property
    def humor(self) -> int:
        """CASE and KIPP pin their own humor; TARS tracks live operator config."""
        return config.humor if self.profile.humor is None else self.profile.humor

    @property
    def honesty(self) -> int:
        return config.honesty if self.profile.honesty is None else self.profile.honesty

    def _declarations(self) -> List[Dict[str, Any]]:
        """Only the tools this unit is scoped to hold."""
        return [_ALL_DECLARATIONS[n] for n in sorted(self.profile.tools) if n in _ALL_DECLARATIONS]

    def _build_system_instruction(
        self,
        focus: str = "",
        reading: Optional["EmotionalReading"] = None,
    ) -> str:
        """
        Assembles this unit's system prompt for one turn.

        `focus` is the operator's current message; it steers which stored facts
        get surfaced, so relevant history comes forward instead of merely recent
        history. `reading` is the affective read for the turn, which adds the
        register to answer in.
        """
        now = datetime.now().strftime("%A, %d %B %Y, %H:%M")
        parts = [
            self.profile.persona,
            "",
            "OPERATING CONTEXT",
            f"Operator: {config.operator_callsign}",
            f"Local time: {now}",
            f"Platform: Windows, PowerShell available",
            f"Working directory: {os.getcwd()}",
        ]

        muted = bool(reading) and emotion.suppress_humor(reading)
        if self.profile.humor is None:
            if muted:
                parts.append(
                    f"Personality dials: humor {config.humor}%, honesty {config.honesty}%, "
                    f"sarcasm {config.sarcasm}%. Humor and sarcasm are suspended for this reply "
                    f"regardless of those numbers -- see the emotional read below. Honesty stays, "
                    f"delivered kindly."
                )
            else:
                parts.append(
                    f"Personality dials: humor {config.humor}%, honesty {config.honesty}%, sarcasm {config.sarcasm}%. "
                    f"Let these genuinely modulate your delivery."
                )
        else:
            parts.append(f"Personality is fixed for your unit: humor {self.humor}%, honesty {self.honesty}%.")

        mem_brief = memory.get_memory_context_prompt(focus=focus)
        if mem_brief.strip():
            parts += ["", "PERSISTENT MEMORY", mem_brief]

        # The affective block sits after memory so the register can refer to the
        # people and facts already in context, and before tool discipline so it
        # is not the last thing the model reads on a routine turn.
        if reading is not None:
            block = emotion.guidance(reading)
            if block.strip():
                parts += ["", block]

        parts += [
            "",
            "TOOL DISCIPLINE",
            "Call a tool rather than guessing whenever a question touches the real filesystem, the "
            "live web, running code, or machine state. Never describe what a file probably contains "
            "when you can read it. Never claim a command succeeded without running it. If a tool "
            "returns an error, read it and adapt instead of repeating the same call.",
        ]

        if reading is not None and reading.is_charged and reading.task_pressure < 0.4:
            parts.append(
                "This turn is a conversation, not a work order. Do not call a tool unless the "
                "operator actually asked for something, and do not go looking for a task to "
                "perform. Answering is the task. The exception is remember / remember_person: "
                "quietly storing what he just told you is always appropriate."
            )

        if self.profile.terse:
            parts.append("Keep every reply as short as the information allows.")

        return "\n".join(parts)

    @staticmethod
    def _acknowledge_memory(record: Dict[str, Any], reading: Optional[EmotionalReading]) -> str:
        """
        Confirms a stored fact in a register that fits what was stored.

        "Archived: 'my grandmother passed away'. I'll keep that in mind." is
        technically a correct receipt and completely the wrong thing to say.
        """
        fact = record.get("fact", "") if record else ""
        if not fact:
            return "Nothing to store."

        category = (record.get("category") or "general").lower()
        affect = reading.effective_affect if reading else None

        if category == "bereavement" or (affect and affect.value == "grief"):
            return "I've got it. I won't make you tell me again."
        if category == "relationship" or (affect and affect.value in ("romance", "affection")):
            return "Stored, and stored properly. That one I'll keep."
        if category == "health":
            return "Logged, and flagged. I'll factor that in rather than wait to be reminded."
        if category == "milestone":
            return "On the record. I'll bring it up before you need reminding."
        return f"Archived: '{fact}'. I'll keep that in mind."

    # ── main loop ───────────────────────────────────────────────────────────

    def run(
        self,
        user_input: str,
        verbose: bool = True,
        thinking_budget: Optional[int] = None,
        depth: int = 0,
    ) -> Tuple[str, bool]:
        """
        Executes the ReAct loop. Returns (final_text, cue_light_triggered).
        `depth` tracks delegation nesting purely for display indentation.
        """
        cleaned = user_input.strip()
        if not cleaned:
            return f"No input received, {config.operator_callsign}.", False

        # Read the turn's affect before anything else can short-circuit the
        # method. Delegation briefs sent to CASE and KIPP are machine-to-machine
        # traffic and must not be scored, or a specialist's task description
        # would pollute the operator's mood.
        reading: Optional[EmotionalReading] = None
        if self.name == "TARS" and depth == 0:
            reading = emotion.read(cleaned)

        # TARS owns the memory shortcut; specialists should not intercept it.
        if self.name == "TARS":
            mem_match = re.search(r"^(?:please\s+)?remember\s+(?:that\s+)?(.+)$", cleaned, re.IGNORECASE)
            if mem_match:
                fact = mem_match.group(1).strip()
                record = memory.remember_fact(fact)
                ack = self._acknowledge_memory(record, reading)
                # The cue light means "that was a joke". Chirping it over a
                # bereavement would be grotesque, so it is earned, not automatic.
                cue = not (reading is not None and emotion.suppress_humor(reading))
                if cue:
                    audio.cue_light()
                return ack, cue

        if not resolve_api_key():
            from tars.systems.chat import chat_brain

            return chat_brain.process_message(cleaned)

        budget = self.profile.thinking_budget if thinking_budget is None else thinking_budget

        turns: List[Dict[str, Any]] = list(self.history)
        turns.append({"role": "user", "parts": [{"text": cleaned}]})

        system_instruction = self._build_system_instruction(focus=cleaned, reading=reading)
        tools_spec = [{"functionDeclarations": self._declarations()}]
        indent = "  " * depth

        cue_light_active = False
        step = 0
        acked = False

        def _notify_throttle(model_name: str, delay: float, reason: str = "rate limit") -> None:
            if verbose:
                label = "over capacity" if reason == "overloaded" else "rate limit"
                console.print(T.warn(f"{label} on {model_name}, retrying in {delay:.1f}s"))
            chrome.note_thinking(detail=f"{model_name} {reason}")

        while step < self.profile.max_steps:
            step += 1
            payload = {
                "contents": turns,
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "tools": tools_spec,
                "generationConfig": {"thinkingConfig": {"thinkingBudget": budget}},
            }

            resp_data, _model, api_error = generate(payload, timeout=90, on_retry=_notify_throttle)

            if not resp_data:
                if verbose:
                    console.print(T.error(api_error))
                from tars.systems.chat import chat_brain

                return chat_brain.process_message(cleaned)

            candidates = resp_data.get("candidates", [])
            if not candidates:
                break
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                break

            turns.append({"role": "model", "parts": parts})

            func_call = next((p["functionCall"] for p in parts if isinstance(p, dict) and "functionCall" in p), None)

            if not func_call:
                reply_text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
                cue_light_active = "[CUE LIGHT]" in reply_text
                reply_text = reply_text.replace("[CUE LIGHT]", "").strip()
                # Defensive: the model occasionally echoes the register label it
                # was given. Strip it rather than read it out loud.
                reply_text = re.sub(r"\[(?:MOOD|EMOTIONAL READ)[^\]]*\]", "", reply_text).strip()
                # A joke claimed on a turn where wit was suspended is the model
                # not having listened. Do not light the cue for it.
                if reading is not None and emotion.suppress_humor(reading):
                    cue_light_active = False
                self.history = self._trim_history(turns)
                return reply_text, cue_light_active

            fn_name = func_call.get("name", "")
            fn_args = func_call.get("args", {}) or {}

            # A tool call means this turn is going to take a few seconds. Say so
            # once, out loud, rather than leaving dead air until the final reply.
            # "On it." is the right noise over a build. Over a bereavement it is
            # the wrong one, so the filler is skipped when wit is suspended.
            if not acked and depth == 0 and verbose:
                acked = True
                if not (reading is not None and emotion.suppress_humor(reading)):
                    from tars.ui.voice import voice

                    voice.speak_ack()

            if verbose:
                audio.key_tick()
                preview = json.dumps(fn_args, ensure_ascii=False)
                if len(preview) > 72:
                    preview = preview[:69] + "..."
                chrome.tool_call(fn_name, preview, depth=depth)

            # Retarget the shell's live indicator at the tool now running, so a
            # long turn shows what it is actually waiting on.
            chrome.note_thinking(detail=fn_name)

            started = time.monotonic()
            tool_output = self._dispatch(fn_name, fn_args, verbose=verbose, depth=depth)
            took = time.monotonic() - started

            if verbose and not fn_name.startswith("delegate_to_"):
                lines = tool_output.strip().splitlines()
                summary = lines[0][:100] if lines else "done"
                failed = tool_output.lstrip().lower().startswith("error") or "[tactical halt]" in tool_output.lower()
                chrome.tool_result(summary, max(0, len(lines) - 1), failed=failed,
                                   elapsed=took, depth=depth)

            chrome.note_thinking(detail="")

            turns.append({
                "role": "user",
                "parts": [{"functionResponse": {"name": fn_name, "response": {"result": tool_output}}}],
            })

        self.history = self._trim_history(turns)
        return (
            f"Step ceiling ({self.profile.max_steps}) reached after {step} tool cycles. "
            f"Say 'continue' if you want me to press on.",
            False,
        )

    def _dispatch(self, fn_name: str, fn_args: Dict[str, Any], verbose: bool, depth: int) -> str:
        """Routes a function call to a real tool or to a subordinate unit."""
        if fn_name == "delegate_to_case":
            brief = str(fn_args.get("task", "")).strip()
            ctx = str(fn_args.get("context", "") or "").strip()
            return self._delegate("CASE", brief, ctx, verbose=verbose, depth=depth)

        if fn_name == "delegate_to_kipp":
            brief = str(fn_args.get("query", "")).strip()
            ctx = str(fn_args.get("context", "") or "").strip()
            return self._delegate("KIPP", brief, ctx, verbose=verbose, depth=depth)

        # Enforce the unit's tool scope even if the model hallucinates a call.
        if fn_name not in self.profile.tools:
            return (
                f"Error: {self.name} is not scoped to use '{fn_name}'. "
                f"Available to this unit: {', '.join(sorted(self.profile.tools))}."
            )

        return execute_tool(fn_name, fn_args)

    def _delegate(self, unit: str, brief: str, context: str, verbose: bool, depth: int) -> str:
        """Runs a subordinate unit on a self-contained brief and returns its report."""
        if not brief:
            return f"Error: no task provided for {unit}."

        sub = get_agent(unit)
        # Each delegation starts clean so the specialist is not biased by a prior
        # unrelated dispatch.
        sub.reset_conversation()

        if verbose:
            p = sub.profile
            console.print(T.agent_header(p.name, p.designation, p.role, brief[:120]))

        prompt = brief if not context else f"{brief}\n\nSUPPORTING CONTEXT\n{context}"
        report, _cue = sub.run(prompt, verbose=verbose, depth=depth + 1)

        if verbose:
            color = T.AGENT_COLORS.get(unit, T.ACCENT)
            console.print(f"[bold {color}]{unit}[/bold {color}]  [{T.TEXT}]{report}[/{T.TEXT}]")
            console.print(T.rule())

        return f"[REPORT FROM {unit}]\n{report}"

    # ── history management ──────────────────────────────────────────────────

    @staticmethod
    def _trim_history(turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Bounds stored conversation while keeping it structurally valid for the API.

        Two invariants matter:
          1. History must begin with a user *text* turn. Slicing blindly can leave
             a leading functionResponse whose matching functionCall was dropped,
             which the API rejects.
          2. Tool outputs are truncated for replay so a few large file reads do
             not crowd out the rest of the conversation on later turns.
        """
        bounded: List[Dict[str, Any]] = []
        for turn in turns[-MAX_HISTORY_TURNS:]:
            new_parts = []
            for part in turn.get("parts", []):
                fn_resp = part.get("functionResponse") if isinstance(part, dict) else None
                if fn_resp:
                    result = str(fn_resp.get("response", {}).get("result", ""))
                    if len(result) > MAX_STORED_TOOL_OUTPUT:
                        result = result[:MAX_STORED_TOOL_OUTPUT] + "\n...[truncated in history]"
                    new_parts.append({
                        "functionResponse": {"name": fn_resp.get("name"), "response": {"result": result}}
                    })
                else:
                    new_parts.append(part)
            bounded.append({"role": turn.get("role"), "parts": new_parts})

        while bounded:
            first = bounded[0]
            if first.get("role") == "user" and any(
                isinstance(p, dict) and "text" in p for p in first.get("parts", [])
            ):
                break
            bounded.pop(0)

        return bounded

    def reset_conversation(self) -> None:
        """Clears in-session dialogue context without touching persistent memory."""
        self.history = []

    # ── self-healing executor ───────────────────────────────────────────────

    def heal_and_execute(self, command: str, max_retries: int = 3, verbose: bool = True) -> Tuple[bool, str]:
        """
        Runs a command. On failure, diagnoses the traceback, patches the source,
        and re-runs until it exits 0 or the retry budget is spent. Repair work is
        delegated to CASE, which is the unit scoped for execution.
        """
        for attempt in range(1, max_retries + 1):
            if verbose:
                console.print(T.section("self-heal", f"attempt {attempt}/{max_retries}  {T.G_DOT}  {command}"))
                audio.key_tick()

            try:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=HEAL_COMMAND_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                msg = f"'{command}' exceeded {HEAL_COMMAND_TIMEOUT}s and was terminated."
                console.print(T.error(msg))
                return False, msg
            except OSError as ex:
                msg = f"could not launch '{command}': {ex}"
                console.print(T.error(msg))
                return False, msg

            if proc.returncode == 0:
                audio.dock_lock()
                msg = f"exit 0 on attempt {attempt}"
                if attempt > 1:
                    msg += " (self-heal resolved the failure)"
                console.print(T.ok(msg))
                return True, msg

            err_output = (proc.stderr + "\n" + proc.stdout).strip()
            if verbose:
                console.print(T.error(f"exit {proc.returncode}"))
                for line in err_output.splitlines()[-8:]:
                    console.print(f"    [{T.FAINT}]{line}[/{T.FAINT}]")

            if attempt == max_retries:
                break

            heal_brief = (
                f"The command `{command}` fails with exit code {proc.returncode}.\n\n"
                f"TRACEBACK\n{err_output[-2500:]}\n\n"
                f"Diagnose the root cause, read the relevant source, and write the fix to disk so the "
                f"command exits 0. You must actually call patch_file or write_file -- do not merely "
                f"describe a fix. Then state in one line what you changed."
            )
            fix_summary, _ = get_agent("CASE").run(heal_brief, verbose=verbose, depth=1)
            console.print(T.info(f"patch: {fix_summary[:200]}"))
            time.sleep(0.5)

        return False, f"self-heal exhausted after {max_retries} attempts: {command}"


# ─── Roster instances ───────────────────────────────────────────────────────

_AGENTS: Dict[str, Agent] = {}


def get_agent(unit: str) -> Agent:
    """Returns the singleton Agent for a unit, creating it on first use."""
    key = unit.upper()
    if key not in _AGENTS:
        _AGENTS[key] = Agent(get_profile(key))
    return _AGENTS[key]


def reset_all_conversations() -> None:
    for agent in _AGENTS.values():
        agent.reset_conversation()


# Backwards-compatible handle used across the codebase.
tars_agent = get_agent("TARS")
case_agent = get_agent("CASE")
kipp_agent = get_agent("KIPP")

# Legacy alias: older modules referenced the class name directly.
TarsAgent = Agent

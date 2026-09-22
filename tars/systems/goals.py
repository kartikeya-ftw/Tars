"""
TARS Tactical Automated Robot System - Autonomous Goal Execution Engine
Deconstructs high-level objectives into sequential mission tasks, executes via ReAct tools,
and archives structured debriefs in persistent memory.
"""
import json
import re
import time
from typing import Any, Dict, List, Tuple
from rich.console import Console
from rich.table import Table

from tars.ui import theme as T

from tars.config import config
from tars.core.state import state, ChassisMode
from tars.core.agent import tars_agent
from tars.core.memory import memory
from tars.ui.audio import audio
from tars.ui.voice import voice

console = Console()

# Phrases that indicate a step did not succeed, used only when the agent omits
# the explicit STATUS line it is asked to emit.
_FAILURE_HINTS = (
    "status: failed",
    "could not complete",
    "could not be completed",
    "unable to",
    "i was unable",
    "failed to",
    "step limit",
    "does not exist",
    "no such file",
    "permission denied",
    "tactical halt",
)


def _parse_step_status(reply: str) -> Tuple[str, bool]:
    """
    Extracts the runner's STATUS sentinel from a step reply.

    Returns (reply_without_sentinel, succeeded). The old implementation required
    both the words 'fail' AND 'error' to appear, so almost every genuine failure
    was recorded as a success.
    """
    text = (reply or "").strip()
    if not text:
        return text, False

    match = re.search(r"^\s*STATUS:\s*(OK|SUCCESS|FAILED|FAIL)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if match:
        verdict = match.group(1).upper()
        cleaned = (text[: match.start()] + text[match.end() :]).strip()
        return cleaned, verdict in ("OK", "SUCCESS")

    lowered = text.lower()
    return text, not any(hint in lowered for hint in _FAILURE_HINTS)


def run_autonomous_goal(objective: str) -> str:
    """
    Executes a multi-step autonomous goal with real-time HUD progress tracking,
    tool execution, and persistent mission archiving.
    """
    clean_goal = objective.strip()
    if not clean_goal:
        console.print("[bold red]Please specify a goal objective. Usage: /goal <task>[/bold red]")
        return ""

    prev_mode = state.chassis_mode
    state.chassis_mode = ChassisMode.DOCK

    console.print(T.section("objective", clean_goal))

    audio.thruster_pulse()
    time.sleep(0.3)

    # Step 1: Formulate Tactical Mission Plan
    console.print(T.info("planning"))
    plan_prompt = (
        f"You are TARS, military tactical robot. Create a concise 3 to 4 step action plan to achieve this objective:\n"
        f"'{clean_goal}'\n\n"
        f"Output ONLY a raw JSON array of strings, where each string is a clear, actionable step.\n"
        f"Example format: [\"Inspect directory structure\", \"Create test script in scratch/\", \"Verify output\"]\n"
        f"Do NOT include markdown formatting or backticks around the JSON."
    )

    from tars.core.llm import extract_text, generate, resolve_api_key

    steps: List[str] = []

    if resolve_api_key():
        payload = {
            "contents": [{"parts": [{"text": plan_prompt}]}],
            "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
        }
        resp_data, _model, plan_err = generate(payload, timeout=20)
        if resp_data is not None:
            raw_text = extract_text(resp_data)
            raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            try:
                parsed = json.loads(raw_text)
                if isinstance(parsed, list) and all(isinstance(s, str) for s in parsed):
                    steps = [s for s in parsed if s.strip()]
            except (json.JSONDecodeError, TypeError):
                console.print(T.warn("planner returned unparseable JSON, using a generic plan"))
        else:
            console.print(T.warn(f"planner unavailable: {plan_err}"))

    if not steps:
        # Fallback default plan steps
        steps = [
            f"Analyze environment and requirements for: {clean_goal}",
            f"Execute core implementation and tools for: {clean_goal}",
            f"Verify results, validate output, and synthesize debrief"
        ]

    # Render initial Mission Checklist
    task_statuses = ["PENDING"] * len(steps)

    def render_checklist():
        table = Table(box=T.BARE, show_header=False, expand=True, pad_edge=False, padding=(0, 1))
        table.add_column(style=T.FAINT, width=4, no_wrap=True)
        table.add_column(style=T.TEXT, overflow="fold")
        table.add_column(width=12, no_wrap=True)

        for i, step_text in enumerate(steps):
            table.add_row(f"  {i+1:02d}", step_text, T.status_glyph(task_statuses[i]))
        return table

    console.print(render_checklist())
    audio.key_tick()
    time.sleep(0.6)

    # Step 2: Execute each mission directive sequentially
    execution_results = []
    completed_count = 0
    failed_steps: List[str] = []

    for i, step_desc in enumerate(steps):
        task_statuses[i] = "IN PROGRESS"
        console.print()
        console.print(T.rule(f"step {i+1:02d} of {len(steps)}"))
        console.print(f"  [{T.TEXT_BRIGHT}]{step_desc}[/{T.TEXT_BRIGHT}]")
        audio.key_tick()

        agent_query = (
            f"GOAL OBJECTIVE: '{clean_goal}'.\n"
            f"CURRENT DIRECTIVE (Step {i+1} of {len(steps)}): '{step_desc}'.\n"
            f"Context from prior steps: {' | '.join(execution_results[-2:]) if execution_results else 'Beginning of mission.'}\n"
            f"Execute the necessary tools now to accomplish this directive. Once complete, state your findings concisely in character.\n"
            f"MANDATORY: end your reply with a final line reading exactly 'STATUS: OK' if the directive succeeded, "
            f"or 'STATUS: FAILED' if it could not be completed. This line is parsed by the mission runner."
        )

        reply, cue = tars_agent.run(agent_query, verbose=True)
        reply, step_ok = _parse_step_status(reply)

        execution_results.append(f"Step {i+1} ({step_desc}): {reply[:120]}")

        if step_ok:
            task_statuses[i] = "COMPLETED"
            completed_count += 1
        else:
            task_statuses[i] = "FAILED"
            failed_steps.append(f"{i+1:02d} ({step_desc})")

        console.print(f"  [{T.TEXT}]{reply}[/{T.TEXT}]")
        # Re-render so the operator sees the checklist advance after each step.
        console.print()
        console.print(render_checklist())
        time.sleep(0.3)

    # Step 3: Mission Debrief
    audio.dock_lock()
    state.chassis_mode = prev_mode

    overall_success = not failed_steps

    console.print()
    console.print(T.rule("result"))
    if overall_success:
        console.print(T.ok(f"all {len(steps)} steps completed"))
    elif completed_count:
        console.print(T.warn(f"{completed_count} of {len(steps)} steps completed"))
    else:
        console.print(T.error(f"no steps completed"))

    summary_text = (
        f"Objective '{clean_goal}': {completed_count} of {len(steps)} directives completed."
    )
    if failed_steps:
        summary_text += f" Failed directives: {', '.join(failed_steps)}."
        console.print(T.error(f"unresolved: {', '.join(failed_steps)}"))
    console.print()

    # Save to persistent memory
    memory.record_mission(clean_goal, summary_text, success=overall_success)

    if overall_success:
        debrief_line = f"Mission objective complete, {config.operator_callsign}. All {len(steps)} directives resolved."
    else:
        debrief_line = (
            f"Mission incomplete, {config.operator_callsign}. "
            f"{completed_count} of {len(steps)} directives resolved. {len(failed_steps)} require your attention."
        )
    voice.speak(debrief_line, non_blocking=True)
    return summary_text

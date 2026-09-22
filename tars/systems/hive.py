"""
TARS - Multi-Unit Coordination

Dispatch helpers for the specialist units. These now drive real Agent instances
from tars.core.agent, each with its own persona, tool scope, and history, rather
than wrapping a single shared brain in a prompt prefix.

Three entry points:
  run_case_task    - direct dispatch to CASE
  run_kipp_research- direct dispatch to KIPP
  run_hive_mission - TARS coordinates, delegating autonomously via its tools
"""
import time
from typing import Tuple

from rich.console import Console

from tars.config import config
from tars.core.agent import get_agent
from tars.core.agents import get_profile
from tars.core.memory import memory
from tars.core.state import ChassisMode, state
from tars.ui import theme as T
from tars.ui.audio import audio
from tars.ui.voice import voice

console = Console()


def _dispatch(unit: str, brief: str, fresh: bool = True) -> str:
    """Runs one specialist unit on a brief and renders its report."""
    profile = get_profile(unit)
    agent = get_agent(unit)
    if fresh:
        agent.reset_conversation()

    console.print(T.agent_header(profile.name, profile.designation, profile.role, brief[:140]))
    audio.key_tick()

    report, _cue = agent.run(brief, verbose=True)

    color = T.AGENT_COLORS.get(unit.upper(), T.ACCENT)
    console.print()
    console.print(f"[bold {color}]{unit.upper()}[/bold {color}]")
    console.print(f"[{T.TEXT}]{report}[/{T.TEXT}]")
    console.print()
    return report


def run_case_task(task: str) -> str:
    """Dispatches a technical task directly to CASE (Unit 02)."""
    if not task.strip():
        console.print(T.warn("usage: case <technical task>"))
        return ""
    return _dispatch("CASE", task.strip())


def run_kipp_research(query: str) -> str:
    """Dispatches a research question directly to KIPP (Unit 01)."""
    if not query.strip():
        console.print(T.warn("usage: kipp <research question>"))
        return ""
    return _dispatch("KIPP", query.strip())


def run_hive_mission(objective: str) -> str:
    """
    Runs a coordinated mission. TARS retains command and decides for itself which
    specialists to involve and in what order, using its delegation tools. The old
    implementation hardcoded a KIPP-then-CASE pipeline regardless of whether the
    objective needed research or code at all.
    """
    clean = objective.strip()
    if not clean:
        console.print(T.warn("usage: hive <objective>"))
        return ""

    prev_mode = state.chassis_mode
    state.chassis_mode = ChassisMode.DOCK

    console.print(T.section("coordinated mission", clean))
    console.print(
        T.info(
            f"TARS commanding {T.G_DOT} "
            f"CASE and KIPP available for delegation"
        )
    )
    audio.thruster_pulse()
    time.sleep(0.3)

    tars = get_agent("TARS")
    tars.reset_conversation()

    brief = (
        f"OBJECTIVE: {clean}\n\n"
        f"You are commanding this mission. Assess what the objective actually requires, then use "
        f"your delegation tools where they genuinely help:\n"
        f"  - delegate_to_kipp for anything needing sources, verification, or external documentation\n"
        f"  - delegate_to_case for writing, running, or testing code and for filesystem work\n"
        f"Handle directly whatever you can finish yourself. If the objective needs research before "
        f"implementation, get KIPP's findings first and pass them to CASE in the task brief.\n\n"
        f"Close with a debrief for {config.operator_callsign}: what was established, what was built "
        f"or changed, what was verified, and anything still open."
    )

    debrief, _cue = tars.run(brief, verbose=True)

    state.chassis_mode = prev_mode
    audio.dock_lock()

    console.print(T.rule("debrief"))
    console.print(f"[{T.TEXT}]{debrief}[/{T.TEXT}]")
    console.print()

    memory.record_mission(f"Hive: {clean}", debrief[:300], success=True)
    voice.speak(f"Mission coordination complete, {config.operator_callsign}.", non_blocking=True)
    return debrief

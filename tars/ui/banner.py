"""
TARS - Startup masthead and status readout.

Replaces the previous block-letter ASCII banner and fictional reactor gauges with
a compact identity block and a status panel that reports real machine state.
"""
import os
import shutil
from typing import List, Tuple

from rich.console import Group

from tars.config import config
from tars.core.state import state
from tars.ui import theme as T


def _model_label() -> str:
    """Name of the model the agent will actually reach for first."""
    from tars.core.llm import TEXT_MODELS

    return TEXT_MODELS[0] if TEXT_MODELS else "offline"


def _tool_count() -> int:
    from tars.core.agents import TARS_TOOLS

    return len(TARS_TOOLS)


def get_masthead() -> Group:
    """Compact startup identity block."""
    from tars.core.llm import resolve_api_key

    online = bool(resolve_api_key())
    return T.masthead(
        model=_model_label() if online else "",
        tool_count=_tool_count(),
        online=online,
    )


def get_hud_banner() -> Group:
    """
    Status readout for the `status` command and startup.

    Reports genuine host and session state. The old version displayed invented
    values (reactor output 98.4%, "DEEP SPACE // GARGANTUA PROXIMITY") which
    looked like telemetry but carried no information.
    """
    from tars.core.llm import resolve_api_key

    online = bool(resolve_api_key())

    # Real host readings, degrading gracefully if psutil is unavailable.
    cpu = mem = disk = "unavailable"
    try:
        import psutil

        cpu = f"{psutil.cpu_percent(interval=0.1):.0f}%  of {psutil.cpu_count(logical=True)} threads"
        vm = psutil.virtual_memory()
        mem = f"{vm.percent:.0f}%  {vm.used / 1024**3:.1f} / {vm.total / 1024**3:.1f} GB"
        du = psutil.disk_usage(os.getcwd())
        disk = f"{du.percent:.0f}%  {du.free / 1024**3:.0f} GB free"
    except Exception:
        pass

    cwd = os.getcwd()
    width = shutil.get_terminal_size((100, 30)).columns
    if len(cwd) > max(28, width // 3):
        cwd = "..." + cwd[-(max(25, width // 3) - 3):]

    brain = f"[{T.OK}]{_model_label()}[/{T.OK}]" if online else f"[{T.WARN}]offline heuristics[/{T.WARN}]"
    voice_on = f"[{T.OK}]on[/{T.OK}]" if config.voice_output_enabled else f"[{T.FAINT}]off[/{T.FAINT}]"
    sound_on = f"[{T.OK}]on[/{T.OK}]" if config.sound_enabled else f"[{T.FAINT}]off[/{T.FAINT}]"

    rows: List[Tuple[str, str]] = [
        ("operator", f"[{T.ACCENT}]{config.operator_callsign}[/{T.ACCENT}]"),
        ("session", state.uptime_str),
        ("model", brain),
        ("tools", f"{_tool_count()} available"),
        ("units", f"TARS [{T.FAINT}]·[/{T.FAINT}] "
                  f"[{T.AGENT_COLORS['CASE']}]CASE[/{T.AGENT_COLORS['CASE']}] [{T.FAINT}]·[/{T.FAINT}] "
                  f"[{T.AGENT_COLORS['KIPP']}]KIPP[/{T.AGENT_COLORS['KIPP']}]"),
        ("posture", state.chassis_mode.value.lower()),
        ("cpu", cpu),
        ("memory", mem),
        ("disk", disk),
        ("directory", cwd),
        ("humor / honesty", f"{config.humor}%  /  {config.honesty}%"),
        ("sarcasm", f"{config.sarcasm}%"),
        ("voice / sound", f"{voice_on}  /  {sound_on}"),
        ("commands run", str(state.commands_processed)),
    ]

    return Group(
        T.rule("status"),
        T.kv_table(rows, columns=2, label_width=17),
        T.hint("type 'help' for commands, or just say what you need"),
    )

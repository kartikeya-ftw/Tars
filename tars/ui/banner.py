"""
TARS - Startup masthead and status readout.

The masthead is the identity block from `tars.ui.chrome`. The status readout is
a three-column instrument panel: host telemetry with segmented meters on the
left, session and unit state in the middle, personality and presence on the
right.

Everything reported here is a real reading. An earlier version of this screen
displayed invented values -- reactor output 98.4%, "DEEP SPACE // GARGANTUA
PROXIMITY" -- which looked like telemetry but carried no information, and taught
you to ignore the panel.
"""
import os
from typing import List, Optional, Tuple

from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from tars.config import config
from tars.core.state import state
from tars.ui import chrome
from tars.ui import theme as T
from tars.ui.console import width


def _model_label() -> str:
    """
    The model that last answered, or the head of the chain prefixed with '~' if
    nothing has answered yet.

    Reporting TEXT_MODELS[0] unconditionally was misleading: with a fallback
    chain, a turn served by a tail model still displayed the head.
    """
    from tars.core.llm import TEXT_MODELS, last_model_used

    served = last_model_used()
    if served:
        return served
    return f"~{TEXT_MODELS[0]}" if TEXT_MODELS else "offline"


def _tool_count() -> int:
    from tars.core.agents import TARS_TOOLS

    return len(TARS_TOOLS)


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def get_masthead() -> RenderableType:
    """Compact startup identity block."""
    from tars.core.llm import resolve_api_key

    online = bool(resolve_api_key())
    if not getattr(config, "ui_logo", True):
        return T.masthead(
            model=_model_label() if online else "",
            tool_count=_tool_count(),
            online=online,
        )
    return chrome.logo(
        model=_model_label() if online else "",
        tool_count=_tool_count(),
        online=online,
    )


# ─── Host telemetry ─────────────────────────────────────────────────────────

def _host_readings() -> List[Tuple[str, Optional[float], str]]:
    """
    Returns (label, fraction, detail) per subsystem. `fraction` is None when the
    reading is genuinely unavailable, so the panel can say so instead of drawing
    an empty meter that looks like zero load.
    """
    readings: List[Tuple[str, Optional[float], str]] = []
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=0.1)
        readings.append(("cpu", cpu / 100.0,
                         f"{cpu:.0f}%  {psutil.cpu_count(logical=True)} threads"))

        vm = psutil.virtual_memory()
        readings.append(("memory", vm.percent / 100.0,
                         f"{vm.used / 1024**3:.1f} / {vm.total / 1024**3:.1f} GB"))

        du = psutil.disk_usage(os.getcwd())
        readings.append(("disk", du.percent / 100.0,
                         f"{du.free / 1024**3:.0f} GB free"))

        battery = psutil.sensors_battery()
        if battery is not None:
            plug = "charging" if battery.power_plugged else "on battery"
            readings.append(("battery", battery.percent / 100.0,
                             f"{battery.percent:.0f}%  {plug}"))
    except Exception:
        readings.append(("telemetry", None, "psutil unavailable"))
    return readings


def _telemetry_block() -> RenderableType:
    grid = Table(box=T.BARE, show_header=False, pad_edge=False, padding=(0, 1))
    grid.add_column(width=8, style=T.MUTED, no_wrap=True)
    grid.add_column(width=12, no_wrap=True)
    grid.add_column(ratio=1, style=T.TEXT, overflow="ellipsis")

    for label, fraction, detail in _host_readings():
        if fraction is None:
            grid.add_row(label, Text("unavailable", style=T.FAINT), detail)
            continue
        # Battery is inverted: a low reading is the bad one.
        if label == "battery":
            bar = T.meter(fraction, 10,
                          color=T.ERR if fraction < 0.15
                          else (T.WARN if fraction < 0.3 else T.OK))
        else:
            bar = T.meter(fraction, 10)
        grid.add_row(label, bar, detail)
    return grid


def _session_block() -> RenderableType:
    from tars.core.llm import resolve_api_key
    from tars.core.memory import memory

    online = bool(resolve_api_key())
    brain = Text(_model_label(), style=T.OK) if online else Text("offline heuristics", style=T.WARN)

    units = Text()
    for i, (unit, color) in enumerate(T.AGENT_COLORS.items()):
        if i:
            units.append(f" {T.G_DOT} ", style=T.FAINT)
        units.append(unit, style=color)

    deceased = sum(1 for p in memory.people.values()
                   if (p.get("status") or "").lower() == "deceased")
    mem = f"{len(memory.facts)} facts · {_plural(len(memory.people), 'person', 'people')}"
    if deceased:
        mem += f" · {deceased} remembered"

    rows: List[Tuple[str, RenderableType]] = [
        ("operator", Text(config.operator_callsign, style=f"bold {T.ACCENT}")),
        ("model", brain),
        ("units", units),
        ("tools", Text(f"{_tool_count()} scoped", style=T.TEXT)),
        ("memory", Text(mem, style=T.TEXT)),
        ("session", Text(f"{state.uptime_str}  ·  {_plural(state.commands_processed, 'cmd', 'cmds')}",
                         style=T.TEXT)),
        ("posture", Text(state.chassis_mode.value.lower(), style=T.TEXT)),
    ]
    return _kv(rows)


def _presence_block() -> RenderableType:
    mood = (getattr(state, "operator_mood", "") or "neutral").lower()
    intensity = float(getattr(state, "mood_intensity", 0.0) or 0.0)

    if mood != "neutral" and intensity >= 0.2:
        read = Text()
        read.append(T.G_EAR, style=T.mood_color(mood))
        read.append(f" {mood} ", style=f"bold {T.mood_color(mood)}")
        read.append(f"{intensity:.0%}", style=T.FAINT)
    else:
        read = Text("nothing notable", style=T.FAINT)

    def toggle(on: bool, on_text: str = "on", off_text: str = "off") -> Text:
        return Text(on_text, style=T.OK) if on else Text(off_text, style=T.FAINT)

    empathy = int(getattr(config, "empathy", 0) or 0)
    dials = Text()
    dials.append(f"{config.humor}", style=T.TEXT_BRIGHT)
    dials.append(" hum  ", style=T.MUTED)
    dials.append(f"{config.honesty}", style=T.TEXT_BRIGHT)
    dials.append(" hon  ", style=T.MUTED)
    dials.append(f"{config.sarcasm}", style=T.TEXT_BRIGHT)
    dials.append(" sar", style=T.MUTED)

    try:
        from tars.ui.voice import voice

        # engine_name() can carry a parenthetical health note that is useful in
        # `settings` but too long for a third-of-the-width column.
        voice_name = voice.engine_name().split(" (")[0]
    except Exception:
        voice_name = "unavailable"

    from tars.systems.sentinel import sentinel

    rows: List[Tuple[str, RenderableType]] = [
        ("dials", dials),
        ("empathy", Text(f"{empathy}%", style=T.TEXT_BRIGHT) if empathy
         else Text("off", style=T.FAINT)),
        ("reading", read),
        ("speech", toggle(config.voice_output_enabled) if not config.voice_output_enabled
         else Text(voice_name, style=T.OK)),
        ("mic", toggle(config.voice_input_enabled, "ready")),
        ("earcons", toggle(config.sound_enabled)),
        ("sentinel", Text("watching", style=T.OK) if sentinel.is_running
         else toggle(config.proactive_enabled, "armed")),
    ]
    return _kv(rows)


def _kv(rows) -> Table:
    grid = Table(box=T.BARE, show_header=False, pad_edge=False, padding=(0, 1))
    grid.add_column(width=9, style=T.MUTED, no_wrap=True)
    grid.add_column(ratio=1, overflow="fold")
    for key, val in rows:
        grid.add_row(key, val)
    return grid


def get_hud_banner() -> Group:
    """
    The `status` readout.

    Three instrument columns on a wide terminal, stacked on a narrow one. Rich
    will not usefully fit three columns of label/value pairs under about 110
    cells, so below that it degrades rather than shredding every row.
    """
    term = width()

    if term < 110:
        return Group(
            T.rule("host"),
            _telemetry_block(),
            T.rule("session"),
            _session_block(),
            T.rule("presence"),
            _presence_block(),
            Text(""),
            T.hint("type 'help' for commands, or just say what you need"),
        )

    # Column titles live in the same table as the columns they label, so they
    # track the real layout instead of sitting at hardcoded offsets that drift
    # the moment the terminal is a different width.
    columns = Table(box=T.BARE, show_header=True, expand=True, pad_edge=False,
                    padding=(0, 2), header_style=T.MUTED)
    columns.add_column("host", ratio=34, overflow="fold")
    columns.add_column("session", ratio=33, overflow="fold")
    columns.add_column("presence", ratio=33, overflow="fold")
    columns.add_row(_telemetry_block(), _session_block(), _presence_block())

    return Group(
        T.rule("status"),
        # Two-space lead so the panel sits on the same left margin as every
        # other body block in the shell.
        Padding(columns, (0, 0, 0, 2)),
        Text(""),
        T.hint("type 'help' for commands, or just say what you need"),
    )

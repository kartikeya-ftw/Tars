"""
TARS - Chassis posture indicator.

The four articulating slabs are now drawn as a compact horizontal segment bar
rather than multi-line ASCII diagrams. It reads as an instrument, not a cartoon,
and stays legible at any terminal width.
"""
from typing import Dict, Optional, Tuple

from rich.console import Group
from rich.text import Text

from tars.config import config
from tars.core.state import ChassisMode, state
from tars.ui import theme as T

# mode -> (segment pattern, descriptor). Each slab is one cell; the pattern
# conveys articulation without pretending to be a technical drawing.
_POSTURE: Dict[ChassisMode, Tuple[str, str]] = {
    ChassisMode.MONOLITH: ("▮▮▮▮", "rigid column, compute and standby"),
    ChassisMode.WALK: ("▮▯▮▯", "staggered gait, tripod stride"),
    ChassisMode.ROLL: ("▰▰▰▰", "centrifugal roll, high velocity transit"),
    ChassisMode.DOCK: ("▮▯▯▮", "thruster spread, docking alignment"),
    ChassisMode.QUANTUM: ("▤▤▤▤", "lattice expansion, data relay"),
}

_SLAB_LABELS = ("01", "02", "03", "04")


def get_monolith_render(mode: Optional[ChassisMode] = None) -> Group:
    """Renders the current chassis posture as a labelled segment strip."""
    if mode is None:
        mode = state.chassis_mode

    pattern, descriptor = _POSTURE.get(mode, _POSTURE[ChassisMode.MONOLITH])

    # Segment strip, one glyph per slab, accent-coloured.
    strip = Text("  ")
    for glyph in pattern:
        strip.append(f" {glyph} ", style=f"bold {T.ACCENT}")
    strip.append(f"   {mode.value.lower()}", style=T.TEXT_BRIGHT)
    strip.append(f"   {T.G_DOT}   {descriptor}", style=T.MUTED)

    # Slab index line beneath, aligned under each segment.
    index = Text("  ")
    for lbl in _SLAB_LABELS:
        index.append(f" {lbl}".ljust(3), style=T.FAINT)

    meta = Text("  ")
    meta.append("humor ", style=T.MUTED)
    meta.append(f"{config.humor}%", style=T.TEXT_BRIGHT)
    meta.append(f"   {T.G_DOT}   ", style=T.FAINT)
    meta.append("honesty ", style=T.MUTED)
    meta.append(f"{config.honesty}%", style=T.TEXT_BRIGHT)
    if state.cue_light_active:
        meta.append(f"   {T.G_DOT}   ", style=T.FAINT)
        meta.append("cue", style=f"bold {T.OK}")

    return Group(Text(""), strip, index, meta, Text(""))

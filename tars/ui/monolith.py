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

# Affect -> colour for the "reading" indicator. Bleak states read cool, warm
# states read warm, and anything unmapped falls back to the accent.
_MOOD_COLORS = {
    "grief": "#a78bfa", "sadness": "#818cf8", "loneliness": "#818cf8",
    "nostalgia": "#a78bfa", "vulnerable": "#c4b5fd",
    "anxiety": "#fbbf24", "exhaustion": "#94a3b8", "illness": "#fbbf24",
    "frustration": "#fb923c", "conflict": "#fb923c", "shame": "#f472b6",
    "romance": "#f472b6", "joy": "#34d399", "pride": "#34d399",
    "gratitude": "#34d399", "affection": "#f472b6",
}


def _MOOD_TONE(mood: str) -> str:
    return _MOOD_COLORS.get(mood, T.ACCENT)


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
    meta.append(f"   {T.G_DOT}   ", style=T.FAINT)
    meta.append("empathy ", style=T.MUTED)
    meta.append(f"{config.empathy}%" if config.empathy else "off", style=T.TEXT_BRIGHT)

    # Surface what the unit currently reads in the operator, but only when it is
    # reading something. A permanent "neutral" label would be noise.
    mood = (state.operator_mood or "neutral").lower()
    if mood != "neutral" and state.mood_intensity >= 0.2:
        meta.append(f"   {T.G_DOT}   ", style=T.FAINT)
        meta.append("reading ", style=T.MUTED)
        meta.append(mood, style=f"bold {_MOOD_TONE(mood)}")

    if state.cue_light_active:
        meta.append(f"   {T.G_DOT}   ", style=T.FAINT)
        meta.append("cue", style=f"bold {T.OK}")

    return Group(Text(""), strip, index, meta, Text(""))

"""
TARS - Terminal Design System

One place for palette, glyphs, and layout primitives. The previous UI leaned on
heavy box-drawing frames, block-letter ASCII, and saturated primary colours. This
module replaces that with a restrained, high-contrast system: a single cool
accent, slate-grey labels, semantic status colours, and thin rules instead of
double-line frames.

Rules of thumb used throughout:
  - Labels are muted, values are bright. Never both.
  - One accent colour per screen. Semantic colour only for state.
  - Rules and whitespace separate sections. Not boxes.
  - Glyphs are single-width and thin. No filled blocks.
"""
from typing import Optional

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# ─── Palette ────────────────────────────────────────────────────────────────
# Cool neutral base with a single sky accent. Deliberately avoids the previous
# magenta/yellow/red combination, which read as toy-like.
ACCENT = "#38bdf8"        # sky 400  - primary accent
ACCENT_DEEP = "#0284c7"   # sky 600  - accent for fills/rules
TEXT = "#e2e8f0"          # slate 200 - primary text
TEXT_BRIGHT = "#f8fafc"   # slate 50  - emphasis
MUTED = "#64748b"         # slate 500 - labels, secondary
FAINT = "#475569"         # slate 600 - dividers, disabled

OK = "#4ade80"            # green 400
WARN = "#fbbf24"          # amber 400
ERR = "#f87171"           # red 400
INFO = "#818cf8"          # indigo 400

# Per-agent identity colours. Each unit keeps one colour everywhere it appears.
AGENT_COLORS = {
    "TARS": ACCENT,
    "CASE": "#fb923c",    # orange 400 - warm, contrasts with TARS
    "KIPP": "#a78bfa",    # violet 400 - cool, distinct from both
}

# ─── Glyphs ─────────────────────────────────────────────────────────────────
# Thin, single-width, consistent weight.
G_PROMPT = "›"
G_STEP = "▸"
G_OK = "✓"
G_FAIL = "✗"
G_PENDING = "○"
G_ACTIVE = "◐"
G_DOT = "·"
G_ARROW = "→"
G_RETURN = "↳"
G_BULLET = "•"

# Tables in this UI read as aligned columns rather than grids. Rich treats
# box=None as "no borders at all", which also avoids the blank padded edge rows
# a custom all-whitespace Box would emit.
BARE = None


def label(text: str) -> Text:
    """Muted column label."""
    return Text(text, style=MUTED)


def value(text: str, style: str = TEXT_BRIGHT) -> Text:
    """Bright value paired with a muted label."""
    return Text(text, style=style)


def rule(title: str = "", style: str = FAINT) -> Rule:
    """Thin horizontal section divider, optionally titled."""
    if title:
        return Rule(Text(f" {title.upper()} ", style=f"bold {MUTED}"), style=style, align="left")
    return Rule(style=style)


def section(title: str, subtitle: str = "") -> Group:
    """
    A titled section header. Replaces the old ╔══╗ banner blocks.

        OBJECTIVE ─────────────────────────────────────────
        deploy the reporting pipeline
    """
    parts: list[RenderableType] = [rule(title)]
    if subtitle:
        parts.append(Text(f"  {subtitle}", style=TEXT))
    return Group(*parts)


def kv_table(pairs, columns: int = 2, label_width: int = 18) -> Table:
    """
    Renders label/value pairs as clean aligned columns with no grid lines.
    `pairs` is a sequence of (label, value) tuples; values may be markup strings.
    """
    table = Table(box=BARE, show_header=False, expand=True, pad_edge=False, padding=(0, 1))
    for _ in range(columns):
        table.add_column(style=MUTED, width=label_width, no_wrap=True)
        # ratio=1 sends all surplus width to the value columns, so label columns
        # stay the same width across separately-constructed tables.
        table.add_column(style=TEXT_BRIGHT, ratio=1, overflow="fold")

    row: list[str] = []
    for key, val in pairs:
        # Two-space lead keeps these columns aligned with the rest of the UI,
        # which indents body content under its section rule.
        prefix = "  " if not row else ""
        row.extend([prefix + key.upper(), str(val)])
        if len(row) >= columns * 2:
            table.add_row(*row)
            row = []
    if row:
        row.extend([""] * (columns * 2 - len(row)))
        table.add_row(*row)
    return table


def panel(body: RenderableType, title: str = "", subtitle: str = "", accent: str = ACCENT) -> Panel:
    """A light-bordered panel. Used sparingly, for output that needs containment."""
    from rich import box as rich_box

    return Panel(
        body,
        title=Text(f" {title} ", style=f"bold {accent}") if title else None,
        title_align="left",
        subtitle=Text(f" {subtitle} ", style=MUTED) if subtitle else None,
        subtitle_align="right",
        border_style=FAINT,
        box=rich_box.SQUARE,
        padding=(1, 2),
    )


def agent_tag(unit: str) -> Text:
    """
    Inline speaker attribution, e.g. a dim bracketed unit name in its own colour.
    Keeps multi-agent transcripts readable without shouting.
    """
    color = AGENT_COLORS.get(unit.upper(), ACCENT)
    return Text.assemble(
        (unit.upper(), f"bold {color}"),
        ("  ", ""),
    )


def agent_header(unit: str, designation: str, role: str, task: str = "") -> Group:
    """
    Header shown when a specialist unit takes over a task. Reads as a handoff
    record rather than a klaxon.
    """
    color = AGENT_COLORS.get(unit.upper(), ACCENT)
    line = Text.assemble(
        (f"{unit.upper()}", f"bold {color}"),
        (f"  {designation}", MUTED),
        (f"  {G_DOT}  ", FAINT),
        (role, TEXT),
    )
    parts: list[RenderableType] = [Text(""), line]
    if task:
        parts.append(Text.assemble(("  task  ", MUTED), (task, TEXT)))
    parts.append(rule())
    return Group(*parts)


def status_glyph(state: str) -> Text:
    """Maps a status keyword to a coloured glyph + label."""
    state = state.upper()
    mapping = {
        "COMPLETED": (G_OK, OK, "done"),
        "OK": (G_OK, OK, "ok"),
        "IN PROGRESS": (G_ACTIVE, ACCENT, "running"),
        "FAILED": (G_FAIL, ERR, "failed"),
        "PENDING": (G_PENDING, FAINT, "queued"),
        "SKIPPED": (G_DOT, FAINT, "skipped"),
    }
    glyph, color, text = mapping.get(state, (G_DOT, MUTED, state.lower()))
    return Text.assemble((glyph, color), ("  ", ""), (text, color))


def tool_call_line(name: str, args_preview: str) -> Text:
    """Single-line record of a tool invocation."""
    return Text.assemble(
        ("  ", ""),
        (G_STEP, ACCENT),
        ("  ", ""),
        (name, f"bold {TEXT_BRIGHT}"),
        (f" {args_preview}" if args_preview else "", MUTED),
    )


def tool_result_line(summary: str, extra_lines: int = 0, failed: bool = False) -> Text:
    """Indented result summary beneath a tool call."""
    tail = f"  (+{extra_lines} lines)" if extra_lines > 0 else ""
    return Text.assemble(
        ("    ", ""),
        (G_RETURN, ERR if failed else FAINT),
        ("  ", ""),
        (summary, ERR if failed else MUTED),
        (tail, FAINT),
    )


def masthead(model: str = "", tool_count: int = 0, online: bool = True) -> Group:
    """
    Compact identity block shown at startup. Two lines of type instead of six
    lines of block-letter ASCII.
    """
    title = Text.assemble(
        ("TARS", f"bold {TEXT_BRIGHT}"),
        ("   Tactical Automated Robot System", MUTED),
    )

    bits = [("unit 04", MUTED)]
    if model:
        bits.append((model, ACCENT))
    if tool_count:
        bits.append((f"{tool_count} tools", MUTED))
    bits.append(("online", OK) if online else ("offline", WARN))

    meta = Text()
    for i, (txt, sty) in enumerate(bits):
        if i:
            meta.append(f"  {G_DOT}  ", style=FAINT)
        meta.append(txt, style=sty)

    return Group(Text(""), title, meta, rule(), Text(""))


def hint(text: str) -> Text:
    """Low-emphasis guidance line."""
    return Text(f"  {text}", style=FAINT)


def error(text: str) -> Text:
    return Text.assemble(("  ", ""), (G_FAIL, ERR), ("  ", ""), (text, ERR))


def warn(text: str) -> Text:
    return Text.assemble(("  ", ""), ("!", WARN), ("  ", ""), (text, WARN))


def ok(text: str) -> Text:
    return Text.assemble(("  ", ""), (G_OK, OK), ("  ", ""), (text, TEXT))


def info(text: str) -> Text:
    return Text.assemble(("  ", ""), (G_DOT, MUTED), ("  ", ""), (text, MUTED))

# ════════════════════════════════════════════════════════════════════════════
# Instrument layer
#
# Everything above is the original restrained type system and still backs every
# command. What follows adds the pieces that make the shell read as an
# instrument panel rather than a log file: a gradient ramp, affect tints,
# segmented meters, badges, and the slab glyph language used by the logo.
#
# Design rules, extending the ones at the top of this file:
#   - Gradients are reserved for identity. Never for data.
#   - Colour encodes state. Brightness encodes importance. Never swap them.
#   - Segmented meters, not smooth bars. The chassis is four slabs; the whole
#     interface speaks in discrete cells.
# ════════════════════════════════════════════════════════════════════════════

# ─── Extended palette ───────────────────────────────────────────────────────
# Surfaces, for panel fills and the status bar. Kept very close to a true
# terminal black so the shell still feels like a terminal.
BG = "#0b1120"            # slate 950, near-black base
BG_PANEL = "#111827"      # gray 900, raised surface
BG_BAR = "#1e293b"        # slate 800, status bar / gutter fill
BORDER = "#1e293b"        # slate 800, hairline borders

# Identity gradient. Sky to indigo to violet: the TARS accent, warmed through
# the two specialist colours so the whole roster is implied by the logo.
RAMP = ("#38bdf8", "#60a5fa", "#818cf8", "#a78bfa")
# Cool monochrome ramp for data that needs depth without implying state.
RAMP_COOL = ("#1e293b", "#334155", "#475569", "#64748b", "#94a3b8")

# ─── Slab glyph language ────────────────────────────────────────────────────
SLAB_FULL = "▮"
SLAB_EMPTY = "▯"
SLAB_WIDE = "▰"
SLAB_WIDE_EMPTY = "▱"
G_SPARK = "▁▂▃▄▅▆▇█"
G_CARET = "❯"
G_HINGE = "┼"
G_VBAR = "│"
G_CORNER_TL = "╭"
G_CORNER_BL = "╰"
G_WAVE = "∿"
G_LOCK = "⏻"
G_SIGNAL = "◈"
G_EAR = "◉"

# ─── Affect tints ───────────────────────────────────────────────────────────
# One home for the affect palette, so the HUD, the reply gutter, and the mood
# readout cannot drift apart. Keys are tars.core.emotion.Affect values.
MOOD_COLORS = {
    "grief": "#a78bfa",
    "sadness": "#818cf8",
    "loneliness": "#818cf8",
    "nostalgia": "#a78bfa",
    "vulnerable": "#c4b5fd",
    "anxiety": "#fbbf24",
    "illness": "#fbbf24",
    "exhaustion": "#94a3b8",
    "frustration": "#fb923c",
    "conflict": "#fb923c",
    "shame": "#f472b6",
    "romance": "#f472b6",
    "affection": "#f472b6",
    "joy": "#34d399",
    "pride": "#34d399",
    "gratitude": "#34d399",
    "neutral": ACCENT,
}


def mood_color(mood: str) -> str:
    """Colour for an affect name, falling back to the primary accent."""
    return MOOD_COLORS.get((mood or "neutral").lower(), ACCENT)


# ─── Colour maths ───────────────────────────────────────────────────────────

def _hex_to_rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(round(c)))) for c in rgb))


def mix(a: str, b: str, t: float) -> str:
    """Linear blend between two hex colours. t=0 returns a, t=1 returns b."""
    t = max(0.0, min(1.0, t))
    ra, rb = _hex_to_rgb(a), _hex_to_rgb(b)
    return _rgb_to_hex(tuple(ra[i] + (rb[i] - ra[i]) * t for i in range(3)))


def ramp_at(position: float, stops=RAMP) -> str:
    """Samples a multi-stop gradient at `position` in 0..1."""
    if not stops:
        return ACCENT
    if len(stops) == 1:
        return stops[0]
    position = max(0.0, min(1.0, position))
    span = position * (len(stops) - 1)
    index = int(span)
    if index >= len(stops) - 1:
        return stops[-1]
    return mix(stops[index], stops[index + 1], span - index)


def gradient_text(content: str, stops=RAMP, bold: bool = False) -> Text:
    """
    Colours a string character by character along a gradient.

    Used for identity only -- the logo and the masthead wordmark. Applying this
    to data would make colour meaningless everywhere else.
    """
    out = Text()
    printable = [i for i, ch in enumerate(content) if ch != " "]
    if not printable:
        return Text(content)
    first, last = printable[0], printable[-1]
    span = max(1, last - first)
    for i, ch in enumerate(content):
        if ch == " ":
            out.append(" ")
            continue
        color = ramp_at((i - first) / span, stops)
        out.append(ch, style=f"bold {color}" if bold else color)
    return out


def gradient_rule(width: int, stops=RAMP, char: str = "─") -> Text:
    """A horizontal rule that fades along the identity ramp."""
    out = Text()
    width = max(1, width)
    for i in range(width):
        out.append(char, style=ramp_at(i / max(1, width - 1), stops))
    return out


# ─── Instrument primitives ──────────────────────────────────────────────────

def meter(fraction: float, width: int = 12, color: Optional[str] = None,
          warn_at: float = 0.75, crit_at: float = 0.9) -> Text:
    """
    Segmented level indicator, in the same slab language as the chassis.

        ▮▮▮▮▮▮▯▯▯▯▯▯

    Colour follows the value unless `color` pins it: green under `warn_at`,
    amber past it, red past `crit_at`. Data gets semantic colour, never a
    gradient.
    """
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    if color is None:
        color = ERR if fraction >= crit_at else (WARN if fraction >= warn_at else OK)
    out = Text()
    out.append(SLAB_FULL * filled, style=color)
    out.append(SLAB_EMPTY * (width - filled), style=FAINT)
    return out


def sparkline(values, color: str = ACCENT) -> Text:
    """Compact trend strip for a sequence of numbers."""
    series = [float(v) for v in values if v is not None]
    if not series:
        return Text("")
    low, high = min(series), max(series)
    span = (high - low) or 1.0
    out = Text()
    for v in series:
        level = int(((v - low) / span) * (len(G_SPARK) - 1))
        out.append(G_SPARK[level], style=color)
    return out


def badge(content: str, color: str = ACCENT, filled: bool = False) -> Text:
    """
    A small inline state tag.

    Filled badges are for live, attention-worthy state (recording, listening,
    a mood read). Outlined badges are for static labels.
    """
    if filled:
        return Text(f" {content} ", style=f"bold {BG} on {color}")
    return Text.assemble(("[", FAINT), (content, color), ("]", FAINT))


def pill(label_text: str, value_text: str, color: str = ACCENT) -> Text:
    """Label/value pair for the status bar: muted key, bright value."""
    return Text.assemble(
        (label_text, MUTED),
        (" ", ""),
        (value_text, f"bold {color}"),
    )


def dim_join(parts, separator: str = f"  {G_DOT}  ") -> Text:
    """Joins Text fragments with a faint separator."""
    out = Text()
    for i, part in enumerate(parts):
        if i:
            out.append(separator, style=FAINT)
        out.append_text(part if isinstance(part, Text) else Text(str(part)))
    return out


def gutter_block(body: RenderableType, color: str = ACCENT, title: str = "",
                 meta: str = "") -> Table:
    """
    Content behind a coloured vertical rule, with an optional title on the rule.

    This is the shell's primary containment device. It gives a reply structure
    and ownership without the visual weight of a full box, and it survives
    terminal resizing better than a panel because only one column is fixed.

        │ TARS  · cue
        │ Your humor setting is currently at 75%.
    """
    grid = Table(box=BARE, show_header=False, expand=True, pad_edge=False, padding=0)
    grid.add_column(width=2, no_wrap=True)
    grid.add_column(ratio=1, overflow="fold")

    if title:
        head = Text.assemble((title, f"bold {color}"))
        if meta:
            head.append(f"  {G_DOT}  ", style=FAINT)
            head.append(meta, style=MUTED)
        grid.add_row(Text(G_VBAR, style=color), head)
        grid.add_row(Text(G_VBAR, style=FAINT), Text(""))

    grid.add_row(Text(G_VBAR, style=FAINT if title else color), body)
    return grid

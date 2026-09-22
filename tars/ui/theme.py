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

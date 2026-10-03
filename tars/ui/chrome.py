"""
TARS - Shell chrome.

The visual identity of the shell: the monolith logo, the boot sequence, the
reply renderer, the live thinking indicator, and the status bar.

`theme.py` holds the design primitives (palette, gradients, meters, badges).
This module composes them into the things you actually look at. Keeping the two
separate means a command can pull a meter or a badge without dragging in the
startup animation.

Three concrete problems this module exists to fix:

  1. Replies were printed as `console.print(f"[{TEXT}]{reply}[/{TEXT}]")`. That
     renders no markdown -- every list, bold run, and code fence in a reply
     arrived as literal asterisks and backticks -- and worse, any square bracket
     in the reply was parsed as Rich markup, so a reply containing `list[int]`
     or a footnote `[1]` could throw or silently lose text.
  2. The blocking model call produced dead air: nothing on screen for several
     seconds, with no sign the shell was alive.
  3. Nothing was visible between turns. Seeing any state required typing
     `status`.
"""
from __future__ import annotations

import os
import re
import time
from typing import List, Optional, Sequence, Tuple

from rich.console import Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.segment import Segment
from rich.table import Table
from rich.text import Text

from tars.config import config
from tars.ui import theme as T
from tars.ui.console import console, is_rich, width

# ════════════════════════════════════════════════════════════════════════════
# Identity
# ════════════════════════════════════════════════════════════════════════════

# The chassis: four articulating slabs, drawn with heavy half-blocks so the
# hinges still read at small sizes. This is the one place a gradient is allowed.
_SLABS: Tuple[str, ...] = (
    "▛▀▜ ▛▀▜ ▛▀▜ ▛▀▜",
    "▌ ▐ ▌ ▐ ▌ ▐ ▌ ▐",
    "▌ ▐ ▌ ▐ ▌ ▐ ▌ ▐",
    "▌ ▐ ▌ ▐ ▌ ▐ ▌ ▐",
    "▙▄▟ ▙▄▟ ▙▄▟ ▙▄▟",
)

# Wordmark in box-drawing rather than filled blocks: same stroke weight as the
# rest of the UI, and it does not read as 1990s shareware.
_WORDMARK: Tuple[str, ...] = (
    "╔╦╗ ╔═╗ ╦═╗ ╔═╗",
    " ║  ╠═╣ ╠╦╝ ╚═╗",
    " ╩  ╩ ╩ ╩╚═ ╚═╝",
)


def _diagonal(rows: Sequence[str], stops=T.RAMP, bold: bool = True) -> List[Text]:
    """
    Applies one gradient across a block of text diagonally, so the sheen runs
    top-left to bottom-right instead of every row repeating the same ramp.
    """
    height = max(1, len(rows) - 1)
    out: List[Text] = []
    for y, row in enumerate(rows):
        line = Text()
        span = max(1, len(row) - 1)
        for x, ch in enumerate(row):
            if ch == " ":
                line.append(" ")
                continue
            position = ((x / span) + (y / height)) / 2
            color = T.ramp_at(position, stops)
            line.append(ch, style=f"bold {color}" if bold else color)
        out.append(line)
    return out


def logo(model: str = "", tool_count: int = 0, online: bool = True) -> RenderableType:
    """
    Startup identity block: chassis mark beside the wordmark, session metadata
    underneath.

    Collapses to one compact line on narrow terminals, because a logo that wraps
    is worse than no logo.
    """
    meta_bits: List[Text] = [Text("unit 04", style=T.MUTED)]
    if model:
        meta_bits.append(Text(model, style=T.ACCENT))
    if tool_count:
        meta_bits.append(Text(f"{tool_count} tools", style=T.MUTED))
    meta_bits.append(Text("online", style=T.OK) if online
                     else Text("offline", style=T.WARN))
    meta = T.dim_join(meta_bits)

    if width() < 72:
        return Group(Text(""), T.gradient_text("T A R S", bold=True), meta, Text(""))

    grid = Table(box=T.BARE, show_header=False, pad_edge=False, padding=(0, 0))
    grid.add_column(width=17, no_wrap=True)
    grid.add_column(width=4, no_wrap=True)
    grid.add_column(ratio=1, no_wrap=True)

    slabs = _diagonal(_SLABS)
    right: List[RenderableType] = list(_diagonal(_WORDMARK))
    right.append(Text("tactical automated robot system", style=T.MUTED))
    right.append(meta)

    for i in range(5):
        grid.add_row(slabs[i], "", right[i])

    return Group(Text(""), grid, Text(""))


# ════════════════════════════════════════════════════════════════════════════
# Boot sequence
# ════════════════════════════════════════════════════════════════════════════

def _boot_checks() -> List[Tuple[str, str, bool]]:
    """
    Real subsystem readings for the boot report, as (name, detail, degraded).

    Deliberately real. An earlier version of this project displayed invented
    reactor percentages; a boot screen that reports fiction trains you to ignore
    it, which defeats the purpose of having one.
    """
    from tars.core.agents import TARS_TOOLS
    from tars.core.llm import TEXT_MODELS, resolve_api_key
    from tars.core.memory import memory

    checks: List[Tuple[str, str, bool]] = [
        ("tool registry", f"{len(TARS_TOOLS)} tools scoped", False),
        ("unit roster", "TARS · CASE · KIPP", False),
    ]

    deceased = sum(1 for p in memory.people.values()
                   if (p.get("status") or "").lower() == "deceased")
    people = len(memory.people)
    mem_line = f"{len(memory.facts)} facts · {people} {'person' if people == 1 else 'people'}"
    if deceased:
        mem_line += f" · {deceased} remembered"
    checks.append(("memory matrix", mem_line, False))

    empathy = int(getattr(config, "empathy", 0) or 0)
    checks.append(("affective core",
                   f"empathy {empathy}%" if empathy else "disengaged",
                   empathy == 0))

    if resolve_api_key():
        checks.append(("comms uplink", TEXT_MODELS[0] if TEXT_MODELS else "ready", False))
    else:
        checks.append(("comms uplink", "no api key · offline heuristics", True))

    if config.voice_output_enabled:
        try:
            from tars.ui.voice import voice

            checks.append(("voice synthesis", voice.engine_name(), False))
        except Exception:
            checks.append(("voice synthesis", "unavailable", True))
    else:
        checks.append(("voice synthesis", "muted", True))

    checks.append(("security boundary",
                   "confined to workspace" if config.confirm_sensitive
                   else "confirmation gate OFF",
                   not config.confirm_sensitive))
    return checks


def boot(animate: Optional[bool] = None) -> None:
    """
    Power-on report, ticking each subsystem as it reports in.

    The checks themselves are near-instant, so the stagger is cosmetic. It is
    also brief, skippable via `ui animation off`, and skipped outright when
    stdout is not a terminal.
    """
    if animate is None:
        animate = bool(getattr(config, "ui_animation", True))
    animate = animate and is_rich()

    console.print(T.rule("power on"))
    for name, detail, degraded in _boot_checks():
        glyph, color = ("!", T.WARN) if degraded else (T.G_OK, T.OK)
        console.print(Text.assemble(
            ("  ", ""),
            (glyph, color),
            ("  ", ""),
            (name.ljust(20), T.TEXT),
            (detail, T.MUTED),
        ))
        if animate:
            time.sleep(0.05)
    console.print()


# ════════════════════════════════════════════════════════════════════════════
# Reply rendering
# ════════════════════════════════════════════════════════════════════════════

# Cheap structural test for "is this markdown worth parsing". Plain prose must
# NOT go through Markdown: Rich's parser collapses single newlines into
# paragraphs, which would destroy deliberate line breaks in a short reply.
_MD_SIGNAL = re.compile(
    r"```"                       # fenced code
    r"|(?:^|\n)[ ]{0,3}#{1,6}\s" # heading
    r"|(?:^|\n)[ ]{0,3}[-*+]\s"  # bullet list
    r"|(?:^|\n)[ ]{0,3}\d+\.\s"  # ordered list
    r"|(?:^|\n)[ ]{0,3}>\s"      # blockquote
    r"|\*\*\S"                   # bold
    r"|(?:^|\n)[ ]*\|.+\|"       # table row
    r"|`[^`\n]+`"                # inline code
)


def render_body(text: str) -> RenderableType:
    """
    Turns reply text into something safe and good-looking.

    Markdown-shaped replies are parsed, so lists, code, and emphasis render as
    intended. Everything else becomes a plain `Text`, which preserves the
    author's line breaks and -- critically -- does not interpret Rich markup, so
    a reply containing `list[int]`, `[1]`, or a stray `[/]` can neither raise
    nor silently drop characters.
    """
    body = (text or "").strip()
    if not body:
        return Text("")
    if _MD_SIGNAL.search(body):
        return Markdown(body, code_theme="github-dark", hyperlinks=False)
    return Text(body, style=T.TEXT)


class GutterBlock:
    """
    Content behind a continuous coloured left rule.

    This is the shell's primary containment device, chosen over a full panel for
    two reasons: only one column is fixed, so it survives a terminal resize
    without reflowing into nonsense, and it reads as attribution rather than as
    a dialog box.

    It rasterises its children rather than relying on a Rich `Box`, because a
    custom left-only Box gets silently swapped for the ASCII fallback box on
    legacy Windows consoles -- which draws all four sides and looks nothing like
    the intent. Rendering to segments and prefixing each line is deterministic.
    """

    def __init__(self, head: Optional[RenderableType], body: RenderableType,
                 color: str = T.ACCENT) -> None:
        self.head = head
        self.body = body
        self.color = color

    def __rich_console__(self, con, options):
        inner = max(24, options.max_width - 2)
        child = options.update(width=inner)

        bright = con.get_style(self.color)
        # The body rule is the same hue, dropped toward the surface colour, so
        # the bar reads as one continuous element that is brightest at the name.
        dim = con.get_style(T.mix(self.color, T.BG_BAR, 0.55))

        if self.head is not None:
            for line in con.render_lines(self.head, child, pad=False):
                yield Segment(T.G_VBAR + " ", bright)
                yield from line
                yield Segment.line()

        for line in con.render_lines(self.body, child, pad=False):
            yield Segment(T.G_VBAR + " ", dim)
            yield from line
            yield Segment.line()


def reply(text: str, unit: str = "TARS", cue: bool = False,
          mood: str = "", designation: str = "") -> None:
    """
    Renders a unit's reply behind its own coloured gutter.

    The gutter carries identity (which unit is speaking); the badges carry state
    (whether it joked, what it is reading in the room). Those stay in separate
    channels on purpose: if mood tinted the gutter, colour would mean two
    different things in the same glyph.
    """
    unit = (unit or "TARS").upper()
    color = T.AGENT_COLORS.get(unit, T.ACCENT)

    head = Text()
    head.append(unit, style=f"bold {color}")
    if designation:
        head.append(f"  {designation}", style=T.FAINT)
    if cue:
        head.append("  ")
        head.append_text(T.badge("cue", T.OK, filled=True))
    if mood and mood.lower() != "neutral":
        head.append("  ")
        head.append_text(T.badge(mood.lower(), T.mood_color(mood)))

    console.print()
    console.print(GutterBlock(head, render_body(text), color))
    console.print()


def echo_operator(text: str, source: str = "") -> None:
    """
    Renders what the operator said. Used by the voice loops, where there is no
    typed line already on screen to refer back to.
    """
    head = Text("  ")
    head.append(config.operator_callsign.lower(), style=T.MUTED)
    if source:
        head.append(f" ({source})", style=T.FAINT)
    head.append(f"  {T.G_CARET}  ", style=T.FAINT)
    head.append(text, style=T.TEXT_BRIGHT)
    console.print(head)


# ════════════════════════════════════════════════════════════════════════════
# Thinking indicator
# ════════════════════════════════════════════════════════════════════════════

# The slabs pulsing left to right. Same glyph language as the chassis and the
# meters, so the shell only ever speaks in one visual dialect.
_PULSE: Tuple[str, ...] = (
    "▮▯▯▯", "▯▮▯▯", "▯▯▮▯", "▯▯▯▮", "▯▯▮▯", "▯▮▯▯",
)


class Thinking:
    """
    Live indicator for the blocking stretch of a turn.

    Shares `tars.ui.console.console` with the agent loop, so tool lines printed
    mid-turn scroll above the indicator instead of tearing through it.

    Degrades to a single static line when stdout is not a terminal, and to
    nothing at all when animation is off.
    """

    def __init__(self, label: str = "thinking", unit: str = "TARS") -> None:
        self.label = label
        self.unit = unit.upper()
        self._live: Optional[Live] = None
        self._start = 0.0
        self._frame = 0
        self._detail = ""

    # ── rendering ──────────────────────────────────────────────────────────

    def _renderable(self) -> Text:
        color = T.AGENT_COLORS.get(self.unit, T.ACCENT)
        self._frame += 1
        pulse = _PULSE[self._frame % len(_PULSE)]
        elapsed = time.monotonic() - self._start

        line = Text("  ")
        line.append(pulse, style=f"bold {color}")
        line.append("  ")
        line.append(self.label, style=T.MUTED)
        if self._detail:
            line.append(f"  {T.G_DOT}  ", style=T.FAINT)
            line.append(self._detail, style=T.TEXT)
        line.append(f"   {elapsed:4.1f}s", style=T.FAINT)
        return line

    # ── lifecycle ──────────────────────────────────────────────────────────

    def update(self, detail: str = "", label: str = "") -> None:
        """Retargets the indicator, e.g. to the tool currently running."""
        if label:
            self.label = label
        self._detail = detail
        if self._live is not None:
            try:
                self._live.refresh()
            except Exception:
                pass

    def __enter__(self) -> "Thinking":
        self._start = time.monotonic()
        if not getattr(config, "ui_animation", True):
            return self
        if not is_rich():
            console.print(T.info(f"{self.label}..."))
            return self
        try:
            self._live = Live(
                get_renderable=self._renderable,
                console=console,
                refresh_per_second=8,
                transient=True,
            )
            self._live.start()
        except Exception:
            self._live = None
        return self

    def __exit__(self, *exc) -> None:
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._start


# Module-level handle so the agent loop can retarget the active indicator
# without the shell having to thread the object down through every call.
_ACTIVE: Optional[Thinking] = None


def begin_thinking(label: str = "thinking", unit: str = "TARS") -> Thinking:
    global _ACTIVE
    _ACTIVE = Thinking(label=label, unit=unit)
    return _ACTIVE


def note_thinking(detail: str = "", label: str = "") -> None:
    """No-op when nothing is running, so the agent can call it unconditionally."""
    if _ACTIVE is not None:
        _ACTIVE.update(detail=detail, label=label)


def end_thinking() -> None:
    global _ACTIVE
    _ACTIVE = None


# ════════════════════════════════════════════════════════════════════════════
# Tool stream
# ════════════════════════════════════════════════════════════════════════════

def tool_call(name: str, args_preview: str = "", depth: int = 0) -> None:
    """One line per tool invocation, indented by delegation depth."""
    indent = "  " * depth
    console.print(Text(indent).append_text(T.tool_call_line(name, args_preview)))


def tool_result(summary: str, extra_lines: int = 0, failed: bool = False,
                elapsed: float = 0.0, depth: int = 0) -> None:
    """Result summary beneath a call, with timing when it is worth knowing."""
    indent = "  " * depth
    line = T.tool_result_line(summary, extra_lines, failed=failed)
    if elapsed >= 0.4:
        line.append(f"  {elapsed:.1f}s", style=T.FAINT)
    console.print(Text(indent).append_text(line))


# ════════════════════════════════════════════════════════════════════════════
# Status bar
# ════════════════════════════════════════════════════════════════════════════

def _short_cwd(limit: int) -> str:
    path = os.getcwd()
    home = os.path.expanduser("~")
    if path.startswith(home):
        path = "~" + path[len(home):]
    if len(path) <= limit:
        return path
    return "..." + path[-(limit - 3):]


def status_bar() -> Optional[Text]:
    """
    One-line HUD printed above the prompt.

    Deliberately a single line. The point is ambient awareness between turns --
    which model is answering, how the dials sit, what the unit is currently
    reading in the room -- not a dashboard. `status` still exists for the full
    readout.
    """
    if not getattr(config, "ui_status_bar", True):
        return None

    from tars.core.state import state

    term = width()
    bar = Text()
    bar.append("  ")

    # Uplink. Shows the model that actually served the last turn where one is
    # known, falling back to the head of the chain before the first call. The
    # tilde marks "intended, not yet confirmed", so the bar never implies a
    # model answered when it has not.
    try:
        from tars.core.llm import TEXT_MODELS, last_model_used, resolve_api_key

        if resolve_api_key():
            served = last_model_used()
            bar.append(T.G_SIGNAL, style=T.OK)
            bar.append(" ")
            if served:
                bar.append(served.replace("gemini-", ""), style=T.MUTED)
            else:
                head = (TEXT_MODELS[0] if TEXT_MODELS else "ready").replace("gemini-", "")
                bar.append(f"~{head}", style=T.FAINT)
        else:
            bar.append(T.G_SIGNAL, style=T.WARN)
            bar.append(" offline", style=T.WARN)
    except Exception:
        pass

    # Dials
    bar.append(f"   {T.G_DOT}   ", style=T.FAINT)
    bar.append_text(T.pill("hum", str(config.humor), T.TEXT_BRIGHT))
    bar.append(" ")
    bar.append_text(T.pill("hon", str(config.honesty), T.TEXT_BRIGHT))
    empathy = int(getattr(config, "empathy", 0) or 0)
    bar.append(" ")
    bar.append_text(T.pill("emp", str(empathy) if empathy else "off",
                           T.TEXT_BRIGHT if empathy else T.FAINT))

    # Affective read, only when there is one
    mood = (getattr(state, "operator_mood", "") or "neutral").lower()
    if mood != "neutral" and getattr(state, "mood_intensity", 0.0) >= 0.2:
        bar.append(f"   {T.G_DOT}   ", style=T.FAINT)
        bar.append(T.G_EAR, style=T.mood_color(mood))
        bar.append(" ")
        bar.append(mood, style=f"bold {T.mood_color(mood)}")

    # Listening state, when a voice mode is live
    try:
        from tars.ui.voice import wake_listener

        if wake_listener.is_running:
            bar.append(f"   {T.G_DOT}   ", style=T.FAINT)
            bar.append_text(T.badge("listening", T.ACCENT, filled=True))
    except Exception:
        pass

    # Right-hand side: directory and uptime, dropped first when space is tight
    tail = Text()
    tail.append(_short_cwd(max(12, term // 4)), style=T.FAINT)
    tail.append(f"   {T.G_DOT}   ", style=T.FAINT)
    tail.append(state.uptime_str, style=T.FAINT)

    pad = term - bar.cell_len - tail.cell_len - 2
    if pad > 2:
        bar.append(" " * pad)
        bar.append_text(tail)
    return bar


def prompt_line() -> None:
    """Prints the status bar and the thin rule that sits above the prompt."""
    bar = status_bar()
    if bar is not None:
        console.print(bar)


# ════════════════════════════════════════════════════════════════════════════
# Palette preview
# ════════════════════════════════════════════════════════════════════════════

def show_theme() -> None:
    """Renders the design system, for tuning it without guessing."""
    console.print()
    console.print(logo(model="preview", tool_count=24, online=True))
    console.print(T.rule("identity"))
    console.print(T.gradient_rule(width() - 4))
    console.print()

    swatches = [
        ("accent", T.ACCENT), ("text", T.TEXT), ("bright", T.TEXT_BRIGHT),
        ("muted", T.MUTED), ("faint", T.FAINT), ("ok", T.OK),
        ("warn", T.WARN), ("err", T.ERR), ("info", T.INFO),
    ]
    row = Text("  ")
    for name, color in swatches:
        row.append("███", style=color)
        row.append(f" {name}  ", style=T.MUTED)
    console.print(row)
    console.print()

    console.print(T.rule("units"))
    row = Text("  ")
    for unit, color in T.AGENT_COLORS.items():
        row.append(T.G_VBAR, style=color)
        row.append(f" {unit}   ", style=f"bold {color}")
    console.print(row)
    console.print()

    console.print(T.rule("affect"))
    row = Text("  ")
    count = 0
    for mood, color in T.MOOD_COLORS.items():
        if mood == "neutral":
            continue
        row.append(T.G_EAR, style=color)
        row.append(f" {mood}  ", style=T.MUTED)
        count += 1
        if count % 5 == 0:
            console.print(row)
            row = Text("  ")
    if row.cell_len > 2:
        console.print(row)
    console.print()

    console.print(T.rule("meters"))
    for label, fraction in (("nominal", 0.32), ("elevated", 0.78), ("critical", 0.94)):
        line = Text("  ")
        line.append_text(T.meter(fraction, 18))
        line.append(f"  {label}", style=T.MUTED)
        console.print(line)
    console.print()

    console.print(T.rule("reply"))
    reply("Markdown renders now. **Bold**, `inline code`, and lists:\n"
          "\n- her birthday is 15 July\n- butterscotch, not chocolate\n"
          "\nBrackets like `list[int]` and [1] no longer break the renderer.",
          unit="TARS", cue=True, mood="romance")

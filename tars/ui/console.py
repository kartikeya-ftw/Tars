"""
TARS - The shared console.

Every module used to build its own `Console()`. That is harmless for plain
printing, but a live region (the thinking indicator) is owned by one Console
instance: if the agent prints a tool line through a *different* Console while a
live region is open on another, the two fight over cursor position and the
output tears.

So the two that interleave -- the shell and the agent loop -- share this one.
The standalone set pieces (docking, morse) keep their own, since they own the
screen for their duration and never overlap with the agent.
"""
from rich.console import Console

# soft_wrap is left at the default so long tool output still folds to width.
console = Console(highlight=False)


def width(default: int = 100) -> int:
    """Current terminal width, clamped to something laying out can rely on."""
    try:
        return max(60, min(200, console.width))
    except Exception:
        return default


def is_rich() -> bool:
    """True when animation and full-width fills are appropriate."""
    try:
        return bool(console.is_terminal and not console.is_jupyter)
    except Exception:
        return False

"""
Demonstrates the markup-injection bug the new reply renderer fixes.

The old renderer interpolated reply text straight into a Rich markup string:

    console.print(f"[{T.TEXT}]{text}[/{T.TEXT}]")

Any square bracket in the reply was therefore parsed as a style tag. Replies
containing slice syntax, type hints, or footnote markers either raised
MarkupError or silently lost characters.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console

from tars.ui import chrome, theme as T

CASES = [
    ("slice syntax", "Use my_list[::-1] to reverse it."),
    ("type hint", "The signature is def f(x: list[int]) -> dict[str, int]."),
    ("footnote", "Gargantua spins at near-maximal rate [1]."),
    ("closing tag", "A stray [/] in prose."),
    ("indexing", "Read turns[0] then parts[-1]."),
]

failures = []
print("=" * 78)
print("OLD RENDERER   console.print(f'[{TEXT}]{reply}[/{TEXT}]')")
print("=" * 78)
for label, text in CASES:
    probe = Console(record=True, width=90, force_terminal=True)
    try:
        probe.print(f"[{T.TEXT}]{text}[/{T.TEXT}]")
        got = probe.export_text().strip()
        lost = len(got) < len(text)
        status = "LOST TEXT" if lost else "ok"
        print(f"  {label:14s} {status:10s} {got!r}")
        if lost:
            failures.append(f"old/{label}")
    except Exception as ex:
        print(f"  {label:14s} RAISED     {type(ex).__name__}: {ex}")
        failures.append(f"old/{label}")

print()
print("=" * 78)
print("NEW RENDERER   chrome.render_body(reply)")
print("=" * 78)
new_failures = []
for label, text in CASES:
    probe = Console(record=True, width=90, force_terminal=True, highlight=False)
    try:
        probe.print(chrome.render_body(text))
        got = probe.export_text().strip()
        # Inline-code backticks are the only legitimate transformation, and none
        # of these cases use them, so the text must survive verbatim.
        intact = text in got
        print(f"  {label:14s} {'ok' if intact else 'ALTERED':10s} {got!r}")
        if not intact:
            new_failures.append(f"new/{label}")
    except Exception as ex:
        print(f"  {label:14s} RAISED     {type(ex).__name__}: {ex}")
        new_failures.append(f"new/{label}")

print()
print("=" * 78)
print(f"old renderer mangled or raised on {len(failures)}/{len(CASES)} cases: {failures}")
print(f"new renderer failed on {len(new_failures)}/{len(CASES)} cases: {new_failures}")
print("=" * 78)
sys.exit(1 if new_failures else 0)

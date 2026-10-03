"""Compact showcase render of the redesigned shell. Writes scratch/ui_showcase.svg."""
import os
import shutil
import sys
import tempfile
import time as _time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_scratch = Path(tempfile.gettempdir()) / "tars_showcase_memory.json"
shutil.copyfile(ROOT / ".tars_memory.json", _scratch)
os.environ["TARS_MEMORY_FILE"] = str(_scratch)

from rich.console import Console

import tars.ui.console as uicon

rec = Console(record=True, width=100, force_terminal=True, highlight=False)
uicon.console = rec

from tars.config import config
from tars.core.emotion import emotion
from tars.ui import chrome, theme as T

chrome.console = rec
config.ui_animation = False

from tars.ui.banner import get_hud_banner, get_masthead

emotion.read("Priya said yes to Saturday, I'm so happy")

rec.print(get_masthead())
chrome.boot(animate=False)
rec.print(get_hud_banner())

rec.print(T.rule("a turn"))
rec.print(chrome.status_bar())
rec.print(T.Text.assemble(("  [", T.FAINT), ("rohit", f"bold {T.TEXT_BRIGHT}"),
                          ("] ", T.FAINT), (f"{T.G_CARET} ", f"bold {T.ACCENT}"),
                          ("what should I get Priya for her birthday", T.TEXT)))
rec.print()
chrome.tool_call("recall", '{"query": "Priya"}')
chrome.tool_result("PEOPLE - Varsha Priya (girlfriend), status: living", 11, elapsed=0.6)

t = chrome.Thinking(label="reasoning", unit="TARS")
t._start = _time.monotonic() - 3.2
t._frame = 2
t._detail = "recall"
rec.print(t._renderable())

chrome.reply(
    "Her birthday is **15 July**, so you have time to do this properly.\n\n"
    "Going on what you have told me:\n\n"
    "- Butterscotch, not chocolate. She likes chocolate but cannot handle much of it.\n"
    "- Nothing metallic. She is allergic.\n"
    "- She likes being pampered and she likes cute stickers, which is a cheaper "
    "combination than it sounds.\n\n"
    "A quiet evening at home with her music beats anything crowded. She is a "
    "`passenger princess`, so you are driving.",
    unit="TARS", mood="romance",
)

chrome.reply(
    "Reverse a list with `my_list[::-1]`. The slice is `[start:stop:step]`; "
    "leaving the bounds empty takes the whole list and `step=-1` walks it backwards.\n\n"
    "Brackets like `list[int]`, `[/]`, and footnotes `[1]` used to break this renderer. "
    "They no longer do.",
    unit="TARS", cue=True,
)

chrome.reply("Patched the retry loop. Suite: 48 passed, 0 failed. Exit code 0.",
             unit="CASE", designation="USMC 02")

chrome.reply(
    "FINDINGS\n"
    "- Gemini 2.0 Flash pricing confirmed against the official pricing page.\n\n"
    "CONFIDENCE\n"
    "- corroborated (two sources)",
    unit="KIPP", designation="USMC 01",
)

out = ROOT / "scratch" / "ui_showcase.svg"
rec.save_svg(str(out), title="TARS")
print(f"wrote {out}  ({out.stat().st_size // 1024} KB)")

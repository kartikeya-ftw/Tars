"""
Renders the TARS shell chrome to an SVG so the layout can actually be looked at
rather than imagined. Writes scratch/ui_after.svg.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Isolated memory so the preview cannot write to the operator's real records.
_scratch = Path(tempfile.gettempdir()) / "tars_render_memory.json"
shutil.copyfile(ROOT / ".tars_memory.json", _scratch)
os.environ["TARS_MEMORY_FILE"] = str(_scratch)

from rich.console import Console

import tars.ui.console as uicon

# Swap in a recording console before anything caches the real one.
rec = Console(record=True, width=118, force_terminal=True, highlight=False)
uicon.console = rec

from tars.config import config
from tars.core.emotion import emotion
from tars.ui import chrome, theme as T

chrome.console = rec
config.ui_animation = False

from tars.ui.banner import get_hud_banner, get_masthead

# Give the status bar something to read.
emotion.read("Priya said yes to Saturday, I'm so happy")

rec.print(get_masthead())
chrome.boot(animate=False)
rec.print(get_hud_banner())

rec.print(T.rule("conversation"))
chrome.echo_operator("what should I get Priya for her birthday", source="voice")

chrome.tool_call("recall", '{"query": "Priya"}')
chrome.tool_result("PEOPLE - Varsha Priya (girlfriend), status: living", 11, elapsed=0.6)

chrome.reply(
    "Her birthday is 15 July, so you have time to do this properly.\n\n"
    "Going on what you have told me:\n\n"
    "- **Butterscotch**, not chocolate. She likes chocolate but cannot handle much of it.\n"
    "- Nothing metallic. She is allergic.\n"
    "- She likes being pampered and she likes cute stickers, which is a cheaper combination "
    "than it sounds.\n\n"
    "A quiet evening at home with her music beats anything crowded. She is a "
    "`passenger princess`, so you are driving.",
    unit="TARS", cue=False, mood="romance",
)

chrome.reply(
    "Patched the retry loop. Ran the suite: 48 passed, 0 failed. Exit code 0.",
    unit="CASE", designation="USMC 02",
)

rec.print(T.rule("thinking indicator"))
import time as _time

for frame, detail, secs in ((0, "", 0.8), (2, "web_search", 2.4), (4, "delegate_to_case", 11.7)):
    t = chrome.Thinking(label="reasoning", unit="TARS")
    t._start = _time.monotonic() - secs
    t._frame = frame
    t._detail = detail
    rec.print(t._renderable())
rec.print()

rec.print(T.rule("status bar"))
bar = chrome.status_bar()
if bar is not None:
    rec.print(bar)
rec.print()

chrome.show_theme()

out = ROOT / "scratch" / "ui_after.svg"
rec.save_svg(str(out), title="TARS")
print(f"wrote {out}")

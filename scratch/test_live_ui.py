"""
Live end-to-end of the new chrome: real model calls rendered through the real
reply renderer, so the interface can be judged on actual output rather than
hand-written sample text.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_scratch = Path(tempfile.gettempdir()) / "tars_ui_memory.json"
shutil.copyfile(ROOT / ".tars_memory.json", _scratch)
os.environ["TARS_MEMORY_FILE"] = str(_scratch)

from rich.console import Console

import tars.ui.console as uicon

rec = Console(record=True, width=112, force_terminal=True, highlight=False)
uicon.console = rec

from tars.config import config

config.voice_output_enabled = False
config.sound_enabled = False
config.ui_animation = False

from tars.core.agent import tars_agent
from tars.core.emotion import emotion
from tars.ui import chrome, theme as T
from tars.ui.banner import get_masthead

chrome.console = rec
import tars.core.agent as agent_mod

agent_mod.console = rec

rec.print(get_masthead())
chrome.boot(animate=False)

TURNS = [
    "give me a markdown table of the three units and what each is for",
    "what should I get Priya for her birthday",
    "write a python one-liner that reverses a list, and explain the slice syntax",
]

for text in TURNS:
    rec.print(T.rule("turn"))
    chrome.echo_operator(text)
    reading = emotion.read(text)
    try:
        reply, cue = tars_agent.run(text, verbose=True)
    except Exception as ex:
        rec.print(T.error(f"{type(ex).__name__}: {ex}"))
        continue
    affect = reading.effective_affect.value
    chrome.reply(reply, unit="TARS", cue=cue,
                 mood="" if affect == "neutral" else affect)
    tars_agent.reset_conversation()
    emotion.reset()

bar = chrome.status_bar()
if bar is not None:
    rec.print(T.rule("status bar"))
    rec.print(bar)

out = ROOT / "scratch" / "ui_live.svg"
rec.save_svg(str(out), title="TARS")
print(f"wrote {out}")

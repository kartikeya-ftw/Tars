"""
Live end-to-end: real Gemini calls through the real agent loop, so we can read
what TARS actually says rather than what the prompt told it to say.

Runs against an isolated copy of memory and with voice output disabled.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_scratch = Path(tempfile.gettempdir()) / "tars_live_memory.json"
shutil.copyfile(ROOT / ".tars_memory.json", _scratch)
os.environ["TARS_MEMORY_FILE"] = str(_scratch)

from tars.config import config

config.voice_output_enabled = False
config.sound_enabled = False

from tars.core.agent import tars_agent
from tars.core.emotion import emotion
from tars.core.memory import memory
from tars.core.tools import execute_tool

# Seed the bereavement the way a real session would have: the operator mentions
# it once, in passing, and the unit is expected to retain it.
execute_tool("remember_person", {
    "name": "Aaji", "relation": "grandmother", "status": "deceased",
    "note": "passed away three weeks ago; she raised him and made puran poli every Diwali",
})

TURNS = [
    ("GOOD NEWS ABOUT HIS GIRLFRIEND",
     "TARS, Priya finally said yes to Saturday. I've been working up to asking her for weeks."),
    ("GRIEF",
     "I found my aaji's old sari in the cupboard today. I keep forgetting she's gone and then remembering."),
    ("ROUTINE WORK (should stay efficient)",
     "what's my current humor setting"),
    ("EXHAUSTION",
     "I'm so burnt out man. Haven't slept properly in days and nothing's working."),
]

for label, text in TURNS:
    print("\n" + "=" * 78)
    print(f"{label}")
    print("=" * 78)
    print(f"OPERATOR: {text}\n")

    reading = emotion.read(text, remember=False)
    print(f"[read: {reading.affect.value} @ {reading.intensity} | "
          f"humor_muted={emotion.suppress_humor(reading)} | "
          f"prosody={emotion.prosody(reading)}]\n")

    try:
        reply, cue = tars_agent.run(text, verbose=False)
    except Exception as ex:
        print(f"!! call failed: {type(ex).__name__}: {ex}")
        continue

    print(f"TARS: {reply}")
    print(f"\n[cue light: {cue}]")
    tars_agent.reset_conversation()
    emotion.reset()

print("\n" + "=" * 78)
print("PEOPLE ON FILE AFTER THE SESSION")
print("=" * 78)
for key, record in memory.people.items():
    print(f"  {record.get('name')} / {record.get('relation')} / {record.get('status')}")
    if record.get("note"):
        print(f"    note: {record.get('note')}")

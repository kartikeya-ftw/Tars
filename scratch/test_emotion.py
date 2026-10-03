"""Exercises the affective core and the upgraded memory retrieval."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Work on a copy of the real memory so detection tests cannot write a fictional
# bereavement into the operator's actual records.
_scratch = Path(tempfile.gettempdir()) / "tars_test_memory.json"
shutil.copyfile(ROOT / ".tars_memory.json", _scratch)
os.environ["TARS_MEMORY_FILE"] = str(_scratch)

from tars.core.emotion import emotion, Affect
from tars.core.memory import memory

assert str(memory.__class__.__module__)
from tars.core import memory as _mem_mod
assert str(_mem_mod.MEMORY_FILE) == str(_scratch), f"test isolation failed: {_mem_mod.MEMORY_FILE}"


def show(label, text):
    reading = emotion.read(text)
    print(f"\n{'=' * 78}")
    print(f"{label}\n  INPUT: {text[:90]}")
    print(f"  -> affect={reading.affect.value} intensity={reading.intensity} "
          f"task={reading.task_pressure:.2f} charged={reading.is_charged}")
    print(f"  -> evidence={reading.evidence[:4]}")
    print(f"  -> subjects={[p.get('name') for p in reading.subjects]}")
    print(f"  -> mute_humor={emotion.suppress_humor(reading)}  prosody={emotion.prosody(reading)}")
    block = emotion.guidance(reading)
    print(f"  -> guidance: {'(none)' if not block else block.splitlines()[1][:100]}")
    return reading


print("### MIGRATED MEMORY ###")
print(f"people registered: {list(memory.people)}")
for key, rec in memory.people.items():
    print(f"  {key} -> {rec.get('name')} / {rec.get('relation')} / {rec.get('status')}")
print("\nfact salience distribution:")
for f in memory.facts:
    print(f"  w{f.get('salience')} [{f.get('category')}] {f.get('fact')[:60]}")

print("\n\n### DETECTION ###")
emotion.reset()
show("girlfriend / hype", "Priya texted me today and said yes to the date on Saturday, I'm so happy")
emotion.reset()
show("bare partner mention", "what should I get Varsha for her birthday")
emotion.reset()
show("grief", "my grandma passed away last night and I can't stop crying")
emotion.reset()
show("pure task", "read tars/core/agent.py and list the functions")
emotion.reset()
show("task + feeling", "fix this script before Priya's birthday, I'm stressed about the deadline")
emotion.reset()
show("negation guard", "I'm not sad, just busy")
emotion.reset()
show("conflict", "me and Priya had a fight and she's not talking to me")
emotion.reset()
show("affection to tars", "honestly talking to you helps, you're the only one who listens")
emotion.reset()
show("pride", "we won the hackathon, I got selected for the finals")
emotion.reset()
show("exhaustion", "I'm completely burnt out, haven't slept in two days")

print("\n\n### MOOD CARRY ###")
emotion.reset()
emotion.read("my grandmother passed away yesterday")
flat = emotion.read("anyway what time is it")
print(f"flat turn after grief -> own={flat.affect.value} residual={flat.residual_affect.value} "
      f"({flat.residual_intensity}) effective={flat.effective_affect.value}")
print(f"humor suppressed on flat turn: {emotion.suppress_humor(flat)}")

print("\n\n### GRIEF GUIDANCE BLOCK (full) ###")
emotion.reset()
r = emotion.read("I miss my grandma so much, the funeral was yesterday")
print(emotion.guidance(r))

print("\n\n### ROMANCE GUIDANCE BLOCK (full) ###")
emotion.reset()
r = emotion.read("Priya said yes! I'm taking her out on Saturday")
print(emotion.guidance(r))

print("\n\n### MEMORY FOCUS RETRIEVAL ###")
picked = memory.relevant_facts("what does Priya like to eat", limit=5)
for f in picked:
    print(f"  w{f.get('salience')} {f.get('fact')[:70]}")

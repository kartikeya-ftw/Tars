"""
End-to-end check of the affective layer: the real system prompt TARS would be
sent, the memory tools, and the guards that keep wit off a painful reply.

No network. Builds the payload and inspects it instead of calling Gemini.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_scratch = Path(tempfile.gettempdir()) / "tars_integration_memory.json"
shutil.copyfile(ROOT / ".tars_memory.json", _scratch)
os.environ["TARS_MEMORY_FILE"] = str(_scratch)

from tars.config import config
from tars.core import memory as mem_mod
from tars.core.agent import Agent, tars_agent, case_agent
from tars.core.agents import get_profile
from tars.core.emotion import Affect, emotion
from tars.core.memory import memory
from tars.core.tools import execute_tool

assert str(mem_mod.MEMORY_FILE) == str(_scratch), "test isolation failed"

FAILURES = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f"  -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


# The persona itself references "an EMOTIONAL READ block", so presence of the
# injected block has to be tested against its exact header line.
BLOCK_HEADER = "EMOTIONAL READ  (this turn)"


def build(agent, text):
    reading = emotion.read(text) if agent.name == "TARS" else None
    return agent._build_system_instruction(focus=text, reading=reading), reading


print("\n" + "=" * 78)
print("1. MEMORY TOOLS REACHABLE BY THE MODEL")
print("=" * 78)
emotion.reset()
out = execute_tool("remember_person", {
    "name": "Sudha", "relation": "grandmother", "status": "deceased",
    "note": "passed away in October; the operator was very close to her",
})
print(f"  remember_person -> {out}")
check("remember_person registers with status", "deceased" in out)

out = execute_tool("remember", {
    "fact": "Operator's grandmother Sudha used to make him puran poli every Diwali.",
    "category": "bereavement", "salience": 10,
})
print(f"  remember -> {out}")
check("remember stores with explicit salience", "salience=10" in out)

out = execute_tool("recall", {"query": "grandmother"})
print(f"  recall ->\n{out}")
check("recall surfaces the deceased grandmother", "Sudha" in out and "deceased" in out)

out = execute_tool("remember", {"fact": "Operator prefers tabs over spaces."})
check("remember auto-classifies without a category", "salience=" in out, out)
print(f"  auto-classify -> {out}")


print("\n" + "=" * 78)
print("2. GRIEF TURN: the register, the memory, and the guards")
print("=" * 78)
emotion.reset()
prompt, reading = build(tars_agent, "I keep thinking about my grandma. I miss her so much.")
check("grief detected", reading.effective_affect is Affect.GRIEF, reading.affect.value)
check("EMOTIONAL READ block present", BLOCK_HEADER in prompt)
check("grief register injected", "Put the mission voice down" in prompt)
check("humor suspended in prompt", "Humor and sarcasm are suspended" in prompt)
check("cue light forbidden", "do not append [CUE LIGHT]" in prompt)
check("grandmother named in memory block", "Sudha" in prompt)
check("death status stated to the model", "HAS DIED" in prompt)
check("the puran poli detail is carried", "puran poli" in prompt)
check("suppress_humor agrees", emotion.suppress_humor(reading))
check("voice slows and lowers", all(emotion.prosody(reading)), str(emotion.prosody(reading)))
check("conversation guard blocks idle tool use", "Answering is the task" in prompt)
print(f"  prosody: {emotion.prosody(reading)}")


print("\n" + "=" * 78)
print("3. GIRLFRIEND TURN: hype register, her details pulled forward")
print("=" * 78)
emotion.reset()
prompt, reading = build(tars_agent, "Priya said yes to Saturday! I want to make it perfect for her")
check("warm register detected", reading.effective_affect in (Affect.ROMANCE, Affect.JOY),
      reading.affect.value)
check("warm register injected",
      "Be the friend who is genuinely" in prompt or "React first, business second" in prompt)
check("humor NOT suppressed", "Humor and sarcasm are suspended" not in prompt)
check("Varsha Priya in people block", "Varsha Priya" in prompt)
check("her likes pulled forward", "butter scotch" in prompt or "chocolate" in prompt)
check("her allergy pulled forward", "allergic" in prompt.lower())
check("voice lifts", emotion.prosody(reading)[0] is not None, str(emotion.prosody(reading)))
print(f"  prosody: {emotion.prosody(reading)}")
print(f"  affect: {reading.affect.value} @ {reading.intensity}")


print("\n" + "=" * 78)
print("4. ROUTINE WORK TURN: no therapy on a file read")
print("=" * 78)
emotion.reset()
prompt, reading = build(tars_agent, "read tars/core/llm.py and tell me the model fallback order")
check("no affect detected", not reading.is_charged, reading.affect.value)
check("no EMOTIONAL READ block", BLOCK_HEADER not in prompt)
check("normal personality dials line", "Let these genuinely modulate" in prompt)
check("tool discipline intact", "TOOL DISCIPLINE" in prompt)
check("no conversation guard", "Answering is the task" not in prompt)


print("\n" + "=" * 78)
print("5. SPECIALISTS ARE UNAFFECTED")
print("=" * 78)
emotion.reset()
prompt, reading = build(case_agent, "patch the retry loop in llm.py and run the tests")
check("CASE gets no affect block", BLOCK_HEADER not in prompt)
check("CASE persona intact", "Maximally economical" in prompt)
check("CASE stays terse", "as short as the information allows" in prompt)
check("CASE has no memory-write tools", not {"remember", "remember_person"} & get_profile("CASE").tools)
check("TARS has memory tools", {"remember", "remember_person", "recall", "forget"} <= get_profile("TARS").tools)


print("\n" + "=" * 78)
print("6. MEMORY SHORTCUT ACKNOWLEDGEMENT FITS THE CONTENT")
print("=" * 78)
emotion.reset()
reading = emotion.read("remember that my grandmother passed away last week")
ack = Agent._acknowledge_memory(
    {"fact": "my grandmother passed away last week", "category": "bereavement"}, reading)
print(f"  bereavement ack: {ack}")
check("no 'Archived:' receipt for a death", "Archived" not in ack)
check("ack is gentle", "won't make you tell me again" in ack)

emotion.reset()
ack2 = Agent._acknowledge_memory({"fact": "Priya likes butterscotch", "category": "relationship"}, None)
print(f"  relationship ack: {ack2}")
check("relationship ack is warm", "stored properly" in ack2.lower())

ack3 = Agent._acknowledge_memory({"fact": "use ruff for linting", "category": "project"}, None)
print(f"  project ack: {ack3}")
check("routine ack unchanged", "Archived:" in ack3)


print("\n" + "=" * 78)
print("7. EMPATHY DIAL ACTUALLY GATES THE LAYER")
print("=" * 78)
original = config.empathy
try:
    config.empathy = 0
    emotion.reset()
    prompt, reading = build(tars_agent, "my grandma passed away and I can't stop crying")
    check("empathy 0 removes the block", BLOCK_HEADER not in prompt)
    check("detection still runs underneath", reading.affect is Affect.GRIEF)

    config.empathy = 20
    emotion.reset()
    prompt, _ = build(tars_agent, "my grandma passed away and I can't stop crying")
    check("low empathy acknowledges briefly", "Acknowledge briefly" in prompt)

    config.empathy = 95
    emotion.reset()
    prompt, _ = build(tars_agent, "my grandma passed away and I can't stop crying")
    check("high empathy lifts the length limit", "length limits in your persona do not apply" in prompt)
finally:
    config.empathy = original


print("\n" + "=" * 78)
print("8. PERSONA NO LONGER FORBIDS WARMTH")
print("=" * 78)
persona = get_profile("TARS").persona
check("the 'do not perform enthusiasm' blanket is gone", "You do not perform enthusiasm" not in persona)
check("deadpan is preserved", "Deadpan, dry, economical" in persona)
check("presence section added", "PRESENCE" in persona)
check("room-reading section added", "READING THE ROOM" in persona)
check("memory discipline added", "Never ask the operator to repeat" in persona)
check("no emotion labelling", "it sounds like you're feeling" in persona)


print("\n" + "=" * 78)
print("9. SALIENCE PROTECTS WHAT MATTERS")
print("=" * 78)
emotion.reset()
for i in range(40):
    memory.remember_fact(f"Scratch note number {i} about a build flag.", category="project", salience=1)
brief = memory.get_memory_context_prompt(focus="tell me about Priya")
check("partner's name survives 40 trivial facts", "Varsha Priya" in brief)
check("the love declaration survives", "first love" in brief or "all my heart" in brief)
check("grandmother still present", "Sudha" in brief)
protected = [f for f in memory.facts if int(f.get("salience", 0)) >= 6]
check("protected tier is non-empty", len(protected) >= 5, str(len(protected)))
print(f"  facts stored: {len(memory.facts)}, protected: {len(protected)}")
print(f"  briefing length: {len(brief)} chars")


print("\n" + "=" * 78)
print("10. CONFIG ROUND-TRIPS THE NEW DIALS")
print("=" * 78)
check("empathy is persisted", "empathy" in config.PERSISTED)
check("affect_voice is persisted", "affect_voice" in config.PERSISTED)


print("\n" + "=" * 78)
if FAILURES:
    print(f"FAILED ({len(FAILURES)}): " + "; ".join(FAILURES))
    sys.exit(1)
print("ALL CHECKS PASSED")
print("=" * 78)

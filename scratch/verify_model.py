"""
Verifies which Gemini model actually serves a TARS request, as opposed to which
one the code lists first.

Also exercises the full agent loop (system prompt + tool declarations + a real
tool call) so the chain head is validated against the payload TARS really sends,
not a toy request.

Prints no credentials.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_scratch = Path(tempfile.gettempdir()) / "tars_verify_memory.json"
shutil.copyfile(ROOT / ".tars_memory.json", _scratch)
os.environ["TARS_MEMORY_FILE"] = str(_scratch)

import requests

from tars.config import config

config.voice_output_enabled = False
config.sound_enabled = False
config.ui_animation = False

from tars.core.llm import (API_ROOT, TEXT_MODELS, VISION_MODELS, extract_text,
                           generate, last_model_used, resolve_api_key)

KEY = resolve_api_key()
if not KEY:
    sys.exit("no api key configured")

print("=" * 76)
print("CONFIGURED CANDIDATE ORDER")
print("=" * 76)
for i, m in enumerate(TEXT_MODELS):
    print(f"  text   {i}  {m}{'   <- head of chain' if i == 0 else ''}")
print()
for i, m in enumerate(VISION_MODELS):
    print(f"  vision {i}  {m}{'   <- head of chain' if i == 0 else ''}")

print()
print("=" * 76)
print("DO THE CONFIGURED NAMES EXIST ON THIS ACCOUNT?")
print("=" * 76)
available = set()
try:
    r = requests.get(f"{API_ROOT}?key={KEY}&pageSize=1000", timeout=30)
    if r.status_code == 200:
        for m in r.json().get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                available.add(m.get("name", "").replace("models/", ""))
    else:
        print(f"  ListModels HTTP {r.status_code}")
except Exception as ex:
    print(f"  ListModels failed: {type(ex).__name__}: {ex}")

if available:
    for m in dict.fromkeys(TEXT_MODELS + VISION_MODELS):
        print(f"  {'YES' if m in available else 'MISSING':8s} {m}")

print()
print("=" * 76)
print("LIVE: plain generate()")
print("=" * 76)


def notify(model, delay, reason="rate limit"):
    print(f"    retrying {model} in {delay:.1f}s ({reason})")


resp, used, err = generate({
    "contents": [{"role": "user", "parts": [{"text": "Reply with exactly: ack"}]}],
    "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
}, timeout=60, on_retry=notify)
if resp is None:
    print(f"  FAILED: {err}")
else:
    print(f"  model_used                : {used}")
    print(f"  API modelVersion          : {resp.get('modelVersion', '(absent)')}")
    print(f"  llm.last_model_used()     : {last_model_used()}")
    print(f"  reply                     : {extract_text(resp)!r}")

print()
print("=" * 76)
print("LIVE: full agent loop, forced through a real tool call")
print("=" * 76)
from tars.core.agent import tars_agent

reply, cue = tars_agent.run(
    "Use get_system_telemetry to tell me my battery percentage. One line.",
    verbose=True,
)
print(f"  reply                     : {reply[:160]}")
print(f"  served by                 : {last_model_used()}")

print()
print("=" * 76)
print("WHAT THE INTERFACE NOW REPORTS")
print("=" * 76)
from tars.ui.banner import _model_label

print(f"  banner/status model label : {_model_label()}")
print("  (a '~' prefix would mean 'intended head, nothing has answered yet')")

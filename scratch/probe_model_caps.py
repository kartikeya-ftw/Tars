"""
Capability probe for candidate models.

TARS's agent loop always sends `generationConfig.thinkingConfig.thinkingBudget`
and a `tools.functionDeclarations` block. A model that rejects either is unusable
as the chain head regardless of how capable it is, so this checks the real
payload shapes before anything is reordered.

Prints no credentials.
"""
import base64
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from tars.core.llm import API_ROOT, resolve_api_key

KEY = resolve_api_key()
if not KEY:
    sys.exit("no api key configured")

CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
]

DECL = [{
    "functionDeclarations": [{
        "name": "get_battery",
        "description": "Reads the host battery percentage.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    }]
}]


def _tiny_png() -> str:
    """A 16x16 solid PNG, built in memory so the probe needs no fixture file."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (56, 189, 248)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def call(model: str, payload: dict, timeout: int = 60):
    url = f"{API_ROOT}/{model}:generateContent?key={KEY}"
    try:
        r = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as ex:
        return None, f"network error: {ex}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code} {r.text[:160]}"
    return r.json(), ""


def probe(model: str) -> None:
    print("=" * 76)
    print(model)
    print("=" * 76)

    # 1. plain text
    data, err = call(model, {
        "contents": [{"role": "user", "parts": [{"text": "Reply with exactly: ack"}]}],
    })
    print(f"  plain text            {'ok' if data else 'FAIL  ' + err}")

    # 2. thinkingBudget 0 -- what TARS sends for conversational turns
    data, err = call(model, {
        "contents": [{"role": "user", "parts": [{"text": "Reply with exactly: ack"}]}],
        "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
    })
    print(f"  thinkingBudget 0      {'ok' if data else 'FAIL  ' + err}")

    # 3. thinkingBudget 1024 -- what CASE and KIPP send
    data, err = call(model, {
        "contents": [{"role": "user", "parts": [{"text": "Reply with exactly: ack"}]}],
        "generationConfig": {"thinkingConfig": {"thinkingBudget": 1024}},
    })
    print(f"  thinkingBudget 1024   {'ok' if data else 'FAIL  ' + err}")

    # 4. function calling, with a system instruction, as the agent loop does
    data, err = call(model, {
        "contents": [{"role": "user", "parts": [{"text": "What is my battery level? Use your tool."}]}],
        "systemInstruction": {"parts": [{"text": "You are a terse assistant. Call tools when relevant."}]},
        "tools": DECL,
        "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
    })
    if not data:
        print(f"  function calling      FAIL  {err}")
    else:
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        called = any("functionCall" in p for p in parts if isinstance(p, dict))
        names = [p["functionCall"].get("name") for p in parts
                 if isinstance(p, dict) and "functionCall" in p]
        print(f"  function calling      {'ok  -> ' + str(names) if called else 'no call emitted (returned text instead)'}")

    # 5. vision
    try:
        b64 = _tiny_png()
        data, err = call(model, {
            "contents": [{"role": "user", "parts": [
                {"text": "What colour is this image? One word."},
                {"inlineData": {"mimeType": "image/png", "data": b64}},
            ]}],
        })
        print(f"  vision (inlineData)   {'ok' if data else 'FAIL  ' + err}")
    except ImportError:
        print("  vision (inlineData)   skipped (pillow missing)")

    print()


for m in CANDIDATES:
    probe(m)

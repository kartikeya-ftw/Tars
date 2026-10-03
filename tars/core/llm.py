"""
TARS Tactical Automated Robot System - Gemini Transport Layer

Single place where API credentials, candidate model lists, retry/backoff, and
model fallback are defined. Every subsystem (agent, chat, research, vision)
routes through here so a quota failure on one model degrades to the next
instead of killing the capability outright.
"""
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from tars.config import config

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# Ordered most capable first, then degrading toward the lite tier.
#
# This ordering is deliberate and is the reverse of the original. The chain used
# to lead with flash-lite for cost and latency, which meant the agent loop did
# its multi-step tool reasoning on the weakest model on the account. The lite
# models are retained at the tail because they are the quota backstop: when the
# free-tier window on the flagship is exhausted, degrading to lite keeps TARS
# answering instead of failing outright.
#
# Every name below was verified present in the account's ListModels response and
# probed for the three payload shapes TARS actually sends: thinkingBudget 0,
# thinkingBudget 1024, and tools.functionDeclarations. See
# scratch/probe_model_caps.py.
TEXT_MODELS: List[str] = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
]

# Models that accept inlineData image parts. Note: gemini-2.5-* is deliberately
# excluded -- it appears in ListModels but returns 404 "no longer available to
# new users" on newer accounts. There is no gemini-3.8-flash-lite; at the 3.8
# tier only the full flash model and the TTS variants exist.
VISION_MODELS: List[str] = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
]

# Statuses worth trying again rather than abandoning the model for.
#
# 429 is quota. The 5xx family is capacity: the flagship models answer
# "This model is currently experiencing high demand ... usually temporary" with
# a 503 under load, which is emphatically not a reason to conclude the model
# does not work. Before this set existed, any non-429 error broke out of the
# retry loop immediately, so a single transient 503 silently demoted the whole
# turn to a weaker model with no indication to the operator.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


# The model that last served a request successfully.
#
# The HUD used to display TEXT_MODELS[0], which is the *intended* first choice,
# not necessarily the one that answered. With a fallback chain that is an
# actively misleading thing to show: a turn silently served by a tail model
# still reported the head. Recording what actually ran lets the interface tell
# the truth.
_LAST_USED: str = ""


def last_model_used() -> str:
    """Model that most recently returned a 200, or '' if nothing has yet."""
    return _LAST_USED


def resolve_api_key() -> str:
    """Returns the Gemini API key from config or the environment, in priority order."""
    return (
        config.gemini_api_key
        or os.getenv("GEMINI_API_KEY", "")
        or os.getenv("GOOGLE_API_KEY", "")
    ).strip()


def generate(
    payload: Dict[str, Any],
    models: Optional[List[str]] = None,
    timeout: int = 30,
    retries_per_model: int = 3,
    on_retry: Optional[Any] = None,
) -> Tuple[Optional[Dict[str, Any]], str, str]:
    """
    POSTs a generateContent payload, walking the candidate model list on failure.

    Returns (response_json, model_used, error_message).
    On success error_message is empty; on total failure response_json is None.

    `on_retry` is an optional callable invoked as on_retry(model, delay, reason)
    when a retryable status forces a backoff, so callers can surface throttling
    to the user. `reason` is "quota" or "overloaded". A two-argument callback is
    still accepted.

    `retries_per_model` defaults to 3 rather than 2 so the head of the chain is
    sticky: the flagship models answer 503 under load, and one extra cheap retry
    keeps a turn on the preferred model instead of demoting it over a blip.
    """
    api_key = resolve_api_key()
    if not api_key:
        return None, "", "No Gemini API key configured. Set one with 'api-key <key>' or the GEMINI_API_KEY environment variable."

    candidates = models or TEXT_MODELS
    errors: List[str] = []
    quota_blocked: List[str] = []
    overloaded: List[str] = []

    for model_name in candidates:
        url = f"{API_ROOT}/{model_name}:generateContent?key={api_key}"
        for attempt in range(retries_per_model):
            try:
                resp = requests.post(url, json=payload, timeout=timeout)
            except requests.RequestException as ex:
                errors.append(f"{model_name}: network error ({ex})")
                break

            if resp.status_code == 200:
                global _LAST_USED
                _LAST_USED = model_name
                return resp.json(), model_name, ""

            if resp.status_code in RETRYABLE_STATUS:
                is_quota = resp.status_code == 429
                bucket = quota_blocked if is_quota else overloaded
                if model_name not in bucket:
                    bucket.append(model_name)

                # Quota needs a real pause; capacity usually clears in under a
                # second. Backing off 2s for an overloaded flagship when the
                # next model in the chain is nearly as good is the wrong trade.
                delay = (2.0 if is_quota else 0.8) * (1.5 ** attempt)
                if attempt < retries_per_model - 1:
                    if on_retry:
                        _call_on_retry(on_retry, model_name, delay,
                                       "quota" if is_quota else "overloaded")
                    time.sleep(delay)
                continue

            # Everything else -- 400, 403, 404 -- is a real rejection. Trying
            # again will not change the answer, so move to the next model.
            errors.append(f"{model_name}: HTTP {resp.status_code} {resp.text[:120]}")
            break

    # Quota exhaustion is the actionable case, so report it ahead of capacity
    # blips and incidental 404s from later fallbacks in the chain.
    if quota_blocked:
        return None, "", (
            f"Gemini quota exhausted on {', '.join(quota_blocked)}. "
            f"The free tier resets on a rolling window -- wait and retry, or enable billing. "
            f"See https://ai.dev/rate-limit"
        )
    if overloaded:
        return None, "", (
            f"Every candidate model is over capacity ({', '.join(overloaded)}). "
            f"This is usually temporary; retry in a moment."
        )
    if errors:
        return None, "", "All candidate models failed. " + " | ".join(errors)
    return None, "", "No response from any candidate model."


def _call_on_retry(callback: Any, model: str, delay: float, reason: str) -> None:
    """
    Invokes a retry callback, tolerating the older two-argument signature.

    The callback gained a `reason` so the shell can say "over capacity" instead
    of mislabelling every backoff as a rate limit. Callers that have not been
    updated still work.
    """
    try:
        callback(model, delay, reason)
    except TypeError:
        try:
            callback(model, delay)
        except Exception:
            pass
    except Exception:
        pass


def extract_text(resp_data: Dict[str, Any]) -> str:
    """Pulls concatenated text out of a generateContent response, tolerating missing fields."""
    for candidate in resp_data.get("candidates", []):
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if text.strip():
            return text.strip()
    return ""

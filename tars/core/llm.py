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

# Ordered cheapest/fastest first. Verified present on the account's ListModels
# response; if one is retired or quota-limited the next is tried automatically.
TEXT_MODELS: List[str] = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
]

# Models that accept inlineData image parts. Note: gemini-2.5-* is deliberately
# excluded -- it appears in ListModels but returns 404 "no longer available to
# new users" on newer accounts.
VISION_MODELS: List[str] = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
]


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
    retries_per_model: int = 2,
    on_retry: Optional[Any] = None,
) -> Tuple[Optional[Dict[str, Any]], str, str]:
    """
    POSTs a generateContent payload, walking the candidate model list on failure.

    Returns (response_json, model_used, error_message).
    On success error_message is empty; on total failure response_json is None.

    `on_retry` is an optional callable invoked as on_retry(model, delay) when a
    429 forces a backoff, so callers can surface throttling to the user.
    """
    api_key = resolve_api_key()
    if not api_key:
        return None, "", "No Gemini API key configured. Set one with 'api-key <key>' or the GEMINI_API_KEY environment variable."

    candidates = models or TEXT_MODELS
    errors: List[str] = []
    quota_blocked: List[str] = []

    for model_name in candidates:
        url = f"{API_ROOT}/{model_name}:generateContent?key={api_key}"
        delay = 2.0
        for attempt in range(retries_per_model):
            try:
                resp = requests.post(url, json=payload, timeout=timeout)
            except requests.RequestException as ex:
                errors.append(f"{model_name}: network error ({ex})")
                break

            if resp.status_code == 200:
                return resp.json(), model_name, ""

            if resp.status_code == 429:
                if model_name not in quota_blocked:
                    quota_blocked.append(model_name)
                # Only sleep if we are going to retry this same model.
                if attempt < retries_per_model - 1:
                    if on_retry:
                        on_retry(model_name, delay)
                    time.sleep(delay)
                    delay *= 1.5
                continue

            # 4xx/5xx other than 429: this model is not going to work, move on.
            errors.append(f"{model_name}: HTTP {resp.status_code} {resp.text[:120]}")
            break

    # Quota exhaustion is the actionable case, so report it ahead of incidental
    # 404s from later fallbacks in the chain.
    if quota_blocked:
        return None, "", (
            f"Gemini quota exhausted on {', '.join(quota_blocked)}. "
            f"The free tier resets on a rolling window -- wait and retry, or enable billing. "
            f"See https://ai.dev/rate-limit"
        )
    if errors:
        return None, "", "All candidate models failed. " + " | ".join(errors)
    return None, "", "No response from any candidate model."


def extract_text(resp_data: Dict[str, Any]) -> str:
    """Pulls concatenated text out of a generateContent response, tolerating missing fields."""
    for candidate in resp_data.get("candidates", []):
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if text.strip():
            return text.strip()
    return ""

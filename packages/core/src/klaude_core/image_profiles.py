"""Reviewed exact-model evidence for APIs whose catalogs omit image modalities.

Profiles apply only to the documented provider root. Add IDs only after checking
the official model page; aliases, dated IDs and fine-tunes never inherit support.
"""

from __future__ import annotations

OPENAI_ROOT = "https://api.openai.com/v1"
OPENAI_IMAGE_SOURCE = "https://developers.openai.com/api/docs/models/gpt-4.1-mini"
OPENAI_IMAGE_REVIEW = "2026-10-15"
OPENAI_IMAGE_IDS = frozenset({"gpt-4.1-mini", "gpt-4.1-mini-2025-04-14"})


def openai_image_profile(endpoint: str, model: str) -> dict | None:
    if endpoint.rstrip("/") != OPENAI_ROOT or model not in OPENAI_IMAGE_IDS:
        return None
    return {
        "source": OPENAI_IMAGE_SOURCE,
        "reviewed": OPENAI_IMAGE_REVIEW,
        "context_window": 1_047_576,
        "max_output_tokens": 32_768,
    }


GEMINI_ROOT = "https://generativelanguage.googleapis.com"
GEMINI_IMAGE_REVIEW = "2026-10-15"
GEMINI_LEVELS = {
    "gemini-3.5-flash-lite": ("minimal", "low", "medium", "high"),
    "gemini-3.8-flash": ("low", "medium", "high"),
}
GEMINI_IMAGE_IDS = frozenset({"gemini-2.5-flash", "gemini-2.5-flash-lite", *GEMINI_LEVELS})


def gemini_image_profile(endpoint: str, model: str) -> dict | None:
    if endpoint.rstrip("/") != GEMINI_ROOT or model not in GEMINI_IMAGE_IDS:
        return None
    return {
        "source": "https://ai.google.dev/gemini-api/docs/models/" + model,
        "reviewed": GEMINI_IMAGE_REVIEW,
        "context_window": 1_048_576,
        "max_output_tokens": 65_536,
        "thinking_control": "level" if model in GEMINI_LEVELS else "budget",
        "thinking_types": ("enabled",) if model in GEMINI_LEVELS else ("disabled", "enabled"),
        "effort_levels": GEMINI_LEVELS.get(model, ("off", "low", "medium", "high")),
    }

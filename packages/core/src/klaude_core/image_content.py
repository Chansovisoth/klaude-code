"""Bounded neutral image parts and explicit catalog evidence, without transport state."""

from __future__ import annotations

import base64
from typing import Any

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ANTHROPIC_IMAGE_BYTES = 7_500_000  # At most 10 MB after base64 encoding.
IMAGE_BACKENDS = frozenset({
    "ollama", "openai_compatible", "anthropic", "openrouter", "openai_api", "gemini_api",
})


def image_token_estimate(width: int, height: int) -> int:
    """Conservative local admission estimate; server tokenization remains provider owned."""
    return max(512, ((width + 15) // 16) * ((height + 15) // 16))


def image_capability_label(supported: bool | None, evidence: str = "") -> str:
    return "Images: " + (
        "documented" if supported is True and evidence.startswith("official-profile:")
        else "declared" if supported is True else "unsupported" if supported is False else "unknown"
    )


def image_parts(message: dict[str, Any], *, max_bytes: int = MAX_IMAGE_BYTES) -> list[dict]:
    value = message.get("image_content")
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 2 or message.get("role") != "user":
        raise ValueError("Image input requires a user message with at most two images")
    result = []
    for part in value:
        if (
            not isinstance(part, dict)
            or part.get("type") != "image"
            or not isinstance(part.get("mime_type"), str)
            or part["mime_type"] not in {"image/png", "image/jpeg"}
            or not isinstance(part.get("data"), str)
            or len(part["data"]) > ((max_bytes + 2) // 3) * 4
        ):
            raise ValueError("Invalid or oversized image input")
        try:
            decoded = base64.b64decode(part["data"], validate=True)
        except ValueError:
            raise ValueError("Invalid image encoding") from None
        if not decoded or len(decoded) > max_bytes:
            raise ValueError("Invalid or oversized image input")
        result.append({"type": "image", "mime_type": part["mime_type"], "data": part["data"]})
    return result


def declared_images(entry: dict[str, Any]) -> bool | None:
    """A compatible catalog's explicit input modalities; absent means unknown."""
    architecture = entry.get("architecture")
    if architecture is None:
        return None
    if not isinstance(architecture, dict):
        raise ValueError("Invalid image capability metadata")
    modalities = architecture.get("input_modalities")
    if modalities is None:
        return None
    if (
        not isinstance(modalities, list)
        or len(modalities) > 16
        or any(not isinstance(item, str) or len(item) > 64 for item in modalities)
    ):
        raise ValueError("Invalid image input modalities")
    return "image" in modalities

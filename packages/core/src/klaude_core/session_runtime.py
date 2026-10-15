"""Bounded session model choices, independent of Default Chat and tool permissions."""

from __future__ import annotations

import json
import time
from typing import Any

from .model_connections import BACKENDS, split_model_ref
from .model_runtime import ModelInfo

PREFIX = "session.runtime."
EFFORTS = {"minimal", "low", "medium", "high", "max"}


def decode(value: Any) -> dict | None:
    if not isinstance(value, dict) or set(value) != {
        "version", "model", "mode", "effort", "definition", "credentials", "at",
    }:
        return None
    reference, mode, effort = value["model"], value["mode"], value["effort"]
    if (
        type(value["version"]) is not int or value["version"] != 1
        or not isinstance(reference, str) or not 0 < len(reference) <= 768
        or not reference.isprintable()
        or not isinstance(mode, str) or mode not in {"standard", "thinking"}
        or (effort is not None and (not isinstance(effort, str) or effort not in EFFORTS))
        or (mode == "thinking" and effort is None)
        or type(value["at"]) not in {int, float} or not 0 <= value["at"] <= 1e12
        or any(not isinstance(value[k], str) or len(value[k]) > 128
               for k in ("definition", "credentials"))
    ):
        return None
    backend = reference.partition("/")[0].partition("@")[0]
    if backend not in BACKENDS or not reference.partition("/")[2]:
        return None
    try:
        qualified = split_model_ref(reference)
    except ValueError:
        return None
    if "@" in reference.partition("/")[0] and qualified is None:
        return None
    if len(json.dumps(value)) > 2048:
        return None
    return dict(value)


def capture(agent: Any) -> dict | None:
    info = getattr(agent, "model_info", None)
    if not isinstance(info, ModelInfo):
        return None
    mode = getattr(agent, "reasoning_mode", "standard")
    return decode({
        "version": 1, "model": info.ref, "mode": mode,
        "effort": getattr(agent, "reasoning_effort", "medium") if mode == "thinking" else None,
        "definition": info.connection_revision, "credentials": info.credential_revision,
        "at": time.time(),
    })


def legacy(turns: list[dict]) -> dict | None:
    """Only Klaude's own exact model-setting events; never infer from dialogue."""
    for turn in reversed(turns):
        content = turn.get("content")
        if turn.get("role") != "system" or not isinstance(content, dict) \
                or content.get("event") != "session_update":
            continue
        detail = content.get("detail")
        if not isinstance(detail, str) or len(detail) > 2048:
            continue
        parts = detail.split(" · ")
        if len(parts) < 3 or not parts[0].startswith("model ") \
                or parts[-1] != "conversation retained":
            continue
        mode = parts[1]
        effort = next((p for p in parts[2:-1] if p in EFFORTS), None)
        return decode({
            "version": 1, "model": parts[0][6:], "mode": mode, "effort": effort,
            "definition": "", "credentials": "",
            "at": 0,
        })
    return None

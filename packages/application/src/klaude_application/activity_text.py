"""Public, bounded wording for persisted activity events."""

from __future__ import annotations

import re
from typing import Any

_SECRET_VALUE = re.compile(
    r"(?i)(?P<prefix>\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|password|passwd|"
    r"secret|credential)s?\s*(?:=|:)\s*)(?P<value>[^\s,;]+)"
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")
_SECRET_FLAG = re.compile(
    r"(?i)(\B--?(?:api[_-]?key|token|password|passwd|secret|credential)\s+)([^\s]+)"
)
_URL_CREDENTIAL = re.compile(r"(?i)(https?://)[^/@\s:]+(?::[^/@\s]*)?@")


def activity_value(value: object, *, limit: int = 180) -> str:
    """Produce one safe, stable transcript line from model-supplied data."""
    text = " ".join(str(value or "").replace("\x00", "").split())
    text = _SECRET_VALUE.sub(r"\g<prefix>[redacted]", text)
    text = _SECRET_FLAG.sub(r"\1[redacted]", text)
    text = _BEARER.sub(r"\1[redacted]", text)
    text = _URL_CREDENTIAL.sub(r"\1[redacted]@", text)
    return text if len(text) <= limit else text[: max(1, limit - 1)].rstrip() + "…"


def activity_elapsed(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def completed_activity_text(label: object, detail: object, elapsed_seconds: object = None) -> str:
    safe_label = activity_value(label, limit=32).casefold()
    safe_detail = activity_value(detail, limit=240)
    if not safe_label or not safe_detail:
        return ""
    elapsed = f" ({activity_elapsed(elapsed_seconds)})" if type(elapsed_seconds) is int else ""
    return f"[{safe_label}]{elapsed} {safe_detail}"


def subagent_activity_text(payload: dict[str, Any]) -> str:
    kind = payload.get("kind")
    if kind not in {"subagent_finished", "subagent_rejected"}:
        return ""
    status = str(payload.get("status", "failed")).casefold()
    label = {"completed": "explored", "cancelled": "cancelled"}.get(status, "failed")
    role = activity_value(payload.get("role") or "read_research", limit=40).replace("_", "/")
    steps = max(0, int(payload.get("model_steps") or 0))
    calls = max(0, int(payload.get("tool_calls") or 0))
    tokens = max(0, int(payload.get("input_tokens") or 0)) + max(
        0, int(payload.get("output_tokens") or 0)
    )
    unknown_token_requests = max(0, int(payload.get("unknown_token_requests") or 0))
    metrics = []
    if steps:
        metrics.append(f"{steps} model {'step' if steps == 1 else 'steps'}")
    if calls:
        metrics.append(f"{calls} tool {'call' if calls == 1 else 'calls'}")
    if tokens:
        metrics.append(f"{tokens:,} tokens")
    if unknown_token_requests:
        metrics.append(
            f"token usage unavailable for {unknown_token_requests} "
            f"{'request' if unknown_token_requests == 1 else 'requests'}"
        )
    suffix = f" ({' · '.join(metrics)})" if metrics else ""
    outcome = "rejected" if kind == "subagent_rejected" else status
    rendered = f"[{label}] {role} subagent {outcome}{suffix}"
    summary = activity_value(payload.get("summary"), limit=500)
    return rendered + (f"\n  └ {summary}" if summary else "")

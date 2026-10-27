"""Numeric generation throughput from reported token counts; never text estimates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


def public_generation_stats(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    tokens, seconds, requests = (value.get(key) for key in (
        "output_tokens", "generation_seconds", "requests",
    ))
    if (type(tokens) is not int or not 0 <= tokens <= 9_000_000_000_000_000
            or not isinstance(seconds, (int, float)) or isinstance(seconds, bool)
            or not 0 < seconds <= 1_000_000_000_000
            or not math.isfinite(seconds)
            or type(requests) is not int or not 1 <= requests <= 10000
            or not isinstance(value.get("timing"), str)
            or value["timing"] not in {"provider", "request", "mixed"}):
        return None
    rate = tokens / seconds
    if not math.isfinite(rate):
        return None
    return {"output_tokens": tokens, "generation_seconds": seconds, "requests": requests,
            "timing": value["timing"], "average_tokens_per_second": rate}


@dataclass
class GenerationStats:
    output_tokens: int = 0
    seconds: float = 0
    requests: int = 0
    provider_requests: int = 0
    unknown: bool = False

    def observe(self, tokens: int | None, duration_ns: object, elapsed: float) -> None:
        if type(tokens) is not int or not 0 <= tokens <= 9_000_000_000_000_000:
            self.unknown = True
            return
        seconds = elapsed
        provider = False
        if isinstance(duration_ns, (int, float)) and not isinstance(duration_ns, bool):
            if 0 < duration_ns <= 9_000_000_000_000_000_000 and math.isfinite(duration_ns):
                seconds = duration_ns / 1_000_000_000
                provider = True
        if not math.isfinite(seconds) or seconds <= 0:
            self.unknown = True
            return
        self.output_tokens += tokens
        self.seconds += seconds
        self.requests += 1
        self.provider_requests += int(provider)

    def public(self) -> dict[str, Any] | None:
        if self.unknown:
            return None
        timing = ("provider" if self.provider_requests == self.requests else
                  "request" if not self.provider_requests else "mixed")
        return public_generation_stats({"output_tokens": self.output_tokens,
                                       "generation_seconds": self.seconds,
                                       "requests": self.requests, "timing": timing})

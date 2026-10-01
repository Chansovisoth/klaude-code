"""Pure overview snapshot state; no filesystem, SQLite, or provider access."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast


@dataclass(frozen=True)
class SettingsOverviewSnapshot:
    memory_enabled: bool | None = None
    mcp_counts: tuple[int, int] | None = None
    memory_loaded_at: float = 0.0
    mcp_loaded_at: float = 0.0
    memory_failed: bool = False
    mcp_failed: bool = False

    def refreshed(self, result: object, now: float) -> SettingsOverviewSnapshot:
        values = result if isinstance(result, dict) else {}
        memory = values.get("memory_enabled")
        enabled, total = values.get("mcp_enabled"), values.get("mcp_total")
        valid_memory = type(memory) is bool
        valid_mcp = (
            type(enabled) is int and type(total) is int and 0 <= enabled <= total <= 100_000
        )
        return SettingsOverviewSnapshot(
            memory if valid_memory else self.memory_enabled,
            (cast(int, enabled), cast(int, total)) if valid_mcp else self.mcp_counts,
            now if valid_memory else self.memory_loaded_at,
            now if valid_mcp else self.mcp_loaded_at,
            not valid_memory, not valid_mcp,
        )

    def with_memory(self, enabled: bool, now: float) -> SettingsOverviewSnapshot:
        return replace(self, memory_enabled=enabled, memory_loaded_at=now, memory_failed=False)

    def labels(self, *, loading: bool, now: float) -> tuple[str, str]:
        def label(value: str | None, loaded_at: float, failed: bool) -> str:
            if value is None:
                return "loading…" if loading else "unavailable" if failed else "not loaded"
            age = max(0, int(now - loaded_at))
            if loading or failed or age >= 30:
                suffix = " · refreshing…" if loading else " · unavailable" if failed else ""
                return f"{value} · cached {age}s ago{suffix}"
            return value

        return (
            label(
                None if self.memory_enabled is None else "on" if self.memory_enabled else "off",
                self.memory_loaded_at, self.memory_failed,
            ),
            label(
                f"{self.mcp_counts[0]}/{self.mcp_counts[1]} enabled" if self.mcp_counts else None,
                self.mcp_loaded_at, self.mcp_failed,
            ),
        )

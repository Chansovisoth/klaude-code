"""Bounded local hardware hints, without repository, location, or model probes."""

from __future__ import annotations

import os
import subprocess
from itertools import islice
from pathlib import Path


def _read_hint(path: Path) -> str:
    try:
        with path.open() as stream:
            return stream.read(65_536).strip()
    except (OSError, UnicodeError):
        return ""


def _positive_integer(value: str) -> int:
    return int(value) if value.isascii() and value.isdigit() and len(value) <= 20 else 0


def hardware_capacity() -> tuple[int, int, int]:
    """Return CPU capacity, RAM bytes, and largest dedicated GPU VRAM only."""
    threads = os.cpu_count() or 1
    try:
        threads = min(threads, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        pass
    quota = _read_hint(Path("/sys/fs/cgroup/cpu.max")).split()
    if len(quota) == 2:
        amount, period = (_positive_integer(part) for part in quota)
        if amount and period:
            threads = min(threads, max(1, amount // period))
    memory = 0
    for line in _read_hint(Path("/proc/meminfo")).splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "MemTotal:" and parts[2] == "kB":
            memory = _positive_integer(parts[1]) * 1024
            break
    if not memory:
        try:
            memory = int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
        except (AttributeError, OSError, ValueError):
            pass
    limit = _positive_integer(_read_hint(Path("/sys/fs/cgroup/memory.max")))
    if limit:
        memory = min(memory, limit) if memory else limit
    vram = max((
        _positive_integer(_read_hint(path)) for path in islice(
            Path("/sys/class/drm").glob("card[0-9]*/device/mem_info_vram_total"), 64
        )
    ), default=0)
    # Fixed executable/arguments only; never search a workspace-controlled PATH.
    executable = Path("/usr/bin/nvidia-smi")
    if executable.is_file():
        try:
            result = subprocess.run(
                [str(executable), "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, timeout=2, check=False,
                env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            )
            if result.returncode == 0:
                values = result.stdout[:65_536].decode("ascii", errors="ignore").splitlines()[:64]
                vram = max(vram, max((
                    _positive_integer(value.strip()) * 1024**2 for value in values
                ), default=0))
        except (OSError, subprocess.TimeoutExpired):
            pass
    return max(1, threads), max(0, memory), vram


def recommend_runtime_options(threads: int, memory: int, vram: int) -> dict[str, int]:
    """Keep calibration bounded; these are hints, not a model-fit guarantee."""
    budget = vram or memory
    if memory:
        budget = min(budget, memory)
    context = (
        65_536 if budget >= 24 * 1024**3 else
        32_768 if budget >= 12 * 1024**3 else
        16_384 if budget >= 8 * 1024**3 else 8_192
    )
    return {"num_thread": max(1, min(16, threads // 2)), "num_ctx": context}


def calibrate_runtime_options() -> dict[str, int]:
    return recommend_runtime_options(*hardware_capacity())

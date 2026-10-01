import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from klaude_core.runtime_calibration import hardware_capacity, recommend_runtime_options


@pytest.mark.parametrize(
    "gib,context", [(0, 8192), (7, 8192), (8, 16384), (12, 32768), (24, 65536)]
)
def test_calibration_thresholds_are_bounded(gib, context):
    assert recommend_runtime_options(128, gib * 1024**3, 0) == {
        "num_thread": 16, "num_ctx": context,
    }
    assert recommend_runtime_options(1, 0, 0)["num_thread"] == 1


def test_vram_is_not_pooled_and_host_memory_remains_a_bound():
    assert recommend_runtime_options(8, 32 * 1024**3, 8 * 1024**3)["num_ctx"] == 16384
    assert recommend_runtime_options(8, 4 * 1024**3, 24 * 1024**3)["num_ctx"] == 8192


def test_capacity_reads_only_fixed_hardware_hints_and_respects_cgroups(monkeypatch):
    import klaude_core.runtime_calibration as module

    seen = []
    hints = {
        "/proc/meminfo": "MemTotal: 33554432 kB\nPrivate: not-returned",
        "/sys/fs/cgroup/cpu.max": "200000 100000",
        "/sys/fs/cgroup/memory.max": str(4 * 1024**3),
        "/gpu/mem_info_vram_total": str(8 * 1024**3),
    }
    def read(path):
        seen.append(str(path))
        return hints.get(str(path), "")
    monkeypatch.setattr(module, "_read_hint", read)
    monkeypatch.setattr(module.os, "cpu_count", lambda: 16)
    monkeypatch.setattr(module.os, "sched_getaffinity", lambda pid: {0, 1, 2, 3})
    monkeypatch.setattr(
        Path, "glob", lambda self, pattern: iter([Path("/gpu/mem_info_vram_total")])
    )
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    assert hardware_capacity() == (2, 4 * 1024**3, 8 * 1024**3)
    assert set(seen) == set(hints)


@pytest.mark.parametrize("failure", [False, True])
def test_nvidia_probe_has_fixed_argv_deadline_and_no_secret_environment(monkeypatch, failure):
    import klaude_core.runtime_calibration as module

    monkeypatch.setattr(module, "_read_hint", lambda path: "")
    monkeypatch.setattr(Path, "glob", lambda self, pattern: iter([]))
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    def run(argv, **kwargs):
        assert argv == [
            "/usr/bin/nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"
        ]
        assert kwargs["timeout"] == 2
        assert kwargs["env"] == {"PATH": "/usr/bin:/bin", "LANG": "C"}
        assert "shell" not in kwargs
        if failure:
            raise subprocess.TimeoutExpired(argv, 2)
        return SimpleNamespace(returncode=0, stdout=b"8192\n24576\nnot a number\n")
    monkeypatch.setattr(module.subprocess, "run", run)
    assert hardware_capacity()[2] == (0 if failure else 24 * 1024**3)


def test_worker_exposes_only_numeric_recommendations(monkeypatch):
    import klaude_core.runtime_calibration as module
    from klaude_cli.background_worker import execute

    monkeypatch.setattr(module, "hardware_capacity", lambda: (8, 16 * 1024**3, 0))
    assert execute({"kind": "runtime_calibration"}) == {"num_thread": 4, "num_ctx": 32768}

"""Native transfer observations and read-only local daemon identity checks.

Private progress observations confer no ownership or recovery authority. Only a
verified newer server generation can establish that an old local request ended.
An absent observer must never change a model operation's result.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .settings_store import atomic_write_private


def process_identity(pid: int) -> str:
    """Linux start ticks prevent a stale file matching a reused process ID."""
    try:
        return Path(f"/proc/{pid}/stat").read_text()[:4096].rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return ""


def local_server_generation(base_url: str) -> tuple[int, int, str] | None:
    """Identify the running standard loopback daemon, never probe/start a pull.

    Stable PID/start-clock/start-ticks identify a generation across two reads.
    This deliberately provides no restart proof for remote/proxied endpoints.
    """
    try:
        address = urlsplit(base_url)
        if (address.scheme != "http" or address.hostname not in {"localhost", "127.0.0.1", "::1"}
                or address.path not in {"", "/"} or address.username or address.password):
            return None
        result = subprocess.run(
            ["systemctl", "show", "ollama.service", "--no-pager",
             "--property=MainPID,ExecMainStartTimestampMonotonic,Environment"],
            capture_output=True, timeout=0.75, check=False,
        )
        if result.returncode or len(result.stdout) > 65536:
            return None
        props = dict(line.split("=", 1) for line in result.stdout.decode().splitlines()
                     if "=" in line)
        host = next((value.split("=", 1)[1]
                     for value in shlex.split(props.get("Environment", ""))
                     if value.startswith("OLLAMA_HOST=")), "127.0.0.1:11434")
        bound = urlsplit(host if "://" in host else "http://" + host)
        if (bound.hostname not in {"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"}
                or (bound.port or 11434) != (address.port or 80)):
            return None
        if ((address.hostname == "127.0.0.1" and bound.hostname == "::1")
                or (address.hostname == "::1" and bound.hostname in {"127.0.0.1", "0.0.0.0"})):
            return None
        pid = int(props.get("MainPID", "0"))
        started = int(props.get("ExecMainStartTimestampMonotonic", "0"))
        identity = process_identity(pid) if pid > 0 else ""
        if not identity or not 0 < started <= time.monotonic() * 1e6:
            return None
        return pid, started, identity
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        return None


def local_request_ended(
    base_url: str, request_id: str, *, generation: tuple[int, int, str] | None,
) -> bool:
    """Read an exact tagged native HTTP-handler completion, never another pull.

    The random request ID is local correlation metadata, never a model/secret.
    Unavailable, omitted or mismatched access logs provide no recovery proof.
    """
    if generation is None or not re.fullmatch(r"[a-f0-9]{32}", request_id):
        return False
    try:
        result = subprocess.run(
            ["journalctl", "--unit=ollama.service", "--boot", "--no-pager", "--output=json",
             "--lines=20", f"--grep=klaude_request={request_id}"],
            capture_output=True, timeout=0.75, check=False,
        )
        if result.returncode or len(result.stdout) > 262144:
            return False
        pattern = re.compile(
            r'^\[GIN\] \d{4}/\d\d/\d\d - \d\d:\d\d:\d\d\s*\|\s*\d{3}\s*\|'
            r'[^|\n]+\|[^|\n]+\|\s*POST\s+"/api/pull\?klaude_request='
            + request_id + r'"\s*$'
        )
        for raw in result.stdout.splitlines():
            row = json.loads(raw)
            if (isinstance(row, dict) and row.get("_PID") == str(generation[0])
                    and isinstance(row.get("MESSAGE"), str) and pattern.fullmatch(row["MESSAGE"])
                    and local_server_generation(base_url) == generation):
                return True
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        pass
    return False


@contextmanager
def track_transfer(
    cfg: Any, connection: Any, model: str, emit: Callable[[dict], None],
) -> Iterator[Callable[[dict], None]]:
    root = cfg.data_dir / "model-manager" / "activity"
    path = root / f"{uuid.uuid4().hex}.json"
    record = {"pid": os.getpid(), "process": process_identity(os.getpid()),
              "connection": connection.id, "revision": connection.revision,
              "model": model, "started_at": time.time(), "progress": {}}

    def publish() -> None:
        try:
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write_private(path, json.dumps(record))
        except OSError:
            pass

    def report(progress: dict) -> None:
        record["progress"] = {key: progress.get(key) for key in ("stage", "completed", "total")}
        publish()
        emit(progress)

    # Bound leftover receipts after killed workers. Current workers own their
    # individual file lifecycle, even during very long transfers.
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with os.scandir(root) as entries:
            for index, entry in enumerate(entries):
                if index >= 256:
                    break
                if entry.name.endswith(".json") and entry.is_file(follow_symlinks=False):
                    try:
                        fd = os.open(entry.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                        with os.fdopen(fd, "rb") as stream:
                            old = json.loads(stream.read(4097))
                        pid = old.get("pid") if isinstance(old, dict) else None
                        if (type(pid) is int and pid > 0
                                and process_identity(pid) != old.get("process")):
                            Path(entry.path).unlink(missing_ok=True)
                    except (OSError, ValueError):
                        pass
    except OSError:
        pass
    publish()
    try:
        yield report
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

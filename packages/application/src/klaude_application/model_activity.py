"""Read-only, bounded observations of model transfers; never submit or join a pull.

Ollama has no list-active-transfers API. Shared Klaude progress gives exact model
identity; local daemon partial-file writes give activity only, never a model name,
percentage, completion claim, cancellation handle or operation-journal authority.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import pwd
import re
import shlex
import stat
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from klaude_core.ollama_activity import process_identity
from klaude_core.ollama_manager import connections, model_name

from .model_store import read_record


def _loopback(value: str) -> bool:
    if value == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _local_store() -> tuple[Path, int] | None:
    """Discover only the running standard system service, without shell or sudo."""
    try:
        result = subprocess.run(
            ["systemctl", "show", "ollama.service", "--no-pager",
             "--property=MainPID,Environment,User"],
            capture_output=True, timeout=0.75, check=False,
        )
        if result.returncode or len(result.stdout) > 65536:
            return None
        props = dict(line.split("=", 1) for line in result.stdout.decode().splitlines()
                     if "=" in line)
        if int(props.get("MainPID", "0")) <= 0:
            return None
        # Never return or persist the other service environment values.
        env = dict(value.split("=", 1) for value in shlex.split(props.get("Environment", ""))
                   if value.startswith(("OLLAMA_HOST=", "OLLAMA_MODELS=")))
        host = env.get("OLLAMA_HOST", "127.0.0.1:11434")
        parsed = urlsplit(host if "://" in host else "http://" + host)
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"}:
            return None
        root = env.get("OLLAMA_MODELS")
        if not root:
            root = str(Path(pwd.getpwnam(props.get("User") or "root").pw_dir)
                       / ".ollama" / "models")
        if not Path(root).is_absolute() or not parsed.hostname:
            return None
        return Path(root) / "blobs", parsed.port or 11434
    except (OSError, ValueError, KeyError, UnicodeError, subprocess.TimeoutExpired):
        return None


def _partials(root: Path) -> dict[str, tuple[int, int, int]]:
    result = {}
    with os.scandir(root) as entries:
        for index, entry in enumerate(entries):
            if index >= 10000:
                raise OSError("Local inventory observation limit")
            if not re.fullmatch(r"sha256-[a-f0-9]{64}-partial", entry.name):
                continue
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISREG(info.st_mode):
                # st_size is preallocated by Ollama. It is NOT bytes completed.
                result[entry.name] = (info.st_ino, info.st_mtime_ns, info.st_blocks)
    return result


class ModelActivity:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._discovered = 0.0
        self._store: tuple[Path, int] | None = None
        self._previous: dict[str, tuple[int, int, int]] = {}
        self._seen: dict[str, float] = {}

    @staticmethod
    def _shared(cfg: Any, endpoints: dict, owned: list[dict]) -> list[dict]:
        result: list[dict] = []
        try:
            with os.scandir(cfg.data_dir / "model-manager" / "activity") as entries:
                for index, entry in enumerate(entries):
                    if index >= 256 or len(result) >= 30:
                        break
                    if not re.fullmatch(r"[a-f0-9]{32}\.json", entry.name):
                        continue
                    try:
                        record = read_record(Path(entry.path), limit=4096)
                        connection = endpoints.get(record.get("connection"))
                        pid = record.get("pid")
                        if (not connection or record.get("revision") != connection.revision
                                or type(pid) is not int or pid <= 0 or not record.get("process")
                                or process_identity(pid) != record["process"]):
                            continue
                        model = model_name(record.get("model"))
                        if any(row.get("connection") == connection.id
                               and row.get("model") == model
                               and row.get("state") in {"accepted", "running", "cancelling"}
                               for row in owned):
                            continue
                        progress = record.get("progress", {})
                        if not isinstance(progress, dict):
                            progress = {}
                        # Stages are fixed, not provider prose or arbitrary file content.
                        stage = progress.get("stage")
                        if stage not in {"Complete", "Downloading file", "Checking manifest",
                                         "Verifying download", "Saving model",
                                         "Preparing download"}:
                            stage = "Preparing download"
                        completed, total = progress.get("completed"), progress.get("total")
                        valid = (type(completed) is int and type(total) is int
                                 and 0 <= completed <= total < 2**63)
                        result.append({"id": entry.name[:-5], "source": "klaude",
                                       "connection": connection.id, "model": model,
                                       "state": "running", "progress": {"stage": stage,
                                       "completed": completed if valid else None,
                                       "total": total if valid else None}})
                    except (OSError, ValueError, TypeError):
                        continue
        except OSError:
            pass
        return result

    def read(self, cfg: Any, owned: list[dict]) -> dict:
        with self._lock:
            try:
                return self._read(cfg, owned)
            except (OSError, ValueError):
                # Observation failure must not hide authoritative job receipts.
                return {"observed": [], "observation": {"local": "unavailable",
                        "remote": "unsupported", "checked_at": time.time()}}

    def _read(self, cfg: Any, owned: list[dict]) -> dict:
        now = time.time()
        endpoints = {key: value for key, value in connections(cfg).items()
                     if value.enabled and value.backend == "ollama" and value.source == "Local"}
        observed = self._shared(cfg, endpoints, owned)
        if time.monotonic() - self._discovered > 30:
            self._store = _local_store()
            self._discovered = time.monotonic()
        status = "unavailable"
        if self._store:
            root, port = self._store
            local = []
            for connection in endpoints.values():
                parsed = urlsplit(connection.base_url)
                if (_loopback(parsed.hostname or "") and parsed.scheme == "http"
                        and (parsed.port or 80) == port and parsed.path in {"", "/"}):
                    local.append(connection.id)
            if local:
                try:
                    current = _partials(root)
                    for name, fingerprint in current.items():
                        previous = self._previous.get(name)
                        if ((previous is not None and previous != fingerprint)
                                or previous is None and -2 <= now - fingerprint[1] / 1e9 <= 10):
                            self._seen[name] = now
                    self._previous = current
                    self._seen = {name: stamp for name, stamp in self._seen.items()
                                  if name in current and now - stamp <= 60}
                    status = "available"
                    # Aliases for this daemon share one observation; prefer an
                    # endpoint without a known pull to avoid a duplicate row.
                    busy = {row.get("connection") for row in [*owned, *observed]
                            if row.get("state") in {"accepted", "running", "cancelling"}}
                    if self._seen and not any(identity in busy for identity in local):
                        recent = any(now - stamp <= 15 for stamp in self._seen.values())
                        identity = local[0]
                        observed.append({"id": hashlib.sha256(identity.encode()).hexdigest()[:32],
                                         "source": "ollama", "connection": identity,
                                         "model": "Ollama transfer activity",
                                         "state": "recent" if recent else "quiet",
                                         "files": len(self._seen), "progress": {}})
                except OSError:
                    status = "unavailable"
        return {"observed": observed, "observation": {"local": status,
                "remote": "unsupported", "checked_at": now}}

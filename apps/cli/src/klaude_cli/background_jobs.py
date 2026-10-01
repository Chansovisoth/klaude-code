"""Owned, replaceable read-only jobs with killable isolated worker processes."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

MAX_JOB_OUTPUT = 2_000_000


@dataclass
class BackgroundJob:
    key: str
    id: str
    cancel: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class OwnedBackgroundJobs:
    def __init__(self, emit: Callable[[str, object], None]):
        self.emit = emit
        self._lock = threading.RLock()
        self._active: dict[str, BackgroundJob] = {}
        self._latest: dict[str, str] = {}
        self._closed = False

    def current(self, key: str, identity: str) -> bool:
        with self._lock:
            return not self._closed and self._latest.get(key) == identity

    def cancel(self, key: str) -> None:
        with self._lock:
            self._latest.pop(key, None)
            for job in self._active.values():
                if job.key == key:
                    job.cancel.set()

    def submit(self, key: str, request: dict[str, Any], *, timeout: float = 30) -> str:
        with self._lock:
            self.cancel(key)
            identity = uuid.uuid4().hex
            self._latest[key] = identity
            if self._closed:
                return identity
            if len(self._active) >= 8:
                self.emit("background_result", (key, identity, None, "Background jobs busy; retry"))
                return identity
            job = BackgroundJob(key, identity)
            self._active[identity] = job
            job.thread = threading.Thread(
                target=self._run,
                args=(job, request, timeout),
                name=f"klaude-background-{key}",
                daemon=True,
            )
            job.thread.start()
            return identity

    def _run(self, job: BackgroundJob, request: dict[str, Any], timeout: float) -> None:
        process: subprocess.Popen[bytes] | None = None
        result = None
        error = ""
        try:
            if job.cancel.is_set():
                return
            # Secrets travel only through a private pipe, never argv/environment.
            environment = {
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "HOME", "LANG", "LC_ALL", "KLAUDE_CODEX_BIN", "CODEX_HOME"}
            }
            process = subprocess.Popen(
                [sys.executable, "-m", "klaude_cli.background_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=environment,
                start_new_session=True,
            )
            payload: bytes | None = json.dumps(request).encode()
            deadline = time.monotonic() + timeout
            while not job.cancel.is_set():
                if time.monotonic() >= deadline:
                    error = "Background job timed out; retry"
                    break
                try:
                    output, _ = process.communicate(payload, timeout=0.05)
                    if len(output) > MAX_JOB_OUTPUT or process.returncode:
                        error = "Background job failed; retry"
                    else:
                        response = json.loads(output)
                        if not isinstance(response, dict):
                            raise ValueError
                        result = response.get("result")
                        error = "Background job unavailable; retry" if response.get("error") else ""
                    break
                except subprocess.TimeoutExpired:
                    payload = None
            if job.cancel.is_set():
                return
        except Exception:  # no credential-bearing exception may reach a UI event
            error = "Background job unavailable; retry"
        finally:
            if process is not None:
                self._stop_process(process)
            with self._lock:
                self._active.pop(job.id, None)
        if self.current(job.key, job.id):
            self.emit("background_result", (job.key, job.id, result, error))

    @staticmethod
    def _stop_process(process: subprocess.Popen[bytes]) -> None:
        # Even a worker that exited may have left a broker descendant. Kill the
        # entire owned group, then reap the worker and close its private pipes.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                continue
        for pipe in (process.stdin, process.stdout):
            if pipe is not None:
                pipe.close()

    def close(self, *, wait: bool = False) -> None:
        with self._lock:
            self._closed = True
            self._latest.clear()
            jobs = list(self._active.values())
            for job in jobs:
                job.cancel.set()
        if wait:
            deadline = time.monotonic() + 2
            for job in jobs:
                if job.thread is not None:
                    job.thread.join(max(0, deadline - time.monotonic()))

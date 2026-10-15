"""Persistent helpers whose stdin lease ends when their owning client exits."""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from klaude_core.managed_serving import reconcile, records, stop_adopted, stop_group

HELPER_STOP_SECONDS = 8
# Leave room for helper exit classification, group reap and endpoint reconciliation.
CLOSE_SECONDS = HELPER_STOP_SECONDS + 4


@dataclass
class ServingJob:
    id: str
    stop: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class ServingJobs:
    def __init__(self, emit):
        self.emit = emit
        self._lock = threading.RLock()
        self._jobs: dict[str, ServingJob] = {}
        self._closed = False

    def owns(self, identity: str) -> bool:
        with self._lock:
            return identity in self._jobs

    def start(self, request: dict) -> None:
        with self._lock:
            if self._closed or len(self._jobs) >= 2 or request["id"] in self._jobs:
                raise ValueError("At most two servers can be owned by this client")
            job = ServingJob(request["id"])
            self._jobs[job.id] = job
            job.thread = threading.Thread(target=self._run, args=(job, request), daemon=True)
            job.thread.start()

    def stop(self, identity: str) -> None:
        with self._lock:
            if job := self._jobs.get(identity):
                job.stop.set()

    def _run(self, job: ServingJob, request: dict) -> None:
        process = None
        pending = b""
        failure = False
        terminal = False
        try:
            payload = json.dumps(request).encode() + b"\n"
            if len(payload) > 32_768:
                raise ValueError
            process = subprocess.Popen(
                [sys.executable, "-m", "klaude_core.managed_serving"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={
                    **{
                        k: v
                        for k, v in os.environ.items()
                        if k in {"HOME", "PATH", "LANG", "LC_ALL"}
                    },
                    "KLAUDE_CONFIG_DIR": request["config_dir"],
                    "KLAUDE_DATA_DIR": request["data_dir"],
                },
                start_new_session=True,
            )
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(payload)
            process.stdin.flush()  # Keep the pipe open as the helper's owner lease.
            stop_at = None
            while True:
                if job.stop.is_set() and stop_at is None:
                    process.stdin.close()
                    stop_at = time.monotonic()
                if stop_at is not None and time.monotonic() - stop_at > HELPER_STOP_SECONDS:
                    break
                if select.select([process.stdout], [], [], 0.1)[0]:
                    chunk = os.read(process.stdout.fileno(), 8192)
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        if len(line) > 16_384:
                            raise ValueError
                        event = json.loads(line)
                        if not isinstance(event, dict) or event.get("id") != job.id:
                            raise ValueError
                        failure |= event.get("state") == "failed"
                        terminal |= event.get("state") in {"failed", "stopped"}
                        self.emit("serving_event", (job.id, event))
                    if len(pending) > 16_384:
                        raise ValueError
                    if not chunk:
                        break
                if process.poll() is not None:
                    # stdout is still drained before closing/reaping the group.
                    if not select.select([process.stdout], [], [], 0)[0]:
                        break
            # EOF can precede waitpid's exit notification. Reap before classifying
            # an exit, and distinguish acknowledged cleanup from a broken lease.
            try:
                code = process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                code = None
            if not terminal and not job.stop.is_set() and code != 0:
                failure = True
                self.emit(
                    "serving_event",
                    (
                        job.id,
                        {
                            "id": job.id,
                            "state": "failed",
                            "message": "Server helper exited unexpectedly; reload servers",
                        },
                    ),
                )
        except Exception:
            failure = True
            self.emit(
                "serving_event",
                (
                    job.id,
                    {
                        "id": job.id,
                        "state": "failed",
                        "message": "Server helper failed; reload managed servers and inspect Logs",
                    },
                ),
            )
        finally:
            if process is not None:
                stop_group(process)
                for pipe in (process.stdin, process.stdout):
                    if pipe and not pipe.closed:
                        pipe.close()
            try:
                record = records(Path(request["data_dir"])).get(job.id, {})
                if (
                    not request["spec"].get("ssh_server")
                    and request["spec"].get("adopt_pid")
                    and record.get("adopted")
                ):
                    stop_adopted(request["evidence"]["adopt_identity"])
                reconcile(request)
            except (OSError, ValueError, KeyError):
                self.emit(
                    "serving_event",
                    (
                        job.id,
                        {
                            "id": job.id,
                            "state": "warning",
                            "message": "Endpoint cleanup unconfirmed; reload Models",
                        },
                    ),
                )
            with self._lock:
                self._jobs.pop(job.id, None)
            self.emit("serving_stopped", (job.id, failure))

    def close(self, *, wait: bool = False) -> None:
        with self._lock:
            self._closed = True
            jobs = list(self._jobs.values())
            for job in jobs:
                job.stop.set()
        if wait:
            deadline = time.monotonic() + CLOSE_SECONDS
            for job in jobs:
                if job.thread:
                    job.thread.join(max(0, deadline - time.monotonic()))

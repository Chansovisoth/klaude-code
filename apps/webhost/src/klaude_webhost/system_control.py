"""Reviewed lifecycle actions for one profile and this Klaude installation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
from klaude_core import config as config_module
from klaude_core.settings_store import atomic_write_private, update_settings


def birth(pid, proc=Path("/proc")):
    return (proc / str(pid) / "stat").read_text().rsplit(") ", 1)[1].split()[19]


def _root(value, cwd, home):
    value = value.replace("~/", home + "/", 1) if value.startswith("~/") else value
    path = Path(value)
    return (path if path.is_absolute() else cwd / path).resolve()


def process_identity(cfg, pid, *, proc=Path("/proc")):
    """No name-based kills: require exact entry point, interpreter and profile roots."""
    directory = proc / str(pid)
    try:
        if directory.stat().st_uid != os.getuid():
            return None
        started = birth(pid, proc)
        raw = (directory / "cmdline").read_bytes()
        if len(raw) > 65536:
            return None
        args = [os.fsdecode(item) for item in raw.split(b"\0") if item]
        known_modules = {"klaude_cli.main": "terminal", "klaude_webhost.main": "webui",
                         "klaude_application.background_worker": "worker"}
        if not args or not (
            Path(args[0]).name == "klaude" or len(args) > 1 and Path(args[1]).name == "klaude"
            or len(args) > 2 and args[1] == "-m" and args[2] in known_modules
        ):
            return None
        cwd = (directory / "cwd").resolve(strict=True)
        interpreter = Path(sys.executable).parent.resolve()
        if not args:
            return None
        executable = Path(args[0]) if Path(args[0]).is_absolute() else cwd / args[0]
        if (executable.parent.resolve() != interpreter
                or (directory / "exe").resolve(strict=True) != Path(sys.executable).resolve()):
            return None
        kind = ""
        if (_root(args[0], cwd, str(Path.home())) == interpreter / "klaude" or
                len(args) > 1 and _root(args[1], cwd, str(Path.home())) == interpreter / "klaude"):
            kind = "terminal"
        elif len(args) > 2 and args[1] == "-m":
            kind = known_modules.get(args[2], "")
        if not kind:
            return None
        # Read only the profile variables; never return or log process secrets.
        raw_env = (directory / "environ").read_bytes()
        if len(raw_env) > 1_000_000:
            raise ValueError("Klaude process environment exceeds its bound")
        env = {}
        for item in raw_env.split(b"\0"):
            key, _, value = item.partition(b"=")
            if key in {b"KLAUDE_CONFIG_DIR", b"KLAUDE_DATA_DIR", b"KLAUDE_HOME", b"HOME"}:
                env[key.decode()] = os.fsdecode(value)
        home = env.get("HOME", str(Path.home()))
        source = config_module.SOURCE_ROOT
        config_default = str(source / "config") if source else home + "/.config/klaude"
        data_default = str(source / ".klaude/data") if source else home + "/.local/share/klaude"
        root = env.get("KLAUDE_HOME", "")
        config = env.get("KLAUDE_CONFIG_DIR") or (root + "/config" if root else config_default)
        data = env.get("KLAUDE_DATA_DIR") or (root + "/data" if root else data_default)
        if (_root(config, cwd, home) != cfg.config_dir.resolve()
                or _root(data, cwd, home) != cfg.data_dir.resolve()):
            return None
        if birth(pid, proc) != started:
            return None
        return {"pid": pid, "birth": started, "kind": kind}
    except (FileNotFoundError, ProcessLookupError):
        return None


def processes(cfg):
    result = []
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        item = process_identity(cfg, int(path.name))
        if item:
            result.append(item)
            if len(result) > 64:
                raise ValueError("Too many Klaude processes to review safely")
    return sorted(result, key=lambda item: item["pid"])


def stop_processes(cfg, targets, *, grace=10):
    """Use birth-checked Linux pidfds so PID reuse cannot target another process."""
    handles = []
    try:
        for target in targets:
            if target["pid"] == os.getpid():
                continue
            try:
                handle = os.pidfd_open(target["pid"])
            except ProcessLookupError:
                continue
            if process_identity(cfg, target["pid"]) != target:
                os.close(handle)
                continue
            handles.append(handle)
            signal.pidfd_send_signal(handle, signal.SIGTERM)
        deadline = time.monotonic() + grace
        poller = select.poll()
        for handle in handles:
            poller.register(handle, select.POLLIN)
        remaining = set(handles)
        while remaining and time.monotonic() < deadline:
            remaining.difference_update(handle for handle, _ in poller.poll(100))
        for handle in remaining:
            signal.pidfd_send_signal(handle, signal.SIGKILL)
    finally:
        for handle in handles:
            os.close(handle)


class SystemControl:
    def __init__(self, host, cfg, workspace, *, managed):
        self.host, self.cfg, self.workspace, self.managed = host, cfg, workspace, managed
        self.instance = uuid.uuid4().hex
        self.reviews = {}
        self.action = ""
        self.accepted = None
        self.directory = cfg.data_dir / "webhost"

    def busy(self):
        if any(self.host._application_busy(app) for app in self.host._applications):
            return True
        if self.host.library is not None:
            with self.host.library._lock:
                if self.host.library._active:
                    return True
        now = time.time()
        for path, query in (
            (self.cfg.sessions_db, "SELECT 1 FROM session_live WHERE state='running' "
                                  "AND owner_lease_until>? LIMIT 1"),
            (self.cfg.data_dir / "operations.db", "SELECT 1 FROM operations WHERE state IN "
             "('accepted','running','cancelling') AND lease_until>? LIMIT 1"),
        ):
            if path.exists():
                with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
                    table = "session_live" if path == self.cfg.sessions_db else "operations"
                    exists = db.execute(
                        "SELECT 1 FROM sqlite_master WHERE name=?", (table,),
                    ).fetchone()
                    if exists and db.execute(query, (now,)).fetchone():
                        return True
                    if table == "session_live" and db.execute(
                        "SELECT 1 FROM sqlite_master WHERE name='application_queue'",
                    ).fetchone() and db.execute(
                        "SELECT 1 FROM application_queue WHERE state IN "
                        "('queued','paused','needs_review','starting') LIMIT 1",
                    ).fetchone():
                        return True
        return False

    def state(self):
        peers = processes(self.cfg)
        if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            raise ValueError("System actions require Linux process identity support")
        busy = self.busy() or any(item["kind"] == "worker" for item in peers)
        identity = {"instance": self.instance, "session": self.host.application.session_id,
                    "workspace": str(self.workspace), "peers": peers,
                    "lan": self.host.lan_ip, "port": self.host.http.server_port}
        revision = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        return {"available": True, "instance": self.instance, "revision": revision,
                "terminal_count": sum(item["kind"] == "terminal" for item in peers),
                "busy": busy, "action": self.action}, peers

    def review(self, owner, action):
        if not isinstance(action, str) or action not in {"restart", "shutdown"} or self.action:
            raise ValueError("Choose an available System action")
        state, peers = self.state()
        if state["busy"]:
            raise ValueError("Wait for Klaude turns, queues and background work to finish")
        identity = uuid.uuid4().hex
        self.reviews = {key: item for key, item in self.reviews.items()
                        if item["expires_at"] > time.time()}
        if len(self.reviews) >= 16:
            raise ValueError("Close an existing System review before retrying")
        self.reviews[identity] = {"owner": owner, "action": action, "revision": state["revision"],
                                  "peers": peers, "expires_at": time.time() + 120}
        summary = ("Restart the Web UI. The hosted conversation, workspace and LAN settings "
                   "are preserved. All browsers disconnect and must sign in again. "
                   "Unsaved browser drafts may be lost. Terminal sessions keep running."
                   if action == "restart" else
                   f"Shut down Klaude, including {state['terminal_count']} running terminal "
                   "session(s) for this profile and the Web UI. Unsaved input is lost. "
                   "Start Klaude from the terminal to use it again.")
        return {"review_id": identity, "action": action, "summary": summary,
                "instance": self.instance}

    def apply(self, owner, identity, request_id):
        if not isinstance(identity, str):
            raise ValueError("Choose an exact System review")
        if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id):
            raise ValueError("Choose an exact System request")
        if self.accepted:
            if (self.accepted["request_id"] == request_id and self.accepted["owner"] == owner
                    and self.accepted["review_id"] == identity):
                return self.accepted["public"]
            raise ValueError("A System action is already in progress")
        review = self.reviews.get(identity)
        if not review or review["owner"] != owner or review["expires_at"] <= time.time():
            raise ValueError("System review expired; review the action again")
        with self.host._lock:
            state, peers = self.state()
            if state["busy"] or state["revision"] != review["revision"]:
                raise ValueError("Klaude runtime changed; review the System action again")
            value = {"request_id": request_id, "action": review["action"],
                     "instance": self.instance, "state": "accepted"}
            self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
            atomic_write_private(self.directory / "lifecycle.json", json.dumps(value))
            if review["action"] == "shutdown":
                update_settings(self.cfg.config_dir / "webui.json", {("enabled",): False})
            self.accepted = {"owner": owner, "request_id": request_id, "review_id": identity,
                             "public": value,
                             "targets": peers, "session": self.host.application.session_id,
                             "lan": self.host.lan_ip, "port": self.host.http.server_port}
            self.action = review["action"]
            self.host.begin_shutdown()
            return value

    def finish(self):
        """Called by the launcher only after all old listeners/workers have drained."""
        if not self.accepted:
            return
        value = {**self.accepted["public"], "state": "completed"}
        try:
            if self.action == "shutdown":
                stop_processes(self.cfg, self.accepted["targets"])
            else:
                args = [sys.executable, "-m", "klaude_webhost.main", "--workspace",
                        str(self.workspace), "--port", str(self.accepted["port"]),
                        "--session-id", self.accepted["session"]]
                if self.managed:
                    args.append("--managed")
                    if self.accepted["lan"]:
                        args += ["--lan-ip", self.accepted["lan"]]
                child = subprocess.Popen(
                    args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, cwd=self.workspace,
                    start_new_session=True, close_fds=True,
                )
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if child.poll() is not None:
                        raise RuntimeError("Restarted Web UI could not start")
                    try:
                        with httpx.Client(trust_env=False, timeout=1) as client:
                            response = client.get(self.host.origin + "/api/v1/system/health")
                        data = response.json()
                        if response.status_code == 200 and data.get("instance") != self.instance:
                            break
                    except (httpx.HTTPError, ValueError):
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError("Restarted Web UI did not become ready")
        except (OSError, ValueError, RuntimeError):
            value["state"] = "failed"
            raise
        finally:
            atomic_write_private(self.directory / "lifecycle.json", json.dumps(value))

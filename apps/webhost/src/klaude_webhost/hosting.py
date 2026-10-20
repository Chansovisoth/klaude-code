"""Owner-only lifecycle for the optional local browser host."""

from __future__ import annotations

import fcntl
import hashlib
import http.client
import json
import os
import socket
import ssl
import stat
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

from klaude_core.settings_store import read_settings, update_settings

from .accounts import AccountStore
from .lan import lan_ipv4_addresses, private_lan_ip

if TYPE_CHECKING:
    from .host import LocalWebHost

WEBUI_PORT = 50_000
CONTROL_VERSION = 1


def _process_start_ticks(pid: int) -> str:
    """Linux process birth identity; PID reuse alone cannot identify an owner."""
    raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    fields = raw.rsplit(") ", 1)[1].split()
    ticks = fields[19]
    if not ticks.isdecimal():
        raise ValueError("Invalid Web UI process identity")
    return ticks


@dataclass(frozen=True)
class HostingStatus:
    enabled: bool
    running: bool
    origin: str = ""
    workspace: str = ""
    lan_enabled: bool = False
    lan_ip: str = ""
    lan_origin: str = ""
    lan_fingerprint: str = ""
    lan_remote_peer: str = ""
    lan_remote_seen_at: float = 0.0
    stopping: bool = False
    runtime_instance: str = ""
    session_id: str = ""
    active_turns: int = 0
    restart_required: bool = False
    auth_mode: str = "bootstrap"

    def recent_lan_peer(self) -> bool:
        age = time.time() - self.lan_remote_seen_at
        return bool(self.lan_remote_peer and 0 <= age <= 300)


@dataclass(frozen=True)
class ExposureReport:
    local: str
    lan: str
    device: str
    remote_peer: str = ""


class WebHostController:
    """Persist desired state and address only this profile's live control socket."""

    def __init__(self, config_dir: Path, data_dir: Path) -> None:
        self.settings = config_dir / "webui.json"
        self.directory = data_dir / "webhost"
        self.socket_path = self.directory / "control.sock"
        self._legacy_owner: tuple[int, str] | None = None

    def desired(self) -> bool:
        value = read_settings(self.settings).get("enabled", False)
        if type(value) is not bool:
            raise ValueError("Invalid Web UI setting")
        return value

    def lan_preference(self) -> tuple[bool, str]:
        settings = read_settings(self.settings)
        enabled = settings.get("lan_enabled", False)
        ip = settings.get("lan_ip", "")
        if type(enabled) is not bool or not isinstance(ip, str):
            raise ValueError("Invalid Web UI LAN setting")
        if ip:
            private_lan_ip(ip)
        return enabled, ip

    def _request(self, command: str, **fields: object) -> dict[str, object] | None:
        if command not in {"status", "stop"}:
            state = self._request("status")
            if state and state.get("restart_required"):
                raise RuntimeError("Web UI host needs an update; disable and enable Web UI")
        try:
            info = self.directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() \
                    or info.st_mode & 0o077:
                raise PermissionError("Unsafe Web UI control directory")
            info = self.socket_path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise PermissionError("Unsafe Web UI control socket")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(15 if command == "lan" else 2)
                client.connect(str(self.socket_path))
                pid, uid, _gid = struct.unpack(
                    "3i", client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                )
                if uid != os.getuid() or pid <= 0:
                    raise PermissionError("Web UI control peer is not this account")
                if command == "stop" and self._legacy_owner is not None:
                    if self._legacy_owner != (pid, _process_start_ticks(pid)):
                        raise RuntimeError("Web UI control owner changed; refresh settings")
                    self._verify_legacy_owner(pid)
                encoded = (json.dumps({
                    "version": CONTROL_VERSION, "command": command, **fields,
                }) + "\n").encode()
                if len(encoded) > 131_072:
                    raise ValueError("Web UI control request too large")
                client.sendall(encoded)
                parts = []
                size = 0
                while chunk := client.recv(65536):
                    size += len(chunk)
                    if size > 1_048_576:
                        raise ValueError("Web UI control response too large")
                    parts.append(chunk)
                data = b"".join(parts)
            response = json.loads(data)
            if (isinstance(response, dict) and "version" not in response
                    and command in {"status", "stop"}):
                self._verify_legacy_owner(pid)
                if command == "status" and type(response.get("running")) is bool:
                    self._legacy_owner = (pid, _process_start_ticks(pid))
                    return {**response, "restart_required": True}
                if (command == "stop" and self._legacy_owner is not None
                        and response.get("stopping") is True):
                    return response
            if (not isinstance(response, dict)
                    or type(response.get("version")) is not int
                    or response["version"] != CONTROL_VERSION):
                raise RuntimeError("Web UI control protocol version mismatch")
            profile = hashlib.sha256(str(self.directory.resolve()).encode()).hexdigest()
            if (response.get("pid") != pid
                    or response.get("start_ticks") != _process_start_ticks(pid)
                    or response.get("profile") != profile):
                raise RuntimeError("Web UI control owner identity mismatch")
            return response
        except (FileNotFoundError, ConnectionRefusedError, ConnectionResetError,
                ConnectionAbortedError, BrokenPipeError, TimeoutError):
            return None

    def _verify_legacy_owner(self, pid: int) -> None:
        """Permit only status/shutdown for the pre-versioned managed host."""
        process = Path(f"/proc/{pid}")
        args = (process / "cmdline").read_bytes().split(b"\0")
        if (len(args) < 4 or args[1:3] != [b"-m", b"klaude_webhost.main"]
                or b"--managed" not in args):
            raise RuntimeError("Web UI legacy owner identity mismatch")
        lock = (self.directory / "host.lock").lstat()
        if (not stat.S_ISREG(lock.st_mode) or lock.st_uid != os.getuid()
                or lock.st_nlink != 1 or lock.st_mode & 0o077):
            raise PermissionError("Unsafe Web UI host lock")
        for descriptor in (process / "fd").iterdir():
            try:
                info = descriptor.stat()
                if (info.st_dev, info.st_ino) != (lock.st_dev, lock.st_ino):
                    continue
                details = (process / "fdinfo" / descriptor.name).read_text()
                if any(line.startswith("lock:") and
                       f"FLOCK  ADVISORY  WRITE {pid} " in line
                       for line in details.splitlines()):
                    return
            except FileNotFoundError:
                continue
        raise RuntimeError("Web UI legacy owner does not hold this profile's lock")

    def status(self) -> HostingStatus:
        response = self._request("status")
        lan_enabled, saved_ip = self.lan_preference()
        seen_at = response.get("lan_remote_seen_at", 0) if response else 0
        return HostingStatus(
            self.desired(), bool(response and response.get("running") is True),
            str(response.get("origin", "")) if response else "",
            str(response.get("workspace", "")) if response else "",
            lan_enabled, saved_ip,
            str(response.get("lan_origin", "")) if response else "",
            str(response.get("lan_fingerprint", "")) if response else "",
            str(response.get("lan_remote_peer", "")) if response else "",
            float(seen_at) if isinstance(seen_at, (int, float)) else 0.0,
            bool(response and response.get("stopping") is True),
            (f"{response['pid']}:{response['start_ticks']}"
             if response and response.get("pid") and response.get("start_ticks") else ""),
            str(response.get("session_id", "")) if response else "",
            (cast(int, response["active_turns"])
             if response and type(response.get("active_turns")) is int else 0),
            bool(response and response.get("restart_required") is True),
            str(response.get("auth_mode", "bootstrap")) if response else
            "password" if AccountStore(self.settings.parent).path.exists() else "bootstrap",
        )

    @staticmethod
    def _probe(origin: str, *, fingerprint: str = "") -> str:
        if not origin:
            return "not listening"
        parsed = urlsplit(origin)
        if parsed.port != WEBUI_PORT:
            return "wrong port"
        if parsed.hostname is None:
            return "not reachable locally"
        connection: http.client.HTTPConnection | None = None
        try:
            if parsed.scheme == "https":
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                connection = http.client.HTTPSConnection(
                    parsed.hostname, parsed.port, context=context, timeout=3,
                )
                connection.connect()
                certificate = connection.sock.getpeercert(binary_form=True) \
                    if connection.sock else None
                if not certificate or hashlib.sha256(certificate).hexdigest() != fingerprint:
                    connection.close()
                    return "TLS identity mismatch"
            else:
                connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
            connection.request("GET", "/", headers={"Host": parsed.netloc})
            response = connection.getresponse()
            return "reachable" if response.status == 200 else f"HTTP {response.status}"
        except (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException):
            return "not reachable locally"
        finally:
            if connection is not None:
                connection.close()

    def diagnose(self) -> ExposureReport:
        state = self.status()
        local = self._probe(state.origin) if state.running else "not listening"
        lan = self._probe(state.lan_origin, fingerprint=state.lan_fingerprint) \
            if state.running else "not listening"
        device = (
            "confirmed by a recent LAN request" if state.recent_lan_peer()
            else "previously reached; recheck from another device"
            if state.lan_remote_peer and lan == "reachable"
            else "unverified from another device" if lan == "reachable"
            else "not exposed" if lan == "not listening" else "unknown"
        )
        return ExposureReport(local, lan, device, state.lan_remote_peer)

    def bootstrap_url(self, *, lan: bool = False) -> str:
        response = self._request("bootstrap", lan=lan)
        url = response.get("url") if response else None
        if not isinstance(url, str):
            raise RuntimeError("Web UI host is unavailable")
        parsed = urlsplit(url)
        expected_ip = self.lan_preference()[1] if lan else "127.0.0.1"
        if (parsed.scheme != "http"
                or parsed.hostname != expected_ip or parsed.port is None
                or (not parsed.fragment and (response or {}).get("auth_mode") != "password")
                or parsed.username or parsed.password):
            raise RuntimeError("Web UI host returned an invalid browser link")
        return url

    def initial_admin_password(self) -> str | None:
        """Local terminal owner access only; never sent through the browser API."""
        return AccountStore(self.settings.parent).initial_password()

    def account_configured(self) -> bool:
        """Read local account availability without contacting the running host."""
        try:
            AccountStore(self.settings.parent).revision()
        except FileNotFoundError:
            return False
        return True

    def set_lan(self, enabled: bool, *, ip: str = "", workspace: Path | None = None) -> None:
        current = self._request("status")
        if current is not None and urlsplit(str(current.get("origin", ""))).port != WEBUI_PORT:
            raise RuntimeError("Web UI must be restarted to use port 50000")
        if current is not None and str(current.get("lan_origin", "")).startswith("https://"):
            raise RuntimeError("Web UI must be restarted to use HTTP for LAN")
        if (current is not None and workspace is not None
                and current.get("workspace") != str(workspace.resolve())):
            raise RuntimeError("Web UI is serving another workspace; disable it first")
        if enabled:
            candidates = lan_ipv4_addresses()
            selected = ip or self.lan_preference()[1] or (candidates[0] if candidates else "")
            if not selected or selected not in candidates:
                raise ValueError("No active private LAN IPv4 address is available")
            private_lan_ip(selected)
            update_settings(self.settings, {("lan_enabled",): True, ("lan_ip",): selected})
            response = self._request("lan", ip=selected)
            if response is not None and response.get("lan_origin") is None:
                raise RuntimeError(str(response.get("error", "LAN listener failed")))
        else:
            update_settings(self.settings, {("lan_enabled",): False})
            response = self._request("lan", ip="")
            if response is not None and response.get("lan_origin") is None:
                raise RuntimeError(str(response.get("error", "LAN listener failed")))

    def enable(self, workspace: Path) -> str:
        workspace = workspace.resolve()
        current = self._request("status")
        if current and current.get("restart_required"):
            raise RuntimeError("Web UI host needs an update; disable and enable Web UI")
        if current is not None and current.get("running") is not True:
            raise RuntimeError("Web UI is still draining; retry after it stops")
        if current is not None:
            if current.get("workspace") != str(workspace):
                raise RuntimeError("Web UI is serving another workspace; disable it first")
            if urlsplit(str(current.get("origin", ""))).port != WEBUI_PORT:
                raise RuntimeError(
                    "Web UI uses an old port; disable and enable it to move to 50000"
                )
            if str(current.get("lan_origin", "")).startswith("https://"):
                raise RuntimeError("Web UI uses LAN HTTPS; disable and enable it for HTTP")
            update_settings(self.settings, {("enabled",): True})
            lan_enabled, lan_ip = self.lan_preference()
            if (lan_enabled and lan_ip in lan_ipv4_addresses()
                    and current.get("lan_ip") != lan_ip):
                self.set_lan(True, ip=lan_ip)
            return self.bootstrap_url()
        update_settings(self.settings, {("enabled",): True})
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() \
                or info.st_mode & 0o077:
            raise PermissionError("Unsafe Web UI control directory")
        lan_enabled, lan_ip = self.lan_preference()
        launch_lan = lan_enabled and lan_ip in lan_ipv4_addresses()
        child = subprocess.Popen(
            [sys.executable, "-m", "klaude_webhost.main", "--managed",
             "--workspace", str(workspace), "--port", str(WEBUI_PORT),
             *(["--lan-ip", lan_ip] if launch_lan else [])],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True,
            cwd=workspace,
        )
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            response = self._request("status")
            if response is not None:
                if response.get("workspace") != str(workspace):
                    raise RuntimeError("Web UI is serving another workspace")
                return self.bootstrap_url()
            if child.poll() is not None:
                raise RuntimeError("Web UI host failed to start")
            time.sleep(0.1)
        raise RuntimeError("Web UI host startup timed out")

    def ensure_started(self, workspace: Path) -> str | None:
        if not self.desired():
            return None
        return self.enable(workspace)

    def disable(self) -> None:
        self._request("status")
        update_settings(self.settings, {("enabled",): False})
        response = self._request("stop")
        if response is None:
            return
        if response.get("stopping") is not True:
            raise RuntimeError("Web UI host did not acknowledge shutdown")

    def runtime_snapshot(self) -> dict[str, object]:
        response = self._request("runtime_snapshot")
        snapshot = response.get("snapshot") if response else None
        if not isinstance(snapshot, dict):
            raise RuntimeError("Hosted chat runtime is unavailable")
        return snapshot

    def runtime_events(self, cursor: str) -> list[dict[str, object]]:
        response = self._request("runtime_events", cursor=cursor)
        events = response.get("events") if response else None
        if not isinstance(events, list) or any(not isinstance(item, dict) for item in events):
            raise RuntimeError("Hosted chat events are unavailable")
        return events

    def submit_hosted_turn(self, request_id: str, text: str) -> dict[str, object]:
        response = self._request("runtime_submit", request_id=request_id, text=text)
        accepted = response.get("accepted") if response else None
        if not isinstance(accepted, dict):
            raise RuntimeError(str(response.get("error", "Hosted chat is unavailable"))
                               if response else "Hosted chat is unavailable")
        return accepted

    def decide_hosted_approval(self, interaction_id: str, decision: str) -> bool:
        response = self._request(
            "runtime_decide", interaction_id=interaction_id, decision=decision,
        )
        if response is None or type(response.get("accepted")) is not bool:
            raise RuntimeError("Hosted approval decision is unavailable")
        return bool(response["accepted"])

    def cancel_hosted_turn(self, turn_id: str) -> bool:
        response = self._request("runtime_cancel", turn_id=turn_id)
        if response is None or type(response.get("accepted")) is not bool:
            raise RuntimeError("Hosted turn cancellation is unavailable")
        return bool(response["accepted"])


class ManagedControl:
    """Private Unix socket; the live host handles its own stop request."""

    def __init__(self, directory: Path, host: LocalWebHost, workspace: Path) -> None:
        self.pid = os.getpid()
        self.start_ticks = _process_start_ticks(self.pid)
        self.profile = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() \
                or info.st_mode & 0o077:
            raise PermissionError("Unsafe Web UI control directory")
        self._lock_fd = os.open(directory / "host.lock",
                                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        info = os.fstat(self._lock_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            os.close(self._lock_fd)
            raise PermissionError("Unsafe Web UI host lock")
        os.fchmod(self._lock_fd, 0o600)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self._lock_fd)
            raise
        self.path = directory / "control.sock"
        self.host = host
        self.workspace = str(workspace.resolve())
        self.closed = threading.Event()
        try:
            if self.path.exists() or self.path.is_socket():
                info = self.path.lstat()
                if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                    raise PermissionError("Unsafe Web UI control socket")
                self.path.unlink()
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.listener.bind(str(self.path))
            os.chmod(self.path, 0o600)
            self.listener.listen(4)
            self.listener.settimeout(0.2)
        except BaseException:
            if hasattr(self, "listener"):
                self.listener.close()
            os.close(self._lock_fd)
            raise
        self.thread = threading.Thread(target=self._serve, name="klaude-webui-control", daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while not self.closed.is_set():
            try:
                client, _ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with client:
                try:
                    client.settimeout(2)
                    pid, uid, _gid = struct.unpack(
                        "3i", client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                    )
                    if uid != os.getuid() or pid <= 0:
                        continue
                    parts: list[bytes] = []
                    size = 0
                    while not parts or b"\n" not in parts[-1]:
                        chunk = client.recv(65536)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > 131_072:
                            raise ValueError("Oversized control request")
                        parts.append(chunk)
                    data = b"".join(parts).split(b"\n", 1)[0]
                    request = json.loads(data)
                    if (not isinstance(request, dict)
                            or type(request.get("version")) is not int
                            or request["version"] != CONTROL_VERSION):
                        client.sendall(json.dumps({
                            "version": CONTROL_VERSION, "error": "Unsupported control protocol",
                        }).encode())
                        continue
                    command = request.get("command")
                    fields_by_command = {
                        "status": set(), "bootstrap": {"lan"}, "lan": {"ip"},
                        "stop": set(), "runtime_snapshot": set(),
                        "runtime_events": {"cursor"},
                        "runtime_submit": {"request_id", "text"},
                        "runtime_decide": {"interaction_id", "decision"},
                        "runtime_cancel": {"turn_id"},
                    }
                    allowed = fields_by_command.get(command) if isinstance(command, str) else None
                    if allowed is None or set(request) != {"version", "command"} | allowed:
                        client.sendall(json.dumps({
                            "version": CONTROL_VERSION, "pid": self.pid,
                            "start_ticks": self.start_ticks, "profile": self.profile,
                            "error": "Invalid control command fields",
                        }).encode())
                        continue
                    if command == "status":
                        response = {"running": not self.host._stopping,
                                    "stopping": self.host._stopping,
                                    "origin": self.host.origin,
                                    "auth_mode": "password" if self.host.accounts else "bootstrap",
                                    "workspace": self.workspace,
                                    "session_id": self.host.application.session_id,
                                    "active_turns": self.host.application.active_turn_count(),
                                    "lan_ip": self.host.lan_ip,
                                    "lan_origin": self.host.lan_origin,
                                    "lan_fingerprint": self.host.lan_fingerprint,
                                    "lan_remote_peer": self.host.lan_remote_peer,
                                    "lan_remote_seen_at": self.host.lan_remote_seen_at}
                    elif command == "bootstrap":
                        try:
                            response = {"url": self.host.new_bootstrap_url(
                                lan=request.get("lan") is True,
                            ), "auth_mode": "password" if self.host.accounts else "bootstrap"}
                        except RuntimeError:
                            response = {"error": "Web UI is stopping"}
                    elif command == "lan":
                        ip = request.get("ip")
                        if not isinstance(ip, str):
                            response = {"error": "Invalid LAN IP"}
                        else:
                            try:
                                if ip:
                                    if self.host.lan_ip and self.host.lan_ip != ip:
                                        self.host.stop_lan()
                                    self.host.start_lan(ip, self.path.parent)
                                else:
                                    self.host.stop_lan()
                                response = {"lan_origin": self.host.lan_origin,
                                            "lan_fingerprint": self.host.lan_fingerprint}
                            except (OSError, ValueError, RuntimeError) as exc:
                                response = {"error": str(exc)}
                    elif command == "stop":
                        self.host.begin_shutdown()
                        response = {"stopping": True}
                    elif command == "runtime_snapshot":
                        try:
                            response = {"snapshot": self.host.public_snapshot()}
                        except (OSError, ValueError, RuntimeError):
                            response = {"error": "Hosted session unavailable"}
                    elif command == "runtime_events":
                        cursor = request.get("cursor")
                        if not isinstance(cursor, str) or len(cursor) > 128:
                            response = {"error": "Invalid event cursor"}
                        else:
                            try:
                                response = {"events": self.host.application.replay(
                                    cursor, limit=8,
                                )}
                            except (OSError, ValueError, RuntimeError):
                                response = {"error": "Hosted events unavailable"}
                    elif command == "runtime_submit":
                        identity, text = request.get("request_id"), request.get("text")
                        if (not isinstance(identity, str)
                                or not isinstance(text, str) or len(text) > 65_536):
                            response = {"error": "Hosted turn unavailable"}
                        else:
                            try:
                                with self.host._lock:
                                    if self.host._stopping:
                                        raise RuntimeError("Host stopping")
                                    handle = self.host.application.submit(
                                        text, request_id=identity,
                                    )
                                response = {"accepted": {
                                    "request_id": handle.request_id, "turn_id": handle.turn_id,
                                    "session_id": handle.session_id, "state": handle.state,
                                }}
                            except (OSError, ValueError, RuntimeError):
                                response = {"error": "Hosted turn unavailable"}
                    elif command == "runtime_decide":
                        from .host import READ_ONLY_TOOLS

                        identity, decision = request.get("interaction_id"), request.get("decision")
                        if (self.host._stopping or not isinstance(identity, str)
                                or not isinstance(decision, str)
                                or decision not in {"allow_once", "deny"}):
                            response = {"accepted": False}
                        else:
                            with self.host._lock:
                                application = self.host.application
                                current = application.control()
                                review = application.review_interaction(
                                    identity, controller_id=current[0] if current else None,
                                )
                                if (review is not None and review["tool"] in READ_ONLY_TOOLS
                                        and current is not None
                                        and current[0] != application.controller_id):
                                    application.take_control(
                                        application.controller_id, expected_epoch=current[1],
                                    )
                                response = {"accepted": bool(
                                    not self.host._stopping
                                    and review is not None
                                    and review["tool"] in READ_ONLY_TOOLS
                                    and self.host.application.decide(identity, decision)
                                )}
                    elif command == "runtime_cancel":
                        turn_id = request.get("turn_id")
                        with self.host._lock:
                            application = self.host.application
                            current = application.control()
                            if (not isinstance(turn_id, str) or current is None
                                    or turn_id != application.active_turn_id()):
                                response = {"accepted": False}
                            else:
                                epoch = current[1]
                                if current[0] != application.controller_id:
                                    epoch = application.take_control(
                                        application.controller_id, expected_epoch=epoch,
                                    )
                                response = {"accepted": application.cancel_active(
                                    turn_id, controller_id=application.controller_id,
                                    control_epoch=epoch,
                                )}
                    else:
                        response = {"error": "unknown command"}
                    client.sendall(json.dumps({
                        "version": CONTROL_VERSION, "pid": self.pid,
                        "start_ticks": self.start_ticks, "profile": self.profile,
                        **response,
                    }).encode())
                    if command == "stop":
                        threading.Thread(target=self.host.http.shutdown, daemon=True).start()
                except Exception:
                    continue

    def close(self) -> None:
        self.closed.set()
        self.listener.close()
        self.thread.join(timeout=2)
        self.path.unlink(missing_ok=True)
        os.close(self._lock_fd)

"""Private SSH definitions, revisioned writes and bounded OpenSSH diagnostics."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import select
import shlex
import shutil
import stat
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from .managed_serving import clean, fingerprint
from .settings_store import atomic_write_private, read_settings, settings_lock
from .ssh_diagnostics import PROGRAM

TIMEOUT = 15
MAX_OUTPUT = 65_536
MAX_SERVERS = 32


@dataclass(frozen=True)
class SSHServer:
    id: str
    name: str
    host: str
    user: str
    port: int = 22
    identity_file: str = ""
    known_hosts: str = ""
    models_dir: str = "/opt/models"
    use_agent: bool = False

    def validate(self) -> SSHServer:
        if (
            not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", self.id)
            or self.id == "local"
            or not self.name.strip()
            or len(self.name) > 120
            or not self.name.isprintable()
            or type(self.port) is not int
            or not 1 <= self.port <= 65535
            or type(self.use_agent) is not bool
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", self.user)
        ):
            raise ValueError("Enter a valid server ID, name, user and SSH port")
        try:
            host = str(ipaddress.ip_address(self.host))
        except ValueError:
            host = self.host.lower().rstrip(".")
            if (
                len(host) > 253
                or not host
                or all(c in "0123456789." for c in host)
                or any(
                    not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                    for label in host.split(".")
                )
            ):
                raise ValueError(
                    "Enter an IP address or DNS hostname without URL/SSH syntax"
                ) from None
        for path in (self.identity_file, self.known_hosts):
            if path and (
                not Path(path).is_absolute()
                or len(path) > 4096
                or not path.isprintable()
                or "$" in path
            ):
                raise ValueError("Enter absolute local key/known-hosts paths without variables")
        if not self.known_hosts or not self.identity_file and not self.use_agent:
            raise ValueError("Choose verified known hosts and an identity file or SSH agent")
        if (
            not self.models_dir.isprintable()
            or len(self.models_dir) > 512
            or not self.models_dir.startswith("/")
            or ".." in PurePosixPath(self.models_dir).parts
        ):
            raise ValueError("Enter an absolute remote model directory without traversal")
        return replace(self, host=host, name=self.name.strip())


def load(root: Path) -> dict:
    path = root / "model-servers.json"
    if path.exists() and (not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > 262_144):
        raise ValueError("Invalid SSH server configuration file")
    value = read_settings(path)
    if not value:
        return {"version": 1, "default": "local", "default_revision": "0", "servers": {}}
    if (
        value.get("version") != 1
        or not isinstance(value.get("servers"), dict)
        or len(value["servers"]) > MAX_SERVERS
    ):
        raise ValueError("Invalid SSH server configuration")
    for key, record in value["servers"].items():
        server = SSHServer(**record["definition"]).validate()
        if server.id != key or not re.fullmatch(r"[a-f0-9]{32}", record["revision"]):
            raise ValueError("Invalid SSH server revision")
    if value.get("default") not in {"local", *value["servers"]}:
        raise ValueError("Default server no longer exists")
    return value


def change(
    root: Path,
    operation: str,
    *,
    definition: dict | None = None,
    target: str = "",
    revision: str = "",
    default_revision: str = "",
) -> dict:
    path = root / "model-servers.json"
    with settings_lock(path):
        value = load(root)
        records = value["servers"]
        if operation in {"add", "edit"}:
            server = SSHServer(**(definition or {})).validate()
            target = server.id
        current = records.get(target)
        if operation == "add":
            if current or len(records) >= MAX_SERVERS:
                raise ValueError("Server ID already exists or server limit reached; reload")
        elif operation in {"edit", "remove", "default", "trust"}:
            if target != "local" and (not current or current["revision"] != revision):
                raise ValueError("Server changed; reload and review again")
            if operation in {"remove", "default"} and value["default_revision"] != default_revision:
                raise ValueError("Default server changed; reload and review again")
        else:
            raise ValueError("Unknown SSH setting operation")
        if operation == "trust":
            from .ssh_setup import pin

            if target == "local" or not current:
                raise ValueError("Choose a saved SSH server")
            server = SSHServer(**current["definition"]).validate()
            server = replace(server, known_hosts=str(pin(root, server, definition or {})))
            records[target] = {"definition": asdict(server), "revision": uuid.uuid4().hex}
        elif operation in {"add", "edit"}:
            records[target] = {"definition": asdict(server), "revision": uuid.uuid4().hex}
        elif operation == "remove":
            if target == "local":
                raise ValueError("This machine cannot be removed")
            del records[target]
            if value["default"] == target:
                value["default"] = "local"
                value["default_revision"] = uuid.uuid4().hex
        elif operation == "default":
            value["default"] = target
            value["default_revision"] = uuid.uuid4().hex
        payload = json.dumps(value)
        if len(payload.encode()) > 262_144:
            raise ValueError("SSH server configuration size limit reached")
        atomic_write_private(path, payload)
        return value


def references(server: SSHServer, agent: str = "") -> dict:
    result = {}
    for key, raw in (("key", server.identity_file), ("hosts", server.known_hosts)):
        if not raw:
            continue
        path = Path(raw)
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size > 1_000_000
            or key == "key"
            and not server.use_agent
            and info.st_mode & 0o077
        ):
            raise ValueError("Use regular bounded files; private identity files must be owner-only")
        result[key] = fingerprint(path)
        if key == "hosts":
            result[key] += hashlib.sha256(path.read_bytes()).hexdigest()
    if server.use_agent:
        if not agent or not Path(agent).is_absolute():
            raise ValueError("SSH agent unavailable; start your agent or select an identity file")
        info = Path(agent).lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("SSH agent socket is not owned by this account")
        result["agent"] = fingerprint(Path(agent))
    return result


def quote_option(path: str) -> str:
    return '"' + path.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"') + '"'


def decoded(value: Any, operation: str) -> dict:
    if (
        not isinstance(value, dict)
        or value.get("version") != 1
        or value.get("connected") is not True
    ):
        raise ValueError("Invalid SSH diagnostic response")
    result: dict[str, Any] = {"version": 1, "connected": True}
    if operation == "test":
        return result
    for name, maximum in (("models", 100), ("processes", 32), ("tools", 3)):
        items = value.get(name)
        if (
            not isinstance(items, list)
            or len(items) > maximum
            or any(
                not isinstance(item, dict) or not isinstance(item.get("name"), str)
                for item in items
            )
        ):
            raise ValueError("Invalid SSH diagnostic inventory")
    result["models"] = []
    for item in value["models"]:
        if item.get("kind") not in {"GGUF", "Model directory"}:
            raise ValueError("Invalid SSH model type")
        size = item.get("size")
        result["models"].append(
            {
                "name": clean(item["name"], 240),
                "kind": item["kind"],
                "size": size if type(size) is int and 0 <= size <= 2**63 else None,
            }
        )
    result["processes"] = []
    for item in value["processes"]:
        if type(item.get("pid")) is not int or not 1 <= item["pid"] <= 2**31:
            raise ValueError("Invalid SSH process identity")
        result["processes"].append({"name": clean(item["name"], 80), "pid": item["pid"]})
    result["tools"] = [
        {"name": clean(item["name"], 30), "path": clean(item.get("path") or "", 512)}
        for item in value["tools"]
    ]
    for key in ("ram", "disk_free", "cpu_threads"):
        number = value.get(key)
        result[key] = number if type(number) is int and 0 <= number <= 2**63 else None
    result["architecture"] = clean(value.get("architecture", "Unknown"), 80)
    result["directory_status"] = (
        "Available" if value.get("directory_status") == "Available" else "Unavailable"
    )
    result["truncated"] = value.get("truncated") is True
    result["process_status"] = (
        "Available" if value.get("process_status") == "Available" else "Unavailable"
    )
    result["process_truncated"] = value.get("process_truncated") is True
    return result


def arguments(
    server: SSHServer,
    agent: str = "",
    *,
    program: str = PROGRAM,
    forward: tuple[int, int] | None = None,
) -> list[str]:
    ssh = shutil.which("ssh", path="/usr/local/bin:/usr/bin:/bin")
    if not ssh:
        raise ValueError("OpenSSH client unavailable")
    options = [
        "BatchMode=yes",
        "StrictHostKeyChecking=yes",
        "UpdateHostKeys=no",
        "CheckHostIP=no",
        "GlobalKnownHostsFile=/dev/null",
        "ConnectionAttempts=1",
        "ConnectTimeout=3",
        "ServerAliveInterval=2",
        "ServerAliveCountMax=1",
        "PasswordAuthentication=no",
        "KbdInteractiveAuthentication=no",
        "PreferredAuthentications=publickey",
        "HostbasedAuthentication=no",
        "GSSAPIAuthentication=no",
        "ForwardAgent=no",
        "ForwardX11=no",
        "ClearAllForwardings=" + ("no" if forward else "yes"),
        "PermitLocalCommand=no",
        "ProxyCommand=none",
        "ProxyJump=none",
        "ControlMaster=no",
        "LogLevel=ERROR",
        "CertificateFile=none",
        "UserKnownHostsFile=" + quote_option(server.known_hosts),
        "IdentityAgent=" + (quote_option(agent) if server.use_agent else "none"),
        "IdentitiesOnly=" + ("yes" if server.identity_file else "no"),
        "IdentityFile=" + (quote_option(server.identity_file) if server.identity_file else "none"),
    ]
    args = [ssh, "-F", "/dev/null", "-T", "-S", "none", "-p", str(server.port), "-l", server.user]
    for option in options:
        args += ["-o", option]
    if forward:
        if any(type(port) is not int or not 1024 <= port <= 65535 for port in forward):
            raise ValueError("Choose valid unprivileged tunnel and remote ports")
        args += [
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "GatewayPorts=no",
            "-L",
            f"127.0.0.1:{forward[0]}:127.0.0.1:{forward[1]}",
        ]
    return args + ["--", server.host, "exec /usr/bin/python3 -I -c " + shlex.quote(program)]


def environment() -> dict[str, str]:
    values = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C", "SSH_ASKPASS_REQUIRE": "never"}
    if "HOME" in os.environ:
        values["HOME"] = os.environ["HOME"]
    return values


def run(
    server: SSHServer,
    operation: str,
    agent: str = "",
    *,
    program: str = PROGRAM,
    payload: dict | None = None,
    projector: Callable[[Any, str], dict] = decoded,
    timeout: int = 10,
) -> dict:
    server = server.validate()
    before = references(server, agent)
    process = subprocess.Popen(
        arguments(server, agent, program=program),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment(),
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    output, errors = bytearray(), bytearray()
    streams = {process.stdout: output, process.stderr: errors}
    start = time.monotonic()
    try:
        try:
            process.stdin.write(
                (
                    json.dumps(payload or {"operation": operation, "models_dir": server.models_dir})
                    + "\n"
                ).encode()
            )
            process.stdin.close()
        except BrokenPipeError:
            pass
        while streams:
            if time.monotonic() - start >= timeout:
                return {"status": "error", "code": "timeout", "message": "SSH check timed out"}
            for stream in select.select(list(streams), [], [], 0.1)[0]:
                chunk = os.read(stream.fileno(), 8192)
                if not chunk:
                    streams.pop(stream)
                else:
                    streams[stream].extend(chunk)
                    if len(output) + len(errors) > MAX_OUTPUT:
                        raise ValueError("SSH response exceeded its limit")
        process.wait(timeout=0.5)
        if process.returncode:
            reason = bytes(errors).lower()
            code, message = (
                ("host_key", "Host key is unverified or changed; verify known hosts")
                if b"host key verification" in reason or b"identification has changed" in reason
                else ("authentication", "SSH authentication failed; check identity or agent")
                if b"permission denied" in reason or b"load key" in reason
                else ("remote", "Remote Python diagnostic failed or is unavailable")
                if process.returncode != 255
                else ("timeout", "SSH connection timed out")
                if b"timed out" in reason
                else ("network", "SSH connection unavailable; check host, port and network")
            )
            return {"status": "error", "code": code, "message": message}
        try:
            value = projector(json.loads(output), operation)
        except (ValueError, TypeError, KeyError):
            return {
                "status": "error",
                "code": "protocol",
                "message": "Invalid remote diagnostic response",
            }
        if references(server, agent) != before:
            raise ValueError("SSH credential references changed; check again")
        return {
            "status": "ok",
            "message": "SSH connection verified"
            if operation == "test"
            else "Remote diagnostics complete",
            "data": value,
            "checked_at": time.time(),
            "elapsed": round(time.monotonic() - start, 2),
        }
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            if not stream.closed:
                stream.close()


def execute(request: dict[str, Any]) -> dict:
    root = Path(request["config_dir"])
    try:
        value = load(root)
        if request["operation"] == "list":
            return {"status": "ok", "inventory": value}
        if request["operation"] not in {"test", "inspect"}:
            raise ValueError("Unknown SSH diagnostic operation")
        record = value["servers"].get(request["target"])
        if not record or record["revision"] != request["revision"]:
            raise ValueError("SSH server changed; reload before testing")
        result = run(
            SSHServer(**record["definition"]), request["operation"], request.get("agent_socket", "")
        )
        current = load(root)["servers"].get(request["target"])
        if current != record:
            raise ValueError("SSH server changed while checking; reload and retry")
        return result
    except ValueError as exc:
        return {"status": "error", "code": "configuration", "message": clean(str(exc), 240)}
    except (OSError, KeyError, TypeError, subprocess.TimeoutExpired):
        return {
            "status": "error",
            "code": "configuration",
            "message": "SSH check unavailable; verify server definition, key and known-hosts files",
        }

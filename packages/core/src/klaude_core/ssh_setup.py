"""Candidate host discovery, explicit fingerprint pinning and public-key enrollment."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import select
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

from . import ssh_enrollment_program
from .managed_serving import fingerprint
from .ssh_servers import SSHServer, environment, load, references, run

TIMEOUT = 20
MAX_PINS = 64


def key_info(value: str) -> dict:
    key = ssh_enrollment_program.public_key(value)
    blob = base64.b64decode(key.split()[1], validate=True)
    return {
        "public_key": key,
        "fingerprint": "SHA256:"
        + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("="),
    }


def public_file(raw: str) -> dict:
    path = Path(raw)
    if not path.is_absolute() or path.suffix != ".pub":
        raise ValueError("Choose an absolute Ed25519 public .pub file, not a private identity")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4096 or info.st_mode & 0o022:
            raise ValueError("Choose a bounded regular public-key file without unsafe writes")
        value = stream.read(4097).decode("utf8", "strict").strip()
    if len(value.splitlines()) != 1:
        raise ValueError("Choose a file containing one public key")
    fields = value.split()
    result = key_info(" ".join(fields[:2]))
    result["public_revision"] = fingerprint(path) + result["fingerprint"]
    return result


def scan(server: SSHServer) -> list[dict]:
    server = server.validate()
    executable = shutil.which("ssh-keyscan", path="/usr/local/bin:/usr/bin:/bin")
    if not executable:
        raise ValueError("OpenSSH keyscan unavailable")
    process = subprocess.Popen(
        [executable, "-T", "3", "-p", str(server.port), "-t", "ed25519", "--", server.host],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment(),
    )
    assert process.stdout is not None and process.stderr is not None
    output, errors = bytearray(), bytearray()
    streams = {process.stdout: output, process.stderr: errors}
    deadline = time.monotonic() + 8
    try:
        while streams and time.monotonic() < deadline:
            for stream in select.select(list(streams), [], [], 0.1)[0]:
                chunk = os.read(stream.fileno(), 4096)
                if not chunk:
                    streams.pop(stream)
                else:
                    streams[stream].extend(chunk)
                    if len(output) + len(errors) > 32_768:
                        raise ValueError("Host-key scan exceeded its limit")
        if streams:
            raise ValueError("Host-key scan timed out")
        process.wait(timeout=0.5)
        keys = {}
        for line in output.decode("utf8", "strict").splitlines():
            fields = line.split()
            if len(fields) == 3:
                item = key_info(" ".join(fields[1:]))
                keys[item["fingerprint"]] = item
        if not keys or len(keys) > 8:
            raise ValueError("No bounded Ed25519 host key observed; check host, port and network")
        return list(keys.values())
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()


def pin(root: Path, server: SSHServer, receipt: dict) -> Path:
    """Called inside the definition's settings transaction; never overwrite user trust files."""
    item = key_info(receipt["public_key"])
    if (
        item["fingerprint"] != receipt.get("expected_fingerprint")
        or receipt.get("host") != server.host
        or receipt.get("port") != server.port
        or type(receipt.get("observed_at")) not in {int, float}
        or not 0 <= time.time() - receipt["observed_at"] <= 120
    ):
        raise ValueError("Fingerprint mismatch or stale discovery; scan and verify again")
    # A new private pin must not bypass a revocation in the selected trust file,
    # including hashed host selectors. Missing trust files allow first-time setup.
    try:
        fd = os.open(server.known_hosts, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        pass
    else:
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1_000_000:
                raise ValueError("Use a regular bounded known-hosts file")
            existing = stream.read(1_000_001)
        if len(existing) > 1_000_000:
            raise ValueError("Known-hosts file exceeded its limit")
        kind, blob = item["public_key"].split()
        for line in existing.decode("utf8", "strict").splitlines():
            fields = line.split()
            if len(fields) >= 4 and fields[0] == "@revoked" and fields[2:4] == [kind, blob]:
                raise ValueError("Host key is revoked in the selected trust file; inspect it first")
    token = server.host if server.port == 22 else f"[{server.host}]:{server.port}"
    payload = (token + " " + item["public_key"] + "\n").encode()
    folder = root / "model-ssh" / "hosts"
    for directory in (folder.parent, folder):
        directory.mkdir(mode=0o700, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Private host-key storage is unsafe")
    path = folder / (hashlib.sha256(payload).hexdigest() + ".known_hosts")
    if path.exists() or path.is_symlink():
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or stream.read(4097) != payload
            ):
                raise ValueError("Existing private host pin changed; inspect it before retrying")
        return path
    if sum(1 for _ in folder.iterdir()) >= MAX_PINS:
        raise ValueError("Private host-pin limit reached; inspect unused pins before retrying")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def project(value: Any, operation: str) -> dict:
    if (
        not isinstance(value, dict)
        or value.get("version") != 1
        or value.get("connected") is not True
    ):
        raise ValueError("Invalid enrollment response")
    if value.get("error") in {"changed", "files", "unsafe"}:
        return {
            "status": "error",
            "message": "Remote SSH files changed or are unsafe; review again",
        }
    if (
        not isinstance(value.get("target"), str)
        or not value["target"].startswith("/")
        or len(value["target"]) > 4096
        or not value["target"].isprintable()
        or not re.fullmatch(r"[a-f0-9]{64}", str(value.get("revision", "")))
        or type(value.get("present")) is not bool
        or type(value.get("bytes")) is not int
        or not 0 <= value["bytes"] <= ssh_enrollment_program.LIMIT
    ):
        raise ValueError("Invalid enrollment metadata")
    result = {key: value[key] for key in ("target", "revision", "present", "bytes")}
    if operation == "enroll":
        if value.get("effect") not in {"appended", "already_present", "unconfirmed"}:
            raise ValueError("Invalid enrollment outcome")
        result["effect"] = value["effect"]
    return result


def execute(request: dict) -> dict:
    mutation = request.get("operation") == "enroll"
    attempted = False
    try:
        root = Path(request["config_dir"])
        record = load(root)["servers"].get(request["target"])
        if not record or record["revision"] != request["revision"]:
            raise ValueError("SSH server changed; reload and review again")
        server = SSHServer(**record["definition"]).validate()
        if request["operation"] == "scan":
            result = {
                "status": "ok",
                "keys": scan(server),
                "host": server.host,
                "port": server.port,
                "observed_at": time.time(),
            }
        else:
            item = public_file(request["public_file"])
            agent = request.get("agent_socket", "")
            refs = references(server, agent)
            if mutation:
                review = request["review"]
                if (
                    review.get("public_revision") != item["public_revision"]
                    or review.get("references") != refs
                    or review.get("server_revision") != record["revision"]
                ):
                    raise ValueError("Key or authentication changed; review enrollment again")
            elif request["operation"] != "review":
                raise ValueError("Unknown SSH setup operation")
            payload = {
                "operation": request["operation"],
                "public_key": item["public_key"],
                "revision": request.get("review", {}).get("revision", ""),
            }
            attempted = mutation
            response = run(
                server,
                request["operation"],
                agent,
                program=Path(ssh_enrollment_program.__file__).read_text(),
                payload=payload,
                projector=project,
                timeout=15,
            )
            if response["status"] != "ok":
                return {
                    "status": "unknown" if mutation else "error",
                    "message": "Enrollment unconfirmed; review remote keys before retrying"
                    if mutation
                    else response["message"],
                }
            data = response["data"]
            if data.get("status") == "error":
                return data
            result = {
                "status": "ok",
                "review": {
                    **data,
                    **item,
                    "references": refs,
                    "server_revision": record["revision"],
                },
            }
            if mutation:
                effect = data["effect"]
                result.update(
                    status="unknown" if effect == "unconfirmed" else "ok",
                    message="Enrollment unconfirmed; inspect remote keys before retrying"
                    if effect == "unconfirmed"
                    else "Public key already present; policy retained"
                    if effect == "already_present"
                    else "Public key appended; test its identity explicitly",
                )
        if load(root)["servers"].get(request["target"]) != record:
            raise ValueError("SSH definition changed; review again")
        result["server_revision"] = record["revision"]
        return result
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {
            "status": "unknown" if attempted else "error",
            "message": "Enrollment unconfirmed; review remote keys before retrying"
            if attempted
            else str(exc)
            if isinstance(exc, ValueError)
            else "SSH setup unavailable; check files and settings",
        }

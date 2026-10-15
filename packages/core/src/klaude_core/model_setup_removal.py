"""Reviewed, bounded removal of one owned setup; never follow environment symlinks.

Build creation, local server acceptance and removal share the inventory lock.
Removal retains status.json until all other entries are gone, so interrupted
cleanup can be reviewed again. Same-account external filesystem writers do not
participate in this lock; changed entries fail closed rather than being swept up.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .ai_defaults import defaults_from_preferences
from .managed_serving import process_identity, records
from .model_management import reference_parts
from .ollama_manager import connections
from .settings_store import read_settings, settings_lock

REMOVE_TIMEOUT = 120
MAX_ENTRIES = 100_000
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def reject_mounts(folder: Path) -> None:
    # st_dev alone cannot distinguish same-filesystem bind mounts.
    with Path("/proc/self/mountinfo").open("rb") as stream:
        data = stream.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError("Mount inspection exceeded its limit")
    for line in data.decode("utf8", "surrogateescape").splitlines():
        fields = line.split()
        if len(fields) < 10 or "-" not in fields[6:]:
            raise ValueError("Mount information is invalid; inspect setup manually")
        target = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4])
        if Path(target).is_relative_to(folder):
            raise ValueError("Setup contains a mount; unmount it before removal")


def inside(value: str, folder: Path) -> bool:
    if not value or not Path(value).is_absolute():
        return False
    # Include aliases, but preserve the lexical path of venv interpreter links.
    path = Path(value)
    return path.is_relative_to(folder) or path.resolve().is_relative_to(folder)


@contextmanager
def setup_directory(data_dir: Path, identity: str):
    if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Invalid setup identity")
    root = data_dir.absolute() / "model-builds"
    if root.resolve(strict=True) != root:
        raise ValueError("Setup directory ancestry cannot contain symlinks")
    reject_mounts(root / identity)
    root_fd = os.open(root, DIRECTORY_FLAGS)
    folder_fd = -1
    try:
        folder_fd = os.open(identity, DIRECTORY_FLAGS, dir_fd=root_fd)
        for fd in (root_fd, folder_fd):
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError("Setup directory must be owned and privately writable")
        yield root, root_fd, folder_fd
    finally:
        if folder_fd >= 0:
            os.close(folder_fd)
        os.close(root_fd)


def signature(info: os.stat_result) -> tuple:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def tree(folder_fd: int, deadline: float) -> tuple[list[tuple], int]:
    entries: list[tuple] = []
    allocated = 0
    device = os.fstat(folder_fd).st_dev
    seen: set[tuple[int, int]] = set()

    def walk(fd: int, prefix: str, depth: int) -> None:
        nonlocal allocated
        if depth > 64 or time.monotonic() > deadline:
            raise ValueError("Setup inspection exceeded its depth/time limit")
        # scandir keeps even a single huge directory bounded before sorting.
        names = []
        with os.scandir(fd) as scan:
            for entry in scan:
                names.append(entry.name)
                if len(entries) + len(names) > MAX_ENTRIES:
                    raise ValueError("Setup inspection exceeded 100,000 entries")
        for name in sorted(names):
            if len(entries) >= MAX_ENTRIES or time.monotonic() > deadline:
                raise ValueError("Setup inspection exceeded its entry/time limit")
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if info.st_dev != device or info.st_uid != os.getuid():
                raise ValueError("Setup contains a mount or files owned by another account")
            if not any(test(info.st_mode) for test in (stat.S_ISREG, stat.S_ISDIR, stat.S_ISLNK)):
                raise ValueError("Setup contains a special file; inspect it manually")
            path = prefix + name
            entries.append((path, signature(info)))
            if stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) not in seen:
                seen.add((info.st_dev, info.st_ino))
                # Hard links outside this setup may retain their storage.
                if info.st_nlink == 1:
                    allocated += info.st_blocks * 512
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, DIRECTORY_FLAGS, dir_fd=fd)
                try:
                    if signature(os.fstat(child)) != signature(info):
                        raise ValueError("Setup changed during inspection; review again")
                    walk(child, path + "/", depth + 1)
                finally:
                    os.close(child)

    walk(folder_fd, "", 0)
    return entries, allocated


def process_users(folder: Path, deadline: float) -> tuple[list[str], list[str]]:
    """Check same-account executables, argv, cwd, mapped libraries and open files."""
    examined = 0
    users = []
    restricted = 0
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal() or int(path.name) == os.getpid():
            continue
        examined += 1
        if examined > 8192 or time.monotonic() > deadline:
            raise ValueError("Process inspection limit exceeded; retry when idle")
        refs: list[str] = []
        try:
            if path.stat().st_uid != os.getuid():
                continue
            state = (path / "stat").read_text().rsplit(")", 1)[1].split()[0]
            if state == "Z":
                continue
            incomplete = False
            for name in ("exe", "cwd"):
                try:
                    refs.append(os.readlink(path / name))
                except PermissionError:
                    incomplete = True
            with (path / "cmdline").open("rb") as stream:
                raw = stream.read(65_537)
            if len(raw) > 65_536:
                raise ValueError("Process arguments exceed the inspection limit")
            refs += [os.fsdecode(a) for a in raw.split(b"\0") if a]
            try:
                with (path / "maps").open() as stream:
                    for index, line in enumerate(stream):
                        if index >= 16_384:
                            raise ValueError("Process mappings exceed the inspection limit")
                        fields = line.split(maxsplit=5)
                        if len(fields) == 6:
                            refs.append(fields[5].rstrip())
            except PermissionError:
                incomplete = True
            try:
                with os.scandir(path / "fd") as scan:
                    for index, entry in enumerate(scan):
                        if index >= 1024:
                            raise ValueError("Process open-file inspection limit exceeded")
                        try:
                            refs.append(os.readlink(entry.path))
                        except FileNotFoundError:
                            pass
            except PermissionError:
                incomplete = True
            if any(inside(ref.removesuffix(" (deleted)"), folder) for ref in refs):
                users.append("Process " + path.name + " is using this setup")
            restricted += int(incomplete)
        except FileNotFoundError:
            continue  # A process or transient descriptor finished during inspection.
        except PermissionError:
            if any(inside(ref.removesuffix(" (deleted)"), folder) for ref in refs):
                users.append("Process " + path.name + " is using this setup")
            restricted += 1
    warnings = (
        [
            "Linux restricted some process checks. "
            "Stop externally launched setup engines before removal."
        ]
        if restricted
        else []
    )
    return users, warnings


def protections(
    cfg: Any, item: dict, folder: Path, current: str, deadline: float
) -> tuple[list[str], list[str]]:
    reasons = []
    if item["state"] == "building":
        try:
            if process_identity(item["pid"])["start"] == item["start"]:
                reasons.append("Build/install worker is still running")
        except (OSError, ValueError):
            pass
    if inside(item["source"], folder):
        reasons.append("Original source/wheel folder is inside this setup")
    saved = read_settings(cfg.data_dir / "chat-preferences.json")
    defaults = defaults_from_preferences(cfg, saved)
    roles = {
        "Current session": current,
        "Saved session model": saved.get("last_model"),
        **{f"Configured {k}": v for k, v in cfg.models.items()},
        "Default Chat": defaults.chat,
        "Utility": defaults.utility,
        "Research": defaults.research,
        "Vision": defaults.vision,
    }
    roles.update({f"Utility fallback {i + 1}": v for i, v in enumerate(defaults.fallbacks)})
    roles.update({f"Vision fallback {i + 1}": v for i, v in enumerate(defaults.vision_fallbacks)})
    endpoints = connections(cfg)
    for record in records(cfg.data_dir).values():
        spec = record.get("spec", {})
        if spec.get("ssh_server"):
            continue
        if inside(spec.get("model", ""), folder):
            reasons.append("A retained server's model weights are inside this setup")
        if not inside(spec.get("executable", ""), folder):
            continue
        if record.get("state") in {"starting", "ready"}:
            try:
                if process_identity(record["helper_pid"])["start"] == record["helper_start"]:
                    reasons.append("Managed server is still using this setup")
            except (OSError, ValueError, KeyError):
                pass
        endpoint = record.get("endpoint", {})
        for label, ref in roles.items():
            if not isinstance(ref, str) or not ref:
                continue
            backend, identity, _ = reference_parts(ref)
            selected = endpoints.get(identity)
            if identity == endpoint.get("id") or (
                selected
                and backend == selected.backend
                and selected.backend == endpoint.get("backend")
                and selected.base_url == endpoint.get("base_url")
            ):
                reasons.append(label + " still selects this setup's endpoint")
        linked = endpoints.get(endpoint.get("id", ""))
        if linked and linked.enabled and linked.base_url == endpoint.get("base_url"):
            reasons.append("Setup's managed endpoint is still enabled; stop/reconcile the server")
    users, warnings = process_users(folder, deadline)
    return list(dict.fromkeys(reasons + users)), warnings


def inspect(cfg: Any, identity: str, current: str = "") -> tuple[dict, list[tuple]]:
    from .model_dependencies import builds

    deadline = time.monotonic() + 25
    with setup_directory(cfg.data_dir, identity) as (root, _, fd):
        item = next((b for b in builds(cfg.data_dir) if b["id"] == identity), None)
        if item is None:
            raise ValueError("Setup metadata unavailable; reload built/installed engines")
        entries, allocated = tree(fd, deadline)
        metadata = os.open("status.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(metadata)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65_536:
                raise ValueError("Invalid setup metadata")
            raw = os.read(metadata, 65_537)
        finally:
            os.close(metadata)
        digest = hashlib.sha256(
            json.dumps(
                [signature(os.fstat(fd)), entries, raw.decode("utf8")],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        folder = root / identity
        reasons, warnings = protections(cfg, item, folder, current, deadline)
        return {
            "id": identity,
            "directory": str(folder),
            "profile": item.get("profile", "cpu"),
            "state": item["state"],
            "bytes": allocated,
            "entries": len(entries),
            "revision": digest,
            "directory_identity": list(signature(os.fstat(fd))[:2]),
            "blockers": reasons,
            "warnings": warnings,
        }, entries


def remove(cfg: Any, evidence: dict, current: str, progress) -> dict:
    root = cfg.data_dir / "model-builds"
    # Same lock as build creation and local serving acceptance. Registry and
    # preference writers cannot change selected defaults during this transaction.
    with (
        settings_lock(root / "inventory.json", timeout=1),
        settings_lock(cfg.config_dir / "model-connections.json", timeout=1),
        settings_lock(cfg.data_dir / "chat-preferences.json", timeout=1),
    ):
        fresh, entries = inspect(cfg, evidence["id"], current)
        if fresh["blockers"]:
            raise ValueError("Cannot remove: " + "; ".join(fresh["blockers"]))
        # Warnings describe process visibility, not the setup revision. Counts
        # or wording may change with unrelated OS services/client versions.
        def scope_fields(value: dict) -> dict:
            return {k: v for k, v in value.items() if k not in {"warnings", "blockers"}}
        if (
            evidence.get("blockers")
            or scope_fields(fresh) != scope_fields(evidence)
            or fresh["warnings"]
            and not evidence.get("warnings")
        ):
            raise ValueError("Setup changed since review; review removal again")
        progress({"stage": "Removing reviewed setup files"})
        deadline = time.monotonic() + REMOVE_TIMEOUT - 35
        expected = dict(entries)
        children: dict[str, list[tuple]] = {}
        for path, sig in entries:
            parent, _, _ = path.rpartition("/")
            children.setdefault(parent + "/" if parent else "", []).append((path, sig))
        with setup_directory(cfg.data_dir, fresh["id"]) as (_, root_fd, folder_fd):
            if list(signature(os.fstat(folder_fd))[:2]) != fresh["directory_identity"]:
                raise ValueError("Setup directory changed; review again")
            # Never offer a partially removed environment as verified/servable.
            metadata = os.open("status.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder_fd)
            try:
                if signature(os.fstat(metadata)) != expected["status.json"]:
                    raise ValueError("Setup metadata changed; review again")
                if os.fstat(metadata).st_nlink != 1:
                    raise ValueError("Setup metadata must not have hard links")
                state = json.loads(os.read(metadata, 65_537))
                state["state"] = "removing"
            finally:
                os.close(metadata)
            temporary = ".removal-" + uuid.uuid4().hex
            metadata = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=folder_fd
            )
            try:
                with os.fdopen(metadata, "w") as stream:
                    stream.write(json.dumps(state))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, "status.json", src_dir_fd=folder_fd, dst_dir_fd=folder_fd)
                os.fsync(folder_fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=folder_fd)
                except FileNotFoundError:
                    pass
            expected["status.json"] = signature(
                os.stat("status.json", dir_fd=folder_fd, follow_symlinks=False)
            )

            def erase(fd: int, prefix: str) -> None:
                for path, sig in children.get(prefix, []):
                    name = path[len(prefix) :]
                    if path == "status.json":
                        continue
                    if time.monotonic() > deadline:
                        raise ValueError("Removal timed out; partial files retained; review again")
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if signature(info) != sig:
                        raise ValueError("Setup changed during removal; partial files retained")
                    if stat.S_ISDIR(info.st_mode):
                        child = os.open(name, DIRECTORY_FLAGS, dir_fd=fd)
                        try:
                            if signature(os.fstat(child)) != sig:
                                raise ValueError("Setup changed during removal; review again")
                            erase(child, path + "/")
                        finally:
                            os.close(child)
                        check = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        if (check.st_dev, check.st_ino) != sig[:2]:
                            raise ValueError("Setup directory changed during removal; review again")
                        os.rmdir(name, dir_fd=fd)
                    else:
                        os.unlink(name, dir_fd=fd)

            erase(folder_fd, "")
            if (
                os.listdir(folder_fd) != ["status.json"]
                or signature(os.stat("status.json", dir_fd=folder_fd, follow_symlinks=False))
                != expected["status.json"]
            ):
                raise ValueError("Setup changed during removal; partial files retained")
            if (
                os.stat(fresh["id"], dir_fd=root_fd, follow_symlinks=False).st_ino
                != os.fstat(folder_fd).st_ino
            ):
                raise ValueError("Setup directory changed during removal; review again")
            os.unlink("status.json", dir_fd=folder_fd)
            os.rmdir(fresh["id"], dir_fd=root_fd)
        return {
            "status": "ok",
            "removed": fresh["id"],
            "message": "Setup removed; original source/wheel folders and external models retained",
        }

"""Reviewed, checksum-verified image weights in the host's SD model directory.

Uses the Store's existing journal, private targets and owned process. Browsing
only reads Hub metadata. Publication never replaces an existing model file.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import shutil
import stat
import time
from contextlib import contextmanager
from itertools import islice
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from klaude_core.library_artifacts import regular_path
from klaude_web.huggingface import hub_gguf_files

from .operation_journal import OperationConflict

OPERATION = "model-image-download"
KEYS = (
    "endpoint",
    "model",
    "root",
    "root_device",
    "root_inode",
    "repo",
    "filename",
    "revision",
    "sha256",
    "size",
    "base_url",
)


def root() -> Path:
    path = Path(os.environ.get("KLAUDE_IMAGE_MODEL_DIR", "/mnt/HDD1/klaude-image/models"))
    if not path.is_absolute():
        raise ValueError("KLAUDE_IMAGE_MODEL_DIR must be an absolute directory")
    regular_path(path)
    return path


def parts(fields):
    # Every directory component is controlled here, never a browser-supplied path.
    return ("checkpoints", *fields["repo"].split("/"), fields["filename"])


@contextmanager
def directory(fields, *, create=False, lock=False, missing=False):
    path = Path(fields["root"])
    regular_path(path)
    descriptors = [os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)]
    lock_fd = None
    try:
        info = os.fstat(descriptors[0])
        if (info.st_dev, info.st_ino) != (fields["root_device"], fields["root_inode"]):
            raise ValueError("The image model directory changed; review again")
        if lock:
            lock_fd = os.open(
                ".klaude-download.lock",
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                0o600,
                dir_fd=descriptors[0],
            )
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise OperationConflict("A local image-model download is still active") from None
        for name in parts(fields)[:-1]:
            if create:
                try:
                    os.mkdir(name, 0o755, dir_fd=descriptors[-1])
                except FileExistsError:
                    pass
            try:
                descriptors.append(
                    os.open(
                        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptors[-1]
                    )
                )
            except FileNotFoundError:
                if not missing:
                    raise
                yield None
                return
        yield descriptors[-1]
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _exists(descriptor, name):
    try:
        os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def prepare(cfg, draft):
    if (
        set(draft) != {"operation", "connection", "model"}
        or draft["connection"] != "image:sdcpp"
        or not isinstance(draft["model"], str)
    ):
        raise ValueError("Choose an exact Stable Diffusion file")
    match = re.fullmatch(r"hf\.co/([^:]+):([^:]+)", draft["model"])
    if not match:
        raise ValueError("Choose an exact Hugging Face image-model file")
    repo, filename = match.groups()
    data = hub_gguf_files(cfg.huggingface_base_url, "", repo, image=True)
    selected = next((row for row in data["files"] if row["filename"] == filename), None)
    if selected is None or not re.fullmatch(r"[a-f0-9]{40}", str(data["revision"])):
        raise ValueError("No supported file with a verified size, checksum and revision")
    path = root()
    info = path.stat()
    if not path.is_dir() or not os.access(path, os.W_OK | os.X_OK):
        raise ValueError("The host image-model directory must exist and be writable")
    fields = {
        "endpoint": "image:sdcpp",
        "model": draft["model"],
        "root": str(path),
        "root_device": info.st_dev,
        "root_inode": info.st_ino,
        "repo": repo,
        "filename": filename,
        "revision": data["revision"],
        "sha256": selected["sha256"],
        "size": selected["size"],
        "base_url": cfg.huggingface_base_url.rstrip("/"),
    }
    try:
        with directory(fields) as descriptor:
            if _exists(descriptor, filename):
                raise ValueError("This file is already installed; refresh Installed")
    except FileNotFoundError:
        pass
    if shutil.disk_usage(path).free < fields["size"] + 16 * 1024**2:
        raise ValueError("Not enough free space in the image-model directory")
    return (
        fields,
        "browser-model-work",
        (
            f"Download {filename} ({fields['size']:,} bytes) from {repo} to the local "
            "Stable Diffusion model directory. Verifies the pinned revision and SHA256. "
            "Loading the model and any required components is a separate image-server action."
        ),
    )


def _redirect(url, origin):
    target, source = urlsplit(url), urlsplit(origin)
    if target.username or target.password or target.fragment:
        raise ValueError("Invalid model download redirect")
    if (target.scheme, target.netloc) == (source.scheme, source.netloc):
        return
    host = target.hostname or ""
    if (
        target.scheme != "https"
        or target.port not in {None, 443}
        or not any(
            host == domain or host.endswith("." + domain) for domain in ("huggingface.co", "hf.co")
        )
    ):
        raise ValueError("Model download redirect is outside the Hugging Face CDN")


def _transfer(fields, descriptor, temporary, progress, check):
    url = f"{fields['base_url']}/{fields['repo']}/resolve/{fields['revision']}/{fields['filename']}"
    deadline = time.monotonic() + 1800
    with httpx.Client(
        timeout=httpx.Timeout(30, connect=5), trust_env=False, follow_redirects=False
    ) as client:
        for _ in range(6):
            _redirect(url, fields["base_url"])
            with client.stream("GET", url, headers={"Accept-Encoding": "identity"}) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code != 200:
                    raise ValueError("Image-model source unavailable or requires access approval")
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise ValueError("Unexpected compressed model response")
                check()
                fd = os.open(
                    temporary,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                    0o644,
                    dir_fd=descriptor,
                )
                digest, completed, reported = hashlib.sha256(), 0, 0.0
                with os.fdopen(fd, "wb") as output:
                    for chunk in response.iter_bytes(256 * 1024):
                        if time.monotonic() > deadline:
                            raise ValueError("Image-model download reached its time limit")
                        completed += len(chunk)
                        if completed > fields["size"]:
                            raise ValueError("Image-model size differs from the reviewed file")
                        output.write(chunk)
                        digest.update(chunk)
                        now = time.monotonic()
                        if now - reported >= 0.25:
                            check()
                            progress(
                                {
                                    "stage": "Downloading file",
                                    "completed": completed,
                                    "total": fields["size"],
                                }
                            )
                            reported = now
                    output.flush()
                    os.fsync(output.fileno())
                progress(
                    {"stage": "Verifying download", "completed": completed, "total": fields["size"]}
                )
                if completed != fields["size"] or digest.hexdigest() != fields["sha256"]:
                    raise ValueError("Image-model checksum or size verification failed")
                return
        raise ValueError("Too many image-model download redirects")


def run(cfg, request, progress):
    from .model_store import OWNER
    from .operation_journal import OperationJournal

    journal = OperationJournal(cfg.data_dir / "operations.db")

    def check():
        journal.check_effect(request["request_id"], OWNER, request["fence"])

    temporary = f".klaude-{request['request_id']}.part"
    published = False
    try:
        check()
        with directory(request, create=True, lock=True) as descriptor:
            try:
                check()
                if _exists(descriptor, request["filename"]):
                    raise ValueError("Destination already exists; no file was replaced")
                if shutil.disk_usage(request["root"]).free < request["size"] + 16 * 1024**2:
                    raise ValueError("Not enough free space in the image-model directory")
                _transfer(request, descriptor, temporary, progress, check)
                check()
                # Hard-link publication is atomic and fails if the destination exists.
                os.link(
                    temporary,
                    request["filename"],
                    src_dir_fd=descriptor,
                    dst_dir_fd=descriptor,
                    follow_symlinks=False,
                )
                published = True
                os.fsync(descriptor)
            finally:
                try:
                    os.unlink(temporary, dir_fd=descriptor)
                except FileNotFoundError:
                    pass
        return {"ok": True, "message": "Downloaded. Load the model in your image server."}
    except (ValueError, OSError, httpx.HTTPError):
        return {
            "ok": False,
            "rejected": not published,
            "message": "Image-model download failed. Check access, disk space and source.",
        }


def reconcile(cfg, journal, identity):
    from .model_store import OWNER, read_record, target_path, witness

    receipt = journal.status(identity, OWNER)
    if receipt is None or receipt.kind != OPERATION or receipt.state != "unknown":
        raise OperationConflict("Only an unconfirmed image-model download can be checked")
    fields = read_record(target_path(cfg, identity), limit=16_384)
    if not journal.witness_after_matches(identity, OWNER, candidate=witness(fields, True)):
        raise OperationConflict("Image-model target differs from its reviewed witness")
    installed = False
    with directory(fields, lock=True, missing=True) as descriptor:
        if descriptor is not None:
            try:
                fd = os.open(
                    fields["filename"],
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                fd = None
            if fd is not None:
                with os.fdopen(fd, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size != fields["size"]:
                        raise OperationConflict("Installed file differs from the reviewed target")
                    if hashlib.file_digest(stream, "sha256").hexdigest() != fields["sha256"]:
                        raise OperationConflict("Installed file checksum differs from the target")
                    installed = True
            try:
                os.unlink(f".klaude-{identity}.part", dir_fd=descriptor)
            except FileNotFoundError:
                pass
        return {
            "request_id": identity,
            "state": journal.reconcile_witness(
                identity, OWNER, current=witness(fields, installed)
            ).state,
        }


def inventory(cfg):
    from .model_store import read_record

    path = root()
    models, known = [], {}
    targets = cfg.data_dir / "model-manager" / "browser"
    for record in islice(targets.glob("*.json"), 1000):
        item = read_record(record, limit=16_384)
        if item.get("endpoint") == "image:sdcpp" and item.get("root") == str(path):
            known["/".join(parts(item))] = item["model"]
    # Bound both directory visits and entries; do not follow links or read weights.
    pending, visited, entries = [path], 0, 0
    while pending and visited < 128 and entries < 2000:
        current = pending.pop()
        regular_path(current)
        try:
            with os.scandir(current) as children:
                visited += 1
                for entry in children:
                    entries += 1
                    if entries > 2000:
                        break
                    if entry.is_dir(follow_symlinks=False):
                        if len(Path(entry.path).relative_to(path).parts) < 5:
                            pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False) and (
                        Path(entry.name).suffix.lower()
                        in {".gguf", ".safetensors", ".sft", ".ckpt"}
                    ):
                        relative = str(Path(entry.path).relative_to(path))
                        models.append(
                            {
                                "name": known.get(relative, relative),
                                "display_name": entry.name,
                                "size": entry.stat(follow_symlinks=False).st_size,
                            }
                        )
        except FileNotFoundError:
            if current == path:
                raise ValueError("The host image-model directory is not configured") from None
    return {
        "connection": "image:sdcpp",
        "models": sorted(models, key=lambda row: row["name"]),
        "checked_at": time.time(),
        "stale": False,
        "running": [],
        "error": "",
        "destination": "Local Stable Diffusion models",
        "truncated": bool(pending) or entries > 2000,
    }

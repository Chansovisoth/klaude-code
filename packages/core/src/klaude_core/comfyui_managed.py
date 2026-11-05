"""Owned local ComfyUI runtime and one verified installed bundle."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import stat
import subprocess
import tarfile
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx

from .comfyui_bundle import COMFY_COMMIT, COMFY_VERSION, CONTROL, ControlBundle, digest
from .comfyui_probe import probe
from .library_artifacts import regular_path
from .settings_store import atomic_write_private, read_settings, settings_lock

SOURCE_SHA = "96c0680fa97ae0f6a0cb23ae8f24347e076eb535b9b3292efcb4a98d72d67ce1"
SOURCE_SIZE = 12830180
LOCK_SHA = "8c1ebbe4d8f08347557478b049933d508c21e5e1e7e348b05b3a6ab8f901c335"
BUNDLE_ID = "sd15-control@1"
LOCK = Path(__file__).parent / "data/comfyui/linux-cu126.lock"


def root(cfg: Any) -> Path:
    value = Path(cfg.data_dir) / "comfyui"
    regular_path(value)
    return value


def support_reason() -> str:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        return "The managed image runtime currently requires Linux x86_64 with NVIDIA CUDA."
    if not Path("/usr/bin/python3.12").is_file() or not shutil.which("uv"):
        return "Install Python 3.12 and uv before setting up the managed image runtime."
    return ""


def definition(bundle: ControlBundle = CONTROL) -> dict:
    return {
        "bundle": bundle.public(),
        "runtime": {
            "source_sha256": SOURCE_SHA,
            "source_bytes": SOURCE_SIZE,
            "lock_sha256": LOCK_SHA,
            "commit": COMFY_COMMIT,
            "version": COMFY_VERSION,
            "platform": "linux-x86_64",
            "python": "3.12",
            "torch": "2.9.1+cu126",
        },
    }


@contextlib.contextmanager
def owned_output(path: Path, *, append: bool = False):
    regular_path(path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise ValueError("Unsafe managed output file")
        if append:
            os.lseek(fd, 0, os.SEEK_END)
        else:
            os.ftruncate(fd, 0)
        with os.fdopen(fd, "r+b", closefd=False) as stream:
            yield stream
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def signature(path: Path) -> list[int]:
    regular_path(path)
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
        raise ValueError("Managed file is not a regular file owned by this account")
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def file_hash(path: Path, check=lambda: None) -> str:
    before = signature(path)
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            check()
            h.update(chunk)
    if signature(path) != before:
        raise ValueError("Model file changed during verification")
    return h.hexdigest()


def model_path(cfg: Any, bundle: ControlBundle = CONTROL) -> Path:
    return root(cfg) / "workspace/models/checkpoints" / bundle.installed_name


def record_path(cfg: Any, model: str = BUNDLE_ID) -> Path:
    if model == BUNDLE_ID:
        return root(cfg) / "installed.json"
    import re

    if not isinstance(model, str) or not re.fullmatch(r"checkpoint-[a-f0-9]{64}@1", model):
        raise ValueError("Choose an exact managed model")
    path = root(cfg) / "bundles" / (model + ".json")
    regular_path(path)
    return path


def bundle_for(cfg: Any, model: str = BUNDLE_ID) -> ControlBundle:
    if model == BUNDLE_ID:
        return CONTROL
    from .comfyui_models import key, parse

    record = read_settings(record_path(cfg, model))
    bundle = parse(record.get("recipe"))
    if key(bundle) != model:
        raise ValueError("Managed model identity changed")
    return bundle


def records(cfg: Any) -> list[tuple[str, dict]]:
    from .comfyui_models import LIMIT

    values = [(BUNDLE_ID, read_settings(record_path(cfg)))]
    folder = root(cfg) / "bundles"
    regular_path(folder)
    from itertools import islice

    paths = list(islice(folder.glob("*.json"), 1001))
    if len(paths) > 1000:
        raise ValueError("Managed model inventory exceeds its bound")
    values.extend((p.stem, read_settings(record_path(cfg, p.stem))) for p in sorted(paths))
    active = [(k, v) for k, v in values if v and not v.get("removed_by")]
    if len(active) > LIMIT:
        raise ValueError("Managed model inventory exceeds its active-model bound")
    return active


def installed(cfg: Any, *, full: bool = False, model: str = BUNDLE_ID) -> dict:
    base = root(cfg)
    bundle = bundle_for(cfg, model)
    regular_path(record_path(cfg, model))
    record = read_settings(record_path(cfg, model))
    if not record or record.get("removed_by"):
        raise ValueError("Install the complete ComfyUI image bundle first")
    changing = read_settings(base / "installing.json")
    if (
        changing
        and changing.get("request_id") != record.get("request_id")
        and changing.get("model", BUNDLE_ID) == model
    ):
        raise ValueError("ComfyUI setup is incomplete; continue the installation")
    if record.get("definition") != digest(definition(bundle)) or record.get("bundle_id") != model:
        raise ValueError("ComfyUI bundle version changed; repair installation")
    runtime_change = read_settings(base / "runtime-installing.json")
    runtime = read_settings(base / "runtime.json")
    if runtime_change and runtime_change.get("request_id") != runtime.get("request_id"):
        raise ValueError("Managed runtime repair is incomplete; repair the installation")
    if (
        record.get("model_signature") != signature(model_path(cfg, bundle))
        or not (base / "venv/bin/python").exists()
        or not (base / "source/main.py").is_file()
        or (base / "runtime.lock").read_bytes() != LOCK.read_bytes()
    ):
        raise ValueError("ComfyUI installation changed; repair installation")
    if full and file_hash(model_path(cfg, bundle)) != bundle.sha256:
        raise ValueError("ComfyUI model checksum changed; repair installation")
    return record


def process_identity(pid: int) -> str:
    try:
        if Path(f"/proc/{pid}").stat().st_uid != os.getuid():
            return ""
        value = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return value[19] if value[0] != "Z" else ""
    except (OSError, IndexError):
        return ""


def owned_process(cfg: Any, record: dict) -> bool:
    pid = record.get("pid")
    if type(pid) is not int or not record.get("birth") or process_identity(pid) != record["birth"]:
        return False
    try:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        expected = str(root(cfg) / "source/main.py").encode()
        return expected in args and str(root(cfg) / "workspace").encode() in args
    except OSError:
        return False


def server_record(cfg: Any) -> dict:
    path = root(cfg) / "server.json"
    regular_path(path)
    value = read_settings(path)
    port = value.get("port")
    if type(port) is not int or not 1024 <= port <= 65535 or not owned_process(cfg, value):
        raise ValueError("Managed ComfyUI is stopped; start or repair the image bundle")
    return value


def server_url(cfg: Any) -> str:
    return f"http://127.0.0.1:{server_record(cfg)['port']}"


def stop(cfg: Any) -> None:
    with settings_lock(root(cfg) / "server.json"):
        _stop(cfg)


def _stop(cfg: Any) -> None:
    try:
        record = server_record(cfg)
    except ValueError:
        return
    if not hasattr(os, "pidfd_open"):
        raise ValueError("Safe managed process control requires Linux pidfds")
    fd = os.pidfd_open(record["pid"])
    try:
        if not owned_process(cfg, record):
            raise ValueError("ComfyUI process identity changed")
        signal.pidfd_send_signal(fd, signal.SIGTERM)
        deadline = time.monotonic() + 10
        while owned_process(cfg, record) and time.monotonic() < deadline:
            time.sleep(0.1)
        if owned_process(cfg, record):
            signal.pidfd_send_signal(fd, signal.SIGKILL)
    finally:
        os.close(fd)


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def start(cfg: Any, check=lambda: None) -> str:
    with settings_lock(root(cfg) / "server.json"):
        return _start(cfg, check)


def _start(cfg: Any, check) -> str:
    base = root(cfg)
    try:
        return server_url(cfg)
    except ValueError:
        pass
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    workspace = base / "workspace"
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    log = base / "server.log"
    regular_path(log)
    if log.exists() and log.stat().st_size > 5_000_000:
        log.replace(base / "server.previous.log")
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG", "LC_ALL"}}
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONNOUSERSITE="1")
    command = [
        str(base / "venv/bin/python"),
        str(base / "source/main.py"),
        "--listen",
        "127.0.0.1",
        "--port",
        str(port),
        "--base-directory",
        str(workspace),
        "--disable-auto-launch",
        "--disable-all-custom-nodes",
        "--offline",
        "--lowvram",
        "--preview-method",
        "none",
        "--disable-metadata",
    ]
    check()
    with owned_output(log, append=True) as output:
        process = subprocess.Popen(
            command,
            cwd=base / "source",
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            env=env,
            start_new_session=True,
        )
    try:
        birth = process_identity(process.pid)
        if not birth:
            raise ValueError("ComfyUI process did not start")
        atomic_write_private(
            base / "server.json",
            json.dumps({"pid": process.pid, "birth": birth, "port": port}) + "\n",
        )
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and process.poll() is None:
            check()
            try:
                with httpx.Client(timeout=2, trust_env=False, follow_redirects=False) as client:
                    response = client.get(f"http://127.0.0.1:{port}/system_stats")
                if response.status_code == 200:
                    return f"http://127.0.0.1:{port}"
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise ValueError("ComfyUI startup failed; inspect the managed runtime log")
    except BaseException:
        _terminate(process)
        raise


@contextlib.contextmanager
def install_lock(cfg: Any, *, shared: bool = False):
    base = root(cfg)
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = base / ".install.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise ValueError("Unsafe managed installation lock")
        fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        yield fd
    finally:
        os.close(fd)


def _run(command: list[str], base: Path, fd: int, check, progress) -> None:
    regular_path(base / "install.log")
    with owned_output(base / "install.log", append=True) as output:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            pass_fds=(fd,),
            start_new_session=True,
        )
        deadline = time.monotonic() + 2700
        try:
            while process.poll() is None:
                check()
                if time.monotonic() >= deadline:
                    raise ValueError("Runtime installation exceeded its deadline")
                progress({"stage": "Installing locked runtime dependencies"})
                time.sleep(1)
            if process.returncode:
                raise ValueError("Runtime installation failed; inspect the managed install log")
        finally:
            _terminate(process)


def require_idle(cfg: Any) -> None:
    """An orphaned remote job outlives its worker's shared filesystem lock."""
    from .image_generation import history, job, packet

    for offset in range(0, 1000, 100):
        page = history(cfg, offset)
        if page["invalid"]:
            raise ValueError("Inspect unreadable image receipts before repairing the engine")
        for item in page["items"]:
            if item["status"] in {"complete", "cancelled", "failed"}:
                continue
            if job(cfg, item["job"])["settings"].get("provider") == "comfyui":
                raise ValueError(
                    "Check or explicitly abandon unfinished ComfyUI jobs before repair"
                )
        if not page["more"]:
            break
    try:
        url = server_url(cfg)
    except ValueError:
        return
    queue = packet(url, "/queue")
    if any(queue.get(key) != [] for key in ("queue_running", "queue_pending")):
        raise ValueError("ComfyUI still has queued or running work; repair is unavailable")


def install(
    cfg: Any,
    request_id: str,
    source: str,
    fetch_model,
    check,
    progress,
    before_publish=lambda value: None,
    *,
    bundle: ControlBundle = CONTROL,
    repair_runtime: bool = True,
) -> dict:
    """Called only by the reviewed application installer under its durable fence."""
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("This runtime build supports Linux x86_64 only")
    if hashlib.sha256(LOCK.read_bytes()).hexdigest() != LOCK_SHA:
        raise ValueError("The packaged runtime lock changed")
    from .comfyui_models import key

    model = key(bundle)
    base = root(cfg)
    with install_lock(cfg) as fd:
        check()
        require_idle(cfg)
        runtime = read_settings(base / "runtime.json")
        reuse_runtime = (
            runtime.get("definition") == digest(definition()["runtime"])
            and (base / "source/main.py").is_file()
            and (base / "venv/bin/python").exists()
            and (base / "runtime.lock").is_file()
            and (base / "runtime.lock").read_bytes() == LOCK.read_bytes()
        )
        target = model_path(cfg, bundle)
        verified = None
        if target.exists():
            progress({"stage": "Verifying installed checkpoint"})
            before = signature(target)
            if file_hash(target, check) == bundle.sha256 and signature(target) == before:
                verified = before
        required = (
            12 * 1024**3
            if repair_runtime or not reuse_runtime
            else (bundle.size if verified is None else 0) + 16 * 1024**2
        )
        if shutil.disk_usage(base).free < required:
            raise ValueError(
                f"Image installation needs {required:,} free bytes for staging/runtime"
            )
        atomic_write_private(
            base / "installing.json", json.dumps({"request_id": request_id, "model": model})
        )
        if repair_runtime or not reuse_runtime:
            atomic_write_private(
                base / "runtime-installing.json", json.dumps({"request_id": request_id})
            )
            archive = base / "source.tar.gz"
            regular_path(archive)
            if not archive.exists() or file_hash(archive, check) != SOURCE_SHA:
                progress({"stage": "Downloading ComfyUI runtime source"})
                with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
                    url = f"https://codeload.github.com/Comfy-Org/ComfyUI/tar.gz/{COMFY_COMMIT}"
                    with client.stream("GET", url, headers={"Accept-Encoding": "identity"}) as res:
                        if (
                            res.status_code != 200
                            or res.headers.get("content-encoding", "identity") != "identity"
                        ):
                            raise ValueError("Pinned ComfyUI source is unavailable")
                        total = 0
                        with owned_output(archive) as output:
                            for chunk in res.iter_bytes():
                                check()
                                total += len(chunk)
                                if total > SOURCE_SIZE:
                                    raise ValueError("ComfyUI source size changed")
                                output.write(chunk)
                                progress(
                                    {
                                        "stage": "Downloading runtime source",
                                        "completed": total,
                                        "total": SOURCE_SIZE,
                                    }
                                )
                if archive.stat().st_size != SOURCE_SIZE or file_hash(archive, check) != SOURCE_SHA:
                    raise ValueError("ComfyUI source checksum differs from review")
            stop(cfg)
            source_dir = base / "source"
            regular_path(source_dir)
            with tempfile.TemporaryDirectory(prefix="source-", dir=base) as staging_name:
                staging = Path(staging_name)
                with tarfile.open(archive) as tf:
                    members = tf.getmembers()
                    if len(members) > 20000 or sum(m.size for m in members) > 200_000_000:
                        raise ValueError("ComfyUI archive exceeds extraction limits")
                    for member in members:
                        check()
                        parts = Path(member.name).parts
                        if (
                            not parts
                            or parts[0] != f"ComfyUI-{COMFY_COMMIT}"
                            or ".." in parts
                            or member.issym()
                            or member.islnk()
                            or not (member.isfile() or member.isdir())
                        ):
                            raise ValueError("Unsafe ComfyUI source archive")
                    tf.extractall(staging, members=members, filter="data")
                if source_dir.exists():
                    shutil.rmtree(source_dir)
                (staging / f"ComfyUI-{COMFY_COMMIT}").rename(source_dir)
            uv = shutil.which("uv")
            if not uv:
                raise ValueError("uv is required to install the managed image runtime")
            python = "/usr/bin/python3.12"
            if not Path(python).is_file():
                raise ValueError("Python 3.12 is required for this managed runtime build")
            if not (base / "venv/bin/python").exists():
                _run(
                    [uv, "venv", "--python", python, str(base / "venv")], base, fd, check, progress
                )
            atomic_write_private(base / "runtime.lock", LOCK.read_text())
            _run(
                [
                    uv,
                    "pip",
                    "sync",
                    "--python",
                    str(base / "venv/bin/python"),
                    "--require-hashes",
                    "--only-binary",
                    ":all:",
                    "--extra-index-url",
                    "https://download.pytorch.org/whl/cu126",
                    "--index-strategy",
                    "unsafe-best-match",
                    str(base / "runtime.lock"),
                ],
                base,
                fd,
                check,
                progress,
            )
            atomic_write_private(
                base / "runtime.json",
                json.dumps(
                    {"definition": digest(definition()["runtime"]), "request_id": request_id}
                ),
            )
        target = model_path(cfg, bundle)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if verified is None:
            temporary = target.with_suffix(".part")
            regular_path(temporary)
            if source:
                source_path = Path(source)
                before = signature(source_path)
                progress({"stage": "Reusing and verifying existing model"})
                with source_path.open("rb") as src, owned_output(temporary) as dest:
                    while chunk := src.read(1024 * 1024):
                        check()
                        dest.write(chunk)
                if signature(source_path) != before:
                    raise ValueError("Source model changed during import")
            else:
                fetch_model(target.parent, temporary.name, progress, check)
            if (
                temporary.stat().st_size != bundle.size
                or file_hash(temporary, check) != bundle.sha256
            ):
                raise ValueError("Image model checksum differs from the reviewed bundle")
            check()
            os.replace(temporary, target)
            verified = signature(target)
        from .comfyui_models import architecture

        if architecture(target) != bundle.architecture:
            raise ValueError("Checkpoint architecture differs from the reviewed recipe")
        progress({"stage": "Starting managed image engine"})
        url = start(cfg, check)
        observed = probe(url)
        if (
            not observed["schema_matches"]
            or not observed["runtime_version_matches"]
            or bundle.installed_name not in observed["checkpoints"]
        ):
            raise ValueError("Installed ComfyUI does not match this bundle's schema/file contract")
        check()
        if signature(target) != verified:
            raise ValueError("Managed checkpoint changed after checksum verification")
        record = {
            "version": 1,
            "definition": digest(definition(bundle)),
            "request_id": request_id,
            "bundle_id": model,
            **({"recipe": asdict(bundle)} if model != BUNDLE_ID else {}),
            "model_signature": verified,
        }
        before_publish(record)
        destination = record_path(cfg, model)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write_private(destination, json.dumps(record) + "\n")
        return record


def inspect_bundle(cfg: Any, model: str, *, launch: bool = False) -> dict:
    with install_lock(cfg, shared=True):
        return _inspect_bundle(cfg, model, launch=launch)


def _inspect_bundle(cfg: Any, model: str, *, launch: bool = False) -> dict:
    bundle = bundle_for(cfg, model)
    record = installed(cfg, model=model)
    url = start(cfg) if launch else server_url(cfg)
    data = probe(url)
    if (
        not data["schema_matches"]
        or not data["runtime_version_matches"]
        or bundle.installed_name not in data["checkpoints"]
    ):
        raise ValueError("Managed ComfyUI changed; repair the installation")
    evidence = {
        "endpoint": url,
        "model": model,
        "provider": "comfyui",
        "installation": digest(record),
        **({"bundle": asdict(bundle)} if model != BUNDLE_ID else {}),
        "metadata_revision": data["metadata_revision"],
        "server": server_record(cfg),
        "limits": {"min_width": 256, "max_width": 768, "min_height": 256, "max_height": 768},
        "sampler": "euler",
        "scheduler": "normal",
        "cancel_queued": True,
        "cancel_generating": True,
        "img2img": False,
    }
    return {**evidence, "revision": digest(evidence)}

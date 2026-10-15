"""Dependency diagnostics and reviewed, isolated CPU/CUDA builds or wheel installs."""

from __future__ import annotations

import json
import os
import re
import select
import shutil
import signal
import stat
import subprocess
import tarfile
import time
from collections import deque
from pathlib import Path, PurePosixPath
from typing import Any

from .managed_serving import clean, fingerprint, probe_engine, process_identity
from .settings_store import atomic_write_private, settings_lock

BUILD_TIMEOUT = 1800
MAX_BUILDS = 8
MIN_FREE = 2 * 1024**3
TOOLS = {"cmake": "cmake", "ninja": "ninja", "git": "git", "cc": "cc", "c++": "c++"}


def environment(home: Path | None = None) -> dict[str, str]:
    result = {k: v for k, v in os.environ.items() if k in {"HOME", "LANG", "LC_ALL"}}
    result.update(
        PATH="/usr/local/bin:/usr/bin:/bin",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_TERMINAL_PROMPT="0",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        VLLM_NO_USAGE_STATS="1",
    )
    if home:
        result["HOME"] = str(home)
    return result


def tool_paths() -> dict[str, str]:
    return {
        key: str(Path(found).resolve())
        for key, name in TOOLS.items()
        if (found := shutil.which(name, path=environment()["PATH"]))
    }


def read_command(args: list[str], limit: int = 2_000_000) -> bytes:
    process = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment()
    )
    assert process.stdout is not None
    data = bytearray()
    deadline = time.monotonic() + 4
    try:
        while time.monotonic() < deadline:
            if select.select([process.stdout], [], [], 0.1)[0]:
                chunk = os.read(process.stdout.fileno(), 16_384)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("Dependency inspection output limit exceeded")
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if process.returncode:
            raise ValueError("Dependency command failed; check the selected source/tools")
        return bytes(data)
    except subprocess.TimeoutExpired:
        raise ValueError("Dependency inspection timed out") from None
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


def git_args(git: str, source: Path) -> list[str]:
    return [
        git,
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "safe.directory=" + str(source),
        "-C",
        str(source),
    ]


def inspection(engine: str = "llama_cpp", executable: str = "llama-server") -> dict:
    paths = tool_paths()
    tools = []
    for name in TOOLS:
        try:
            version = clean(
                read_command([paths[name], "--version"], 65_536)
                .decode("utf8", "replace")
                .splitlines()[0],
                160,
            )
            tools.append(
                {"name": name, "status": "Installed", "path": paths[name], "version": version}
            )
        except (KeyError, OSError, ValueError, IndexError):
            tools.append({"name": name, "status": "Unavailable", "path": paths.get(name, "")})
    try:
        checked = probe_engine(engine, executable, owned_group=True)
        tested = {"status": "Ready", **checked}
    except (OSError, ValueError) as exc:
        tested = {
            "status": "Unavailable",
            "message": clean(str(exc), 240)
            if isinstance(exc, ValueError)
            else "Engine test failed; check installation",
        }
    return {"tools": tools, "engine": tested, "checked_at": time.time()}


def prepare(
    source: str,
    data_dir: Path,
    jobs: int = 2,
    *,
    profile: str = "cpu",
    architectures: str = "",
    host_compiler: str = "",
    python: str = "",
) -> dict:
    if profile == "vllm_cuda":
        from .model_recipes import wheels

        return wheels(source, data_dir, python)
    if profile not in {"cpu", "cuda"}:
        raise ValueError("Choose cpu, cuda or vllm_cuda")
    if type(jobs) is not int or not 1 <= jobs <= 8:
        raise ValueError("Build jobs must be 1–8")
    folder = Path(source)
    if not folder.is_absolute() or folder.is_symlink() or not folder.is_dir():
        raise ValueError("Choose an absolute local llama.cpp Git checkout")
    folder = folder.resolve(strict=True)
    paths = tool_paths()
    if set(paths) != set(TOOLS):
        raise ValueError("Install CMake, Ninja, Git and C/C++ compilers before building")
    git = git_args(paths["git"], folder)
    commit = read_command(git + ["rev-parse", "--verify", "HEAD^{commit}"], 100).decode().strip()
    if not re.fullmatch(r"[a-f0-9]{40,64}", commit):
        raise ValueError("Source commit identity unavailable")
    files = {
        name: read_command(git + ["show", f"{commit}:{name}"]).decode("utf8", "replace")
        for name in ("CMakeLists.txt", "ggml/CMakeLists.txt", "tools/server/CMakeLists.txt")
    }
    required = {"LLAMA_BUILD_SERVER", "LLAMA_BUILD_WEBUI", "BUILD_SHARED_LIBS"}
    if not all(name in files["CMakeLists.txt"] for name in required):
        raise ValueError("This source does not support the bounded llama.cpp CPU recipe")
    available = set(re.findall(r"option\(\s*([A-Z][A-Z0-9_]+)", "\n".join(files.values())))
    flags = {
        "BUILD_SHARED_LIBS": "OFF",
        "LLAMA_BUILD_SERVER": "ON",
        "LLAMA_BUILD_WEBUI": "OFF",
        "LLAMA_BUILD_TESTS": "OFF",
        "LLAMA_BUILD_EXAMPLES": "OFF",
        "LLAMA_BUILD_TOOLS": "ON",
        "FETCHCONTENT_FULLY_DISCONNECTED": "ON",
    }
    for name in (
        "GGML_CUDA",
        "GGML_VULKAN",
        "GGML_HIP",
        "GGML_SYCL",
        "GGML_OPENCL",
        "GGML_BLAS",
        "GGML_METAL",
        "GGML_RPC",
        "GGML_NATIVE",
        "GGML_CCACHE",
        "GGML_CPU_KLEIDIAI",
        "GGML_OPENMP_FETCH",
        "LLAMA_OPENSSL",
        "LLAMA_CURL",
    ):
        if name in available:
            flags[name] = "OFF"
    cuda_settings = {}
    if profile == "cuda":
        from .model_recipes import cuda

        if "GGML_CUDA" not in available:
            raise ValueError("This committed source does not support the CUDA recipe")
        cuda_settings = cuda(architectures, host_compiler, paths)
        paths = cuda_settings.pop("tools")
        flags.update(
            GGML_CUDA="ON",
            CMAKE_CUDA_ARCHITECTURES=cuda_settings["architectures"],
            CMAKE_CUDA_COMPILER=paths["nvcc"],
            CMAKE_CUDA_HOST_COMPILER=paths["cuda_host"],
        )
    disk_root = data_dir
    while not disk_root.exists():
        disk_root = disk_root.parent
    if shutil.disk_usage(disk_root).free < MIN_FREE:
        raise ValueError("At least 2 GiB free space is required for a new build")
    return {
        "profile": profile,
        "engine": "llama_cpp",
        "cuda": cuda_settings,
        "source": str(folder),
        "commit": commit,
        "jobs": jobs,
        "flags": flags,
        "tools": paths,
        "revisions": {key: fingerprint(Path(path)) for key, path in paths.items()},
    }


def builds(data_dir: Path) -> list[dict]:
    root = data_dir / "model-builds"
    if not root.exists():
        return []
    result: list[dict] = []
    for folder in sorted(root.iterdir()):
        if not re.fullmatch(r"[a-f0-9]{32}", folder.name) or folder.is_symlink():
            continue
        if len(result) >= MAX_BUILDS:
            raise ValueError("Build inventory exceeds its limit")
        path = folder / "status.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65_536:
            continue
        item = json.loads(path.read_text())
        if (
            not isinstance(item, dict)
            or item.get("id") != folder.name
            or not isinstance(item.get("source"), str)
            or not isinstance(item.get("commit"), str)
            or not re.fullmatch(r"[a-f0-9]{40,64}", item["commit"])
            or type(item.get("pid")) is not int
            or not isinstance(item.get("start"), str)
            or item.get("state") not in {"building", "ready", "failed", "interrupted", "removing"}
            or item.get("engine", "llama_cpp") not in {"llama_cpp", "vllm"}
            or item.get("profile", "cpu") not in {"cpu", "cuda", "vllm_cuda"}
        ):
            raise ValueError("Invalid build record")
        if item.get("state") == "building":
            try:
                if process_identity(item["pid"])["start"] != item["start"]:
                    item["state"] = "interrupted"
            except (OSError, ValueError):
                item["state"] = "interrupted"
        elif item["state"] == "ready":
            try:
                if fingerprint(Path(item["executable"])) != item["revision"]:
                    item["state"] = "changed"
            except (OSError, KeyError, TypeError):
                item["state"] = "unavailable"
        result.append(item)
    return result


def log_tail(data_dir: Path, identity: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Invalid build identity")
    descriptor = os.open(
        data_dir / "model-builds" / identity / "build.log",
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 262_148:
            raise ValueError("Invalid build log")
        stream.seek(max(0, info.st_size - 16_384))
        return clean(stream.read(16_384).decode("utf8", "replace"), 16_384)


def build(data_dir: Path, identity: str, evidence: dict, progress, owner: int = 0) -> dict:
    if not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Invalid build identity")
    profile = evidence.get("profile", "cpu")
    if (
        prepare(
            evidence["source"],
            data_dir,
            evidence["jobs"],
            profile=profile,
            architectures=evidence.get("cuda", {}).get("architectures", ""),
            host_compiler=evidence.get("cuda", {}).get("host_compiler", ""),
            python=evidence["tools"].get("python", ""),
        )
        != evidence
    ):
        raise ValueError("Source commit or build tools changed; review again")
    root = data_dir / "model-builds"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("Build directory cannot be a symlink")
    with settings_lock(root / "inventory.json"):
        if len(builds(data_dir)) >= MAX_BUILDS:
            raise ValueError(
                "Eight setups retained; review removal in Built/installed engines "
                "or use model-manager remove-build ID"
            )
        folder = root / identity
        folder.mkdir(mode=0o700)
        state = {
            "id": identity,
            "source": evidence["source"],
            "commit": evidence["commit"],
            "engine": evidence["engine"],
            "profile": profile,
            "state": "building",
            "pid": os.getpid(),
            "start": process_identity(os.getpid())["start"],
            "updated_at": time.time(),
        }
        atomic_write_private(folder / "status.json", json.dumps(state))
    home = folder / "home"
    home.mkdir(mode=0o700)
    logs: deque[str] = deque(maxlen=500)
    deadline = time.monotonic() + BUILD_TIMEOUT - 15
    last_progress = 0.0

    def check() -> None:
        if owner and os.getppid() != owner:
            raise ValueError("Build owner exited")
        if time.monotonic() >= deadline:
            raise ValueError("Build timed out")
        if shutil.disk_usage(folder).free < 256 * 1024**2:
            raise ValueError("Build stopped: disk space below 256 MiB")

    def command(args: list[str], stage: str) -> None:
        nonlocal last_progress
        progress({"stage": stage})
        process = subprocess.Popen(
            args,
            env={**environment(home), "TMPDIR": str(home)},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert process.stdout is not None
        try:
            while True:
                check()
                if select.select([process.stdout], [], [], 0.1)[0]:
                    raw = os.read(process.stdout.fileno(), 4096)
                    if not raw:
                        break
                    logs.append(clean(raw.decode("utf8", "replace"), 4096))
                    if time.monotonic() - last_progress >= 1:
                        atomic_write_private(
                            folder / "build.log",
                            "".join(logs).encode()[-262_144:].decode("utf8", "replace"),
                        )
                        progress({"stage": stage})
                        last_progress = time.monotonic()
            while process.poll() is None:
                check()
                time.sleep(0.1)
            if process.returncode:
                raise ValueError(stage + " failed; inspect the private build log")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()

    try:
        check()
        if profile == "vllm_cuda":
            from .model_recipes import install

            installed = install(folder, evidence, command, check)
            progress({"stage": "Verify engine help"})
            checked = probe_engine("vllm", installed["executable"], owned_group=True)
            state.update(
                state="ready",
                executable=checked["executable"],
                revision=checked["revision"],
                compatibility=installed["compatibility"],
            )
            return {
                "status": "ok",
                "message": "vLLM installed; help verified, GPU inference untested",
                "build": state,
            }
        progress({"stage": "Snapshot committed source"})
        source = folder / "source"
        source.mkdir(mode=0o700)
        archive = subprocess.Popen(
            git_args(evidence["tools"]["git"], Path(evidence["source"]))
            + ["archive", "--format=tar", evidence["commit"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment(home),
        )
        assert archive.stdout is not None
        try:
            total = 0
            with tarfile.open(fileobj=archive.stdout, mode="r|") as stream:
                for count, member in enumerate(stream):
                    check()
                    parts = PurePosixPath(member.name).parts
                    total += member.size
                    if (
                        count >= 50_000
                        or total > 256 * 1024**2
                        or member.size > 32 * 1024**2
                        or not parts
                        or member.name.startswith("/")
                        or ".." in parts
                        or member.issym()
                        or member.islnk()
                    ):
                        raise ValueError(
                            "Source snapshot contains unsupported paths or exceeds bounds"
                        )
                    path = source.joinpath(*parts)
                    if member.isdir():
                        path.mkdir(mode=0o700, parents=True, exist_ok=True)
                    elif member.isfile():
                        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        body = stream.extractfile(member)
                        assert body is not None
                        with path.open("xb") as target:
                            shutil.copyfileobj(body, target, 65_536)
                        path.chmod(0o700 if member.mode & 0o111 else 0o600)
                    else:
                        raise ValueError("Source snapshot requires regular files and directories")
            archive.wait(timeout=4)
            if archive.returncode:
                raise ValueError("Source snapshot failed")
        finally:
            if archive.poll() is None:
                archive.kill()
            archive.wait()
            archive.stdout.close()
        output = folder / "output"
        configure = [
            evidence["tools"]["cmake"],
            "-S",
            str(source),
            "-B",
            str(output),
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_C_COMPILER=" + evidence["tools"]["cc"],
            "-DCMAKE_CXX_COMPILER=" + evidence["tools"]["c++"],
            "-DCMAKE_MAKE_PROGRAM=" + evidence["tools"]["ninja"],
        ]
        configure += [f"-D{key}={value}" for key, value in evidence["flags"].items()]
        command(configure, "Configure CUDA build" if profile == "cuda" else "Configure CPU build")
        command(
            [
                evidence["tools"]["cmake"],
                "--build",
                str(output),
                "--target",
                "llama-server",
                "--parallel",
                str(evidence["jobs"]),
            ],
            "Compile llama-server",
        )
        progress({"stage": "Verify engine help"})
        checked = probe_engine("llama_cpp", str(output / "bin" / "llama-server"), owned_group=True)
        state.update(
            state="ready",
            executable=checked["executable"],
            revision=checked["revision"],
            devices=checked.get("devices"),
            cuda=evidence.get("cuda", {}),
        )
        return {
            "status": "ok",
            "message": "CUDA engine built; GPU inference untested"
            if profile == "cuda"
            else "CPU engine built and verified",
            "build": state,
        }
    except (OSError, ValueError, tarfile.TarError, subprocess.TimeoutExpired):
        state["state"] = "failed"
        raise
    finally:
        state["updated_at"] = time.time()
        atomic_write_private(
            folder / "build.log", "".join(logs).encode()[-262_144:].decode("utf8", "replace")
        )
        atomic_write_private(folder / "status.json", json.dumps(state))
        if owner and os.getppid() != owner and os.getpgrp() == os.getpid():
            os.killpg(os.getpid(), signal.SIGKILL)


def execute(request: dict[str, Any], progress) -> dict:
    directory = Path(request["data_dir"])
    operation = request["operation"]
    try:
        if operation == "inspect":
            return inspection(
                request.get("engine", "llama_cpp"), request.get("executable", "llama-server")
            )
        if operation == "prepare":
            return {
                "evidence": prepare(
                    request["source"],
                    directory,
                    request.get("jobs", 2),
                    profile=request.get("profile", "cpu"),
                    architectures=request.get("architectures", ""),
                    host_compiler=request.get("host_compiler", ""),
                    python=request.get("python", ""),
                )
            }
        if operation == "build":
            return build(
                directory, request["id"], request["evidence"], progress, request.get("owner", 0)
            )
        if operation == "inventory":
            return {"builds": builds(directory)}
        if operation == "logs":
            return {"logs": log_tail(directory, request["id"])}
        if operation in {"prepare_remove", "remove"}:
            from .config import load_config
            from .model_setup_removal import inspect, remove

            cfg = load_config()
            if cfg.data_dir != directory:
                raise ValueError("Setup storage changed; reload before removal")
            if operation == "prepare_remove":
                evidence, _ = inspect(cfg, request["id"], request.get("current", ""))
                return {"evidence": evidence}
            return remove(cfg, request["evidence"], request.get("current", ""), progress)
        raise ValueError("Unknown dependency operation")
    except (OSError, ValueError, tarfile.TarError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "error",
            "message": clean(str(exc), 240)
            if isinstance(exc, ValueError)
            else "Removal incomplete or unconfirmed; reload built/installed engines; "
            "some files may have been removed"
            if operation == "remove"
            else "Build inspection failed; check local paths/logs",
        }

"""Explicit CUDA compiler targets and a bounded local vLLM wheel recipe."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import struct
import sys
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

from .managed_serving import fingerprint

MAX_WHEELS = 128
MAX_WHEEL_BYTES = 8 * 1024**3
MAX_EXPANDED = 32 * 1024**3


def binary(value: str) -> str:
    path = Path(value)
    if not path.is_absolute() or not str(path).isprintable():
        raise ValueError("Choose an absolute installed executable")
    path = path.resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("Choose an executable regular file")
    return str(path)


def cuda(architectures: str, host_compiler: str, tools: dict) -> dict:
    from .model_dependencies import read_command

    nvcc = shutil.which("nvcc", path="/usr/local/cuda/bin:/usr/local/bin:/usr/bin:/bin")
    if not nvcc:
        raise ValueError("CUDA toolkit unavailable; install it explicitly before building")
    tools = {**tools, "nvcc": binary(nvcc), "cuda_host": binary(host_compiler or tools["c++"])}
    supported = set(
        re.findall(
            r"compute_(\d{2,3})", read_command([tools["nvcc"], "--list-gpu-arch"], 16_384).decode()
        )
    )
    if not architectures:
        smi = shutil.which("nvidia-smi", path="/usr/local/bin:/usr/bin:/bin")
        if not smi:
            raise ValueError("Enter explicit CUDA architectures; GPU discovery is unavailable")
        try:
            observed = (
                read_command([smi, "--query-gpu=compute_cap", "--format=csv,noheader"], 4096)
                .decode()
                .splitlines()
            )
        except ValueError:
            raise ValueError("GPU unavailable; enter CUDA targets or choose CPU") from None
        if (
            not observed
            or len(observed) > 8
            or any(not re.fullmatch(r"\d{1,2}\.\d", value.strip()) for value in observed)
        ):
            raise ValueError("GPU architectures unknown; enter verified target architectures")
        architectures = ";".join(value.strip().replace(".", "") for value in observed)
    if not re.fullmatch(r"\d{2,3}(;\d{2,3}){0,7}", architectures):
        raise ValueError("Use up to eight numeric CUDA targets, such as 75;86")
    targets = sorted(set(architectures.split(";")))
    if not set(targets).issubset(supported):
        raise ValueError("Selected CUDA architectures are unsupported by the installed toolkit")
    # Check the chosen host compiler with fixed code, without executing source
    # build instructions or initializing a GPU. Never bypass NVCC's compiler gate.
    with tempfile.TemporaryDirectory(prefix="klaude-cuda-probe-", dir="/tmp") as temporary:
        sample = Path(temporary) / "probe.cu"
        sample.write_text("__global__ void klaude_compiler_probe() {}\n")
        try:
            read_command(
                [
                    tools["nvcc"],
                    "-ccbin",
                    tools["cuda_host"],
                    "-arch=compute_" + targets[0],
                    "-c",
                    str(sample),
                    "-o",
                    str(Path(temporary) / "probe.o"),
                ],
                65_536,
            )
        except ValueError:
            raise ValueError(
                "CUDA compiler check failed; choose a compatible host compiler"
            ) from None
    return {"architectures": ";".join(targets), "host_compiler": tools["cuda_host"], "tools": tools}


def wheel(path: Path) -> dict:
    """Bound the central directory before zipfile allocates it; parse only metadata."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 2 * 1024**3:
            raise ValueError("Use regular wheel files up to 2 GiB")
        stream.seek(max(0, info.st_size - 65_558))
        tail = stream.read(65_558)
        offset = tail.rfind(b"PK\x05\x06")
        if offset < 0 or len(tail) - offset < 22:
            raise ValueError("Invalid wheel archive")
        header = struct.unpack("<4s4H2IH", tail[offset : offset + 22])
        if (
            header[1]
            or header[2]
            or header[3] != header[4]
            or header[4] > 50_000
            or header[5] > 16 * 1024**2
            or offset + 22 + header[7] != len(tail)
        ):
            raise ValueError("Wheel central directory exceeds supported bounds")
        stream.seek(0)
        try:
            with zipfile.ZipFile(stream) as archive:
                items = archive.infolist()
                expanded = sum(item.file_size for item in items)
                if (
                    len(items) > 50_000
                    or expanded > MAX_EXPANDED
                    or any(
                        item.filename.startswith("/")
                        or ".." in PurePosixPath(item.filename).parts
                        or "\\" in item.filename
                        or item.flag_bits & 1
                        or stat.S_ISLNK(item.external_attr >> 16)
                        for item in items
                    )
                ):
                    raise ValueError("Wheel contains unsupported paths or exceeds bounds")
                metadata = [item for item in items if item.filename.endswith(".dist-info/METADATA")]
                if len(metadata) != 1 or metadata[0].file_size > 262_144:
                    raise ValueError("Wheel metadata is missing or oversized")
                parsed = BytesParser().parsebytes(archive.read(metadata[0]))
                name, version = str(parsed.get("Name", "")), str(parsed.get("Version", ""))
                if (
                    not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+!]{0,79}", version)
                    or any(
                        "@" in value or "://" in value
                        for value in parsed.get_all("Requires-Dist", [])
                    )
                ):
                    raise ValueError("Use named versioned wheels without URL dependencies")
        except (zipfile.BadZipFile, RuntimeError, UnicodeError):
            raise ValueError("Wheel metadata is unreadable") from None
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "file": path.name,
        "name": re.sub(r"[-_.]+", "-", name).lower(),
        "version": version,
        "sha256": digest,
        "revision": fingerprint(path),
        "bytes": info.st_size,
        "expanded": expanded,
    }


def wheels(source: str, data_dir: Path, python: str = "") -> dict:
    from .model_dependencies import MIN_FREE, read_command

    folder = Path(source)
    if not folder.is_absolute() or folder.is_symlink() or not folder.is_dir():
        raise ValueError("Choose an absolute local directory containing trusted vLLM wheels")
    folder = folder.resolve(strict=True)
    files: list[Path] = []
    for path in folder.iterdir():
        if path.suffix != ".whl":
            continue
        if len(files) >= MAX_WHEELS or len(path.name) > 240 or not path.name.isprintable():
            raise ValueError("Wheel inventory exceeds its limit")
        files.append(path)
    if sum(path.lstat().st_size for path in files) > MAX_WHEEL_BYTES:
        raise ValueError("Wheel set exceeds the 8-GiB archive limit")
    entries = [wheel(path) for path in sorted(files)]
    names = [item["name"] for item in entries]
    if not entries or len(set(names)) != len(names) or "vllm" not in names or "torch" not in names:
        raise ValueError("Choose one version per package, including vLLM and CUDA PyTorch wheels")
    total = sum(item["bytes"] for item in entries)
    expanded = sum(item["expanded"] for item in entries)
    if total > MAX_WHEEL_BYTES or expanded > MAX_EXPANDED:
        raise ValueError("Wheel set exceeds the 8-GiB archive/32-GiB expanded limits")
    interpreter = binary(python or str(Path(sys.executable).resolve()))
    info = json.loads(
        read_command(
            [
                interpreter,
                "-I",
                "-c",
                "import json,sys,platform;print(json.dumps({'version':list(sys.version_info[:3]),"
                "'platform':sys.platform,'machine':platform.machine()}))",
            ],
            4096,
        )
    )
    if (
        info.get("platform") != "linux"
        or info.get("machine") not in {"x86_64", "aarch64"}
        or info.get("version", [])[:2] not in [[3, 10], [3, 11], [3, 12], [3, 13]]
    ):
        raise ValueError(
            "This NVIDIA wheel recipe requires Linux Python 3.10–3.13 on x86_64/aarch64"
        )
    uv = shutil.which(
        "uv",
        path=os.pathsep.join(
            (str(Path.home() / ".local/bin"), "/usr/local/bin", "/usr/bin", "/bin")
        ),
    )
    if not uv:
        raise ValueError("Install uv explicitly before installing a separate engine environment")
    tools = {"python": interpreter, "uv": binary(uv)}
    help_text = read_command([tools["uv"], "pip", "install", "--help"], 131_072).decode()
    if not all(flag in help_text for flag in ("--offline", "--no-config", "--require-hashes")):
        raise ValueError("Installed uv lacks the bounded offline/hash installation options")
    # Resolve the whole wheel closure for the selected interpreter before copying
    # large bundles or creating a persistent environment. Never use installed
    # packages as a substitute for a missing reviewed wheel.
    with tempfile.TemporaryDirectory(prefix="klaude-wheel-review-", dir="/tmp") as temporary:
        requirements = Path(temporary) / "requirements.txt"
        requirements.write_text(
            "\n".join(f"{item['name']}=={item['version']}" for item in entries) + "\n"
        )
        try:
            read_command(
                [
                    tools["uv"],
                    "--offline",
                    "--no-config",
                    "--no-cache",
                    "--no-python-downloads",
                    "pip",
                    "compile",
                    str(requirements),
                    "--python",
                    interpreter,
                    "--no-index",
                    "--find-links",
                    str(folder),
                    "--only-binary",
                    ":all:",
                ],
                131_072,
            )
        except ValueError:
            raise ValueError(
                "Wheel closure incomplete or incompatible with Python/platform"
            ) from None
    disk = data_dir
    while not disk.exists():
        disk = disk.parent
    required = total + expanded * 2 + MIN_FREE
    if shutil.disk_usage(disk).free < required:
        raise ValueError(f"Wheel installation requires at least {required / 1024**3:.1f} GiB free")
    return {
        "source": str(folder),
        "commit": hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest(),
        "profile": "vllm_cuda",
        "engine": "vllm",
        "wheels": entries,
        "python_info": info,
        "tools": tools,
        "revisions": {key: fingerprint(Path(path)) for key, path in tools.items()},
        "version": next(item["version"] for item in entries if item["name"] == "vllm"),
        "bytes": total,
        "required_free": required,
        "jobs": 2,
    }


def install(folder: Path, evidence: dict, command, check) -> dict:
    snapshot = folder / "wheels"
    snapshot.mkdir(mode=0o700)
    for item in evidence["wheels"]:
        check()
        path = Path(evidence["source"]) / item["file"]
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        digest = hashlib.sha256()
        copied = 0
        with os.fdopen(fd, "rb") as source, (snapshot / item["file"]).open("xb") as target:
            while chunk := source.read(1024**2):
                check()
                copied += len(chunk)
                if copied > item["bytes"]:
                    raise ValueError("Wheel changed while copying; review again")
                digest.update(chunk)
                target.write(chunk)
        if digest.hexdigest() != item["sha256"]:
            raise ValueError("Wheel changed while copying; review again")
        (snapshot / item["file"]).chmod(0o600)
    requirements = folder / "requirements.txt"
    requirements.write_text(
        "\n".join(
            f"{item['name']}=={item['version']} --hash=sha256:{item['sha256']}"
            for item in evidence["wheels"]
        )
        + "\n"
    )
    requirements.chmod(0o600)
    venv = folder / "venv"
    command(
        [evidence["tools"]["python"], "-I", "-m", "venv", "--without-pip", str(venv)],
        "Create separate Python environment",
    )
    command(
        [
            evidence["tools"]["uv"],
            "--offline",
            "--no-config",
            "--no-cache",
            "--no-python-downloads",
            "pip",
            "install",
            "--python",
            str(venv / "bin/python"),
            "--no-index",
            "--find-links",
            str(snapshot),
            "--only-binary",
            ":all:",
            "--require-hashes",
            "--link-mode",
            "copy",
            "-r",
            str(requirements),
        ],
        "Install reviewed local wheels",
    )
    receipt = folder / "compatibility.json"
    command(
        [
            str(venv / "bin/python"),
            "-I",
            "-c",
            "import json,torch,sys,importlib.metadata as m;"
            "json.dump({'cuda':torch.version.cuda,'gpu_available':torch.cuda.is_available(),"
            "'torch':m.version('torch'),'vllm':m.version('vllm')},open(sys.argv[1],'w'))",
            str(receipt),
        ],
        "Check installed CUDA Python backend",
    )
    if receipt.is_symlink() or receipt.stat().st_size > 4096:
        raise ValueError("Invalid installed-backend receipt")
    info = json.loads(receipt.read_text())
    if (
        not isinstance(info, dict)
        or not re.fullmatch(r"\d{1,2}\.\d{1,2}", str(info.get("cuda", "")))
        or type(info.get("gpu_available")) is not bool
        or info.get("vllm") != evidence["version"]
    ):
        raise ValueError("Installed wheels lack the selected NVIDIA CUDA backend/version")
    return {"executable": str(venv / "bin/vllm"), "compatibility": info}

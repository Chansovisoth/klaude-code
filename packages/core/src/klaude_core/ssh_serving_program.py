"""Self-contained Linux remote program sent to Python over a verified SSH channel."""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

LEASE_SECONDS = 6
REQUIRED = {
    "--host",
    "--port",
    "--alias",
    "--model",
    "--ctx-size",
    "--threads",
    "--n-gpu-layers",
    "--parallel",
    "--device",
}
VLLM_REQUIRED = {
    "--host",
    "--port",
    "--served-model-name",
    "--max-model-len",
    "--gpu-memory-utilization",
    "--max-num-seqs",
    "--tensor-parallel-size",
    "--load-format",
    "--dtype",
    "--enforce-eager",
    "--distributed-executor-backend",
}
cancelled = False
cleanup_state = "not_started"


def interrupt(*_: Any) -> None:
    global cancelled
    cancelled = True


def emit(value: dict) -> None:
    print(json.dumps(value, separators=(",", ":")), flush=True)


def revision(path: Path) -> str:
    info = path.stat()
    return hashlib.sha256(
        str((str(path), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)).encode()
    ).hexdigest()


def environment(path: Path) -> dict[str, str]:
    values = {k: v for k, v in os.environ.items() if k in {"HOME", "LANG", "LC_ALL"}}
    values.update(
        PATH=str(path.parent) + ":/usr/local/bin:/usr/bin:/bin",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        TOKENIZERS_PARALLELISM="false",
        VLLM_NO_USAGE_STATS="1",
        DO_NOT_TRACK="1",
        VLLM_WORKER_MULTIPROC_METHOD="spawn",
    )
    return values


def required(engine: str) -> set[str]:
    return VLLM_REQUIRED if engine == "vllm" else REQUIRED


def resource_fields(spec: dict) -> None:
    if (
        spec["engine"] not in {"llama_cpp", "vllm"}
        or type(spec.get("adopt_pid", 0)) is not int
        or spec.get("adopt_pid", 0) < 0
        or any(type(spec[k]) is not int for k in ("port", "context", "threads", "gpu_layers"))
        or not 1024 <= spec["port"] <= 65535
        or not 512 <= spec["context"] <= 65536
        or not 1 <= spec["threads"] <= 256
        or not 0 <= spec["gpu_layers"] <= 999
        or not isinstance(spec.get("gpu"), str)
        or not re.fullmatch(r"\d{1,2}(?:,\d{1,2}){0,7}", spec["gpu"])
        or len(set(map(int, spec["gpu"].split(",")))) != len(spec["gpu"].split(","))
        or type(spec.get("memory")) not in {int, float}
        or not 0.1 <= spec["memory"] <= 0.95
        or spec.get("dtype", "auto") not in {"auto", "half", "bfloat16", "float32"}
        or type(spec.get("enforce_eager", False)) is not bool
        or (spec["engine"] == "vllm" and spec["gpu_layers"] != 0)
    ):
        raise ValueError("Remote serving requires valid engine, context and GPU settings")
    if spec.get("adopt_pid") and (
        spec["adopt_pid"] < 2
        or not isinstance(spec.get("model_id"), str)
        or not spec["model_id"]
        or len(spec["model_id"]) > 200
        or not spec["model_id"].isprintable()
        or any(c.isspace() for c in spec["model_id"])
    ):
        raise ValueError("Enter the existing server's PID and exact model ID")


def model_revision(model: Path, engine: str) -> str:
    if engine == "llama_cpp":
        return revision(model)
    # Fingerprint all visible bundle metadata, not gigabytes of tensor bodies.
    # No symlink can route the loader outside the reviewed directory.
    deadline = time.monotonic() + 3
    manifest = [(".", revision(model))]
    pending = [model]
    weights: set[str] = set()
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if cancelled or time.monotonic() >= deadline or len(manifest) >= 10_000:
                    raise ValueError("Remote model inventory exceeded its bound")
                path = Path(entry.path)
                relative = path.relative_to(model)
                if entry.name in {".cache", ".git"} and directory == model:
                    continue
                if entry.is_symlink():
                    raise ValueError("Remote model bundle must not contain symlinks")
                if entry.is_dir(follow_symlinks=False):
                    if len(relative.parts) > 16:
                        raise ValueError("Remote model directory is too deeply nested")
                    pending.append(path)
                elif not entry.is_file(follow_symlinks=False):
                    raise ValueError("Remote model bundle must contain regular files")
                manifest.append((str(relative), revision(path)))
                if path.suffix == ".safetensors" and directory == model:
                    weights.add(path.name)
    if not weights or len(weights) > 1000:
        raise ValueError("vLLM requires 1–1000 local safetensors weight files")
    config = model / "config.json"
    if not config.is_file() or config.stat().st_size > 1_000_000:
        raise ValueError("Choose a remote model directory with bounded config.json")
    if not isinstance(json.loads(config.read_text()), dict):
        raise ValueError("Remote model config.json must be a JSON object")
    index = model / "model.safetensors.index.json"
    if index.exists():
        if index.stat().st_size > 1_000_000:
            raise ValueError("Remote weight index exceeded its bound")
        data = json.loads(index.read_text())
        mapping = data.get("weight_map") if isinstance(data, dict) else None
        if (
            not isinstance(mapping, dict)
            or not mapping
            or any(not isinstance(name, str) or name not in weights for name in mapping.values())
        ):
            raise ValueError("Remote safetensors index references missing weight files")
    return hashlib.sha256(json.dumps(sorted(manifest)).encode()).hexdigest()


def group_alive(group: int) -> bool:
    for index, entry in enumerate(Path("/proc").iterdir()):
        if index >= 4096:
            return True
        if not entry.name.isdecimal():
            continue
        try:
            if os.getpgid(int(entry.name)) == group:
                state = (entry / "stat").read_text().rsplit(")", 1)[1].split()[0]
                if state != "Z":
                    return True
        except (OSError, ValueError, IndexError):
            pass
    return False


def process_identity(pid: int) -> dict:
    if type(pid) is not int or pid < 2:
        raise ValueError("Invalid remote PID")
    path = Path("/proc") / str(pid)
    info = (path / "stat").read_text().rsplit(")", 1)[1].split()
    if path.stat().st_uid != os.getuid() or info[0] == "Z":
        raise ValueError("Remote process is not live or owned by this account")
    with (path / "cmdline").open("rb") as stream:
        command = stream.read(8193)
    if len(command) > 8192:
        raise ValueError("Remote process command exceeds the inspection limit")
    return {
        "pid": pid,
        "start": info[19],
        "group": int(info[2]),
        "session": int(info[3]),
        "executable": str((path / "exe").resolve(strict=True)),
        "command_revision": hashlib.sha256(command).hexdigest(),
    }


def adoption_identity(pid: int, path: Path) -> dict:
    identity = process_identity(pid)
    if identity["group"] != pid or identity["session"] != pid:
        raise ValueError("Adoption requires an isolated remote server process/session")
    if identity["executable"] != str(path):
        with path.open("rb") as stream:
            first = stream.readline(4097)
        interpreter = first.removeprefix(b"#!").strip()
        # Only native engines or an exact Python console script are supported.
        # A matching string elsewhere in arbitrary argv is not executable proof.
        if (
            not first.startswith(b"#!")
            or len(first) > 4096
            or not os.fsdecode(interpreter).startswith("/")
            or "python" not in Path(os.fsdecode(interpreter)).name
            or str(Path(os.fsdecode(interpreter)).resolve(strict=True)) != identity["executable"]
        ):
            raise ValueError("PID does not match the tested remote engine executable")
        with (Path("/proc") / str(pid) / "cmdline").open("rb") as stream:
            args = stream.read(8193).split(b"\0")
        if len(args) < 2 or os.fsdecode(args[1]) != str(path):
            raise ValueError("PID does not match the tested remote engine executable")
    return identity


def identity_evidence(value: Any) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != {"pid", "start", "group", "session", "executable", "command_revision"}
        or type(value["pid"]) is not int
        or value["pid"] < 2
        or type(value["group"]) is not int
        or type(value["session"]) is not int
        or value["group"] != value["pid"]
        or value["session"] != value["pid"]
        or not isinstance(value["start"], str)
        or not re.fullmatch(r"\d{1,20}", value["start"])
        or not isinstance(value["executable"], str)
        or len(value["executable"]) > 4096
        or not value["executable"].isprintable()
        or not Path(value["executable"]).is_absolute()
        or not isinstance(value["command_revision"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", value["command_revision"])
    ):
        raise ValueError("Invalid remote adoption identity")
    return dict(value)


def stop_adopted(identity: dict) -> bool:
    group = identity["pid"]
    if not group_alive(group):
        return True
    try:
        if process_identity(group) != identity:
            return False
        # Keep witnessed descendants as anchors if the leader exits on TERM.
        # Never escalate against a recycled PID/group with no original member.
        members = []
        for index, entry in enumerate(Path("/proc").iterdir()):
            if index >= 4096:
                return False
            if not entry.name.isdecimal():
                continue
            try:
                member = process_identity(int(entry.name))
                if member["group"] == group and member["session"] == group:
                    members.append(member)
                    if len(members) > 64:
                        return False
            except (OSError, ValueError):
                pass
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                if process_identity(group) != identity:
                    return False
            except (OSError, ValueError):
                pass
            anchor = False
            for member in members:
                try:
                    anchor |= process_identity(member["pid"]) == member
                except (OSError, ValueError):
                    pass
            if not anchor:
                return not group_alive(group)
            os.killpg(group, sig)
            deadline = time.monotonic() + 0.7
            while time.monotonic() < deadline:
                if not group_alive(group):
                    return True
                time.sleep(0.03)
    except (OSError, ValueError):
        pass
    return not group_alive(group)


def stop(process: subprocess.Popen) -> bool:
    # Only groups created by this supervisor are ever signalled.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=0.6)
        except subprocess.TimeoutExpired:
            pass
    if process.stdout:
        process.stdout.close()
    deadline = time.monotonic() + 0.3
    while group_alive(process.pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    return process.poll() is not None and not group_alive(process.pid)


def fields(request: dict) -> tuple[Path, Path | None]:
    spec = request["spec"]
    resource_fields(spec)
    path = Path(spec["executable"])
    if (
        not path.is_absolute()
        or len(str(path)) > 4096
        or not str(path).isprintable()
        or not path.is_file()
        or not os.access(path, os.X_OK)
    ):
        raise ValueError("Choose an absolute installed remote executable")
    path = path.resolve(strict=True)
    model = None
    if request["operation"] != "probe" and not spec.get("adopt_pid"):
        model = Path(spec["model"])
        root = Path(request["models_dir"]).resolve(strict=True)
        if (
            not model.is_absolute()
            or len(str(model)) > 4096
            or not str(model).isprintable()
            or model.is_symlink()
            or not model.resolve(strict=True).is_relative_to(root)
            or (spec["engine"] == "llama_cpp" and not stat.S_ISREG(model.stat().st_mode))
            or (spec["engine"] == "vllm" and not model.is_dir())
        ):
            raise ValueError(
                "Choose a remote model file/directory inside the configured model directory"
            )
        model = model.resolve(strict=True)
        if spec["engine"] == "llama_cpp":
            with model.open("rb") as stream:
                if stream.read(4) != b"GGUF":
                    raise ValueError("Remote model is not a GGUF file")
    return path, model


def command_output(
    path: Path,
    option: str | list[str],
    deadline: float,
    limit: int,
    *,
    env: dict[str, str] | None = None,
) -> str:
    process = subprocess.Popen(
        [str(path), *([option] if isinstance(option, str) else option)],
        env=environment(path) if env is None else env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    output = bytearray()
    try:
        assert process.stdout is not None
        while time.monotonic() < deadline and not cancelled:
            if select.select([process.stdout], [], [], 0.05)[0]:
                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > limit:
                    raise ValueError("Remote engine check exceeded its output limit")
        if cancelled:
            raise ValueError("Remote engine check cancelled")
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if cancelled or process.returncode:
            raise ValueError("Remote engine test failed")
        return output.decode("utf8", "replace")
    except subprocess.TimeoutExpired:
        raise ValueError("Remote engine test timed out") from None
    finally:
        stop(process)


def devices(path: Path, flags: list[str], deadline: float) -> list[str] | None:
    if "--list-devices" not in flags:
        return None
    try:
        text = command_output(path, "--list-devices", min(deadline, time.monotonic() + 4), 65_536)
        if "Available devices:" not in text:
            return None
        names = re.findall(
            r"^\s*([A-Za-z0-9_-]{1,80}):\s+\S.*$",
            text.split("Available devices:", 1)[1],
            re.MULTILINE,
        )
        if len(names) > 32 or len(set(names)) != len(names):
            return None
        return names
    except ValueError:
        # An unknown inventory keeps CPU usable, but can never authorize offload.
        return None


def selection(spec: dict, inventory: Any) -> list[str]:
    if spec["engine"] == "llama_cpp" and not spec["gpu_layers"]:
        return []
    if (
        not isinstance(inventory, list)
        or not inventory
        or len(inventory) > 32
        or any(
            not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name)
            for name in inventory
        )
        or len(set(inventory)) != len(inventory)
    ):
        raise ValueError("Remote GPU devices unavailable; test the engine or choose CPU explicitly")
    indices = [int(value) for value in spec["gpu"].split(",")]
    if any(index >= len(inventory) for index in indices) or len(set(indices)) != len(indices):
        raise ValueError("GPU IDs must select distinct devices from the tested remote inventory")
    return [inventory[index] for index in indices]


CUDA_CHECK = """
import hashlib, importlib.metadata, importlib.util, json, os
from pathlib import Path
import torch
if not torch.version.cuda or not torch.cuda.is_available():
    raise SystemExit('CUDA unavailable')
count = torch.cuda.device_count()
if not 1 <= count <= 8:
    raise SystemExit('Invalid selected CUDA device count')
items = []
versions = {}
for name in ('torch', 'vllm'):
    dist = importlib.metadata.distribution(name)
    versions[name] = dist.version
    for filename in ('METADATA', 'RECORD'):
        text = dist.read_text(filename)
        if text is None or len(text) > 2000000:
            raise SystemExit('Missing or oversized environment metadata')
        items.append((name, filename, hashlib.sha256(text.encode()).hexdigest()))
for path in (Path(torch.__file__), Path(importlib.util.find_spec('vllm').origin),
             Path(os.sys.executable)):
    info = path.stat()
    items.append((str(path), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns))
print('KLAUDE_CUDA_EVIDENCE ' + json.dumps({
 'revision': hashlib.sha256(repr(items).encode()).hexdigest(),
 'torch': versions['torch'], 'vllm': versions['vllm'], 'cuda': torch.version.cuda,
 'capabilities': [list(torch.cuda.get_device_capability(i)) for i in range(count)]}))
"""


def runtime_evidence(value: Any) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != {"revision", "torch", "vllm", "cuda", "capabilities"}
        or not re.fullmatch(r"[a-f0-9]{64}", str(value["revision"]))
        or any(
            not isinstance(value[k], str)
            or not 0 < len(value[k]) <= 80
            or not value[k].isprintable()
            for k in ("torch", "vllm", "cuda")
        )
        or not isinstance(value["capabilities"], list)
        or not 1 <= len(value["capabilities"]) <= 8
        or any(
            not isinstance(pair, list)
            or len(pair) != 2
            or any(type(number) is not int or not 0 <= number <= 99 for number in pair)
            or tuple(pair) < (7, 5)
            for pair in value["capabilities"]
        )
    ):
        raise ValueError("Remote vLLM CUDA evidence unavailable or unsupported")
    return value


def vllm_devices(path: Path, deadline: float) -> list[str]:
    tool = shutil.which("nvidia-smi", path=environment(path)["PATH"])
    if not tool:
        raise ValueError(
            "Remote NVIDIA inventory unavailable; install/test the GPU driver separately"
        )
    text = command_output(
        Path(tool),
        ["--query-gpu=uuid", "--format=csv,noheader,nounits"],
        min(deadline, time.monotonic() + 3),
        65_536,
    )
    inventory = [line.strip() for line in text.splitlines() if line.strip()]
    if (
        not inventory
        or len(inventory) > 32
        or len(set(inventory)) != len(inventory)
        or any(not re.fullmatch(r"GPU-[a-fA-F0-9-]{8,72}", name) for name in inventory)
    ):
        raise ValueError("Remote NVIDIA inventory is unavailable or malformed")
    return inventory


def vllm_runtime(path: Path, spec: dict, inventory: list[str], deadline: float) -> dict:
    # Preserve the lexical venv interpreter path: resolving its symlink would
    # silently test system Python instead of the reviewed vLLM environment.
    with path.open("rb") as stream:
        line = stream.readline(4097).decode("utf8", "replace").strip()
    if not line.startswith("#!/") or len(line) > 4096 or any(c.isspace() for c in line[2:]):
        raise ValueError("vLLM must use an absolute Python console-script launcher")
    python = Path(line[2:])
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError("Remote vLLM Python environment unavailable")
    env = environment(path)
    env.update(
        CUDA_VISIBLE_DEVICES=",".join(selection(spec, inventory)), CUDA_DEVICE_ORDER="PCI_BUS_ID"
    )
    try:
        output = command_output(
            python,
            ["-I", "-c", CUDA_CHECK],
            min(deadline, time.monotonic() + 10),
            65_536,
            env=env,
        )
        # Imports can emit warnings even when CUDA is usable. Consume only our
        # one framed record; bounded diagnostic output stays out of the UI.
        prefix = "KLAUDE_CUDA_EVIDENCE "
        entries = [line[len(prefix) :] for line in output.splitlines() if line.startswith(prefix)]
        if len(entries) != 1:
            raise ValueError("Invalid CUDA check response")
        checked = runtime_evidence(json.loads(entries[0]))
    except ValueError:
        if cancelled:
            raise
        raise ValueError("vLLM CUDA unavailable; no CPU fallback") from None
    if len(checked["capabilities"]) != len(selection(spec, inventory)):
        raise ValueError("vLLM environment does not see every selected GPU")
    if spec.get("dtype") == "bfloat16" and any(pair[0] < 8 for pair in checked["capabilities"]):
        raise ValueError("Selected GPUs lack bfloat16 support; choose half precision explicitly")
    return checked


def probe(path: Path, spec: dict | None = None) -> dict:
    engine = spec["engine"] if spec else "llama_cpp"
    deadline = time.monotonic() + (45 if engine == "vllm" else 8)
    text = command_output(
        path,
        ["serve", "--help=all"] if engine == "vllm" else "--help",
        min(deadline, time.monotonic() + 30) if engine == "vllm" else deadline,
        512_000,
    )
    flags = sorted(set(re.findall(r"(?<!\w)--[a-z][a-z0-9-]+", text)))
    if len(flags) > 1000 or not required(engine).issubset(flags):
        raise ValueError("Remote engine lacks required serving flags")
    result: dict[str, Any] = {
        "engine": engine,
        "executable": str(path),
        "revision": revision(path),
        "flags": sorted(set(flags) & (required(engine) | {"--jinja", "--list-devices"})),
        "devices": None
        if spec and spec.get("adopt_pid")
        else (vllm_devices(path, deadline) if engine == "vllm" else devices(path, flags, deadline)),
    }
    if engine == "vllm" and not (spec and spec.get("adopt_pid")):
        assert spec is not None
        result["runtime"] = vllm_runtime(path, spec, result["devices"], deadline)
    return result


def prepare(request: dict) -> dict:
    path, model = fields(request)
    spec = request["spec"]
    engine = spec["engine"]
    previous = request.get("evidence", {})
    if spec.get("adopt_pid"):
        # Installed-engine inspection and process observation never confer ownership.
        if previous:
            if (
                previous.get("executable") != str(path)
                or previous.get("revision") != revision(path)
                or previous.get("engine") != engine
                or not required(engine).issubset(previous.get("flags", []))
            ):
                raise ValueError("Remote engine changed; inspect again")
            checked = {key: previous[key] for key in ("executable", "revision", "engine", "flags")}
            checked["devices"] = None
        else:
            checked = probe(path, spec)
        identity = adoption_identity(spec["adopt_pid"], path)
        checked["adopt_identity"] = identity
        if request["operation"] == "prepare":
            if not listener_owned(spec["port"], spec["adopt_pid"], loopback=True) or not healthy(
                spec["port"], spec["model_id"]
            ):
                raise ValueError("PID must own a healthy loopback server with the exact model ID")
            if adoption_identity(spec["adopt_pid"], path) != identity:
                raise ValueError("Remote process changed during review; inspect again")
        if previous and any(
            previous.get(key) != checked.get(key)
            for key in ("executable", "revision", "engine", "adopt_identity")
        ):
            raise ValueError("Remote engine/process changed; inspect again")
        return checked
    if previous:
        if (
            previous.get("executable") != str(path)
            or previous.get("revision") != revision(path)
            or previous.get("engine", "llama_cpp") != engine
            or not required(engine).issubset(previous.get("flags", []))
        ):
            raise ValueError("Remote engine changed; test it again")
        checked = {key: previous[key] for key in ("executable", "revision", "flags")}
        checked["devices"] = (
            vllm_devices(path, time.monotonic() + 3)
            if engine == "vllm"
            else devices(path, checked["flags"], time.monotonic() + 4)
        )
        if (engine == "vllm" or spec["gpu_layers"]) and checked["devices"] != previous.get(
            "devices"
        ):
            raise ValueError("Remote GPU inventory changed; test the engine again")
        if engine == "vllm":
            checked["runtime"] = vllm_runtime(path, spec, checked["devices"], time.monotonic() + 10)
            # GPU selection can change after Test. The fresh check is scoped to
            # the selected devices; only installed environment identity must match.
            if checked["runtime"]["revision"] != previous.get("runtime", {}).get("revision"):
                raise ValueError("Remote vLLM environment changed; test it again")
    else:
        checked = probe(path, spec)
    checked["engine"] = engine
    checked["selected_devices"] = selection(spec, checked["devices"])
    if model is not None:
        checked.update(model=str(model), model_revision=model_revision(model, engine))
        if engine == "vllm" and spec.get("dtype", "auto") == "auto":
            config = json.loads((model / "config.json").read_text())
            if config.get("dtype", config.get("torch_dtype")) == "bfloat16" and any(
                pair[0] < 8 for pair in checked["runtime"]["capabilities"]
            ):
                raise ValueError("Model defaults to bfloat16; choose half precision explicitly")
        check_port(spec["port"])
    return checked


def check_port(port: int) -> None:
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))


def listener_owned(port: int, process: subprocess.Popen | int, *, loopback: bool = False) -> bool:
    group = process if isinstance(process, int) else process.pid
    sockets = set()
    for name in ("tcp", "tcp6"):
        for line in (Path("/proc/net") / name).read_text().splitlines()[1:]:
            values = line.split()
            if values[3] == "0A" and int(values[1].split(":")[1], 16) == port:
                if loopback and values[1].split(":")[0] not in {
                    "0100007F",
                    "00000000000000000000000001000000",
                }:
                    return False
                sockets.add("socket:[" + values[9] + "]")
    if not sockets:
        return False
    # vLLM's API listener may belong to a child. Ownership requires the process
    # group created here, never just an observed listener or matching model ID.
    members = 0
    for index, entry in enumerate(Path("/proc").iterdir()):
        if index >= 4096:
            return False
        if not entry.name.isdecimal():
            continue
        try:
            if os.getpgid(int(entry.name)) != group or entry.stat().st_uid != os.getuid():
                continue
            members += 1
            if members > 64:
                return False
            for number, descriptor in enumerate((entry / "fd").iterdir()):
                if number >= 512:
                    break
                try:
                    if os.readlink(descriptor) in sockets:
                        return True
                except OSError:
                    pass
        except OSError:
            pass
    return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def healthy(port: int, alias: str) -> bool:
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        for route in ("/health", "/v1/models"):
            with opener.open(Request(f"http://127.0.0.1:{port}" + route), timeout=0.5) as response:
                body = response.read(1_000_001)
                if response.status != 200 or len(body) > 1_000_000:
                    return False
                if route.endswith("models") and not any(
                    isinstance(item, dict) and item.get("id") == alias
                    for item in json.loads(body).get("data", [])[:1000]
                ):
                    return False
        return True
    except (OSError, URLError, ValueError, AttributeError, TypeError):
        return False


class HealthCheck:
    """One daemon request at a time; HTTP cannot block lease ownership/cleanup."""

    def __init__(self, check: Callable[[], bool]):
        self.check = check
        self.done = threading.Event()
        self.thread: threading.Thread | None = None
        self.result = False
        self.next_check = 0.0

    def poll(self) -> bool:
        if self.done.is_set():
            self.done.clear()
            self.thread = None
            self.next_check = time.monotonic() + 0.5
            if self.result:
                return True
        if self.thread is None and time.monotonic() >= self.next_check:

            def run() -> None:
                try:
                    self.result = self.check()
                except Exception:
                    self.result = False
                finally:
                    self.done.set()

            self.thread = threading.Thread(target=run, daemon=True)
            self.thread.start()
        return False


def adopt(request: dict) -> None:
    """Observe first; only the client's post-registration acknowledgement owns it."""
    global cleanup_state
    path, _ = fields(request)
    spec, expected = request["spec"], request["evidence"]
    identity = identity_evidence(expected.get("adopt_identity"))
    if (
        identity["pid"] != spec["adopt_pid"]
        or adoption_identity(identity["pid"], path) != identity
        or expected.get("executable") != str(path)
        or expected.get("revision") != revision(path)
        or expected.get("engine") != spec["engine"]
        or not required(spec["engine"]).issubset(expected.get("flags", []))
        or not listener_owned(spec["port"], identity["pid"], loopback=True)
        or not healthy(spec["port"], spec["model_id"])
    ):
        raise ValueError("Remote process/endpoint changed; review adoption again")
    owned = False
    owner_lock = socket.socket(socket.AF_UNIX)
    pending = bytearray()
    lease = time.monotonic() + LEASE_SECONDS
    state, message = "stopped", "Remote adoption ended; original server retained"
    try:
        emit({"state": "ready", "pid": identity["pid"], "model": spec["model_id"]})
        while not cancelled:
            if time.monotonic() >= lease:
                message = "Remote owner lease expired"
                break
            if (
                adoption_identity(identity["pid"], path) != identity
                or revision(path) != expected["revision"]
            ):
                raise ValueError("Remote adopted process changed; ownership rejected")
            if not select.select([sys.stdin.buffer], [], [], 0.1)[0]:
                continue
            chunk = os.read(0, 16)
            if not chunk:
                break
            pending.extend(chunk)
            if len(pending) > 32:
                raise ValueError("Invalid adoption owner lease")
            while b"\n" in pending:
                line, _, rest = pending.partition(b"\n")
                pending = bytearray(rest)
                if line == b"A" and not owned:
                    try:
                        owner_lock.bind(
                            f"\0klaude-adopt-{os.getuid()}-{identity['pid']}-{identity['start']}"
                        )
                    except OSError:
                        raise ValueError("Remote server already has an adoption owner") from None
                    if (
                        cancelled
                        or adoption_identity(identity["pid"], path) != identity
                        or not listener_owned(spec["port"], identity["pid"], loopback=True)
                        or not healthy(spec["port"], spec["model_id"])
                    ):
                        raise ValueError("Remote adoption changed before takeover")
                    owned = True
                    cleanup_state = "unconfirmed"
                    message = "Adopted remote server stopped"
                    emit({"state": "owned", "pid": identity["pid"], "model": spec["model_id"]})
                elif line != b".":
                    raise ValueError("Invalid adoption owner lease")
                lease = time.monotonic() + LEASE_SECONDS
    except (OSError, ValueError) as exc:
        state, message = (
            "failed",
            str(exc) if isinstance(exc, ValueError) else "Remote process exited",
        )
    finally:
        if owned:
            cleanup_state = "confirmed" if stop_adopted(identity) else "unconfirmed"
        owner_lock.close()
        emit({"state": state, "message": message, "cleanup": cleanup_state})


def serve(request: dict) -> None:
    global cleanup_state
    if request["spec"].get("adopt_pid"):
        adopt(request)
        return
    path, model = fields(request)
    spec = request["spec"]
    expected = request["evidence"]
    if (
        model is None
        or revision(path) != expected["revision"]
        or model_revision(model, spec["engine"]) != expected["model_revision"]
        or str(path) != expected["executable"]
        or str(model) != expected["model"]
        or expected.get("engine", "llama_cpp") != spec["engine"]
        or not required(spec["engine"]).issubset(expected["flags"])
    ):
        raise ValueError("Remote executable/model changed; review again")
    check_port(request["spec"]["port"])
    identity = request["id"]
    if not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Invalid owned server identity")
    selected = selection(spec, expected.get("devices"))
    if spec["gpu_layers"] or spec["engine"] == "vllm":
        current = (
            vllm_devices(path, time.monotonic() + 3)
            if spec["engine"] == "vllm"
            else devices(path, expected["flags"], time.monotonic() + 4)
        )
        if current != expected.get("devices") or selected != expected.get("selected_devices"):
            raise ValueError("Remote GPU inventory changed; review again")
        if spec["engine"] == "vllm":
            assert isinstance(current, list)
            if vllm_runtime(path, spec, current, time.monotonic() + 10) != expected.get("runtime"):
                raise ValueError("Remote vLLM environment changed; review again")
    alias = "klaude-" + identity[:16]
    args = [
        str(path),
        "--model",
        str(model),
        "--host",
        "127.0.0.1",
        "--port",
        str(spec["port"]),
        "--ctx-size",
        str(spec["context"]),
        "--threads",
        str(spec["threads"]),
        "--n-gpu-layers",
        str(spec["gpu_layers"]),
        "--parallel",
        "1",
        "--device",
        ",".join(selected) if selected else "none",
        "--alias",
        alias,
    ]
    env = environment(path)
    if spec["engine"] == "vllm":
        args = [
            str(path),
            "serve",
            str(model),
            "--host",
            "127.0.0.1",
            "--port",
            str(spec["port"]),
            "--max-model-len",
            str(spec["context"]),
            "--gpu-memory-utilization",
            str(spec["memory"]),
            "--max-num-seqs",
            "1",
            "--tensor-parallel-size",
            str(len(selected)),
            "--load-format",
            "safetensors",
            "--served-model-name",
            alias,
            "--dtype",
            spec.get("dtype", "auto"),
            "--distributed-executor-backend",
            "mp",
        ]
        if spec.get("enforce_eager"):
            args.append("--enforce-eager")
        env.update(CUDA_VISIBLE_DEVICES=",".join(selected), CUDA_DEVICE_ORDER="PCI_BUS_ID")
    elif "--jinja" in expected["flags"]:
        args += ["--jinja"]
    if (
        revision(path) != expected["revision"]
        or model_revision(model, spec["engine"]) != expected["model_revision"]
    ):
        raise ValueError("Remote executable/model changed during preflight; review again")
    process = subprocess.Popen(
        args,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    cleanup_state = "unconfirmed"
    assert process.stdout is not None
    lease = time.monotonic() + LEASE_SECONDS
    start = time.monotonic()
    ready = False
    state, message = "stopped", "Remote server stopped"
    pending = bytearray()
    health_check = HealthCheck(lambda: healthy(spec["port"], alias))
    try:
        emit(
            {
                "state": "starting",
                "pid": process.pid,
                "message": "Loading remote GPU model" if selected else "Loading remote CPU model",
            }
        )
        while not cancelled:
            now = time.monotonic()
            if now >= lease:
                message = "Remote owner lease expired"
                break
            if process.poll() is not None:
                raise ValueError("Remote engine exited; inspect Logs")
            for stream in select.select([sys.stdin.buffer, process.stdout], [], [], 0.1)[0]:
                chunk = os.read(stream.fileno(), 4096)
                if stream is sys.stdin.buffer:
                    if not chunk:
                        return
                    # Heartbeats are fixed bytes. No runtime commands/PIDs are accepted.
                    if chunk != b".\n" and any(c not in b".\n" for c in chunk):
                        raise ValueError("Invalid owner lease")
                    lease = time.monotonic() + LEASE_SECONDS
                else:
                    pending.extend(chunk)
                    while b"\n" in pending or len(pending) >= 4096:
                        end = pending.find(b"\n") + 1 if b"\n" in pending else 4096
                        text = bytes(pending[:end]).decode("utf8", "replace")
                        del pending[:end]
                        emit({"state": "log", "text": text})
            if not ready:
                if health_check.poll() and listener_owned(spec["port"], process):
                    ready = True
                    emit({"state": "ready", "pid": process.pid, "model": alias})
                elif now - start > 180:
                    raise ValueError("Remote health check timed out")
    except ValueError as exc:
        state, message = "failed", str(exc)
    finally:
        cleanup_state = "confirmed" if stop(process) else "unconfirmed"
        emit({"state": state, "message": message, "cleanup": cleanup_state})


def main() -> None:
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupt)
    # Raw reads avoid buffering heartbeats past the initial request line.
    raw = bytearray()
    while b"\n" not in raw and len(raw) <= 16_384:
        part = os.read(0, 1)
        if not part:
            raise ValueError("Missing SSH request")
        raw.extend(part)
    if len(raw) > 16_384:
        raise ValueError("SSH request exceeded its limit")
    request = json.loads(raw)
    try:
        if request["operation"] == "serve":
            serve(request)
        elif request["operation"] in {"probe", "prepare"}:
            emit({"version": 1, "connected": True, "evidence": prepare(request)})
        else:
            raise ValueError("Unknown remote serving operation")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        message = (
            "".join(c for c in str(exc) if c.isprintable())[:240]
            if isinstance(exc, ValueError)
            else "Remote preflight/launch failed; check paths and ports"
        )
        if request["operation"] in {"probe", "prepare"}:
            # A completed fixed-operation error is distinct from SSH failure.
            emit({"version": 1, "connected": True, "error": message})
            return
        emit(
            {
                "state": "failed",
                "message": message,
                "cleanup": cleanup_state,
            }
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

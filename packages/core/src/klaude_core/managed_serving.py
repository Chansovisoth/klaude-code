"""Local engine profiles and lease-owned serving; no installers or shell text."""

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
from collections import deque
from dataclasses import asdict, dataclass
from itertools import islice
from pathlib import Path
from typing import Any

import httpx

from .model_connections import ModelConnection, connection_registry
from .settings_store import atomic_write_private, read_settings, settings_lock

MAX_LOG = 262_144
MAX_RECORDS = 32
START_TIMEOUT = 180
ENGINES = {"llama_cpp": "llama-server", "vllm": "vllm"}


def clean(value: Any, limit: int = 240) -> str:
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(value))
    return "".join(c for c in value if c.isprintable() or c == "\n")[:limit]


def executable(value: str, engine: str) -> Path:
    if engine not in ENGINES:
        raise ValueError("Choose llama_cpp or vllm")
    found = shutil.which(value) if not Path(value).is_absolute() else value
    if not found:
        raise ValueError("Engine unavailable; enter the path to an installed executable")
    try:
        path = Path(found).resolve(strict=True)
    except OSError:
        raise ValueError("Engine unavailable; check the installed executable path") from None
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("Engine must be an executable regular file")
    return path


def fingerprint(path: Path) -> str:
    info = path.stat()
    return hashlib.sha256(str((str(path), info.st_dev, info.st_ino,
                              info.st_size, info.st_mtime_ns)).encode()).hexdigest()


def engine_environment(path: Path, gpu: str = "") -> dict[str, str]:
    result = {k: v for k, v in os.environ.items() if k in {"HOME", "LANG", "LC_ALL"}}
    result.update(PATH=str(path.parent) + os.pathsep + "/usr/local/bin:/usr/bin:/bin",
                  HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                  HF_DATASETS_OFFLINE="1", TOKENIZERS_PARALLELISM="false",
                  VLLM_NO_USAGE_STATS="1", DO_NOT_TRACK="1", HF_HUB_DISABLE_TELEMETRY="1")
    if gpu:
        result["CUDA_VISIBLE_DEVICES"] = gpu
    return result


def stop_group(process: subprocess.Popen) -> None:
    # This group was created by us; even an exited leader may leave descendants.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            continue


def _probe_output(path: Path, args: list[str], *, owned_group: bool = False,
                  timeout: float = 8) -> str:
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               env=engine_environment(path), start_new_session=not owned_group)
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        assert process.stdout is not None
        while time.monotonic() < deadline:
            if select.select([process.stdout], [], [], 0.05)[0]:
                chunk = os.read(process.stdout.fileno(), 16_384)
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > 512_000:
                    raise ValueError("Engine help exceeded its limit")
        if process.poll() is None:
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if process.returncode or len(output) > 512_000:
            raise ValueError("Engine test failed; inspect its installation and dependencies")
        return output.decode("utf8", "replace")
    except subprocess.TimeoutExpired:
        raise ValueError("Engine test timed out") from None
    finally:
        if owned_group:
            # The worker supervisor owns this group. An isolated child group
            # could survive when forced cancellation preempts this finally.
            if process.poll() is None:
                process.kill()
            process.wait(timeout=1)
        else:
            stop_group(process)
        if process.stdout:
            process.stdout.close()


def probe_engine(engine: str, value: str, *, owned_group: bool = False) -> dict:
    path = executable(value, engine)
    args = [str(path), "serve", "--help=all"] if engine == "vllm" else [str(path), "--help"]
    output = _probe_output(path, args, owned_group=owned_group,
                           timeout=30 if engine == "vllm" else 8)
    flags = sorted(set(re.findall(r"(?<!\w)--[a-z][a-z0-9-]+", output)))
    required = {"--host", "--port", "--alias", "--model", "--ctx-size", "--threads",
                "--n-gpu-layers", "--parallel"} if engine == "llama_cpp" else {
                    "--host", "--port", "--served-model-name", "--max-model-len",
                    "--gpu-memory-utilization", "--max-num-seqs", "--tensor-parallel-size",
                    "--load-format"}
    if not required.issubset(flags):
        raise ValueError("Installed engine lacks required serving flags")
    devices = None
    if engine == "llama_cpp" and "--list-devices" in flags:
        try:
            info = _probe_output(path, [str(path), "--list-devices"], owned_group=owned_group)
            if "Available devices:" in info:
                devices = re.findall(r"^\s*([A-Za-z0-9_-]+):\s+.+$",
                                     info.split("Available devices:", 1)[1], re.MULTILINE)[:32]
        except ValueError:
            pass
    return {"engine": engine, "executable": str(path), "revision": fingerprint(path),
            "flags": flags[:600], "devices": devices}


@dataclass(frozen=True)
class LaunchSpec:
    engine: str
    executable: str
    model: str
    name: str = "Local model server"
    port: int = 8080
    context: int = 8192
    threads: int = 4
    gpu_layers: int = 0
    gpu: str = "0"
    memory: float = 0.5
    adopt_pid: int = 0
    model_id: str = ""
    ssh_server: str = ""
    local_port: int = 18080
    dtype: str = "auto"
    enforce_eager: bool = False

    def validate(self, evidence: dict) -> tuple[list[str], dict[str, str]]:
        path = executable(self.executable, self.engine)
        if (evidence.get("engine") != self.engine or evidence.get("executable") != str(path)
                or evidence.get("revision") != fingerprint(path)):
            raise ValueError("Engine changed; test it again")
        if (not self.name.strip() or len(self.name) > 120 or not self.name.isprintable()
                or any(type(v) is not int for v in
                       (self.port, self.context, self.threads, self.gpu_layers, self.adopt_pid))
                or not 1024 <= self.port <= 65535 or not 512 <= self.context <= 65536
                or not 1 <= self.threads <= 256 or not 0 <= self.gpu_layers <= 999
                or not re.fullmatch(r"\d{1,2}(?:,\d{1,2}){0,7}", self.gpu)
                or len(set(self.gpu.split(","))) != len(self.gpu.split(","))
                or not 0.1 <= self.memory <= 0.95
                or self.dtype not in {"auto", "half", "bfloat16", "float32"}
                or type(self.enforce_eager) is not bool):
            raise ValueError("Invalid name, port, context, threads or GPU settings")
        if self.adopt_pid:
            if (not self.model_id or len(self.model_id) > 200 or not self.model_id.isprintable()
                    or any(c.isspace() for c in self.model_id)):
                raise ValueError("Enter the existing server's exact model ID")
            adoption_identity(self.adopt_pid, path)
            return [], {}
        model = Path(self.model)
        if not model.is_absolute() or model.is_symlink():
            raise ValueError("Choose an absolute local model path without a symlink")
        if self.engine == "llama_cpp":
            if not model.is_file():
                raise ValueError("Choose a local GGUF file")
            with model.open("rb") as stream:
                if stream.read(4) != b"GGUF":
                    raise ValueError("Model is not a GGUF file")
            args = [str(path), "--model", str(model), "--host", "127.0.0.1",
                    "--port", str(self.port), "--ctx-size", str(self.context),
                    "--threads", str(self.threads), "--n-gpu-layers", str(self.gpu_layers),
                    "--parallel", "1"]
            if self.gpu_layers == 0 and "--device" in evidence["flags"]:
                args += ["--device", "none"]
            elif self.gpu_layers:
                devices = evidence.get("devices")
                if not devices or "--device" not in evidence["flags"]:
                    raise ValueError("GPU devices unavailable; use CPU or retest the engine")
                try:
                    selected = [devices[int(i)] for i in self.gpu.split(",")]
                except IndexError:
                    raise ValueError("GPU ID is not in the tested device inventory") from None
                args += ["--device", ",".join(selected)]
            if "--jinja" in evidence["flags"]:
                args += ["--jinja"]
        else:
            if not model.is_dir() or not (model / "config.json").is_file():
                raise ValueError("Choose an installed local model directory with config.json")
            weights = list(islice(model.glob("*.safetensors"), 1001))
            if not weights or len(weights) > 1000 or any(p.is_symlink() for p in weights):
                raise ValueError("vLLM requires local safetensors weights")
            args = [str(path), "serve", str(model), "--host", "127.0.0.1",
                    "--port", str(self.port), "--max-model-len", str(self.context),
                    "--gpu-memory-utilization", str(self.memory), "--max-num-seqs", "1",
                    "--tensor-parallel-size", str(len(self.gpu.split(","))),
                    "--load-format", "safetensors"]
            if self.dtype != "auto":
                if "--dtype" not in evidence["flags"]:
                    raise ValueError("Installed vLLM lacks the requested precision control")
                args += ["--dtype", self.dtype]
            if self.enforce_eager:
                if "--enforce-eager" not in evidence["flags"]:
                    raise ValueError("Installed vLLM lacks eager execution control")
                args += ["--enforce-eager"]
        return args, engine_environment(path, self.gpu if self.engine == "vllm" else "")


def store_path(data_dir: Path) -> Path:
    return data_dir / "model-serving" / "servers.json"


def records(data_dir: Path) -> dict:
    path = store_path(data_dir)
    if path.exists() and (not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > 256_000):
        raise ValueError("Invalid managed-server inventory")
    result = read_settings(path)
    if (not isinstance(result, dict) or len(result) > MAX_RECORDS or any(
            not re.fullmatch(r"[a-f0-9]{32}", k) or not isinstance(v, dict)
            for k, v in result.items())):
        raise ValueError("Managed-server inventory limit exceeded")
    return result


def publish(data_dir: Path, identity: str, value: dict) -> None:
    path = store_path(data_dir)
    with settings_lock(path):
        saved = records(data_dir)
        if identity not in saved and len(saved) >= MAX_RECORDS:
            terminal = [k for k, v in saved.items()
                        if v.get("state") in {"stopped", "failed", "interrupted"}]
            if not terminal:
                raise ValueError("Managed-server inventory is full")
            expired = terminal[0]
            saved.pop(expired)
            (path.parent / (expired + ".log")).unlink(missing_ok=True)
        saved[identity] = value
        atomic_write_private(path, json.dumps(saved))


def read_log(data_dir: Path, identity: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Invalid managed server identity")
    path = data_dir / "model-serving" / (identity + ".log")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_LOG:
            raise ValueError("Invalid managed server log")
        handle.seek(max(0, info.st_size - 16_384))
        return clean(handle.read(16_384).decode("utf8", "replace"), 16_384)


def process_identity(pid: int) -> dict:
    if type(pid) is not int or pid < 2:
        raise ValueError("Invalid server PID")
    path = Path("/proc") / str(pid)
    fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
    if path.stat().st_uid != os.getuid() or fields[0] == "Z":
        raise ValueError("Server process is not live or owned by this account")
    return {"pid": pid, "start": fields[19], "group": int(fields[2]),
            "session": int(fields[3]),
            "executable": str((path / "exe").resolve(strict=True))}


def adoption_identity(pid: int, path: Path) -> dict:
    identity = process_identity(pid)
    # Require a standalone session; never acquire Ollama's internal runners,
    # another Klaude helper's children or a shared shell/process group.
    if identity["group"] != pid or identity["session"] != pid:
        raise ValueError("Adoption requires an isolated server process/session")
    if identity["executable"] != str(path):
        with (Path("/proc") / str(pid) / "cmdline").open("rb") as handle:
            args = handle.read(8193).split(b"\0")
        if len(b"\0".join(args)) > 8192 or not any(
                os.fsdecode(a) == str(path) for a in args[:2]):
            raise ValueError("PID does not match the tested engine executable")
    return identity


def prepare(spec: LaunchSpec, evidence: dict) -> dict:
    if spec.ssh_server:
        raise ValueError("Remote models require SSH preflight through the owned worker")
    spec.validate(evidence)
    checked = dict(evidence)
    if spec.adopt_pid:
        checked["adopt_identity"] = adoption_identity(spec.adopt_pid, Path(spec.executable))
    else:
        path = Path(spec.model)
        checked["model_revision"] = fingerprint(path if path.is_file() else path / "config.json")
    return checked


def inventory(data_dir: Path) -> list[dict]:
    result = []
    for value in records(data_dir).values():
        item = dict(value)
        if item.get("state") in {"ready", "starting"}:
            try:
                live = process_identity(item["helper_pid"])
                if live["start"] != item.get("helper_start"):
                    item["state"] = "interrupted"
            except (OSError, ValueError):
                item["state"] = "interrupted"
        result.append(item)
    return result


def reconcile(request: dict) -> None:
    from types import SimpleNamespace

    cfg = SimpleNamespace(config_dir=Path(request["config_dir"]),
                          data_dir=Path(request["data_dir"]))
    value = records(cfg.data_dir).get(request["id"])
    if value and value.get("endpoint"):
        disable_connection(cfg, ModelConnection.from_record(value["endpoint"]))
    if value and value.get("state") in {"ready", "starting"}:
        value.update(state="interrupted", updated_at=time.time())
        publish(cfg.data_dir, request["id"], value)


def stop_adopted(identity: dict) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            if process_identity(identity["pid"]) != identity:
                return
            os.killpg(identity["pid"], sig)
        except (OSError, ValueError):
            return
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            try:
                if process_identity(identity["pid"]) != identity:
                    return
            except (OSError, ValueError):
                return
            time.sleep(0.05)


def listener_owned(port: int, group: int) -> bool:
    sockets = set()
    for name in ("tcp", "tcp6"):
        for row in (Path("/proc/net") / name).read_text().splitlines()[1:]:
            fields = row.split()
            if fields[3] == "0A" and int(fields[1].split(":")[1], 16) == port:
                sockets.add("socket:[" + fields[9] + "]")
    if not sockets:
        return False
    examined = 0
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            if process_identity(int(path.name))["group"] != group:
                continue
            examined += 1
            if examined > 64:
                return False
            for index, fd in enumerate((path / "fd").iterdir()):
                if index >= 512:
                    break
                if os.readlink(fd) in sockets:
                    return True
        except (OSError, ValueError):
            continue
    return False


def health(client: httpx.Client, model: str) -> bool:
    try:
        for route in ("/health", "/v1/models"):
            with client.stream("GET", route) as response:
                body = bytearray()
                for part in response.iter_bytes():
                    body.extend(part)
                    if len(body) > 1_000_000:
                        return False
                if response.status_code != 200:
                    return False
                if route.endswith("models"):
                    data = json.loads(body).get("data")
                    if (not isinstance(data, list) or len(data) > 1000
                            or not any(isinstance(m, dict) and m.get("id") == model for m in data)):
                        return False
        return True
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


def disable_connection(cfg: Any, connection: ModelConnection) -> None:
    from .model_runtime import save_model_cache

    registry = connection_registry(cfg)
    with settings_lock(registry.path):
        payload = registry._read()
        current = registry._records(payload)
        if current.get(connection.id) != connection:
            return
        payload["connections"][connection.id]["enabled"] = False
        atomic_write_private(registry.path, json.dumps(payload))
    save_model_cache(cfg.data_dir / "model-cache.json", [], backend="openai_compatible",
                     connection_id=connection.id, invalidate=True)


def check_loopback_port(port: int) -> None:
    with socket.socket() as sock:
        # Match server/SSH bind semantics: TIME_WAIT is reusable, live listeners aren't.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))


def serve(request: dict, emit, stopped: threading.Event) -> None:
    if request.get("spec", {}).get("ssh_server"):
        from .ssh_serving import serve as remote_serve

        remote_serve(request, emit, stopped)
        return
    from .config import load_config

    cfg = load_config()
    identity = request["id"]
    if not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Invalid server identity")
    spec = LaunchSpec(**request["spec"])
    alias = spec.model_id if spec.adopt_pid else "klaude-" + identity[:16]
    connection = ModelConnection("serve-" + identity[:16], spec.name, "openai_compatible",
                                 f"http://127.0.0.1:{spec.port}/v1")
    value = {"id": identity, "spec": asdict(spec), "state": "starting", "model": alias,
             "owner": request.get("owner", ""), "helper_pid": os.getpid(),
             "helper_start": process_identity(os.getpid())["start"],
             "endpoint": asdict(connection), "updated_at": time.time()}
    process = None
    registered = False
    log_thread = None
    log_stop = threading.Event()
    adopted = None
    try:
        # Test the bind without claiming that it can reserve the engine's port.
        if not spec.adopt_pid:
            check_loopback_port(spec.port)
        # Share acceptance with retained-setup removal. Once starting is
        # published the live helper protects its executable until cleanup.
        with settings_lock(cfg.data_dir / "model-builds" / "inventory.json", timeout=1):
            args, environment = spec.validate(request["evidence"])
            args += ["--alias" if spec.engine == "llama_cpp" else "--served-model-name", alias]
            if prepare(spec, request["evidence"]) != request["evidence"]:
                raise ValueError("Model or adopted process changed; review again")
            setup_root = (cfg.data_dir / "model-builds").resolve()
            path = Path(spec.executable).resolve()
            if path.is_relative_to(setup_root):
                relative = path.relative_to(setup_root)
                status = read_settings(setup_root / relative.parts[0] / "status.json")
                if status.get("state") == "removing":
                    raise ValueError("Setup removal is incomplete; choose another engine")
            publish(cfg.data_dir, identity, value)
        if stopped.is_set():
            return
        if spec.adopt_pid:
            adopted = request["evidence"]["adopt_identity"]
            value["pid"] = spec.adopt_pid
        else:
            process = subprocess.Popen(args, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            value["pid"] = process.pid
        logs: deque[str] = deque(maxlen=500)

        def drain() -> None:
            assert process is not None and process.stdout is not None
            pending = b""

            def append(raw: bytes) -> None:
                line = clean(raw.decode("utf8", "replace"), 4096)
                line = re.sub(r"(?i)((?:api[_ -]?key|token|authorization|password)\s*[:=]\s*)\S+",
                              r"\1[redacted]", line)
                logs.append(line)

            while not log_stop.is_set():
                # Engine workers may inherit stdout after their leader exits.
                # Do not hold a buffered readline lock that blocks shutdown.
                if not select.select([process.stdout], [], [], 0.1)[0]:
                    continue
                raw = os.read(process.stdout.fileno(), 4096)
                if not raw:
                    break
                pending += raw
                while b"\n" in pending or len(pending) >= 4096:
                    end = pending.find(b"\n") + 1 if b"\n" in pending else 4096
                    append(pending[:end])
                    pending = pending[end:]
                payload = "".join(logs).encode()[-MAX_LOG:].decode("utf8", "replace")
                path = cfg.data_dir / "model-serving" / (identity + ".log")
                atomic_write_private(path, payload)
            if pending:
                append(pending)
                atomic_write_private(cfg.data_dir / "model-serving" / (identity + ".log"),
                                     "".join(logs).encode()[-MAX_LOG:].decode("utf8", "replace"))

        if process is not None:
            log_thread = threading.Thread(target=drain, daemon=True)
            log_thread.start()
        emit({"state": "starting", "id": identity, "message": "Loading local model"})
        with httpx.Client(base_url=f"http://127.0.0.1:{spec.port}", trust_env=False,
                          follow_redirects=False, timeout=httpx.Timeout(2, connect=0.5)) as client:
            if adopted and not health(client, alias):
                raise ValueError("Existing server is unavailable or lacks the reviewed model ID")
            deadline = time.monotonic() + START_TIMEOUT
            while not stopped.is_set():
                if (process is not None and process.poll() is not None
                        or adopted is not None and process_identity(adopted["pid"]) != adopted):
                    raise ValueError("Server exited; open Logs to inspect the engine failure")
                if health(client, alias) and listener_owned(
                        spec.port, spec.adopt_pid if spec.adopt_pid else os.getpgrp()):
                    registry = connection_registry(cfg)
                    registry.migrate(cfg)
                    registry.add(connection)
                    registered = True
                    value.update(state="ready", updated_at=time.time(), adopted=bool(adopted))
                    publish(cfg.data_dir, identity, value)
                    emit({**value, "message": "Server ready; endpoint registered"})
                    break
                if time.monotonic() >= deadline:
                    raise ValueError("Server health check timed out; open Logs")
                stopped.wait(0.25)
            while not stopped.wait(0.25):
                if (process is not None and process.poll() is not None
                        or adopted is not None and process_identity(adopted["pid"]) != adopted):
                    raise ValueError("Server exited; open Logs")
        value.update(state="stopped", updated_at=time.time())
    except (OSError, ValueError) as exc:
        value.update(state="failed", updated_at=time.time(), message=str(exc)
                     if isinstance(exc, ValueError)
                     else "Server operation failed; inspect port and Logs")
        emit({"id": identity, "state": "failed", "message": value["message"]})
    finally:
        if adopted and registered:
            stop_adopted(adopted)
        if process is not None:
            # The helper is group leader; its supervisor owns group termination.
            process.terminate() if process.poll() is None else None
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            if log_thread:
                log_stop.set()
                log_thread.join(timeout=1)
            if process.stdout:
                process.stdout.close()
        if registered:
            try:
                disable_connection(cfg, connection)
            except (OSError, ValueError):
                emit({"id": identity, "state": "warning",
                      "message": "Server stopped; endpoint disable unconfirmed; reload Models"})
        value["state"] = "stopped" if stopped.is_set() else value.get("state", "failed")
        try:
            publish(cfg.data_dir, identity, value)
        except (OSError, ValueError):
            pass
        emit({"id": identity, "state": value["state"],
              "message": value.get("message", "Server stopped")})


def main() -> None:
    request = json.loads(sys.stdin.buffer.readline(32_769))
    os.environ["KLAUDE_CONFIG_DIR"] = request["config_dir"]
    os.environ["KLAUDE_DATA_DIR"] = request["data_dir"]
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())

    def lease() -> None:
        sys.stdin.buffer.read(1)
        stopped.set()

    threading.Thread(target=lease, daemon=True).start()

    def emit(value: dict) -> None:
        print(json.dumps(value), flush=True)

    try:
        serve(request, emit, stopped)
    except ValueError as exc:
        emit({"id": request.get("id"), "state": "failed", "message": clean(str(exc), 240)})
    except Exception:
        emit({"id": request.get("id"), "state": "failed",
              "message": "Managed server unavailable; inspect its configuration"})
    finally:
        # Cleanup must also work when the client/supervisor has died. This
        # isolated group belongs to the helper, including engine descendants.
        # Persist and flush the terminal acknowledgement before ending it.
        if os.getpgrp() == os.getpid():
            os.killpg(os.getpid(), signal.SIGTERM)
            time.sleep(0.2)
            os.killpg(os.getpid(), signal.SIGKILL)


if __name__ == "__main__":
    main()

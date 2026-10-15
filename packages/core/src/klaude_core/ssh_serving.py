"""Reviewed remote llama.cpp CPU/GPU serving through client-owned SSH leases."""

from __future__ import annotations

import json
import os
import re
import select
import subprocess
import threading
import time
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx

from . import ssh_serving_program
from .managed_serving import (
    MAX_LOG,
    LaunchSpec,
    check_loopback_port,
    clean,
    disable_connection,
    health,
    listener_owned,
    process_identity,
    publish,
)
from .model_connections import ModelConnection, connection_registry
from .settings_store import atomic_write_private
from .ssh_servers import SSHServer, arguments, environment, load, references, run

PREFLIGHT_TIMEOUT = 20


def program() -> str:
    return Path(ssh_serving_program.__file__).read_text()


def validate(spec: LaunchSpec) -> None:
    ssh_serving_program.resource_fields(asdict(spec))
    if (
        not spec.name.strip()
        or len(spec.name) > 120
        or not spec.name.isprintable()
        or type(spec.local_port) is not int
        or not 1024 <= spec.local_port <= 65535
    ):
        raise ValueError("Remote serving requires a valid name and tunnel port")


def preflight_timeout(spec: LaunchSpec) -> int:
    if spec.engine == "vllm":
        return 60 if spec.ssh_server else 40
    return 20 if spec.ssh_server else 15


def decoded(value: Any, operation: str) -> dict:
    if (
        isinstance(value, dict)
        and value.get("connected") is True
        and value.get("version") == 1
        and isinstance(value.get("error"), str)
        and 0 < len(value["error"]) <= 240
        and value["error"].isprintable()
    ):
        return {"error": value["error"]}
    evidence = value.get("evidence") if isinstance(value, dict) else None
    if (
        not isinstance(evidence, dict)
        or value.get("connected") is not True
        or value.get("version") != 1
        or not isinstance(evidence.get("executable"), str)
        or not Path(evidence["executable"]).is_absolute()
        or len(evidence["executable"]) > 4096
        or not evidence["executable"].isprintable()
        or not re.fullmatch(r"[a-f0-9]{64}", str(evidence.get("revision", "")))
        or not isinstance(evidence.get("flags"), list)
        or len(evidence["flags"]) > 1000
        or any(
            not isinstance(flag, str) or not re.fullmatch(r"--[a-z][a-z0-9-]{0,79}", flag)
            for flag in evidence["flags"]
        )
        or evidence.get("engine", "llama_cpp") not in {"llama_cpp", "vllm"}
        or not ssh_serving_program.required(evidence.get("engine", "llama_cpp")).issubset(
            evidence["flags"]
        )
    ):
        raise ValueError("Invalid remote engine evidence")
    result = {
        "engine": evidence.get("engine", "llama_cpp"),
        "executable": evidence["executable"],
        "revision": evidence["revision"],
        "flags": evidence["flags"],
        "devices": evidence.get("devices"),
    }
    inventory = result["devices"]
    if inventory is not None and (
        not isinstance(inventory, list)
        or len(inventory) > 32
        or any(
            not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name)
            for name in inventory
        )
        or len(set(inventory)) != len(inventory)
    ):
        raise ValueError("Invalid remote GPU inventory")
    if evidence.get("adopt_identity") is not None:
        result["adopt_identity"] = ssh_serving_program.identity_evidence(evidence["adopt_identity"])
    elif result["engine"] == "vllm":
        result["runtime"] = ssh_serving_program.runtime_evidence(evidence.get("runtime"))
    if operation == "prepare" and "adopt_identity" not in result:
        if (
            not isinstance(evidence.get("model"), str)
            or not Path(evidence["model"]).is_absolute()
            or len(evidence["model"]) > 4096
            or not evidence["model"].isprintable()
            or not re.fullmatch(r"[a-f0-9]{64}", str(evidence.get("model_revision", "")))
        ):
            raise ValueError("Invalid remote model evidence")
        result.update(model=evidence["model"], model_revision=evidence["model_revision"])
    return result


def definition(root: Path, spec: LaunchSpec, revision: str) -> tuple[SSHServer, dict]:
    record = load(root)["servers"].get(spec.ssh_server)
    if not record or record["revision"] != revision:
        raise ValueError("SSH server changed; reopen its serving form and review again")
    return SSHServer(**record["definition"]).validate(), record


def inspect(request: dict) -> dict:
    try:
        spec = LaunchSpec(**request["spec"])
        validate(spec)
        root = Path(request["config_dir"])
        server, record = definition(root, spec, request["server_revision"])
        agent = request.get("agent_socket", "")
        refs = references(server, agent)
        operation = request["operation"]
        payload = {"operation": operation, "spec": asdict(spec), "models_dir": server.models_dir}
        previous = request.get("evidence", {})
        if operation == "prepare" and previous:
            if (
                previous.get("server_revision") != record["revision"]
                or previous.get("references") != refs
            ):
                raise ValueError("SSH definition or credential references changed; test again")
            payload["evidence"] = previous
        result = run(
            server,
            operation,
            agent,
            program=program(),
            payload=payload,
            projector=decoded,
            timeout=50 if spec.engine == "vllm" else 15,
        )
        if result["status"] != "ok":
            return {"error": result["message"]}
        if load(root)["servers"].get(server.id) != record or references(server, agent) != refs:
            raise ValueError("SSH definition or credential references changed; test again")
        checked = result["data"]
        if checked.get("error"):
            return checked
        if checked["engine"] != spec.engine:
            raise ValueError("Remote engine evidence does not match the requested engine")
        if spec.adopt_pid:
            if checked.get("adopt_identity", {}).get("pid") != spec.adopt_pid:
                raise ValueError("Remote adoption identity does not match the reviewed PID")
            checked["selected_devices"] = []
        else:
            if "adopt_identity" in checked:
                raise ValueError("Unexpected remote adoption evidence")
            checked["selected_devices"] = ssh_serving_program.selection(
                asdict(spec), checked["devices"]
            )
        checked.update(server_revision=record["revision"], references=refs)
        if operation == "prepare":
            check_loopback_port(spec.local_port)
            return {"evidence": checked}
        return checked
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {
            "error": clean(str(exc), 240)
            if isinstance(exc, ValueError)
            else "SSH preflight failed; check server, engine, model and tunnel port"
        }


def serve(request: dict, emit, stopped: threading.Event) -> None:
    from .config import load_config

    cfg = load_config()
    spec = LaunchSpec(**request["spec"])
    validate(spec)
    expected = request["evidence"]
    server, record = definition(cfg.config_dir, spec, expected["server_revision"])
    agent = request.get("agent_socket", "")
    if references(server, agent) != expected["references"]:
        raise ValueError("SSH credential references changed; review again")
    identity = request["id"]
    if not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Invalid server identity")
    alias = spec.model_id if spec.adopt_pid else "klaude-" + identity[:16]
    connection = ModelConnection(
        "serve-" + identity[:16],
        spec.name,
        "openai_compatible",
        f"http://127.0.0.1:{spec.local_port}/v1",
    )
    value = {
        "id": identity,
        "spec": asdict(spec),
        "state": "starting",
        "model": alias,
        "owner": request.get("owner", ""),
        "helper_pid": os.getpid(),
        "helper_start": process_identity(os.getpid())["start"],
        "endpoint": asdict(connection),
        "ssh": {"id": server.id, "name": server.name, "host": server.host},
        "updated_at": time.time(),
        "remote_cleanup": "not_started",
        "selected_devices": expected.get("selected_devices", []),
        "adopted": False,
    }
    publish(cfg.data_dir, identity, value)
    process = None
    registered = False
    remote_ready = False
    acknowledged = False
    pending = bytearray()
    errors = bytearray()
    logs: deque[str] = deque(maxlen=500)
    last_log = 0.0
    next_beat = 0.0
    ending = None
    adoption_deadline = None
    try:
        payload = (
            json.dumps(
                {
                    "operation": "serve",
                    "id": identity,
                    "spec": asdict(spec),
                    "models_dir": server.models_dir,
                    "evidence": expected,
                }
            )
            + "\n"
        ).encode()
        if len(payload) > 16_384:
            raise ValueError("Remote launch request exceeded its bound")
        check_loopback_port(spec.local_port)
        if stopped.is_set():
            return
        process = subprocess.Popen(
            arguments(server, agent, program=program(), forward=(spec.local_port, spec.port)),
            env=environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert (
            process.stdin is not None and process.stdout is not None and process.stderr is not None
        )
        process.stdin.write(payload)
        process.stdin.flush()
        value["remote_cleanup"] = "unconfirmed"
        emit({"id": identity, "state": "starting", "message": "Opening verified SSH tunnel"})
        deadline = time.monotonic() + (215 if spec.engine == "vllm" else 185)
        streams = {process.stdout, process.stderr}
        with httpx.Client(
            base_url=f"http://127.0.0.1:{spec.local_port}",
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(1, connect=0.5),
        ) as client:
            health_check = ssh_serving_program.HealthCheck(lambda: health(client, alias))
            while streams:
                now = time.monotonic()
                if stopped.is_set() and ending is None:
                    process.stdin.close()
                    # The outer helper allows eight seconds: receive the remote
                    # cleanup receipt before its supervisor has to force a stop.
                    ending = now + 6
                if ending is not None and now >= ending:
                    break
                if ending is None and now >= next_beat:
                    process.stdin.write(b".\n")
                    process.stdin.flush()
                    next_beat = now + 1
                for stream in select.select(list(streams), [], [], 0.1)[0]:
                    chunk = os.read(stream.fileno(), 8192)
                    if not chunk:
                        streams.discard(stream)
                        continue
                    if stream is process.stderr:
                        errors.extend(chunk)
                        if len(errors) > 65_536:
                            raise ValueError("SSH error output exceeded its bound")
                        continue
                    pending.extend(chunk)
                    while b"\n" in pending:
                        line, _, rest = pending.partition(b"\n")
                        pending = bytearray(rest)
                        if len(line) > 65_536:
                            raise ValueError("Remote server event exceeded its bound")
                        event = json.loads(line)
                        state = event.get("state")
                        if state == "log":
                            text = clean(event.get("text", ""), 4096)
                            text = re.sub(
                                r"(?i)((?:api[_ -]?key|token|authorization|password)\s*[:=]\s*)\S+",
                                r"\1[redacted]",
                                text,
                            )
                            logs.append(text)
                        elif state in {"starting", "ready", "owned"}:
                            if type(event.get("pid")) is not int or event["pid"] < 2:
                                raise ValueError("Invalid remote process evidence")
                            value["remote_pid"] = event["pid"]
                            if state == "starting":
                                publish(cfg.data_dir, identity, value)
                                emit(
                                    {
                                        "id": identity,
                                        "state": "starting",
                                        "message": "Loading remote GPU model"
                                        if spec.gpu_layers or spec.engine == "vllm"
                                        else "Loading remote CPU model",
                                    }
                                )
                            if state == "ready":
                                if event.get("model") != alias:
                                    raise ValueError("Remote model identity mismatch")
                                if spec.adopt_pid and event["pid"] != spec.adopt_pid:
                                    raise ValueError("Remote PID identity mismatch")
                                remote_ready = True
                                if spec.adopt_pid:
                                    adoption_deadline = now + 10
                            if state == "owned":
                                if (
                                    not spec.adopt_pid
                                    or not registered
                                    or event["pid"] != spec.adopt_pid
                                    or event.get("model") != alias
                                ):
                                    raise ValueError("Invalid remote adoption acknowledgement")
                                value.update(state="ready", adopted=True, updated_at=time.time())
                                publish(cfg.data_dir, identity, value)
                                emit(
                                    {
                                        **value,
                                        "message": "Remote server adopted; stops on client exit",
                                    }
                                )
                        elif state in {"stopped", "failed"}:
                            acknowledged = event.get("cleanup") == "confirmed"
                            if event.get("cleanup") == "not_started":
                                value["remote_cleanup"] = "not_started"
                            if state == "failed":
                                raise ValueError(
                                    clean(
                                        event.get("message")
                                        or "Remote engine failed; inspect Logs and reviewed paths",
                                        240,
                                    )
                                )
                            if not stopped.is_set():
                                raise ValueError("Remote owner lease ended unexpectedly")
                        else:
                            raise ValueError("Invalid remote server event")
                    if len(pending) > 65_536:
                        raise ValueError("Remote server event exceeded its bound")
                if logs and now - last_log >= 1:
                    atomic_write_private(
                        cfg.data_dir / "model-serving" / (identity + ".log"),
                        "".join(logs).encode()[-MAX_LOG:].decode("utf8", "replace"),
                    )
                    last_log = now
                if not registered and remote_ready and ending is None:
                    if health_check.poll() and listener_owned(spec.local_port, os.getpgrp()):
                        if (
                            load(cfg.config_dir)["servers"].get(server.id) != record
                            or references(server, agent) != expected["references"]
                        ):
                            raise ValueError(
                                "SSH definition or credentials changed before registration"
                            )
                        registry = connection_registry(cfg)
                        registry.migrate(cfg)
                        registry.add(connection)
                        registered = True
                        if spec.adopt_pid:
                            if not stopped.is_set():
                                process.stdin.write(b"A\n")
                                process.stdin.flush()
                        else:
                            value.update(state="ready", updated_at=time.time())
                            publish(cfg.data_dir, identity, value)
                            emit(
                                {
                                    **value,
                                    "message": "Remote server ready; tunnel endpoint registered",
                                }
                            )
                if not registered and ending is None and now >= deadline:
                    raise ValueError("Remote server startup timed out; inspect Logs")
                if (
                    adoption_deadline is not None
                    and not value.get("adopted")
                    and ending is None
                    and now >= adoption_deadline
                ):
                    raise ValueError(
                        "Remote takeover acknowledgement timed out; inspect cleanup status"
                    )
                if acknowledged:
                    break
        if not stopped.is_set():
            raise ValueError("SSH connection lost; remote cleanup awaits its bounded owner lease")
        value["state"] = "stopped"
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        value.update(
            state="failed",
            message=clean(str(exc), 240)
            if isinstance(exc, ValueError)
            else "SSH tunnel failed; check connectivity, identity and reviewed ports",
        )
    finally:
        if process is not None:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            for pipe in (process.stdout, process.stderr):
                if pipe:
                    pipe.close()
        if logs:
            atomic_write_private(
                cfg.data_dir / "model-serving" / (identity + ".log"),
                "".join(logs).encode()[-MAX_LOG:].decode("utf8", "replace"),
            )
        if registered:
            try:
                disable_connection(cfg, connection)
            except (OSError, ValueError):
                emit(
                    {
                        "id": identity,
                        "state": "warning",
                        "message": "Tunnel closed; endpoint disable unconfirmed; reload Models",
                    }
                )
        value["remote_cleanup"] = "confirmed" if acknowledged else value["remote_cleanup"]
        if value["remote_cleanup"] == "unconfirmed":
            emit(
                {
                    "id": identity,
                    "state": "warning",
                    "message": "Remote cleanup unconfirmed; owner lease expires within 8 seconds",
                }
            )
        value.update(state="stopped" if stopped.is_set() else "failed", updated_at=time.time())
        publish(cfg.data_dir, identity, value)
        emit(
            {
                "id": identity,
                "state": value["state"],
                "remote_cleanup": value["remote_cleanup"],
                "message": value.get(
                    "message",
                    "Remote server stopped"
                    if acknowledged
                    else "SSH request ended; see cleanup status",
                ),
            }
        )

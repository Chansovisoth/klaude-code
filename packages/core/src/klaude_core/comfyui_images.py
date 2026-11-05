"""Exact owned ComfyUI graph jobs; never replay generation or interrupt globally."""

from __future__ import annotations

import base64
import json
import re
import time
import uuid

import httpx

from . import comfyui_managed as managed
from .comfyui_bundle import sd15_workflow
from .settings_store import atomic_write_private, read_settings, settings_lock


def graph(record: dict) -> dict:
    from .comfyui_models import parse

    bundle = record["evidence"].get("bundle")
    return sd15_workflow(
        record["id"],
        record["prompt"],
        width=record["width"],
        height=record["height"],
        steps=record["steps"],
        seed=record["seed"],
        negative_prompt=record.get("negative_prompt", ""),
        checkpoint=parse(bundle).installed_name if bundle else None,
    )


def bound(cfg, record: dict) -> str:
    expected = record["evidence"]["server"]
    if managed.server_record(cfg) != expected:
        raise ValueError("The owned ComfyUI server instance changed; inspect this job")
    return record["evidence"]["endpoint"]


def remote_id(value) -> str:
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise ValueError("ComfyUI returned an invalid job ID; submission outcome unknown") from None
    return value


def observe(cfg, record: dict) -> tuple[str, dict]:
    from .image_generation import packet

    url, identity = bound(cfg, record), remote_id(record["remote_id"])
    data = packet(url, f"/history/{identity}")
    if data and set(data) != {identity}:
        raise ValueError("ComfyUI returned another job's history")
    if not data:
        queued = packet(url, "/queue")
        for key, state in (("queue_running", "running_remote"), ("queue_pending", "queued_remote")):
            rows = queued.get(key, [])
            if not isinstance(rows, list) or len(rows) > 1000:
                raise ValueError("ComfyUI queue response exceeds its bound")
            if any(isinstance(row, list) and len(row) > 1 and row[1] == identity for row in rows):
                return state, {}
        return "unknown", {}
    item = data[identity]
    if not isinstance(item, dict):
        raise ValueError("ComfyUI returned invalid job history")
    prompt = item.get("prompt", [])
    if (
        not isinstance(prompt, list)
        or len(prompt) < 4
        or prompt[1] != identity
        or prompt[2] != graph(record)
        or not isinstance(prompt[3], dict)
        or prompt[3].get("client_id") != record["id"]
    ):
        raise ValueError("ComfyUI job does not match the reviewed graph and owner")
    status = item.get("status", {})
    if not isinstance(status, dict) or not isinstance(status.get("messages", []), list):
        raise ValueError("ComfyUI returned invalid job status")
    if status.get("completed") is True and status.get("status_str") == "success":
        return "completed_remote", item
    if status.get("status_str") == "error":
        interrupted = any(
            isinstance(message, list) and bool(message) and message[0] == "execution_interrupted"
            for message in status.get("messages", [])
        )
        return "cancelled" if interrupted else "failed", item
    return "running_remote", item


def output(cfg, record: dict, item: dict) -> dict:
    from .image_generation import IMAGE_LIMIT, store_output

    outputs = item.get("outputs", {})
    if not isinstance(outputs, dict) or not isinstance(outputs.get("9"), dict):
        raise ValueError("ComfyUI returned invalid image output")
    images = outputs["9"].get("images", [])
    if (
        set(outputs) != {"9"}
        or not isinstance(images, list)
        or len(images) != 1
        or not isinstance(images[0], dict)
    ):
        raise ValueError("ComfyUI must return the one reviewed output image")
    image = images[0]
    name = image.get("filename", "")
    if (
        image.get("type") != "output"
        or image.get("subfolder") != "klaude"
        or not isinstance(name, str)
        or not re.fullmatch(re.escape(record["id"]) + r"_\d+_\.png", name)
    ):
        raise ValueError("ComfyUI output does not belong to this exact job")
    url = bound(cfg, record)
    pixels = bytearray()
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        with client.stream(
            "GET",
            url + "/view",
            params={"filename": name, "subfolder": "klaude", "type": "output"},
            headers={"Accept-Encoding": "identity"},
        ) as response:
            if (
                response.status_code != 200
                or response.headers.get("content-encoding", "identity") != "identity"
            ):
                raise ValueError("ComfyUI output unavailable")
            for chunk in response.iter_bytes():
                pixels.extend(chunk)
                if len(pixels) > IMAGE_LIMIT:
                    raise ValueError("ComfyUI image exceeds its byte limit")
    result = store_output(
        cfg,
        record,
        record["remote_id"],
        {
            "id": record["remote_id"],
            "kind": "img_gen",
            "result": {"images": [{"b64_json": base64.b64encode(pixels).decode()}]},
        },
    )
    try:
        path = managed.root(cfg) / "last-generation.json"
        with settings_lock(path):
            current = read_settings(path)
            checks = current.get("models", {})
            if not isinstance(checks, dict):
                checks = {}
            entry = {
                "installation": record["evidence"]["installation"],
                "job": record["id"],
                "checked_at": time.time(),
            }
            checks[record["settings"]["model"]] = entry
            # A presentation cache never becomes an unbounded job history.
            checks = dict(list(checks.items())[-50:])
            atomic_write_private(path, json.dumps({**entry, "models": checks}))
    except OSError:
        pass  # Saved output wins over an unavailable presentation cache.
    return result


def generate(cfg, record: dict, progress) -> dict:
    from .image_generation import reviewed_binding

    with managed.install_lock(cfg, shared=True):
        reviewed_binding(cfg, record)
        return _generate(cfg, record, progress)


def _generate(cfg, record: dict, progress) -> dict:
    from .image_generation import DEADLINE, packet, publish

    try:
        url = bound(cfg, record)
        result = packet(url, "/prompt", {"prompt": graph(record), "client_id": record["id"]})
        if result.get("node_errors"):
            record.update(status="failed")
            publish(cfg, record)
            raise ValueError("ComfyUI rejected this graph; repair the bundle")
        identity = remote_id(result.get("prompt_id"))
        record.update(remote_id=identity, status="running")
        publish(cfg, record)
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            status, item = observe(cfg, record)
            progress({"job": record["id"], "status": status})
            if status == "completed_remote":
                return output(cfg, record, item)
            if status in {"cancelled", "failed"}:
                record.update(status=status)
                publish(cfg, record)
                raise ValueError(f"ComfyUI job {status}; no output saved")
            time.sleep(0.5)
        raise ValueError("ComfyUI generation reached its five-minute deadline")
    except BaseException:
        if record["status"] not in {"failed", "cancelled", "complete"}:
            record.update(status="unknown")
            publish(cfg, record)
        raise


def refresh(cfg, record: dict) -> dict:
    from .image_generation import publish

    if record.get("queue_cancelled") is True and record.get("status") == "cancelled":
        return {
            "status": "cancelled",
            "job": record["id"],
            "recoverable": False,
            "message": "Exact queued ComfyUI job was removed",
        }
    state, _ = observe(cfg, record)
    record.update(status=state)
    publish(cfg, record)
    return {
        "status": state,
        "job": record["id"],
        "recoverable": state not in {"failed", "cancelled"},
        "message": "ComfyUI state checked; no output retrieved or generation submitted",
    }


def recover(cfg, record: dict) -> dict:
    state, item = observe(cfg, record)
    if state != "completed_remote":
        raise ValueError("ComfyUI output is not complete; no generation resubmitted")
    return output(cfg, record, item)


def cancel(cfg, record: dict) -> dict:
    from .image_generation import packet

    url = bound(cfg, record)
    identity = remote_id(record.get("remote_id"))
    before, _ = observe(cfg, record)
    response = packet(url, f"/api/jobs/{identity}/cancel", {})
    if type(response.get("cancelled")) is not bool:
        raise ValueError("ComfyUI cancellation acknowledgement is invalid")
    result = refresh(cfg, record)
    if (
        before == "queued_remote"
        and response["cancelled"] is True
        and result["status"] == "unknown"
    ):
        # Pinned PromptQueue moves running jobs into history under one mutex.
        # Re-read after queue absence: a running/completion race has history,
        # while a successfully dequeued job has neither queue nor history.
        after, _ = observe(cfg, record)
        if after == "unknown":
            from .image_generation import publish

            record.update(status="cancelled", queue_cancelled=True)
            publish(cfg, record)
            result = {"status": "cancelled", "job": record["id"], "recoverable": False}
        else:
            result = refresh(cfg, record)
    confirmed = result["status"] in {"cancelled", "failed", "completed_remote"}
    return {
        **result,
        "cleanup": "Confirmed" if confirmed else "Unconfirmed",
        "message": "Only this acknowledged ComfyUI job was targeted. "
        + ("Terminal state confirmed." if confirmed else "Server cleanup is unconfirmed."),
    }

"""Reviewed native stable-diffusion.cpp jobs; no chat, installers or model selection."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import secrets
import time
import uuid
from collections.abc import Callable
from itertools import islice
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from .library_artifacts import ArtifactStore, image_header, regular_path
from .model_connections import normalize_model_url
from .settings_store import atomic_write_private, read_settings, settings_lock

METADATA_LIMIT = 512_000
RESULT_LIMIT = 12_000_000
IMAGE_LIMIT = 8 * 1024 * 1024
DEADLINE = 300
ID = re.compile(r"[0-9a-f]{32}\Z")
REMOTE_ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
DEFAULTS = {"enabled": False, "endpoint": "", "model": "", "revision": ""}


def endpoint(value: str) -> str:
    if not isinstance(value, str) or len(value) > 500:
        raise ValueError("Enter an HTTP(S) image server URL")
    normalized = normalize_model_url(value, "ollama")
    if value.strip().rstrip("/").endswith("/sdcpp/v1"):
        return normalized.removesuffix("/sdcpp")
    return normalized


def text(value: Any, limit: int, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > limit
        or (not empty and not value.strip())
        or any(not c.isprintable() and c != "\n" for c in value)
    ):
        raise ValueError(f"Enter {'0' if empty else '1'}–{limit} printable characters")
    return value.strip()


def read(cfg: Any) -> dict:
    path = cfg.config_dir / "image-generation.json"
    regular_path(path)
    data = {**DEFAULTS, **read_settings(path)}
    if type(data["enabled"]) is not bool or not isinstance(data["revision"], str):
        raise ValueError("Image generation settings are invalid; review configuration")
    if data["endpoint"]:
        data["endpoint"] = endpoint(data["endpoint"])
    text(data["model"], 200, empty=True)
    if data["enabled"] and not (data["endpoint"] and data["model"]):
        raise ValueError("Test and save an image server/model before enabling generation")
    return {key: data[key] for key in DEFAULTS}


def save(
    cfg: Any, candidate: dict, expected: str, *,
    before_publish: Callable[[dict, dict], None] | None = None,
) -> dict:
    path = cfg.config_dir / "image-generation.json"
    regular_path(path)
    with settings_lock(path):
        before = read(cfg)
        if before["revision"] != expected:
            raise ValueError("Image generation settings changed; Reload before saving")
        value = {key: candidate[key] for key in DEFAULTS if key != "revision"}
        if type(value["enabled"]) is not bool:
            raise ValueError("Invalid generation enable switch")
        value["endpoint"] = endpoint(value["endpoint"]) if value["endpoint"] else ""
        value["model"] = text(value["model"], 200, empty=not value["enabled"])
        if value["enabled"] and not value["endpoint"]:
            raise ValueError("Choose an image server before enabling generation")
        value["revision"] = uuid.uuid4().hex
        if before_publish is not None:
            before_publish(before, value)
        atomic_write_private(path, json.dumps(value) + "\n")
        return value


def packet(
    url: str, path: str, payload: dict | None = None, *, limit: int = METADATA_LIMIT
) -> dict:
    # Explicit user-configured service, including LAN hosts. No redirects, proxies,
    # URL credentials, arbitrary result URLs, retries or ambient provider keys.
    with httpx.Client(
        timeout=httpx.Timeout(6, connect=3), trust_env=False, follow_redirects=False
    ) as client:
        with client.stream(
            "POST" if payload is not None else "GET",
            url + path,
            json=payload if payload is not None else None,
        ) as response:
            if response.status_code not in {200, 202}:
                raise ValueError(
                    f"Image server returned HTTP {response.status_code}; no retry sent"
                )
            body = bytearray()
            for part in response.iter_bytes(65536):
                body.extend(part)
                if len(body) > limit:
                    raise ValueError("Image server response exceeds its byte limit")
    try:
        result = json.loads(body)
    except (ValueError, UnicodeError):
        raise ValueError("Image server returned invalid JSON") from None
    if not isinstance(result, dict):
        raise ValueError("Image server returned an invalid object")
    return result


def inspect(url: str) -> dict:
    url = endpoint(url)
    data = packet(url, "/sdcpp/v1/capabilities")
    if "img_gen" not in data.get("supported_modes", []) or "png" not in data.get(
        "output_formats_by_mode", {}
    ).get("img_gen", []):
        raise ValueError("This endpoint does not declare native PNG image generation")
    model = text(data.get("model", {}).get("name"), 200)
    defaults = data.get("defaults_by_mode", {}).get("img_gen", {})
    limits = data.get("limits", {})
    # Retain only controls actually exposed by this adapter; no workflow, model
    # loading, arbitrary extra_args, filesystem paths or server-wide settings.
    checked = {}
    for name in ("min_width", "max_width", "min_height", "max_height"):
        number = limits.get(name)
        if type(number) is not int or not 1 <= number <= 65536:
            raise ValueError("Image server has invalid size capabilities")
        checked[name] = number
    if any(checked["min_" + axis] > checked["max_" + axis] for axis in ("width", "height")):
        raise ValueError("Image server has inconsistent size capabilities")
    sampling = defaults.get("sample_params", {})
    method = text(sampling.get("sample_method"), 100)
    scheduler = text(sampling.get("scheduler"), 100)
    if (
        not isinstance(data.get("samplers"), list)
        or method != "default" and method not in data["samplers"]
        or not isinstance(data.get("schedulers"), list)
        or scheduler != "default" and scheduler not in data["schedulers"]
    ):
        raise ValueError("Image server has invalid sampler defaults")
    features = data.get("features_by_mode", {}).get("img_gen", {})
    evidence = {
        "endpoint": url,
        "model": model,
        "limits": checked,
        "sampler": method,
        "scheduler": scheduler,
        "cancel_queued": features.get("cancel_queued") is True,
        "cancel_generating": features.get("cancel_generating") is True,
    }
    evidence["revision"] = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    return evidence


def cancellation_notice(evidence: dict) -> str:
    if evidence["cancel_generating"]:
        return "Cancel targets this job only. Lost replies can leave its outcome unknown."
    return (
        "Only queued jobs can be cancelled; the server may continue after Cancel or the "
        "client deadline. Recover completed output by job ID."
    )


def prepare(
    cfg: Any,
    prompt: str,
    *,
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    seed: int = -1,
    session: str = "",
) -> dict:
    settings = read(cfg)
    if not settings["enabled"]:
        raise ValueError("Image generation is OFF; configure Model Defaults → Image generation")
    evidence = inspect(settings["endpoint"])
    if evidence["model"] != settings["model"]:
        raise ValueError(
            "The server's loaded model changed; test and save the new model explicitly"
        )
    if not evidence["cancel_queued"]:
        raise ValueError("This adapter requires declared cancellation of queued jobs")
    prompt = text(prompt, 2000)
    for name, number in (("width", width), ("height", height)):
        limits = evidence["limits"]
        if (
            type(number) is not int
            or number % 64
            or not 256 <= number <= 1024
            or not limits["min_" + name] <= number <= limits["max_" + name]
        ):
            raise ValueError("Use supported dimensions, multiples of 64 between 256 and 1024")
    if type(steps) is not int or not 1 <= steps <= 50:
        raise ValueError("Sampling steps must be 1–50")
    if type(seed) is not int or not -1 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be -1 (random) or 0–4294967295")
    return {
        "id": uuid.uuid4().hex,
        "settings": settings,
        "evidence": evidence,
        "prompt": prompt,
        "width": width,
        "height": height,
        "steps": steps,
        "seed": secrets.randbelow(2**32) if seed == -1 else seed,
        "session": text(session, 100, empty=True),
    }


def job_path(cfg: Any, identity: str) -> Path:
    if not isinstance(identity, str) or not ID.fullmatch(identity):
        raise ValueError("Use the exact image-generation job ID")
    path = cfg.data_dir / "image-generation" / (identity + ".json")
    regular_path(path)
    return path


def job(cfg: Any, identity: str) -> dict:
    path = job_path(cfg, identity)
    if not path.exists():
        raise ValueError("Image-generation job is unavailable")
    if path.stat().st_size > 32_000:
        raise ValueError("Invalid image-generation job record")
    record = read_settings(path)
    if record.get("id") != identity:
        raise ValueError("Image-generation receipt identity changed")
    return record


def publish(cfg: Any, record: dict) -> None:
    path = job_path(cfg, record["id"])
    with settings_lock(path):
        atomic_write_private(path, json.dumps(record) + "\n")


def saved_output(cfg: Any, record: dict) -> dict | None:
    """A committed image wins over a lost receipt; deleted output stays deleted."""
    stored = ArtifactStore(cfg.data_dir / "library").generated_for_job(record["id"])
    if stored:
        record.update(status="complete", artifact=stored["id"])
        publish(cfg, record)
        return {
            "status": "complete", "artifact": stored["id"], "job": record["id"],
            "message": "Output already saved in Media",
        }
    if record.get("artifact"):
        raise ValueError("Saved image was removed from Media; its receipt cannot restore it")
    return None


def cancel(cfg: Any, identity: str) -> dict:
    if not job_path(cfg, identity).exists():
        return {
            "status": "not_started",
            "cleanup": "Not started",
            "message": "No local job was accepted; generation was not submitted",
        }
    record = job(cfg, identity)
    stored = saved_output(cfg, record)
    if stored:
        return stored
    remote = record.get("remote_id")
    outcome, terminal, observed = "Unconfirmed", "", ""
    if isinstance(remote, str) and REMOTE_ID.fullmatch(remote):
        try:
            # A scoped native ID never becomes an arbitrary route or global stop.
            packet(record["settings"]["endpoint"], f"/sdcpp/v1/jobs/{remote}/cancel", {})
        except (ValueError, httpx.HTTPError):
            pass
        try:
            # A rejected cancel (including native HTTP 409 while generating)
            # does not prevent observing this exact job's current state.
            status = packet(
                record["settings"]["endpoint"], f"/sdcpp/v1/jobs/{remote}", limit=RESULT_LIMIT
            )
            if status.get("id") == remote and status.get("kind") == "img_gen":
                observed = status.get("status", "")
                if observed in {"cancelled", "failed", "completed"}:
                    outcome, terminal = "Confirmed", observed
        except (ValueError, httpx.HTTPError):
            pass
    local_status = {
        "completed": "completed_remote", "cancelled": "cancelled", "failed": "failed",
    }.get(terminal, "running_remote" if observed == "generating" else "unknown")
    record.update(status=local_status, cleanup=outcome)
    publish(cfg, record)
    return {
        "status": record["status"],
        "message": (
            "Server completed before cancellation. Output is not saved; review recovery explicitly"
            if terminal == "completed"
            else "Local request stopped; server is still generating. "
            "Recover completed output using the saved job ID. Server cleanup: Unconfirmed"
            if observed == "generating"
            else "Local request stopped. Server cleanup: " + outcome
        ),
        "job": identity,
        "cleanup": outcome,
        "recoverable": bool(
            isinstance(remote, str) and REMOTE_ID.fullmatch(remote)
            and local_status not in {"cancelled", "failed"}
        ),
    }


def reviewed_binding(cfg: Any, spec: dict) -> None:
    check = prepare(
        cfg, spec["prompt"], **{k: spec[k] for k in ("width", "height", "steps", "seed", "session")}
    )
    if check["settings"] != spec["settings"] or check["evidence"] != spec["evidence"]:
        raise ValueError("Image settings or server capabilities changed; review again")


def store_output(cfg: Any, spec: dict, remote: str, result: dict) -> dict:
    """The same pixel, revision and atomic-publication boundary for run and recovery."""
    if result.get("id") != remote or result.get("kind") != "img_gen":
        raise ValueError("Image server returned a different job identity")
    output = result.get("result")
    images = output.get("images") if isinstance(output, dict) else None
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
        raise ValueError("Image server must return exactly one generated PNG")
    encoded = images[0].get("b64_json")
    if not isinstance(encoded, str) or len(encoded) > (IMAGE_LIMIT + 2) // 3 * 4:
        raise ValueError("Generated image exceeds the 8 MiB bound")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Generated image is not valid base64") from None
    mime, width, height = image_header(data[:65536])
    if (
        len(data) > IMAGE_LIMIT or mime != "image/png"
        or (width, height) != (spec["width"], spec["height"])
    ):
        raise ValueError("Generated PNG does not match the reviewed size")
    if read(cfg) != spec["settings"] or inspect(spec["settings"]["endpoint"]) != spec["evidence"]:
        raise ValueError("Image service changed during generation; output was not saved")
    with settings_lock(cfg.config_dir / "image-generation.json"):
        if read(cfg) != spec["settings"]:
            raise ValueError("Image settings changed before output save; review again")
        item = ArtifactStore(cfg.data_dir / "library").store_generated_image(data, spec, remote)
    spec.update(status="complete", artifact=item["id"])
    publish(cfg, spec)
    return {
        "status": "complete", "artifact": item["id"], "job": spec["id"],
        "model": spec["settings"]["model"],
    }


def recovery_review(cfg: Any, identity: str) -> dict:
    record = job(cfg, identity)
    if record.get("id") != identity:
        raise ValueError("Image-generation receipt identity changed")
    remote = record.get("remote_id")
    if not isinstance(remote, str) or not REMOTE_ID.fullmatch(remote):
        raise ValueError("No acknowledged server job ID; recovery cannot resubmit generation")
    reviewed_binding(cfg, record)
    return record


def recover(cfg: Any, identity: str, expected: dict | None = None) -> dict:
    record = job(cfg, identity)
    stored = saved_output(cfg, record)
    if stored:
        return stored
    record = recovery_review(cfg, identity)
    if expected is not None and any(
        record.get(key) != expected.get(key)
        for key in (
            "id", "settings", "evidence", "prompt", "width", "height", "steps", "seed",
            "session", "remote_id",
        )
    ):
        raise ValueError("Image receipt changed; review recovery again")
    result = packet(
        record["settings"]["endpoint"], f"/sdcpp/v1/jobs/{record['remote_id']}", limit=RESULT_LIMIT
    )
    if result.get("id") != record["remote_id"] or result.get("kind") != "img_gen":
        raise ValueError("Image server returned a different job identity")
    if result.get("status") != "completed":
        raise ValueError("Server output is not complete; no image saved or generation submitted")
    return store_output(cfg, record, record["remote_id"], result)


def history(cfg: Any, offset: int = 0) -> dict:
    if type(offset) is not int or not 0 <= offset <= 1000:
        raise ValueError("Image job offset must be 0–1000")
    root = cfg.data_dir / "image-generation"
    regular_path(root)
    if not root.exists():
        return {"items": [], "more": False, "invalid": 0}
    paths = list(islice(root.glob("*.json"), 1001))
    if len(paths) > 1000:
        raise ValueError("Job inventory exceeds 1000 receipts; "
                         "inspect exact IDs to remove old receipts")
    items, invalid = [], 0
    for path in paths:
        try:
            record = job(cfg, path.stem)
            created = record.get("created", 0)
            if not isinstance(created, (int, float)) or not 0 <= created <= 2**40:
                raise ValueError("Invalid job date")
            items.append({
                "job": record["id"], "status": text(record["status"], 40),
                "created": created, "model": text(record["settings"]["model"], 200),
                "endpoint": endpoint(record["settings"]["endpoint"]),
                "artifact": record.get("artifact", ""),
            })
        except (ValueError, OSError, KeyError, TypeError):
            invalid += 1
    items.sort(key=lambda item: (item["created"], item["job"]), reverse=True)
    return {"items": items[offset:offset + 100], "more": len(items) > offset + 100,
            "invalid": invalid}


def refresh(cfg: Any, identity: str) -> dict:
    record = job(cfg, identity)
    if stored := saved_output(cfg, record):
        return stored
    remote = record.get("remote_id")
    if not isinstance(remote, str) or not REMOTE_ID.fullmatch(remote):
        raise ValueError("No acknowledged server ID; its outcome cannot be checked safely")
    result = packet(record["settings"]["endpoint"], f"/sdcpp/v1/jobs/{remote}", limit=RESULT_LIMIT)
    if result.get("id") != remote or result.get("kind") != "img_gen":
        raise ValueError("Image server returned a different job identity")
    statuses = {"queued": "queued_remote", "generating": "running_remote",
                "completed": "completed_remote", "cancelled": "cancelled", "failed": "failed"}
    if result.get("status") not in statuses:
        raise ValueError("Image server returned an invalid job state")
    record.update(status=statuses[result["status"]])
    publish(cfg, record)
    return {"status": record["status"], "job": identity,
            "recoverable": result["status"] in {"queued", "generating", "completed"},
            "message": "Server state: " + result["status"] + ". No output retrieved into Media."}


def forget(cfg: Any, identity: str, expected: dict, *, abandon: bool = False) -> dict:
    path = job_path(cfg, identity)
    with settings_lock(path):
        record = job(cfg, identity)
        if record != expected:
            raise ValueError("Job receipt changed; review removal again")
        if type(abandon) is not bool:
            raise ValueError("Invalid tracking-abandonment confirmation")
        if (record["status"] not in {"complete", "completed_remote", "failed", "cancelled"}
                and not abandon):
            raise ValueError("Check the job or confirm abandoning tracking "
                             "before removing its receipt")
        path.unlink()
    return {"status": "forgotten", "job": identity,
            "message": "Private job receipt removed. Media images and server jobs are retained."}


def run(cfg: Any, spec: dict, progress=lambda _: None) -> dict:
    # Rebuild and compare only the executable selection/controls, never silently
    # accept new settings, model, sampler or budget from a stale review.
    reviewed_binding(cfg, spec)
    path = job_path(cfg, spec["id"])
    with settings_lock(path):
        if path.exists():
            raise ValueError(
                "This job was already accepted; never resubmit an uncertain generation"
            )
        record = {**spec, "status": "submitting", "created": time.time()}
        atomic_write_private(path, json.dumps(record) + "\n")
    url, remote = spec["settings"]["endpoint"], ""
    try:
        response = packet(
            url,
            "/sdcpp/v1/img_gen",
            {
                "prompt": spec["prompt"],
                "width": spec["width"],
                "height": spec["height"],
                "seed": spec["seed"],
                "batch_count": 1,
                "output_format": "png",
                "embed_image_metadata": False,
                "preview": "none",
                "hires": {"enabled": False},
                "sample_params": {
                    # Native capabilities use "default" for automatic model-
                    # dependent selection, outside the explicit sampler catalog.
                    # Omit that field to retain the reviewed server default.
                    **({"sample_method": spec["evidence"]["sampler"]}
                       if spec["evidence"]["sampler"] != "default" else {}),
                    **({"scheduler": spec["evidence"]["scheduler"]}
                       if spec["evidence"]["scheduler"] != "default" else {}),
                    "sample_steps": spec["steps"],
                },
            },
        )
        remote = response.get("id", "")
        if (
            not isinstance(remote, str)
            or not REMOTE_ID.fullmatch(remote)
            or response.get("kind") != "img_gen"
        ):
            raise ValueError(
                "Image server returned an invalid job identity; submission outcome unknown"
            )
        record.update(remote_id=remote, status="running")
        publish(cfg, record)
        progress({"job": spec["id"], "status": "accepted"})
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            result = packet(url, f"/sdcpp/v1/jobs/{remote}", limit=RESULT_LIMIT)
            if result.get("id") != remote or result.get("kind") != "img_gen":
                raise ValueError("Image server returned a different job identity")
            status = result.get("status")
            if status == "completed":
                break
            if status in {"failed", "cancelled"}:
                raise ValueError("Image server job " + status + "; no output saved")
            if status not in {"queued", "generating"}:
                raise ValueError("Image server returned an invalid job state")
            time.sleep(0.5)
        else:
            raise ValueError("Image generation reached the five-minute deadline")
        return store_output(cfg, record, remote, result)
    except BaseException:
        # Disposable workers may be terminated while submitting/polling. Parent
        # cleanup reads this private receipt after reaping; it never resubmits.
        raise


def execute(request: dict) -> dict:
    cfg = SimpleNamespace(
        config_dir=Path(request["config_dir"]), data_dir=Path(request["data_dir"])
    )
    op = request["operation"]
    try:
        if op == "read":
            return {"settings": read(cfg)}
        if op == "inspect":
            return {"evidence": inspect(request["endpoint"])}
        if op == "save":
            candidate = request["settings"]
            if candidate["enabled"]:
                evidence = inspect(candidate["endpoint"])
                if evidence["model"] != candidate["model"]:
                    raise ValueError("Loaded model changed; Test again")
            return {"settings": save(cfg, candidate, request["revision"])}
        if op == "prepare":
            return {"spec": prepare(cfg, request["prompt"], **request.get("options", {}))}
        if op == "run":
            return run(cfg, request["spec"])
        if op == "recovery_review":
            return {"spec": recovery_review(cfg, request["id"])}
        if op == "recover":
            return recover(cfg, request["id"], request["spec"])
        if op == "history":
            return history(cfg, request.get("offset", 0))
        if op == "review_job":
            return {"record": job(cfg, request["id"])}
        if op == "refresh":
            return refresh(cfg, request["id"])
        if op == "forget":
            return forget(cfg, request["id"], request["spec"],
                          abandon=request.get("abandon", False))
        if op == "cancel":
            return cancel(cfg, request["id"])
        if op == "status":
            record = job(cfg, request["id"])
            return {
                "status": record["status"],
                "job": record["id"],
                "artifact": record.get("artifact", ""),
                "endpoint": record["settings"]["endpoint"],
                "model": record["settings"]["model"],
            }
        raise ValueError("Unknown image generation operation")
    except (ValueError, OSError, httpx.HTTPError, KeyError, TypeError) as exc:
        return {
            "status": "error",
            "message": str(exc)
            if isinstance(exc, ValueError)
            else "Image generation unavailable; check service and settings",
            "job": request.get("spec", {}).get("id", ""),
        }

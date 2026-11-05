"""Shared image readiness inventory; listing never contacts a model server."""

from __future__ import annotations

import json
import time
from typing import Any

from klaude_core.image_generation import endpoint, read
from klaude_core.settings_store import atomic_write_private, settings_lock

from . import image_install_plans as plans
from . import image_setups as setups
from .image_model_selection import digest
from .model_store import jobs, read_record

LIMIT = 2_000_000


def _settings_revision(cfg):
    return digest(read(cfg))


def record(cfg, key, readiness):
    path = cfg.data_dir / "image-readiness.json"
    with settings_lock(path):
        values = read_record(path, limit=LIMIT).get("items", {})
        values.pop(key, None)
        values[key] = {"readiness": readiness, "checked_at": time.time(),
                       "settings_revision": _settings_revision(cfg)}
        while len(values) > 100:
            del values[next(iter(values))]
        payload = json.dumps({"version": 1, "items": values})
        if len(payload.encode()) > LIMIT:
            raise ValueError("Readiness inventory exceeds its limit")
        atomic_write_private(path, payload)


def check(cfg, kind, identity, url=""):
    if kind == "setup":
        result = setups.check(cfg, identity)
        readiness = result["readiness"]
    elif kind == "plan":
        # Resolve locally before contacting a user-selected server.
        plans.get(cfg, identity)
        url = endpoint(url)
        try:
            result = plans.check_server(cfg, identity, url)
            rows = result["components"]
            missing = sum(row["visibility"] != "candidate" for row in rows)
            readiness = {"headline": f"{missing} planned paths need attention" if missing else
                         "Planned paths visible; select files for review",
                         "visibility": "missing_or_ambiguous" if missing else "path_candidates",
                         "compatibility": "unverified", "inference": "untested",
                         "can_review_load": False}
        except Exception:
            readiness = {"headline": "Service unavailable", "visibility": "unchecked",
                         "can_review_load": False, "compatibility": "unverified",
                         "inference": "untested"}
    else:
        raise ValueError("Choose a saved plan or setup")
    if kind == "plan":
        readiness["endpoint"] = url
    record(cfg, f"{kind}:{identity}", readiness)
    return readiness


def listing(cfg, journal):
    errors, plan_items, setup_items = [], {}, {}
    try:
        plan_items = plans._document(cfg)["items"]
    except (ValueError, OSError):
        errors.append("Installation plans unavailable")
    try:
        setup_items = setups._document(cfg)["items"]
    except (ValueError, OSError):
        errors.append("Saved setups unavailable")
    try:
        evidence = read_record(cfg.data_dir / "image-readiness.json", limit=LIMIT).get("items", {})
    except (ValueError, OSError):
        evidence = {}
        errors.append("Previous readiness checks unavailable")
    try:
        transfers = jobs(cfg, journal)["items"]
    except Exception:
        transfers = []
        errors.append("Recent transfers unavailable")
    recent: dict[str, dict[str, Any]] = {}
    for transfer in transfers:
        if transfer.get("artifact_id"):
            recent.setdefault(transfer["artifact_id"], transfer)
    transfers = list(recent.values())
    try:
        settings = read(cfg)
    except (ValueError, OSError):
        settings = {"endpoint": ""}
        errors.append("Image service settings unavailable")
    revision = digest(settings)
    items = []
    for kind, records in (("setup", setup_items), ("plan", plan_items)):
        for identity, value in reversed(list(records.items())):
            selection = value["selection"]
            plan_id = identity if kind == "plan" else selection.get("install_plan", "")
            plan = plan_items.get(plan_id, {}).get("selection")
            components = plan["components"] if plan else []
            artifacts = {row["artifact_id"] for row in components}
            children = [row for row in transfers if row.get("artifact_id") in artifacts]
            model_refs = [plan["model"]] if plan else []
            if kind == "setup" and plan:
                primary = next(row for row in components if row["slot"] == "primary")
                selected = [selection["files"].get(selection["models"].get(slot, ""), {})
                            for slot in ("model", "diffusion_model")]
                if not any(file.get("category") == primary["category"] and
                           (file.get("id") == primary["destination"] or
                            file.get("id", "").endswith("/" + primary["destination"]))
                           for file in selected):
                    model_refs = []
            observation = evidence.get(f"{kind}:{identity}")
            checked = observation and observation.get("settings_revision") == revision
            headline = observation["readiness"]["headline"] if checked else "Setup not checked"
            transfer_state = ""
            for state, label in (("unknown", "Download outcome unconfirmed"),
                                 ("cancelling", "Download stopping"), ("running", "Downloading"),
                                 ("accepted", "Download queued")):
                if any(row["state"] == state for row in children):
                    transfer_state = label
                    break
            if not transfer_state and any(row.get("paused") for row in children):
                transfer_state = "Download paused"
            if not transfer_state and any(row["state"] == "failed" for row in children):
                transfer_state = "Download failed"
            pending = None
            if kind == "setup" and journal is not None:
                from .image_model_selection import resource

                try:
                    pending = journal.fenced_operation(resource(selection["endpoint"]))
                except Exception:
                    if "Load status unavailable" not in errors:
                        errors.append("Load status unavailable")
            load_state = ("Load outcome unconfirmed" if pending.receipt.state == "unknown" else
                          "Model load in progress") if pending else ""
            items.append({"id": identity, "kind": kind, "plan_id": plan_id,
                          "plan_available": bool(plan), "name": selection.get("name") or
                          selection["recipe"]["name"], "model_refs": model_refs,
                          "endpoint": selection.get("endpoint", ""),
                          "created_at": value.get("created_at", value.get("checked_at")),
                          "headline": load_state or transfer_state or headline,
                          "live_status": bool(load_state or transfer_state),
                          "checked_at": observation.get("checked_at") if checked else None,
                          "readiness": observation["readiness"] if checked else None,
                          "transfers": [{key: row.get(key) for key in
                                         ("request_id", "model", "state", "paused", "progress",
                                          "artifact_id", "message")} for row in children]})
    return {"items": items, "errors": errors, "checked_at": time.time(),
            "default_endpoint": settings["endpoint"] if settings.get("provider", "sdcpp") ==
                                "sdcpp" else ""}

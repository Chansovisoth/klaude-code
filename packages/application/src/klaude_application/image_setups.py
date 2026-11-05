"""Immutable image setup drafts and read-only readiness evidence.

Saving a draft never authorizes downloads, runtime loading or settings changes.
Server file IDs are metadata identities, not content hashes or architecture proof.
"""

from __future__ import annotations

import json
import re
import time

from klaude_core.image_generation import endpoint, read
from klaude_core.settings_store import atomic_write_private, settings_lock

from .image_model_selection import catalog, digest, matches
from .model_store import read_record

VERSION = 1
MAX_SETUPS = 50
MAX_BYTES = 8_000_000


def _document(cfg):
    value = read_record(cfg.data_dir / "image-setups.json", limit=MAX_BYTES)
    if not value:
        return {"version": VERSION, "items": {}}
    if (value.get("version") != VERSION or not isinstance(value.get("items"), dict)
            or len(value["items"]) > MAX_SETUPS):
        raise ValueError("Saved setup inventory is invalid")
    for identity, item in value["items"].items():
        if (not isinstance(item, dict) or set(item) != {"selection", "created_at"}
                or digest(item["selection"]) != identity):
            raise ValueError("Saved setup identity changed")
    return value


def _get(cfg, identity):
    if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{64}", identity):
        raise ValueError("Choose an exact saved setup")
    record = _document(cfg)["items"].get(identity)
    if record is None:
        raise ValueError("Saved setup is unavailable")
    return record


def save(cfg, body):
    if set(body) not in ({"endpoint", "recipe", "models", "catalog_revision"},
                         {"endpoint", "recipe", "models", "catalog_revision", "install_plan"}):
        raise ValueError("Choose an exact setup draft")
    data = catalog(cfg, body["endpoint"])
    if data["catalog_revision"] != body["catalog_revision"]:
        raise ValueError("Image catalog changed; refresh before saving setup")
    recipe = next((r for r in data["recipes"] if r["id"] == body["recipe"]), None)
    values = body["models"]
    if recipe is None or not isinstance(values, dict):
        raise ValueError("Choose a server setup")
    slots = {s["id"]: s for s in recipe["slots"]}
    if set(values) - slots.keys():
        raise ValueError("Unknown setup component")
    files = {f["id"]: f for f in data["files"]}
    models = {key: values.get(key, "") for key in slots}
    for key, value in models.items():
        if (not isinstance(value, str) or value and
                (value not in files or files[value]["category"] not in slots[key]["categories"])):
            raise ValueError("Selected file is absent or has the wrong category")
    selection = {"version": VERSION, "endpoint": data["endpoint"], "recipe": recipe,
                 "models": models,
                 "files": {value: files[value] for value in models.values() if value}}
    if "install_plan" in body:
        from .image_install_plans import get

        get(cfg, body["install_plan"])
        selection["install_plan"] = body["install_plan"]
    identity = digest(selection)
    path = cfg.data_dir / "image-setups.json"
    with settings_lock(path):
        document = _document(cfg)
        if identity not in document["items"]:
            if len(document["items"]) >= MAX_SETUPS:
                raise ValueError("Saved setup limit reached (50)")
            document["items"][identity] = {"selection": selection, "created_at": time.time()}
            payload = json.dumps(document)
            if len(payload.encode()) > MAX_BYTES:
                raise ValueError("Saved setup inventory exceeds its size limit")
            atomic_write_private(path, payload)
    return {"version": VERSION, "id": identity, "selection": selection,
            "readiness": project(selection, data, read(cfg))}


def listing(cfg, url):
    url = endpoint(url)
    return {"version": VERSION, "items": [
        {"id": identity, "name": item["selection"]["recipe"]["name"],
         "models": item["selection"]["models"], "created_at": item["created_at"]}
        for identity, item in reversed(list(_document(cfg)["items"].items()))
        if item["selection"]["endpoint"] == url
    ]}


def project(selection, data, settings):
    """Derive independent evidence axes; never infer inference or compatibility."""
    recipe = selection["recipe"]
    current = next((r for r in data["recipes"] if r["id"] == recipe["id"]), None)
    changed = current != recipe
    files = {f["id"]: f for f in data["files"]}
    models = selection["models"]
    unavailable = [key for key, value in models.items() if value and
                   files.get(value) != selection["files"].get(value)]
    missing = [s["id"] for s in recipe["slots"] if s["required"] and not models[s["id"]]]
    alternatives = [group for group in recipe["required_any"]
                    if not any(models[key] for key in group)]
    complete = not (changed or unavailable or missing or alternatives)
    loaded = matches(data["runtime"], {"recipe": recipe["id"], "models": models})
    configured = bool(loaded and settings["enabled"] and
                      settings.get("provider", "sdcpp") == "sdcpp" and
                      settings["endpoint"] == selection["endpoint"] and
                      settings["model"] == data["model"])
    pending = data["pending"]
    headline = ("Load outcome unconfirmed" if pending and pending["state"] == "unknown" else
                "Model load in progress" if pending or data["runtime"]["state"] == "loading" else
                "Setup changed" if changed else "Selected files unavailable" if unavailable else
                "Missing components" if missing or alternatives else
                "Loaded and configured" if configured else "Loaded; default not applied" if loaded
                else "Components selected; ready for load review")
    return {"headline": headline, "checked_at": time.time(),
            "recipe": ("changed" if changed else
                       "incomplete" if missing or alternatives else "valid"),
            "visibility": ("missing_or_changed" if unavailable else "selected_files_visible"
                           if any(models.values()) else "no_files_selected"),
            "missing_slots": missing, "missing_alternatives": alternatives,
            "unavailable_slots": unavailable,
            "runtime": "unconfirmed" if pending and pending["state"] == "unknown" else
                       "loaded" if loaded else "other_model_loaded"
                       if data["runtime"]["state"] == "ready" else data["runtime"]["state"],
            "configuration": "applied" if configured else "not_applied",
            "compatibility": "unverified", "inference": "untested", "pending": pending,
            "can_review_load": complete and not pending and data["runtime"]["state"] != "loading"}


def check(cfg, identity):
    selection = _get(cfg, identity)["selection"]
    try:
        data = catalog(cfg, selection["endpoint"], refresh=True)
    except Exception:
        # Retain the exact draft without returning stale success or private errors.
        return {"version": VERSION, "id": identity, "selection": selection,
                "readiness": {"headline": "Service unavailable", "can_review_load": False,
                              "recipe": "unchecked", "visibility": "unchecked",
                              "runtime": "unchecked", "configuration": "unchecked",
                              "compatibility": "unverified", "inference": "untested"}}
    return {"version": VERSION, "id": identity, "selection": selection,
            "readiness": project(selection, data, read(cfg)), "catalog": data}


def forget(cfg, identity):
    """Forget only draft metadata; never remove weights, receipts or runtime state."""
    path = cfg.data_dir / "image-setups.json"
    with settings_lock(path):
        _get(cfg, identity)
        document = _document(cfg)
        del document["items"][identity]
        atomic_write_private(path, json.dumps(document))
    return {"version": VERSION, "forgotten": identity}

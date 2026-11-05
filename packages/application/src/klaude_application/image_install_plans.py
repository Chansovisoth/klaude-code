"""Bounded, immutable artifact plans. Each file still requires its own review."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time

from klaude_core.settings_store import atomic_write_private, settings_lock

from . import image_model_store as store
from .image_dependencies import RECIPES
from .image_model_selection import digest
from .model_store import read_record

VERSION = 1
MAX_PLANS = 50
MAX_BYTES = 2_000_000
PROFILES = {"file-only": "Selected file only", "flux3-klein": "FLUX.3 Klein",
            "flux3-klein-base": "FLUX.3 Klein Base"}


def child_request_id(request_id, plan_id, slot):
    if (not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id)
            or not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{64}", plan_id)
            or slot not in {"primary", "llm", "vae"}):
        raise ValueError("Invalid installation approval")
    return hashlib.sha256(f"image-plan:{request_id}:{plan_id}:{slot}".encode()).hexdigest()[:32]


def _document(cfg):
    value = read_record(cfg.data_dir / "image-install-plans.json", limit=MAX_BYTES)
    if not value:
        return {"version": VERSION, "items": {}}
    if (value.get("version") != VERSION or not isinstance(value.get("items"), dict)
            or len(value["items"]) > MAX_PLANS):
        raise ValueError("Install plan inventory is invalid")
    for identity, record in value["items"].items():
        if not isinstance(record, dict) or digest(record.get("selection")) != identity:
            raise ValueError("Install plan identity changed")
    return value


def get(cfg, identity):
    if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{64}", identity):
        raise ValueError("Choose a saved install plan")
    record = _document(cfg)["items"].get(identity)
    if record is None:
        raise ValueError("Install plan unavailable; build a new plan")
    return {"id": identity, **record}


def check_server(cfg, identity, url):
    """Report path candidates only; server metadata cannot verify weight content."""
    from .image_model_selection import catalog

    plan = get(cfg, identity)
    data = catalog(cfg, url, refresh=True)
    rows = []
    for component in plan["selection"]["components"]:
        destination = component["destination"]
        candidates = [file for file in data["files"]
                      if file["category"] == component["category"] and
                      (file["id"] == destination or file["id"].endswith("/" + destination))]
        rows.append({"slot": component["slot"], "label": component["label"],
                     "destination": destination, "candidates": candidates,
                     "visibility": "candidate" if len(candidates) == 1 else
                                   "ambiguous" if candidates else "not_visible",
                     "content": "unverified"})
    return {"plan": plan, "catalog": data, "components": rows}


def create(cfg, model, profile):
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError("Choose a supported install profile")
    choices = [("primary", "Selected model", model,
                "checkpoints" if profile == "file-only" else "diffusion_models")]
    choices += [(slot, label, f"hf.co/{repo}:{filename}", category)
                for slot, (label, repo, filename, category) in RECIPES.get(profile, {}).items()]
    components, present = [], []
    for slot, label, reference, category in choices:
        draft = {"operation": store.OPERATION, "connection": "image:sdcpp",
                 "model": reference, "category": category}
        fields = store.describe(cfg, draft)
        identity = store.artifact_identity(fields)
        with store.directory(fields, missing=True) as descriptor:
            exists = descriptor is not None and store._exists(descriptor, store.parts(fields)[-1])
        if exists:
            present.append(slot)
        components.append({"slot": slot, "label": label, "filename": fields["filename"],
                           "category": category, "destination": "/".join(store.parts(fields)),
                           "size": fields["size"], "revision": fields["revision"],
                           "sha256": fields["sha256"], "artifact_id": identity,
                           "source_url": (f"https://huggingface.co/{fields['repo']}/blob/"
                                          f"{fields['revision']}/{fields['filename']}"),
                           "draft": {**draft, "expected_artifact": identity}})
    selection = {"version": VERSION, "model": model, "profile": profile,
                 "name": PROFILES[profile], "components": components,
                 "total_bytes": sum(row["size"] for row in components)}
    identity = digest(selection)
    record = {"selection": selection, "checked_at": time.time(),
              "existing_unverified": present, "free_bytes": shutil.disk_usage(store.root()).free}
    path = cfg.data_dir / "image-install-plans.json"
    with settings_lock(path):
        document = _document(cfg)
        # Plans are metadata snapshots, never operation receipts or runtime defaults.
        document["items"].pop(identity, None)
        document["items"][identity] = record
        while len(document["items"]) > MAX_PLANS:
            del document["items"][next(iter(document["items"]))]
        payload = json.dumps(document)
        if len(payload.encode()) > MAX_BYTES:
            raise ValueError("Install plan inventory exceeds its size limit")
        atomic_write_private(path, payload)
    return {"id": identity, **record}

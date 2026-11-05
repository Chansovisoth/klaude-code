"""Reviewed Store checkpoint adoption and managed bundle removal."""

from __future__ import annotations

import json
import os
import re
import struct
import time
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urljoin

import httpx
from klaude_core import comfyui_managed as managed
from klaude_core.comfyui_bundle import ControlBundle, digest
from klaude_core.comfyui_models import LIMIT, architecture, inspect_header, key, parse
from klaude_core.image_generation import read as image_settings
from klaude_core.settings_store import atomic_write_private, read_settings, settings_lock

from . import image_model_store, model_store
from .operation_journal import OperationConflict, OperationJournal

OWNER = "web-admin"
OPERATIONS = frozenset({"comfy-import", "comfy-remove", "comfy-repair", "comfy-store-install"})


def source(cfg, model, *, expected_root=None):
    """Resolve only completed, witnessed Store downloads, never a caller's path."""
    if not isinstance(model, str) or len(model) > 500:
        raise ValueError("Choose an exact downloaded Store checkpoint")
    selected_root = expected_root or str(image_model_store.root())
    journal = OperationJournal(cfg.data_dir / "operations.db")
    found = {}
    from itertools import islice

    folder = cfg.data_dir / "model-manager/browser"
    for path in islice(folder.glob("*.json"), 1000):
        fields = model_store.read_record(path, limit=16_384)
        if (
            fields.get("model") != model
            or fields.get("endpoint") != "image:sdcpp"
            or fields.get("category", "checkpoints") != "checkpoints"
        ):
            continue
        receipt = journal.status(path.stem, OWNER)
        if (
            not receipt
            or receipt.state != "completed"
            or receipt.kind != "model-image-download"
            or not journal.settled_witness_after_matches(
                path.stem, OWNER, candidate=model_store.witness(fields, True)
            )
        ):
            continue
        if fields["root"] != selected_root:
            continue
        with image_model_store.directory(fields) as descriptor:
            if descriptor is None:
                continue
        candidate = Path(fields["root"]).joinpath(*image_model_store.parts(fields))
        if not candidate.name.lower().endswith(".safetensors"):
            raise ValueError("Setup not supported: managed imports require safetensors checkpoints")
        if managed.signature(candidate)[2] != fields["size"]:
            raise ValueError("Downloaded checkpoint changed; verify its Store download")
        found[image_model_store.artifact_identity(fields)] = (fields, candidate)
    if len(found) != 1:
        raise ValueError("Choose one completed, witnessed Store checkpoint download")
    return next(iter(found.values()))


def remote_source(cfg, model):
    """Read only pinned metadata and bounded Range responses before Install review."""
    from klaude_web.huggingface import hub_gguf_files

    match = re.fullmatch(r"hf\.co/([^:]+):([^:]+)", str(model))
    if not match:
        raise ValueError("Choose an exact Store safetensors variant")
    repo, filename = match.groups()
    image_model_store.parts({"repo": repo, "filename": filename})
    if not filename.lower().endswith(".safetensors"):
        raise ValueError("Setup not supported: use a complete safetensors checkpoint")
    metadata = hub_gguf_files(cfg.huggingface_base_url, "", repo, image=True)
    selected = next((row for row in metadata["files"] if row["filename"] == filename), None)
    if (
        not selected
        or not re.fullmatch(r"[a-f0-9]{40}", str(metadata["revision"]))
        or not re.fullmatch(r"[a-f0-9]{64}", str(selected.get("sha256", "")))
        or type(selected.get("size")) is not int
        or not 0 < selected["size"] < 32 * 1024**3
    ):
        raise ValueError("The checkpoint requires a pinned revision, size and checksum")
    fields = {
        "base_url": cfg.huggingface_base_url.rstrip("/"),
        "repo": repo,
        "filename": filename,
        "revision": metadata["revision"],
        "sha256": selected["sha256"],
        "size": selected["size"],
        "model": model,
    }
    original = f"{fields['base_url']}/{repo}/resolve/{fields['revision']}/{filename}"
    deadline = time.monotonic() + 30
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:

        def read_range(start, end):
            url = original
            for _ in range(6):
                if time.monotonic() >= deadline:
                    raise ValueError("Checkpoint metadata reached its deadline")
                image_model_store._redirect(url, fields["base_url"])
                with client.stream(
                    "GET",
                    url,
                    headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
                ) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    if (
                        response.status_code != 206
                        or response.headers.get("content-range")
                        != f"bytes {start}-{end}/{fields['size']}"
                        or response.headers.get("content-encoding", "identity") != "identity"
                    ):
                        raise ValueError(
                            "Source cannot provide bounded checkpoint metadata; use Download file"
                        )
                    data = bytearray()
                    for chunk in response.iter_bytes(65536):
                        data.extend(chunk)
                        if len(data) > end - start + 1 or time.monotonic() >= deadline:
                            raise ValueError("Checkpoint metadata exceeds its bound")
                    if len(data) != end - start + 1:
                        raise ValueError("Checkpoint metadata was truncated")
                    return bytes(data)
            raise ValueError("Too many checkpoint metadata redirects")

        prefix = read_range(0, 7)
        count = struct.unpack("<Q", prefix)[0]
        if not 2 <= count <= 8 * 1024**2 or count + 8 >= fields["size"]:
            raise ValueError("Checkpoint metadata exceeds its bound")
        header = prefix + read_range(8, count + 7)
    return fields, inspect_header(header, fields["size"])


def inspect_source(cfg, model):
    fields, path = source(cfg, model)
    family = architecture(path)
    return {
        "model": model,
        "architecture": family,
        "size": fields["size"],
        "sha256": fields["sha256"],
        "supported": True,
        "hardware_verified": False,
        "generation_verified": False,
    }


def public_items(cfg):
    try:
        observed = read_settings(managed.root(cfg) / "last-generation.json").get("models", {})
    except OSError:
        observed = {}
    if not isinstance(observed, dict):
        observed = {}
    result = []
    records = managed.records(cfg)
    from itertools import islice

    drafts = managed.root(cfg) / "drafts"
    for path in islice(drafts.glob("*.json"), LIMIT):
        if not any(model == path.stem for model, _ in records) and not read_settings(
            managed.record_path(cfg, path.stem)
        ).get("removed_by"):
            managed.record_path(cfg, path.stem)  # Validate the opaque inventory ID.
            records.append((path.stem, read_settings(path)))
    for model, record in records:
        recipe = parse(record["recipe"]) if "recipe" in record else managed.bundle_for(cfg, model)
        error, installed = "", False
        try:
            managed.installed(cfg, model=model)
            installed = True
        except (ValueError, OSError) as exc:
            error = str(exc) if isinstance(exc, ValueError) else "Installation unavailable"
        result.append(
            {
                "id": model,
                "name": record.get("name", "Stable Diffusion 1.5"),
                "architecture": recipe.architecture,
                "size": recipe.size,
                "installed": installed,
                "message": error,
                "source_model": record.get("source", {}).get("model", ""),
                "source_url": recipe.public()["source_url"],
                "revision": digest(record),
                "generation_verified": bool(
                    installed
                    and isinstance(observed.get(model), dict)
                    and observed[model].get("installation") == digest(record)
                ),
            }
        )
    return result


def prepare(cfg, draft):
    from .comfyui_install import resource

    op = draft["operation"]
    if set(draft) != {"operation", "model"} or not isinstance(draft["model"], str):
        raise ValueError("Choose an exact managed image model")
    if op in {"comfy-import", "comfy-store-install"}:
        if op == "comfy-import":
            fields, path = source(cfg, draft["model"])
            family = architecture(path)
        else:
            fields, family = remote_source(cfg, draft["model"])
            path = None
        recipe = ControlBundle(
            id="checkpoint-" + fields["sha256"],
            architecture=family,
            repository=fields["repo"],
            revision=fields["revision"],
            filename=fields["filename"],
            sha256=fields["sha256"],
            size=fields["size"],
            license="Review the original model source license",
        )
        parse(asdict(recipe))
        model = key(recipe)
        if len(managed.records(cfg)) >= LIMIT and not managed.record_path(cfg, model).exists():
            raise ValueError("Remove an unused managed model before adding another")
        review = {
            "recipe": asdict(recipe),
            "model": model,
            "source": fields,
            "source_signature": managed.signature(path) if path else [],
            "before": read_settings(managed.record_path(cfg, model)),
        }
        if (
            review["before"].get("recipe")
            and not review["before"].get("removed_by")
            and review["before"]["recipe"] != review["recipe"]
        ):
            raise ValueError("These exact weights already have a managed recipe; choose that model")
        warning = (
            "SDXL device compatibility has not been verified on this GPU. "
            "This model can exceed available memory. "
            if family == "sdxl"
            else ""
        )
        return (
            review,
            resource(cfg),
            (
                f"Install complete {family} checkpoint: {fields['filename']}. "
                f"Install and verify {recipe.size:,} bytes. SHA-256: {recipe.sha256}. "
                "Install the pinned managed ComfyUI runtime if missing; "
                "runtime download size is unknown. "
                "The embedded text encoder(s) and VAE are required and "
                "were identified in its tensor header. "
                + warning
                + "Review the original source license. Keeps the Store original. "
                "Does not load weights, generate or change defaults."
            ),
        )
    if op == "comfy-repair":
        model = draft["model"]
        record = read_settings(managed.record_path(cfg, model))
        draft_record = read_settings(managed.root(cfg) / "drafts" / (model + ".json"))
        retained = record or draft_record
        recipe = parse(retained.get("recipe"))
        fields = retained.get("source", {})
        if any(
            fields.get(a) != getattr(recipe, b)
            for a, b in (
                ("sha256", "sha256"),
                ("size", "size"),
                ("repo", "repository"),
                ("revision", "revision"),
                ("filename", "filename"),
            )
        ):
            raise ValueError("Original pinned checkpoint source is unavailable")
        path = (
            Path(fields["root"]).joinpath(*image_model_store.parts(fields))
            if fields.get("root")
            else None
        )
        available = (
            path is not None and fields["root"] == str(image_model_store.root()) and path.exists()
        )
        return (
            {
                "model": model,
                "recipe": asdict(recipe),
                "source": fields,
                "source_signature": managed.signature(path)
                if available and path is not None
                else [],
                "before": record,
            },
            resource(cfg),
            (
                f"Repair {record.get('name', model)} using the exact pinned checkpoint "
                f"({recipe.size:,} bytes, SHA-256 {recipe.sha256}). "
                "Reuses verified managed bytes; copies the retained original or downloads "
                "only missing/corrupt model bytes. Checks the installed runtime. "
                "Does not change defaults, generate or delete the Store original."
            ),
        )
    if op != "comfy-remove":
        raise ValueError("Unsupported managed model action")
    model = draft["model"]
    record = read_settings(managed.record_path(cfg, model))
    retained = record or read_settings(managed.root(cfg) / "drafts" / (model + ".json"))
    if not retained or record.get("removed_by"):
        raise ValueError("This managed model was already removed")
    settings = image_settings(cfg)
    if settings.get("provider") == "comfyui" and settings["model"] == model:
        raise ValueError("Choose and Apply another image default before removing this model")
    recipe = parse(retained["recipe"]) if "recipe" in retained else managed.bundle_for(cfg, model)
    path = managed.model_path(cfg, recipe)
    # Missing weights may still have a removable metadata record.
    signature = managed.signature(path) if path.exists() else []
    shared = any(
        other != model and managed.bundle_for(cfg, other).installed_name == recipe.installed_name
        for other, _ in managed.records(cfg)
    )
    return (
        {
            "model": model,
            "recipe": asdict(recipe),
            "before": record,
            "retained": retained,
            "settings": settings,
            "signature": signature,
            "shared": shared,
        },
        resource(cfg),
        (
            f"Remove {retained.get('name', 'Stable Diffusion 1.5')} from managed image models. "
            + (
                "Its verified weights are shared and will be retained. "
                if shared
                else (
                    f"Delete only its managed checkpoint copy "
                    f"({signature[2] if signature else 0:,} bytes). "
                )
            )
            + "Keeps the original Store download, runtime, other models and Library images."
        ),
    )


def _cleanup(cfg, request, check):
    recipe = parse(request["recipe"])
    model = request["model"]
    path = managed.model_path(cfg, recipe)
    shared = any(
        other != model and managed.bundle_for(cfg, other).installed_name == recipe.installed_name
        for other, _ in managed.records(cfg)
    )
    if shared != request["shared"]:
        raise OperationConflict("Shared model references changed; removal remains fenced")
    if not shared and path.exists():
        if managed.signature(path) != request["signature"]:
            raise OperationConflict("Managed checkpoint changed; removal remains fenced")
        check()
        path.unlink()
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def run(cfg, request, progress):
    try:
        return _run(cfg, request, progress)
    except (ValueError, OSError, OperationConflict):
        receipt = OperationJournal(cfg.data_dir / "operations.db").status(
            request["request_id"], OWNER
        )
        if receipt and receipt.state == "accepted":
            return {"rejected": True}
        raise


def _run(cfg, request, progress):
    journal = OperationJournal(cfg.data_dir / "operations.db")
    rid, fence = request["request_id"], request["fence"]
    recipe = parse(request["recipe"])
    model = key(recipe)
    if (
        request["model"] != model
        or read_settings(managed.record_path(cfg, model)) != request["before"]
    ):
        return {"rejected": True}
    if request["operation"] == "comfy-remove" and image_settings(cfg) != request["settings"]:
        return {"rejected": True}
    if request["operation"] == "comfy-import":
        fields, path = source(
            cfg, request["source"]["model"], expected_root=request["source"]["root"]
        )
        if fields != request["source"] or managed.signature(path) != request["source_signature"]:
            return {"rejected": True}
    if request["operation"] == "comfy-store-install":
        path = None
    if request["operation"] == "comfy-repair":
        fields = request["source"]
        candidate = (
            Path(fields["root"]).joinpath(*image_model_store.parts(fields))
            if fields.get("root")
            else None
        )
        path = candidate if request["source_signature"] else None
        if path is not None and managed.signature(path) != request["source_signature"]:
            return {"rejected": True}
    evidence = {
        "operation": request["operation"],
        **{
            k: request[k]
            for k in ("model", "recipe", "before", "signature", "shared")
            if k in request
        },
    }
    journal.save_evidence(rid, OWNER, fence, evidence)
    journal.start(rid, OWNER, fence)

    def check():
        journal.check_effect(rid, OWNER, fence)

    def notify(value):
        if progress:
            progress(value)
        # Only stage checkpoints are durable; live chunk progress uses the owner.
        if value.get("stage") != journal.evidence(rid, OWNER).get("progress", {}).get("stage"):
            old = journal.evidence(rid, OWNER)
            journal.save_evidence(
                rid, OWNER, fence, {**old, "progress": value}, expected=old, require_running=True
            )

    def publish(record):
        check()
        record.update(name=Path(recipe.filename).stem, source=request["source"])

    if request["operation"] == "comfy-remove":
        with managed.install_lock(cfg), settings_lock(cfg.config_dir / "image-generation.json"):
            managed.require_idle(cfg)
            if image_settings(cfg) != request["settings"]:
                return {"rejected": True}
            managed.stop(cfg)
            check()
            location = managed.record_path(cfg, model)
            location.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write_private(location, json.dumps({**request["retained"], "removed_by": rid}))
            _cleanup(cfg, request, check)
        return {"ok": True}

    def fetch(directory, temporary, report, verify):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            try:
                image_model_store._transfer(request["source"], fd, temporary, report, verify)
            except image_model_store.InvalidPartial:
                os.unlink(temporary, dir_fd=fd)
                raise
        finally:
            os.close(fd)

    try:
        with managed.install_lock(cfg):
            check()
            folder = managed.root(cfg) / "drafts"
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write_private(
                folder / (model + ".json"),
                json.dumps(
                    {
                        "recipe": asdict(recipe),
                        "source": request["source"],
                        "name": Path(recipe.filename).stem,
                    }
                ),
            )
        managed.install(
            cfg,
            rid,
            str(path) if path is not None else "",
            fetch,
            check,
            notify,
            publish,
            bundle=recipe,
            repair_runtime=False,
        )
        return {"ok": True}
    except (OSError, ValueError):
        return {"rejected": True}


def recover(cfg, target, evidence, check=lambda: None):
    """Called under the exclusive installer lock; never resubmit an import."""
    model = evidence["model"]
    current = read_settings(managed.record_path(cfg, model))
    if evidence["operation"] in {"comfy-import", "comfy-repair", "comfy-store-install"}:
        if current.get("request_id") == target:
            managed.installed(cfg, model=model, full=True)
            return "completed"
    elif current.get("removed_by") == target:
        managed.require_idle(cfg)
        check()
        managed.stop(cfg)
        _cleanup(cfg, evidence, check)
        return "completed"
    if current == evidence["before"]:
        return "failed"
    raise OperationConflict("Managed model differs from the exact reviewed outcome")

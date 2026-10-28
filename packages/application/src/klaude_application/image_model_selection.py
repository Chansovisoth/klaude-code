"""Explicit, reviewed native SD model loading; discovery never loads weights."""

from __future__ import annotations

import hashlib
import json
import re

import httpx
from klaude_core.image_generation import endpoint, packet, text
from klaude_core.settings_store import atomic_write_private

from .model_store import read_record
from .operation_journal import OperationConflict, OperationJournal

OPERATIONS = frozenset({"image-model-load", "image-model-recover"})
OWNER = "web-admin"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def resource(url):
    return "image-runtime:" + digest(endpoint(url))


def runtime(value):
    if value.get("state") not in {"empty", "loading", "ready", "error"}:
        raise ValueError("Image server returned invalid model status")
    models = value.get("models", {})
    if not isinstance(models, dict) or len(models) > 64:
        raise ValueError("Image server returned invalid model selection")
    return {key: value.get(key) for key in ("state", "recipe", "origin", "revision")} | {
        "models": {text(key, 128): text(item, 1000) for key, item in models.items() if item},
    }


def catalog(cfg, url, *, refresh=False):
    url = endpoint(url)
    if refresh:
        packet(url, "/sdcpp/v1/models/refresh", {})
    state = runtime(packet(url, "/sdcpp/v1/models/status"))
    raw_recipes = packet(url, "/sdcpp/v1/recipes").get("recipes")
    raw_files = packet(url, "/sdcpp/v1/model-files").get("files")
    if (not isinstance(raw_recipes, list) or len(raw_recipes) > 256
            or not isinstance(raw_files, list) or len(raw_files) > 2000):
        raise ValueError("Image model catalog exceeds its supported bounds")
    files, recipes = [], []
    for item in raw_files:
        files.append({"id": text(item["id"], 1000), "name": text(item["name"], 1000),
                      "category": text(item["category"], 100)})
    for item in raw_recipes:
        slots = item.get("slots")
        if not isinstance(slots, list) or not 1 <= len(slots) <= 64:
            continue  # Runtime-only command-line recipes cannot be submitted.
        checked = []
        for slot in slots:
            categories = slot.get("categories", [slot.get("category")])
            if (not isinstance(categories, list) or not 1 <= len(categories) <= 10
                    or type(slot.get("required")) is not bool):
                raise ValueError("Unsupported image recipe")
            checked.append({"id": text(slot["id"], 128),
                            "label": text(slot.get("label", slot["id"]), 200),
                            "required": slot["required"],
                            "categories": [text(category, 100) for category in categories]})
        recipes.append({"id": text(item["id"], 128), "name": text(item["name"], 200),
                        "description": text(item.get("description", ""), 2000, empty=True),
                        "slots": checked, "models": item.get("models", {}),
                        "required_any": item.get("required_any", [])})
        recipe = recipes[-1]
        slot_ids = {slot["id"] for slot in checked}
        if (len(slot_ids) != len(checked) or not isinstance(recipe["models"], dict)
                or set(recipe["models"]) - slot_ids
                or not isinstance(recipe["required_any"], list)
                or any(not isinstance(group, list) or not group or
                       any(not isinstance(key, str) or key not in slot_ids for key in group)
                       for group in recipe["required_any"])):
            raise ValueError("Unsupported image recipe component defaults")
    if (len({item["id"] for item in recipes}) != len(recipes)
            or len({item["id"] for item in files}) != len(files)):
        raise ValueError("Image server returned duplicate catalog identities")
    model = ""
    if state["state"] == "ready":
        model = text(packet(url, "/sdcpp/v1/capabilities").get("model", {}).get("name"), 200)
    pending = None
    if (cfg.data_dir / "operations.db").exists():
        fenced = OperationJournal(cfg.data_dir / "operations.db").fenced_operation(resource(url))
        if fenced:
            pending = {"request_id": fenced.receipt.request_id, "state": fenced.receipt.state}
    return {"endpoint": url, "recipes": recipes, "files": files, "runtime": state,
            "model": model, "catalog_revision": digest([raw_recipes, raw_files]),
            "runtime_revision": digest(state), "pending": pending}


def selection(data, recipe_id, values):
    recipe = next((item for item in data["recipes"] if item["id"] == recipe_id), None)
    if recipe is None or not isinstance(values, dict):
        raise ValueError("Choose a recipe from this server")
    slots = {item["id"]: item for item in recipe["slots"]}
    if set(values) - slots.keys():
        raise ValueError("Choose only this recipe's model components")
    selected = {**recipe["models"], **values}
    files = {item["id"]: item for item in data["files"]}
    for key, slot in slots.items():
        value = selected.get(key, "")
        if not isinstance(value, str):
            raise ValueError("Choose an exact model file")
        if value:
            item = files.get(value)
            if not item or item["category"] not in slot["categories"]:
                raise ValueError("Model file changed or has the wrong component type")
        elif slot["required"]:
            raise ValueError("Choose every required model component")
    for group in recipe["required_any"]:
        if not isinstance(group, list) or not any(selected.get(key) for key in group):
            raise ValueError("Choose one component from each required alternative")
    return recipe, {key: selected.get(key, "") for key in slots}


def target_path(cfg, identity):
    if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Choose an exact model load")
    return cfg.data_dir / "image-model-loads" / (identity + ".json")


def recover_target(cfg, journal, identity, url):
    fenced = journal.fenced_operation(resource(url))
    value = read_record(target_path(cfg, identity))
    if (not fenced or fenced.owner_id != OWNER or fenced.receipt.request_id != identity
            or fenced.receipt.state != "unknown" or fenced.receipt.kind != "image-model-load"
            or not value or value.get("endpoint") != endpoint(url)
            or not journal.witness_after_matches(identity, OWNER, candidate=value)):
        raise ValueError("Unconfirmed model load changed; refresh its state")
    state = runtime(packet(url, "/sdcpp/v1/models/status"))
    if not matches(state, value):
        raise ValueError("The server has not confirmed this selection; the load remains fenced")
    return value


def prepare(cfg, draft):
    if draft["operation"] == "image-model-recover":
        if set(draft) != {"operation", "endpoint", "target"}:
            raise ValueError("Choose an exact unconfirmed model load")
        url = endpoint(draft["endpoint"])
        journal = OperationJournal(cfg.data_dir / "operations.db")
        value = recover_target(cfg, journal, draft["target"], url)
        return {"target": draft["target"], "value": value}, "recover:" + resource(url), (
            "Check that the server is running the exact reviewed model selection. "
            "Does not load a model again or save image defaults."
        )
    if set(draft) != {"operation", "endpoint", "recipe", "models",
                      "catalog_revision", "runtime_revision"}:
        raise ValueError("Choose an exact server model selection")
    data = catalog(cfg, draft["endpoint"])
    if (data["pending"] or data["runtime"]["state"] == "loading"
            or any(data[key] != draft[key] for key in ("catalog_revision", "runtime_revision"))):
        raise ValueError("Image server changed or is loading; refresh model choices")
    recipe, models = selection(data, draft["recipe"], draft["models"])
    value = {key: data[key] for key in ("endpoint", "catalog_revision", "runtime_revision")}
    value.update(recipe=recipe["id"], models=models)
    names = {item["id"]: item["name"] for item in data["files"]}
    description = "\n".join(f"{key}: {names[file]}" for key, file in models.items() if file)
    return value, resource(data["endpoint"]), (
        f"Load {recipe['name']} on {data['endpoint']}.\n{description}\n"
        "Replaces the server's loaded model and uses its memory. Other clients share this server. "
        "No weights are downloaded. Image defaults are saved separately after loading."
    )


def matches(state, value):
    return (state["state"] == "ready" and state["recipe"] == value["recipe"]
            and state["models"] == {key: item for key, item in value["models"].items() if item})


def load_once(url, payload):
    with httpx.Client(trust_env=False, follow_redirects=False,
                      timeout=httpx.Timeout(600, connect=3)) as client:
        with client.stream("POST", url + "/sdcpp/v1/models/load", json=payload) as response:
            if response.status_code in {400, 409, 422}:
                return None  # Explicit native rejection/failure, never a retry.
            response.raise_for_status()
            body = bytearray()
            for part in response.iter_bytes(65536):
                body.extend(part)
                if len(body) > 512_000:
                    raise ValueError("Model load response exceeds limit")
    return runtime(json.loads(body))


def run(cfg, request):
    journal = OperationJournal(cfg.data_dir / "operations.db")
    if request["operation"] == "image-model-recover":
        value = request["value"]
        observed = recover_target(cfg, journal, request["target"], value["endpoint"])
        if observed != value:
            raise OperationConflict("Model load changed; review again")
        journal.check_effect(request["request_id"], OWNER, request["fence"])
        journal.reconcile(request["target"], OWNER, state="completed",
                          evidence="Native server confirms exact reviewed recipe and model files")
        return {"ok": True}
    value = {key: request[key] for key in (
        "endpoint", "catalog_revision", "runtime_revision", "recipe", "models",
    )}
    try:
        data = catalog(cfg, value["endpoint"])
        if any(data[key] != value[key] for key in ("catalog_revision", "runtime_revision")):
            return {"rejected": True}
        selection(data, value["recipe"], value["models"])
    except (ValueError, OSError, httpx.HTTPError):
        return {"rejected": True}
    path = target_path(cfg, request["request_id"])
    if path.parent.is_symlink():
        return {"rejected": True}
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    atomic_write_private(path, json.dumps(value))
    journal.record_witness(request["request_id"], OWNER, request["fence"],
                           before={"unstarted": True}, after=value)
    journal.start(request["request_id"], OWNER, request["fence"])
    journal.check_effect(request["request_id"], OWNER, request["fence"])
    try:
        state = load_once(value["endpoint"], {"recipe": value["recipe"], "models": value["models"]})
        if state is None:
            return {"rejected": True}
        return {"ok": matches(state, value)}
    except (ValueError, OSError, httpx.HTTPError, KeyError, TypeError):
        return {"ok": False}  # A lost acknowledgement stays fenced; never replay.

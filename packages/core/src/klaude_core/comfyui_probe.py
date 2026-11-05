"""Bounded, read-only ComfyUI preflight. Metadata never certifies installation."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .comfyui_bundle import COMFY_VERSION, CONTROL, NODE_INPUTS, NODE_OUTPUTS, digest
from .model_connections import normalize_model_url

BYTE_LIMIT = 512_000
TOTAL_LIMIT = 2_000_000
DEADLINE = 20.0
CONTROL_RANGES: dict[str, dict[str, tuple[int | float, int | float]]] = {
    "KSampler": {
        "seed": (0, 2**32 - 1),
        "steps": (1, 50),
        "cfg": (8.0, 8.0),
        "denoise": (1.0, 1.0),
    },
    "EmptyLatentImage": {"width": (256, 768), "height": (256, 768), "batch_size": (1, 1)},
}


def _text(value: Any, limit: int = 200) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > limit
        or not all(c.isprintable() for c in value)
    ):
        raise ValueError("ComfyUI returned invalid metadata text")
    return value


def _bytes(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 2**60:
        raise ValueError("ComfyUI returned invalid memory metadata")
    return value


def _object(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError("ComfyUI returned invalid metadata structure")
    return value


def _pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ComfyUI returned duplicate JSON keys")
        result[key] = value
    return result


def _invalid_constant(_: str) -> None:
    raise ValueError("ComfyUI returned non-finite JSON")


def _names(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 500:
        raise ValueError("ComfyUI checkpoint inventory exceeds its bound or is invalid")
    result = []
    for item in value:
        name = _text(item, 512)
        # Names are server-relative identifiers, never host paths or fetch URLs.
        path = name.replace("\\", "/")
        if ":" in path or any(p in {"", ".", ".."} for p in path.split("/")):
            raise ValueError("ComfyUI returned an unsafe checkpoint identifier")
        result.append(name)
    if len(set(result)) != len(result):
        raise ValueError("ComfyUI returned duplicate checkpoint identifiers")
    return result


def _node(name: str, payload: Any) -> tuple[dict, list[str]]:
    value = _object(payload).get(name)
    if value is None:
        return {}, [f"Missing built-in node: {name}"]
    value = _object(value)
    required = _object(_object(value.get("input")).get("required", {}))
    problems = []
    if value.get("python_module") != "nodes":
        problems.append(f"Built-in node provenance not declared: {name}")
    if value.get("output") != NODE_OUTPUTS[name]:
        problems.append(f"Changed output contract: {name}")
    if name == "SaveImage" and value.get("output_node") is not True:
        problems.append("SaveImage is not declared an output node")
    if set(required) != set(NODE_INPUTS[name]):
        problems.append(f"Changed required inputs: {name}")
    for field, expected in NODE_INPUTS[name].items():
        definition = required.get(field)
        kind = definition[0] if isinstance(definition, list) and definition else None
        if expected == "COMBO":
            if not isinstance(kind, list) or len(kind) > 500:
                problems.append(f"Missing choices: {name}.{field}")
            elif field in {"sampler_name", "scheduler"}:
                choice = "euler" if field == "sampler_name" else "normal"
                if choice not in kind:
                    problems.append(f"Missing supported choice: {name}.{field}")
        elif kind != expected:
            problems.append(f"Changed input type: {name}.{field}")
        bounds = CONTROL_RANGES.get(name, {}).get(field)
        if bounds:
            options = definition[1] if isinstance(definition, list) and len(definition) > 1 else {}
            options = options if isinstance(options, dict) else {}
            minimum, maximum = options.get("min"), options.get("max")
            if (
                not isinstance(minimum, (int, float))
                or isinstance(minimum, bool)
                or not isinstance(maximum, (int, float))
                or isinstance(maximum, bool)
                or minimum > bounds[0]
                or maximum < bounds[1]
            ):
                problems.append(f"Unsupported control range: {name}.{field}")
            if field in {"width", "height"}:
                step = options.get("step", 1)
                if type(step) is not int or step < 1 or 64 % step:
                    problems.append(f"Unsupported dimension step: {name}.{field}")
    selected = {key: value.get(key) for key in ("input", "output", "output_node", "python_module")}
    return selected, problems


def probe(url: str) -> dict:
    """Read only fixed metadata endpoints; never load, install, queue or cancel.

    Unknown versions remain inspectable, with compatibility explicitly unverified.
    No authentication negotiation or ambient credential use is performed.
    """
    if not isinstance(url, str) or len(url) > 500:
        raise ValueError("Enter a ComfyUI server root URL")
    url = normalize_model_url(url, "comfyui")
    deadline = time.monotonic() + DEADLINE
    total = 0
    with httpx.Client(
        timeout=httpx.Timeout(4, connect=2), trust_env=False, follow_redirects=False
    ) as client:

        def get(path: str) -> Any:
            nonlocal total
            if time.monotonic() >= deadline:
                raise ValueError("ComfyUI preflight exceeded its deadline")
            body = bytearray()
            try:
                with client.stream(
                    "GET",
                    url + path,
                    headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                    timeout=min(4, max(0.001, deadline - time.monotonic())),
                ) as res:
                    if res.status_code != 200:
                        if res.status_code in {401, 403}:
                            raise ValueError(
                                "ComfyUI requires an authenticated connection; "
                                "this initial probe supports no credentials"
                            )
                        raise ValueError(f"ComfyUI metadata returned HTTP {res.status_code}")
                    if res.headers.get("content-encoding", "identity") != "identity":
                        raise ValueError("ComfyUI returned unsupported compressed metadata")
                    # Do not buffer small network chunks into a larger chunk: that
                    # would postpone the overall deadline on a slow-drip response.
                    for chunk in res.iter_bytes():
                        total += len(chunk)
                        body.extend(chunk)
                        if len(body) > BYTE_LIMIT or total > TOTAL_LIMIT:
                            raise ValueError("ComfyUI metadata exceeded its byte limit")
                        if time.monotonic() >= deadline:
                            raise ValueError("ComfyUI preflight exceeded its deadline")
            except httpx.HTTPError:
                raise ValueError(
                    "ComfyUI metadata unavailable; check the configured service"
                ) from None
            try:
                return json.loads(body, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
            except (UnicodeError, json.JSONDecodeError, RecursionError):
                raise ValueError("ComfyUI returned invalid JSON metadata") from None

        raw = _object(get("/system_stats"))
        system = _object(raw.get("system"))
        version = _text(system.get("comfyui_version"), 64)
        public_system: dict[str, Any] = {
            key: _text(system.get(key)) for key in ("os", "python_version", "pytorch_version")
        }
        public_system.update(
            comfyui_version=version,
            ram_total=_bytes(system.get("ram_total")),
            ram_free=_bytes(system.get("ram_free")),
        )
        devices = raw.get("devices")
        if not isinstance(devices, list) or len(devices) > 16:
            raise ValueError("ComfyUI returned invalid device inventory")
        public_devices = []
        for item in devices:
            device = _object(item)
            public_devices.append(
                {
                    "name": _text(device.get("name")),
                    "type": _text(device.get("type"), 32),
                    "vram_total": _bytes(device.get("vram_total")),
                    "vram_free": _bytes(device.get("vram_free")),
                }
            )
        checkpoints = _names(get("/models/checkpoints"))
        schemas, problems = {}, []
        for name in NODE_INPUTS:
            schema, errors = _node(name, get("/object_info/" + name))
            schemas[name] = schema
            problems.extend(errors)
    binding = {"version": version, "schemas": schemas, "checkpoints": checkpoints}
    return {
        "endpoint": url,
        "checked_at": time.time(),
        "system": public_system,
        "devices": public_devices,
        "checkpoints": checkpoints,
        "runtime_version_matches": version == COMFY_VERSION,
        "schema_matches": not problems,
        "problems": problems,
        "metadata_revision": digest(binding),
        "bundle": CONTROL.public(),
        "installed_bundle_verified": False,
        "generation_verified": False,
        "checkpoint_name_visible": CONTROL.installed_name in checkpoints,
        "message": "Metadata only; file content, runtime lock and generation are unverified",
    }

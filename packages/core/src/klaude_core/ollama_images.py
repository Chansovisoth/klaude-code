"""Experimental Ollama image streams; never pull models or replay a request."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import httpx


def inspect_model(url: str, model: str) -> dict:
    from .image_generation import packet, text

    model = text(model, 200)
    shown = packet(url, "/api/show", {"model": model})
    capabilities = shown.get("capabilities")
    if not isinstance(capabilities, list) or "image" not in capabilities:
        raise ValueError("This Ollama model does not advertise image generation. "
                         "Choose an installed image model on a supported Ollama build.")
    # A tag can be replaced without changing its name. Pin its installed digest,
    # and recheck it at review, submission and output publication.
    models = packet(url, "/api/tags").get("models", [])
    names = {model, model if ":" in model.rsplit("/", 1)[-1] else model + ":latest"}
    matches = [item for item in models if isinstance(item, dict)
               and (item.get("name") in names or item.get("model") in names)]
    if len(matches) != 1:
        raise ValueError("Choose one exact installed Ollama image model")
    digest = text(matches[0].get("digest"), 200)
    evidence = {"endpoint": url, "model": model, "provider": "ollama", "digest": digest,
                "limits": {"min_width": 256, "max_width": 1024,
                           "min_height": 256, "max_height": 1024},
                "sampler": "model default", "scheduler": "model default",
                "cancel_queued": False, "cancel_generating": False}
    evidence["revision"] = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    return evidence


def generate(cfg: Any, record: dict, progress) -> dict:
    from .image_generation import DEADLINE, RESULT_LIMIT, publish, store_output

    settings = record["settings"]
    payload = {"model": settings["model"], "prompt": record["prompt"], "stream": True,
               "width": record["width"], "height": record["height"], "steps": record["steps"],
               "options": {"seed": record["seed"]}}
    deadline = time.monotonic() + DEADLINE
    image, done, received = None, False, 0
    pending = bytearray()
    try:
        with httpx.Client(timeout=httpx.Timeout(30, connect=3), trust_env=False,
                          follow_redirects=False) as client:
            with client.stream("POST", settings["endpoint"] + "/api/generate",
                               json=payload) as response:
                if response.status_code != 200:
                    record.update(status="failed")
                    publish(cfg, record)
                    raise ValueError(f"Ollama returned HTTP {response.status_code}; no retry sent")
                record.update(status="running")
                publish(cfg, record)
                progress({"job": record["id"], "status": "accepted"})
                # Bounded chunks, including an unterminated/oversized NDJSON line.
                for chunk in response.iter_bytes():
                    received += len(chunk)
                    if received > RESULT_LIMIT or time.monotonic() > deadline:
                        raise ValueError("Ollama image stream exceeded its byte or time limit")
                    pending.extend(chunk)
                    while b"\n" in pending:
                        line, _, rest = pending.partition(b"\n")
                        pending = bytearray(rest)
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        if not isinstance(event, dict) or event.get("error"):
                            raise ValueError("Ollama image generation failed; no retry sent")
                        if done:
                            raise ValueError("Ollama sent data after its final image event")
                        if event.get("image"):
                            if image is not None or not isinstance(event["image"], str):
                                raise ValueError("Ollama must return exactly one image")
                            image = event["image"]
                        done = event.get("done") is True
                if pending.strip() or not done or image is None:
                    raise ValueError("Ollama image stream ended without a complete image")
        # Reuse the existing bounded PNG/size/authorship publication boundary.
        return store_output(cfg, record, record["id"], {
            "id": record["id"], "kind": "img_gen",
            "result": {"images": [{"b64_json": image}]},
        })
    except BaseException:
        if record["status"] != "failed":
            record.update(status="unknown")
            publish(cfg, record)
        raise

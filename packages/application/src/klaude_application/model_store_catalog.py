"""Cached, bounded discovery using the documented Hugging Face GGUF API."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from typing import Any, cast

from klaude_core.settings_store import atomic_write_private
from klaude_web.huggingface import hub_gguf_files, hub_repo_search

from .model_store import read_record

_LOCK = threading.RLock()
TTL = 3600
MAX_CACHES = 64


def _text(value: Any, limit=200):
    return "".join(c for c in str(value or "") if c.isprintable())[:limit]


def _cache(cfg, key, read, refresh, *, metadata_version=None):
    identity = hashlib.sha256((cfg.huggingface_base_url + ":" + key).encode()).hexdigest()
    root = cfg.data_dir / "model-manager" / "discovery"
    path = root / f"{identity}.json"
    with _LOCK:
        previous = read_record(path)
        if (
            not refresh
            and previous
            and 0 <= time.time() - previous.get("checked_at", 0) < TTL
            and (metadata_version is None or previous.get("metadata_version") == metadata_version)
        ):
            return {**previous, "stale": False}
        try:
            data = {**read(), "checked_at": time.time(), "source": "Hugging Face GGUF"}
            if metadata_version is not None:
                data["metadata_version"] = metadata_version
        except Exception:
            return {
                **previous,
                "stale": True,
                "error": "Hugging Face catalog unavailable. Cached results remain available."
                if previous
                else "Hugging Face unavailable. Use curated models or Installed while offline.",
            }
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_private(path, json.dumps(data))
        files = [p for p in root.glob("*.json") if re.fullmatch(r"[a-f0-9]{64}\.json", p.name)]
        for old in sorted(files, key=lambda p: p.stat().st_mtime)[:-MAX_CACHES]:
            if not old.is_symlink():
                old.unlink(missing_ok=True)
        return {**data, "stale": False}


def catalog(cfg, query="", sort="downloads", *, refresh=False, page=1, limit=20,
            runtime="ollama"):
    if (
        runtime not in {"ollama", "sdcpp"}
        or not isinstance(query, str)
        or len(query) > 200
        or any(not c.isprintable() for c in query)
        or sort not in {"downloads", "lastModified"}
        or type(page) is not int
        or not 1 <= page <= 500
        or type(limit) is not int
        or not 1 <= limit <= 50
    ):
        raise ValueError("Choose a bounded catalog query and ordering")

    def read():
        cursor = ""
        if page > 1:
            previous_key = ("sdcpp:" if runtime == "sdcpp" else "") + (
                "list:" + sort + ":" + query + ":limit:" + str(limit) + ":page:" + str(page - 1)
            )
            previous_digest = hashlib.sha256(
                (cfg.huggingface_base_url + ":" + previous_key).encode()
            ).hexdigest()
            previous = read_record(
                cfg.data_dir / "model-manager" / "discovery" / f"{previous_digest}.json"
            )
            if not previous or not previous.get("next_cursor"):
                raise ValueError("No further catalog page is available")
            cursor = previous["next_cursor"]
        models: list[dict[str, Any]] = []
        seen: set[str] = set()
        next_cursor = ""
        # Hub can return a short batch or entries outside our identity bounds.
        # Fill from its continuation without dropping valid models or guessing a
        # page-number offset. Retain a small, explicit metadata request budget.
        for _ in range(4):
            remaining = limit - len(models)
            rows, next_cursor = cast(tuple[list[dict[str, Any]], str], hub_repo_search(
                cfg.huggingface_base_url, "", "model", query, remaining, sort,
                filter_tag="text-to-image" if runtime == "sdcpp" else "gguf",
                cursor=cursor, with_cursor=True,
            ))
            if len(rows) > remaining:
                raise ValueError("Catalog returned more models than requested")
            for row in rows:
                identity = row["id"]
                if not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", identity
                ):
                    continue
                if identity in seen:
                    continue
                seen.add(identity)
                downloads = row.get("downloads")
                models.append(
                    {
                        "id": "hf:" + identity,
                        "name": identity.split("/")[-1],
                        "publisher": identity.split("/")[0],
                        "task": _text(row.get("pipeline_tag"), 80),
                        "summary": _text(row["summary"], 240)
                        or ("Image model weights. Check the model card and required components."
                            if runtime == "sdcpp" else
                            "Community GGUF. Read its model card and choose an exact file."),
                        "categories": [],
                        "capabilities": [],
                        "variants": [],
                        "downloads": downloads
                        if row.get("downloads_known") and type(downloads) is int and downloads >= 0
                        else None,
                        "modified": _text(row.get("last_modified"), 80),
                        "source_url": "https://huggingface.co/" + identity,
                        "license": None,
                    }
                )
            if len(models) == limit or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return {"models": models, "sort": sort, "query": query, "page": page,
                "page_size": limit, "more": bool(next_cursor), "next_cursor": next_cursor}

    key = ("sdcpp:" if runtime == "sdcpp" else "") + (
        "list:" + sort + ":" + query + ":limit:" + str(limit) + ":page:" + str(page))
    result = _cache(cfg, key, read, refresh, metadata_version=2)
    return {**result, "source": "Hugging Face text-to-image"} if runtime == "sdcpp" else result


def detail(cfg, identity, *, refresh=False, runtime="ollama"):
    if runtime not in {"ollama", "sdcpp"}:
        raise ValueError("Choose a supported runtime")
    if not isinstance(identity, str) or not identity.startswith("hf:"):
        raise ValueError("Choose a Hugging Face model")
    repo = identity[3:]

    def read():
        data = hub_gguf_files(cfg.huggingface_base_url, "", repo, image=True) if (
            runtime == "sdcpp") else hub_gguf_files(cfg.huggingface_base_url, "", repo)
        return {
            "id": identity,
            "name": repo.split("/")[-1],
            "publisher": repo.split("/")[0],
            "summary": ("Image model weights. Check the model card for stable-diffusion.cpp "
                        "compatibility and any required text encoders or VAE. Downloading "
                        "does not load the model into the image server."
                        if runtime == "sdcpp" else
                        "Community GGUF model. Capabilities and device fit are not verified."),
            "source_url": "https://huggingface.co/" + repo,
            "license": data["license"],
            "task": _text(data.get("pipeline_tag"), 80),
            "categories": [],
            "capabilities": [],
            "variants": [
                {
                    "tag": f"hf.co/{repo}:{row['filename']}",
                    "name": row["filename"],
                    "size": row["size"],
                    "source_url": "https://huggingface.co/"
                    + repo
                    + "/blob/main/"
                    + row["filename"],
                }
                for row in data["files"]
            ],
        }

    return _cache(cfg, ("sdcpp:" if runtime == "sdcpp" else "") + "detail:" + repo,
                  read, refresh)

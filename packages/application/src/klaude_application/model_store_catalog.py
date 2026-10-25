"""Cached, bounded discovery using the documented Hugging Face GGUF API."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from typing import Any

from klaude_core.settings_store import atomic_write_private
from klaude_web.huggingface import hub_gguf_files, hub_repo_search

from .model_store import read_record

_LOCK = threading.RLock()
TTL = 3600
MAX_CACHES = 64


def _text(value: Any, limit=200):
    return "".join(c for c in str(value or "") if c.isprintable())[:limit]


def _cache(cfg, key, read, refresh):
    identity = hashlib.sha256((cfg.huggingface_base_url + ":" + key).encode()).hexdigest()
    root = cfg.data_dir / "model-manager" / "discovery"
    path = root / f"{identity}.json"
    with _LOCK:
        previous = read_record(path)
        if not refresh and previous and 0 <= time.time() - previous.get("checked_at", 0) < TTL:
            return {**previous, "stale": False}
        try:
            data = {**read(), "checked_at": time.time(), "source": "Hugging Face GGUF"}
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


def catalog(cfg, query="", sort="downloads", *, refresh=False):
    if (
        not isinstance(query, str)
        or len(query) > 200
        or any(not c.isprintable() for c in query)
        or sort not in {"downloads", "lastModified"}
    ):
        raise ValueError("Choose a bounded catalog query and ordering")

    def read():
        rows = hub_repo_search(
            cfg.huggingface_base_url, "", "model", query, 20, sort, filter_tag="gguf"
        )
        models = []
        for row in rows:
            identity = row["id"]
            if not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", identity
            ):
                continue
            downloads = row.get("downloads")
            models.append(
                {
                    "id": "hf:" + identity,
                    "name": identity.split("/")[-1],
                    "publisher": identity.split("/")[0],
                    "summary": _text(row["summary"], 240)
                    or "Community GGUF. Read its model card and choose an exact file.",
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
        return {"models": models, "sort": sort, "query": query}

    return _cache(cfg, "list:" + sort + ":" + query, read, refresh)


def detail(cfg, identity, *, refresh=False):
    if not isinstance(identity, str) or not identity.startswith("hf:"):
        raise ValueError("Choose a Hugging Face model")
    repo = identity[3:]

    def read():
        data = hub_gguf_files(cfg.huggingface_base_url, "", repo)
        return {
            "id": identity,
            "name": repo.split("/")[-1],
            "publisher": repo.split("/")[0],
            "summary": "Community GGUF model. Capabilities and device fit are not verified.",
            "source_url": "https://huggingface.co/" + repo,
            "license": data["license"],
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

    return _cache(cfg, "detail:" + repo, read, refresh)

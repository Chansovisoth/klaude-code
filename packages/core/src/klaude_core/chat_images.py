"""Private image snapshots and a provider-neutral chat image contract.

History stores bounded Media references, never base64 pixels. Only the request
projection materializes pixels for an enabled, verified, approved endpoint.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import time
from itertools import islice
from pathlib import Path
from typing import Any

from .ai_defaults import read_defaults
from .chat_image_support import active_binding, inspect_support
from .image_content import ANTHROPIC_IMAGE_BYTES, IMAGE_BACKENDS, image_token_estimate
from .library_artifacts import ID, ArtifactStore, image_header, plain
from .model_connections import normalize_model_url
from .vision import MAX_IMAGE_BYTES

MAX_IMAGES = 2
INPUT_KIND = "chat_image_input"


def references(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_IMAGES:
        raise ValueError("Chat accepts at most two image attachments per turn")
    result = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "sha256", "mime", "width", "height", "name", "scope"}
            or not isinstance(item["id"], str)
            or not ID.fullmatch(item["id"])
            or not item["id"].startswith("media:")
            or not isinstance(item["sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])
            or not isinstance(item["scope"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", item["scope"])
            or not isinstance(item["mime"], str)
            or item["mime"] not in {"image/png", "image/jpeg"}
            or type(item["width"]) is not int
            or type(item["height"]) is not int
            or not 1 <= item["width"] <= 4096
            or not 1 <= item["height"] <= 4096
            or item["width"] * item["height"] > 4_194_304
            or not isinstance(item["name"], str)
            or len(item["name"]) > 160
            or not item["name"].isprintable()
        ):
            raise ValueError("Invalid private image reference")
        result.append(dict(item))
    return result


def unpack_input(value: str | dict) -> tuple[str, list[dict]]:
    if isinstance(value, str):
        return value, []
    if (
        not isinstance(value, dict)
        or value.get("kind") != INPUT_KIND
        or value.get("version") != 1
        or not isinstance(value.get("content"), str)
        or not isinstance(value.get("request", value.get("content")), str)
    ):
        raise ValueError("Invalid private chat input")
    return value["content"], references(value.get("image_inputs"))


def image_cost(message: dict) -> int:
    """Conservative image-token estimate; encoded bytes are never text tokens."""
    return sum(
        image_token_estimate(r["width"], r["height"])
        for r in references(message.get("image_inputs", []))
    )


def read_file(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Attachments must be regular files")
        return stream.read(limit)


def is_image(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return True
    head = read_file(path, 16)
    return head.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8", b"GIF87a", b"GIF89a")) or (
        head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    )


def text_attachments(paths: tuple[Path, ...]) -> str:
    parts = []
    for path in paths:
        try:
            if path.is_file():
                if is_image(path):
                    parts.append(
                        f"[Attached image: {plain(path.name, 160)}; pixels are separate from text]"
                    )
                    continue
                data = read_file(path, 32768)
                text = (
                    "Binary attachment; no text decoded"
                    if b"\0" in data
                    else data.decode("utf8", "replace")
                )
                parts.append(f"[Attached file: {path}]\n{text}")
            elif path.is_dir():
                entries = sorted(islice(path.rglob("*"), 200), key=str)
                listing = "\n".join(
                    str(p.relative_to(path)) + ("/" if p.is_dir() else "") for p in entries
                )
                parts.append(f"[Attached folder: {path}]\n{listing}")
        except (OSError, ValueError):
            parts.append(f"[Attached file unavailable: {plain(str(path), 500)}]")
    return "\n\n".join(parts)


def inline_paths(text: str, workdir: Path) -> tuple[Path, ...]:
    result = []
    for match in re.finditer(r'(?<!\S)@(?:"([^"\n]+)"|([^\s]+))', text):
        raw = (match.group(1) or match.group(2)).rstrip(".,;:!?)")
        path = Path(raw).expanduser()
        try:
            resolved = (path if path.is_absolute() else workdir / path).resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved not in result:
            result.append(resolved)
    return tuple(result)


class ChatImages:
    def __init__(self, cfg: Any, agent: Any):
        self.cfg, self.agent = cfg, agent
        self.store = ArtifactStore(cfg.data_dir / "library")
        self.checked: dict | None = None
        self.cache: dict[str, dict] = {}
        self.transport: Any = None

    def reset(self) -> None:
        self.cache.clear()

    def scope(self) -> str:
        backend = self.agent.model_info.backend
        runtime = (
            getattr(self.agent.runtime, "ollama", None)
            if backend == "ollama"
            else self.agent.runtime
        )
        url = getattr(runtime, "base_url", "")
        scope = [
            normalize_model_url(url, backend) if url else "",
            hashlib.sha256(getattr(runtime, "api_key", "").encode()).hexdigest(),
        ]
        if backend != "ollama":
            scope.insert(0, backend)
        return hashlib.sha256(json.dumps(scope).encode()).hexdigest()

    def verify(self) -> None:
        if self.agent.cancellation_check():
            raise ValueError("Image preparation cancelled")
        if not read_defaults(self.cfg).vision_enabled:
            raise ValueError("Enable Vision in AI Defaults before sending image attachments")
        reference = self.agent.model_info.ref
        connection, model, _ = active_binding(self.cfg, self.agent)
        key = (reference, connection.revision, self.scope())
        if (
            self.checked is None
            or self.checked.get("key") != key
            or time.monotonic() - self.checked["at"] >= 30
        ):
            metadata = inspect_support(self.cfg, self.agent, self.track_transport)
            self.checked = {"key": key, "at": time.monotonic(), **metadata}
        if connection.backend != "ollama":
            self.agent.runtime.image_model = model

    def track_transport(self, transport: Any) -> None:
        self.transport = transport

    def cancel_active(self) -> bool:
        return bool(self.transport is not None and self.transport.cancel_active())

    def capture(self, path: Path, session: str) -> dict:
        if self.agent.cancellation_check():
            raise ValueError("Image preparation cancelled")
        maximum = (
            ANTHROPIC_IMAGE_BYTES
            if self.agent.model_info.backend == "anthropic"
            else MAX_IMAGE_BYTES
        )
        data = read_file(path, maximum + 1)
        if len(data) > maximum:
            raise ValueError(f"Chat images must fit in {maximum:,} bytes for this provider")
        mime, width, height = image_header(data[:65536])
        if (
            mime not in {"image/png", "image/jpeg"}
            or not width
            or not height
            or max(width, height) > 4096
            or width * height > 4_194_304
        ):
            raise ValueError("Chat images require PNG/JPEG up to 4096 per side and 4 megapixels")
        digest = hashlib.sha256(data).hexdigest()
        with self.store.database(write=True) as db:
            existing = db.execute(
                "SELECT id FROM artifacts WHERE kind='media' AND session=? "
                "AND sha256=? AND origin='Chat image attachment' ORDER BY created LIMIT 1",
                (session, digest),
            ).fetchone()
            item = (
                self.store.get(existing["id"])
                if existing
                else self.store._insert(
                    data, "media", path.name, "Chat image attachment", session=session, db=db
                )
            )
        return {
            "id": item["id"],
            "sha256": digest,
            "mime": mime,
            "width": width,
            "height": height,
            "name": plain(path.name, 160),
            "scope": self.scope(),
        }

    def compose(self, text: str, paths: tuple[Path, ...], session: str) -> str | dict:
        self.reset()
        paths = tuple(dict.fromkeys(paths))
        pictures = [p for p in paths if is_image(p)]
        if len(pictures) > MAX_IMAGES:
            raise ValueError("Attach at most two images per message")
        if pictures:
            self.verify()
        context = text_attachments(paths)
        content = text + "\n\n" + context if context else text
        if not pictures:
            return content
        refs = [self.capture(path, session) for path in pictures]
        refs = list({ref["sha256"]: ref for ref in refs}.values())
        return {
            "kind": INPUT_KIND,
            "version": 1,
            "request": text,
            "content": content,
            "image_inputs": refs,
        }

    def load(self, ref: dict) -> dict:
        item = self.store.get(ref["id"])
        if item["size"] > MAX_IMAGE_BYTES or item["sha256"] != ref["sha256"]:
            raise ValueError("Stored chat image changed or exceeds its size bound")
        if any(item[key] != ref[key] for key in ("mime", "width", "height")):
            raise ValueError("Stored chat image metadata changed")
        if ref["id"] not in self.cache:
            with self.store.database() as db:
                data = db.execute(
                    "SELECT substr(content,1,?) FROM artifacts WHERE id=?",
                    (MAX_IMAGE_BYTES + 1, ref["id"]),
                ).fetchone()
            if (
                data is None
                or len(data[0]) != item["size"]
                or hashlib.sha256(data[0]).hexdigest() != ref["sha256"]
            ):
                raise ValueError("Stored chat image checksum failed")
            self.cache[ref["id"]] = {
                "type": "image",
                "mime_type": ref["mime"],
                "data": base64.b64encode(data[0]).decode("ascii"),
            }
        return self.cache[ref["id"]]

    def project(self, messages: list[dict], *, schema_tokens: int = 0) -> tuple[list[dict], int]:
        locations = [
            (i, ref)
            for i, m in enumerate(messages)
            for ref in references(m.get("image_inputs", []))
        ]
        current = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
        current_refs = [ref for i, ref in locations if i == current]
        enabled = (
            bool(locations)
            and read_defaults(self.cfg).vision_enabled
            and self.agent.model_info.backend in IMAGE_BACKENDS
        )
        if current_refs:
            self.verify()
        if enabled and locations:
            try:
                self.verify()
            except (OSError, ValueError):
                if current_refs or self.agent.cancellation_check():
                    raise
                enabled = False
        chosen: list[tuple[int, dict]] = []
        seen = set()
        for i, ref in reversed(locations if enabled else []):
            identity = (ref["sha256"], ref["scope"])
            if ref["scope"] == self.scope() and identity not in seen:
                chosen.append((i, ref))
                seen.add(identity)
                if len(chosen) == MAX_IMAGES:
                    break
        chosen.reverse()
        if current_refs and any(ref["scope"] != self.scope() for ref in current_refs):
            raise ValueError(
                "Image approved for a different endpoint; reattach to authorize its pixels"
            )
        window = self.agent.request_context_window or 8192
        output = max(1024, int(self.agent._last_request_options.get("num_predict", 2048)))
        text_cost = (
            sum(
                (len(str(m.get("content", ""))) + 2) // (3 if m.get("role") == "system" else 2)
                for m in messages
            )
            + schema_tokens
        )
        while chosen and sum(image_cost({"image_inputs": [ref]}) for _, ref in chosen) > max(
            0, window - output - text_cost
        ):
            if chosen[0][0] == current:
                raise ValueError(
                    "Image input exceeds the allocated context estimate; use a smaller image "
                    "or explicitly increase Runtime context"
                )
            chosen.pop(0)
        result, count = [], 0
        for i, message in enumerate(messages):
            item = {
                k: v
                for k, v in message.items()
                if k not in {"image_inputs", "image_content", "images"}
            }
            blocks = []
            loaded = set()
            for ref in references(message.get("image_inputs", [])):
                identity = (ref["sha256"], ref["scope"])
                if (i, ref) not in chosen or identity in loaded:
                    continue
                try:
                    blocks.append(self.load(ref))
                    loaded.add(identity)
                except (OSError, ValueError):
                    if i == current:
                        raise ValueError(
                            "Image pixels are unavailable; reattach the image"
                        ) from None
            if blocks:
                item["image_content"] = blocks
                count += len(blocks)
            elif message.get("image_inputs"):
                item["content"] = str(item.get("content", "")) + (
                    "\n[Image pixels omitted: disabled, unavailable, outside this endpoint's "
                    "approval or outside the working image bound. "
                    "Text descriptions are not fresh visual evidence.]"
                )
            result.append(item)
        return result, count


def unavailable_projection(messages: list[dict]) -> tuple[list[dict], int]:
    result = []
    for message in messages:
        item = {
            k: v for k, v in message.items() if k not in {"image_inputs", "image_content", "images"}
        }
        if message.get("image_inputs"):
            item["content"] = (
                str(item.get("content", "")) + "\n[Image pixels unavailable in this request.]"
            )
        result.append(item)
    return result, 0

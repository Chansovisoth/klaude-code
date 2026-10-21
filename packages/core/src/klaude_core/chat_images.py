"""Private image snapshots and a provider-neutral chat image contract.

History stores bounded artifact references, never base64 pixels. Only the request
projection materializes pixels for an enabled, verified, approved endpoint.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import stat
import sys
import time
from dataclasses import replace
from itertools import islice
from pathlib import Path
from typing import Any

from .ai_defaults import read_defaults
from .chat_image_support import active_binding, inspect_support
from .image_content import IMAGE_BACKENDS, image_token_estimate
from .image_preparation import (
    DETAILS,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_PIXELS,
    MAX_SOURCE_SIDE,
    dimensions,
    prepare_image,
)
from .library_artifacts import ID, ArtifactStore, image_header, plain
from .model_connections import normalize_model_url
from .vision import checked_capabilities

MAX_IMAGES = 2
INPUT_KIND = "chat_image_input"


def references(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_IMAGES:
        raise ValueError("Chat accepts at most two image attachments per turn")
    result = []
    for item in value:
        if (
            not isinstance(item, dict)
            or not {"id", "sha256", "mime", "width", "height", "name", "scope"} <= set(item)
            or set(item) - {"id", "sha256", "mime", "width", "height", "name", "scope", "options"}
            or not isinstance(item["id"], str)
            or not ID.fullmatch(item["id"])
            or not item["id"].startswith(("media:", "document:"))
            or not isinstance(item["sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])
            or not isinstance(item["scope"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", item["scope"])
            or not isinstance(item["mime"], str)
            or item["mime"] not in {"image/png", "image/jpeg", "image/webp", "image/gif"}
            or type(item["width"]) is not int
            or type(item["height"]) is not int
            or not 1 <= item["width"] <= MAX_SOURCE_SIDE
            or not 1 <= item["height"] <= MAX_SOURCE_SIDE
            or item["width"] * item["height"] > MAX_SOURCE_PIXELS
            or not isinstance(item["name"], str)
            or len(item["name"]) > 160
            or not item["name"].isprintable()
        ):
            raise ValueError("Invalid private image reference")
        validate_options(item.get("options", {}))
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


def image_request_text(text: str, refs: list[dict]) -> str:
    """Keep delivered image paths out of intent routing, without hiding other files.

    Directory names such as ``workspace`` and ``models`` describe the attachment's
    location, not a request to inspect files or search a model catalog. The original
    text still belongs in public history and in the actual model message.
    """
    names = {ref["name"] for ref in refs}

    def replace_mention(match: re.Match) -> str:
        raw = (match.group(1) or match.group(2)).rstrip(".,;:!?)")
        return "[attached image]" if plain(Path(raw).name, 160) in names else match.group(0)

    routed = re.sub(r'(?<!\S)@(?:"([^"\n]+)"|([^\s]+))', replace_mention, text)
    return routed if "[attached image]" in routed else routed + "\n[attached image]"


def image_cost(message: dict, *, backend: str = "", model: str = "") -> int:
    """Conservative image-token estimate; encoded bytes are never text tokens."""
    return sum(
        image_token_estimate(
            *dimensions(
                (r.get("options", {}).get("crop") or [0, 0, r["width"], r["height"]])[2],
                (r.get("options", {}).get("crop") or [0, 0, r["width"], r["height"]])[3],
                100_000,
                detail=r.get("options", {}).get("detail", "auto"),
                backend=backend,
                model=model,
            ),
            backend=backend,
            model=model,
        )
        for r in references(message.get("image_inputs", []))
    )


def validate_options(options: Any) -> dict:
    if not isinstance(options, dict) or set(options) - {"detail", "frame", "crop"}:
        raise ValueError("Invalid image options")
    if options.get("detail", "auto") not in DETAILS:
        raise ValueError("Image detail must be auto, detailed or original")
    frame, crop = options.get("frame"), options.get("crop")
    if frame is not None and (type(frame) is not int or not 0 <= frame <= 255):
        raise ValueError("Choose image frame 0–255")
    if crop is not None and (
        not isinstance(crop, (list, tuple))
        or len(crop) != 4
        or any(type(n) is not int or not 0 <= n <= MAX_SOURCE_SIDE for n in crop)
        or crop[2] == 0
        or crop[3] == 0
    ):
        raise ValueError("Image crop must be x,y,width,height in oriented source pixels")
    return options


class AttachmentPath(Path):
    """A queued path with local per-attachment options; no pixels or provider state."""

    _flavour = getattr(type(Path()), "_flavour", None)
    image_options: dict[str, Any]
    stored_id = ""
    source_sha256 = ""

    def __new__(cls, path: Path, options: dict | None = None):
        result = super().__new__(cls, path)
        result.image_options = validate_options(options or {})
        return result

    def __init__(self, path: Path, options: dict | None = None):
        if sys.version_info >= (3, 12):
            super().__init__(path)


def attachment_path(text: str, workdir: Path, context: Any = None) -> Path:
    options: dict = {}
    raw = text
    if text.startswith(("--", '"', "'")):
        parts = shlex.split(text)
        while parts and parts[0].startswith("--"):
            flag = parts.pop(0)
            if flag not in {"--detail", "--frame", "--crop"} or not parts:
                raise ValueError(
                    "Use /attach [--detail auto|detailed|original] "
                    "[--frame N] [--crop x,y,width,height] PATH"
                )
            value = parts.pop(0)
            options[flag[2:]] = (
                value
                if flag == "--detail"
                else int(value)
                if flag == "--frame"
                else [int(n) for n in value.split(",")]
            )
        raw = " ".join(parts)
    if not raw.strip():
        raise ValueError("Choose an attachment path or stored media:ID")
    validate_options(options)
    if context is not None:
        stored = (
            raw
            if ID.fullmatch(raw) and raw.startswith("media:")
            else next(
                (
                    r["id"]
                    for r in reversed(context.known)
                    if r["name"] == raw and not (workdir / raw).exists()
                ),
                "",
            )
        )
        if stored:
            item = context.store.get(stored)
            if item["archived"]:
                raise ValueError("Restore this Media image before attaching it again")
            result = AttachmentPath(Path(item["filename"]), options)
            result.stored_id = stored
            return result
    path = Path(raw).expanduser()
    path = (path if path.is_absolute() else workdir / path).resolve(strict=True)
    return AttachmentPath(path, options)


def read_file(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Attachments must be regular files")
        return stream.read(limit)


def is_image(path: Path) -> bool:
    if getattr(path, "stored_id", ""):
        return True
    if not path.is_file():
        return False
    if path.suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".heic",
        ".heif",
        ".avif",
        ".bmp",
        ".tif",
        ".tiff",
    }:
        return True
    head = read_file(path, 16)
    return head.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8", b"GIF87a", b"GIF89a")) or (
        head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    )


def text_attachments(paths: tuple[Path, ...]) -> str:
    parts = []
    for path in paths:
        try:
            if getattr(path, "stored_id", ""):
                parts.append(
                    f"[Attached image: {plain(path.name, 160)}; pixels are separate from text]"
                )
                continue
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
        self.prepared: list[dict] = []
        self.failed: dict | None = None
        self.attempt: dict | None = None
        self.known: list[dict] = []
        self.repair_scale = 1.0
        self.repair_tokens: int | None = None
        self.transport: Any = None

    def reset(self) -> None:
        self.prepared.clear()

    def remember(self, refs: list[dict]) -> None:
        for ref in references(refs):
            self.known = [
                r
                for r in self.known
                if (r["id"], r.get("options")) != (ref["id"], ref.get("options"))
            ]
            self.known.append(ref)
        self.known = self.known[-100:]

    def finish(self, failed: bool) -> None:
        if self.attempt and failed:
            self.failed = self.attempt
        elif not failed:
            self.failed = None
        self.attempt = None

    def restore_attempt(self, turns: list[dict]) -> None:
        self.failed = None
        self.known.clear()
        candidate, answered, failed = None, False, False
        for turn in turns:
            private = turn.get("model_content")
            if turn.get("role") == "user":
                candidate, answered, failed = None, False, False
                if isinstance(private, dict) and private.get("kind") == INPUT_KIND:
                    try:
                        _, refs = unpack_input(private)
                        self.remember(refs)
                        # The private input envelope also carries text files.
                        # Their retry must not require Vision to be enabled.
                        candidate = private if refs else None
                    except ValueError:
                        pass
            elif turn.get("role") == "assistant":
                answered = True
            elif turn.get("role") == "system" and isinstance(turn.get("content"), dict):
                failed |= turn["content"].get("event") in {"runtime_error", "interruption"}
        self.failed = candidate if failed or not answered else None

    def resolve_retry(self, text: str) -> str | dict:
        retry = bool(
            re.fullmatch(
                r"(?is)\s*(?:please\s+)?(?:try\s+again|retry|retry\s+that|"
                r"try\s+it\s+again)[.!\s]*",
                text,
            )
        )
        if retry and self.failed:
            self.verify()
            self.attempt = dict(self.failed)
            return self.attempt
        selected = [r for r in self.known if r["name"] and r["name"] in text][-MAX_IMAGES:]
        if not selected and re.search(
            r"(?i)\b(?:this|that|the|previous|last|earlier|first|second|both) "
            r"(?:image|photo|picture|screenshot)s?\b",
            text,
        ):
            selected = self.known[-MAX_IMAGES:]
        if selected:
            try:
                self.verify()
            except (OSError, ValueError):
                # An older image does not authorize a new/unavailable provider.
                # Preserve ordinary text continuation with honest omitted pixels.
                self.failed = None
                return text
            self.attempt = {
                "kind": INPUT_KIND,
                "version": 1,
                "request": text,
                "content": text,
                "image_inputs": selected,
            }
            return self.attempt
        self.failed = None
        return text

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
            raise ValueError("Enable Vision in Model Defaults before sending image attachments")
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
        caps = checked_capabilities(self.checked)
        current = self.agent.model_info.capabilities
        limits = [n for n in (current.context_window, caps.context_window) if n]
        self.agent.model_info = replace(
            self.agent.model_info,
            capabilities=replace(
                current,
                supports_images=True,
                images_evidence=caps.images_evidence,
                context_window=min(limits) if limits else None,
                max_output_tokens=caps.max_output_tokens or current.max_output_tokens,
            ),
        )
        if connection.backend != "ollama":
            self.agent.runtime.image_model = model

    def track_transport(self, transport: Any) -> None:
        self.transport = transport

    def cancel_active(self) -> bool:
        return bool(self.transport is not None and self.transport.cancel_active())

    def capture(self, path: Path, session: str, options: dict | None = None) -> dict:
        if self.agent.cancellation_check():
            raise ValueError("Image preparation cancelled")
        options = validate_options(options or {})
        maximum = MAX_SOURCE_BYTES
        stored_id = getattr(path, "stored_id", "")
        if stored_id:
            item = self.store.get(stored_id)
            if item["size"] > maximum or item["archived"]:
                raise ValueError("Choose a current image source up to 32 MiB")
            with self.store.database() as db:
                row = db.execute(
                    "SELECT substr(content,1,?) FROM artifacts WHERE id=?",
                    (maximum + 1, stored_id),
                ).fetchone()
            data = bytes(row[0]) if row else b""
            if len(data) != item["size"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError("Stored image checksum failed")
        else:
            data = read_file(path, maximum + 1)
        if len(data) > maximum:
            raise ValueError(f"Chat images must fit in {maximum:,} bytes for this provider")
        digest = hashlib.sha256(data).hexdigest()
        if getattr(path, "source_sha256", "") not in {"", digest}:
            raise ValueError("Library file changed; choose the attachment again")
        metadata, _ = prepare_image(data, **options, cancelled=self.agent.cancellation_check)
        mime, _, _ = image_header(data[:65536])
        width, height = metadata["source_width"], metadata["source_height"]
        if not stored_id:
            item = self.snapshot(data, path, session, digest)
        return {
            "id": item["id"],
            "sha256": digest,
            "mime": mime,
            "width": width,
            "height": height,
            "name": plain(path.name, 160),
            "scope": self.scope(),
            **({"options": options} if options else {}),
        }

    def snapshot(self, data: bytes, path: Path, session: str, digest: str) -> dict:
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
        return item

    def compose(
        self, text: str, paths: tuple[Path, ...], session: str, options: dict | None = None
    ) -> str | dict:
        self.reset()
        paths = tuple(
            {
                (
                    str(path),
                    getattr(path, "stored_id", ""),
                    json.dumps(getattr(path, "image_options", {})),
                ): path
                for path in paths
            }.values()
        )
        pictures = [p for p in paths if is_image(p)]
        if len(pictures) > MAX_IMAGES:
            raise ValueError("Attach at most two images per message")
        if pictures:
            self.verify()
        context = text_attachments(paths)
        content = text + "\n\n" + context if context else text
        if not pictures:
            return self.resolve_retry(content)
        detailed = bool(
            re.search(r"(?i)\b(text|read|screenshot|diagram|code|document|ocr|detail)\b", text)
        )
        refs = [
            self.capture(
                path,
                session,
                getattr(path, "image_options", {})
                or options
                or ({"detail": "detailed"} if detailed else {}),
            )
            for path in pictures
        ]
        refs = list(
            {(ref["sha256"], json.dumps(ref.get("options", {}))): ref for ref in refs}.values()
        )
        self.remember(refs)
        value = {
            "kind": INPUT_KIND,
            "version": 1,
            "request": text,
            "content": content,
            "image_inputs": refs,
        }
        self.attempt = value
        return value

    def load(self, ref: dict, tokens: int = 100_000) -> dict:
        item = self.store.get(ref["id"])
        if item["size"] > MAX_SOURCE_BYTES or item["sha256"] != ref["sha256"]:
            raise ValueError("Stored chat image changed or exceeds its size bound")
        if item["kind"] == "media" and item["mime"] != ref["mime"]:
            raise ValueError("Stored chat image metadata changed")
        with self.store.database() as db:
            data = db.execute(
                "SELECT substr(content,1,?) FROM artifacts WHERE id=?",
                (MAX_SOURCE_BYTES + 1, ref["id"]),
            ).fetchone()
        if (
            data is None
            or len(data[0]) != item["size"]
            or hashlib.sha256(data[0]).hexdigest() != ref["sha256"]
        ):
            raise ValueError("Stored chat image checksum failed")
        if image_header(bytes(data[0][:65536]))[0] != ref["mime"]:
            raise ValueError("Stored chat image metadata changed")
        options = ref.get("options", {})
        info = self.agent.model_info
        source_size = (options.get("crop") or [0, 0, ref["width"], ref["height"]])[2:]
        target = dimensions(
            source_size[0],
            source_size[1],
            tokens,
            detail=options.get("detail", "auto"),
            backend=info.backend,
            model=info.model_id,
        )
        key = json.dumps(
            [ref["sha256"], self.scope(), info.backend, info.model_id, target, options]
        )
        if key not in self.cache:
            metadata, prepared = prepare_image(
                data[0],
                tokens=tokens,
                backend=info.backend,
                model=info.model_id,
                **options,
                cancelled=self.agent.cancellation_check,
            )
            if (metadata["source_width"], metadata["source_height"]) != (
                ref["width"],
                ref["height"],
            ):
                raise ValueError("Stored chat image dimensions changed")
            if len(self.cache) >= 4:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = {
                "metadata": metadata,
                "part": {
                    "type": "image",
                    "mime_type": metadata["mime"],
                    "data": base64.b64encode(prepared).decode("ascii"),
                },
            }
        self.prepared.append({"name": ref["name"], **self.cache[key]["metadata"]})
        return self.cache[key]["part"]

    def project(
        self, messages: list[dict], *, schema_tokens: int = 0, _compacted: bool = False
    ) -> tuple[list[dict], int]:
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
            identity = (ref["sha256"], ref["scope"], json.dumps(ref.get("options", {})))
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
        budget = self.agent.request_budget
        window, output = budget.context, budget.output
        text_cost = (
            sum(
                (len(str(m.get("content", ""))) + 2) // (3 if m.get("role") == "system" else 2)
                + sum(
                    len(json.dumps(m.get(k, ""), default=str)) // 2
                    for k in (
                        "tool_calls",
                        "openai_response_items",
                        "codex_reasoning_items",
                        "openrouter_reasoning_details",
                        "anthropic_continuation",
                        "deepseek_continuation",
                        "gemini_continuation",
                    )
                    if m.get(k)
                )
                for m in messages
            )
            + schema_tokens
            + (256 * (1 + len(chosen)) if chosen else 0)
        )
        while chosen and window - output - text_cost < 512 * len(chosen):
            if chosen[0][0] == current:
                if not _compacted:
                    from .context_compaction import build_recap

                    previous_user = max(
                        (i for i, m in enumerate(messages[:current]) if m.get("role") == "user"),
                        default=1,
                    )
                    if current > previous_user:
                        # Whole earlier user/tool rounds are replaced together.
                        # Keep the full current round and the generated policy.
                        recap = build_recap(messages[1:current], 1200)
                        shortened = [messages[0], *([recap] if recap else []), *messages[current:]]
                        return self.project(shortened, schema_tokens=schema_tokens, _compacted=True)
                raise ValueError(
                    "Image input exceeds the allocated context: essential text, "
                    "tools and reserved output leave insufficient space even after "
                    "automatic resizing. Shorten the question or adjust Runtime context."
                )
            chosen.pop(0)
        available = max(1, int((window - output - text_cost) * self.repair_scale))
        per_image = available // max(1, len(chosen))
        if self.repair_tokens is not None:
            per_image = min(per_image, self.repair_tokens)
        self.prepared.clear()
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
                identity = (ref["sha256"], ref["scope"], json.dumps(ref.get("options", {})))
                if (i, ref) not in chosen or identity in loaded:
                    continue
                try:
                    blocks.append(self.load(ref, per_image))
                    loaded.add(identity)
                except (OSError, ValueError) as exc:
                    if i == current:
                        raise ValueError(
                            "Image pixels are unavailable or preparation failed: " + str(exc)
                        ) from None
            if blocks:
                item["image_content"] = blocks
                prepared = self.prepared[-len(blocks) :]
                item["content"] = (
                    str(item.get("content", ""))
                    + "\n"
                    + "\n".join(
                        f"[Image preparation: source {p['oriented_width']}×{p['oriented_height']}; "
                        f"supplied {p['width']}×{p['height']}; "
                        f"crop {p['crop']}; frame {p['frame']}. "
                        "Coordinates refer to supplied pixels; fine detail may require a crop.]"
                        for p in prepared
                        if p["crop"] is not None
                        or p["frame"] is not None
                        or (p["width"], p["height"]) != (p["oriented_width"], p["oriented_height"])
                    )
                )
                count += len(blocks)
            elif message.get("image_inputs"):
                item["content"] = str(item.get("content", "")) + (
                    "\n[Image pixels omitted: disabled, unavailable, outside this endpoint's "
                    "approval or outside the working image bound. "
                    "Text descriptions are not fresh visual evidence.]"
                )
            result.append(item)
        if count and self.attempt is None:
            refs = [ref for _, ref in chosen]
            self.attempt = {
                "kind": INPUT_KIND,
                "version": 1,
                "request": str(messages[current].get("content", "")),
                "content": str(messages[current].get("content", "")),
                "image_inputs": refs,
            }
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

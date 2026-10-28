"""Durable conversational image actions, sharing the reviewed image worker/store.

One logical action per admitted chat turn. A reserved child is never submitted
again after an uncertain admission. The external server cannot promise exactly
once execution; durable admission and pixel publication are idempotent.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from typing import Any

from klaude_core import Tool
from klaude_core import image_generation as generation
from klaude_core.library_artifacts import ArtifactStore
from klaude_core.settings_store import read_settings

TERMINAL = {"completed", "failed", "cancelled", "unknown"}
ERRORS = {
    "failed": "Image generation failed. Check the local service and available memory.",
    "unknown": "Outcome unconfirmed. Check the original job; do not submit it again.",
    "source": "Source image is missing, changed or outside this conversation.",
}
NEGATIVE = re.compile(
    r"(?i)\b(?:don't|do not|never|not yet|avoid|without)\b.{0,35}"
    r"\b(?:generate|draw|create|render|generation)\b|"
    r"\b(?:translate|summari[sz]e|quote|example of|what would happen)\b|"
    r"^(?:please )?(?:why|how|what (?:is|does)|tell me why)\b|"
    r"\b(?:explain|how (?:do|does|to)|write (?:an? |the )?(?:image |sd )?prompt|"
    r"search|find (?:photos|images)|analy[sz]e|describe (?:this|the) (?:image|photo|screenshot))\b|"
    r"\b(?:svg|html|css|mermaid|canvas|component|image gallery|code)\b"
)


def image_intent(text: str, has_images: bool = False) -> dict[str, Any] | None:
    """Conservative direct raster intent; all candidates still pass policy and admission."""
    value = text.strip()
    if NEGATIVE.search(value):
        return None
    selected = re.match(r"(?i)^(edit|regenerate) image (media:[a-f0-9]{32}):\s*(.*)", value, re.S)
    direct = re.search(
        r"(?i)\b(?:generate|create|make|draw|render|paint|illustrate)\b.{0,60}"
        r"\b(?:images?|pictures?|photos?|paintings?|illustrations?|portraits?|landscapes?|wallpaper|pixel.art)\b",
        value,
    )
    direct = direct or re.match(
        r"(?i)^(?:please )?(?:draw|paint|illustrate)\s+(?:me\s+)?(?:an?|the)\s+\S", value
    )
    followup = (
        has_images or bool(re.search(r"(?i)\b(?:last|first|second|third) image\b", value))
    ) and re.match(
        r"(?i)^(?:make (?:it|this image|that image|the (?:last|second|first) (?:one|image))|"
        r"(?:edit|refine|change) (?:it|this|the)|try (?:again|a .*version)|"
        r"(?:generate|create) (?:another|\d+ more|two more|three more)|"
        r"use (?:this|the attached|my uploaded) (?:image|picture|photo))\b",
        value,
    )
    if (has_images or direct or selected) and re.search(
        r"(?i)\b(?:only the|inpaint|mask|remove (?:the|this)|keep everything else)\b", value
    ):
        return {
            "clarify": "Localized edits need an explicit mask. I can make a broader "
            "image-to-image refinement if you ask for that; the current chat editor "
            "does not supply masks."
        }
    if not direct and not followup and not selected:
        return None
    request: dict[str, Any] = {"prompt": value, "operation": "edit" if followup else "generate"}
    if selected:
        request.update(
            source=selected[2],
            prompt=selected[3] or "A new variation of this image",
            operation="edit" if selected[1].lower() == "edit" else "variation",
        )
    if re.search(r"(?i)\b(?:again|another|more|variation)\b", value) and followup:
        request["operation"] = "variation"
    number = re.search(r"(?i)\b(one|two|three|four|\d+)\s+(?:more\b|images?\b|pictures?\b)", value)
    if number:
        request["count"] = {"one": 1, "two": 2, "three": 3, "four": 4}.get(
            number[1].lower(), int(number[1]) if number[1].isdigit() else 1
        )
    ratio = re.search(r"\b(\d{1,2}):(\d{1,2})\b", value)
    sizes = {
        "1:1": (512, 512),
        "16:9": (1024, 576),
        "9:16": (576, 1024),
        "3:2": (768, 512),
        "2:3": (512, 768),
        "4:3": (768, 576),
        "3:4": (576, 768),
    }
    if ratio:
        key = f"{int(ratio[1])}:{int(ratio[2])}"
        if key not in sizes:
            return {
                "clarify": "Choose a supported image ratio: 1:1, 16:9, 9:16, 3:2, 2:3, 4:3 or 3:4."
            }
        request["width"], request["height"] = sizes[key]
    elif re.search(r"(?i)\bportrait\b", value):
        request.update(width=512, height=768)
    dimensions = re.search(r"\b(\d{3,4})\s*[x×]\s*(\d{3,4})\b", value)
    if dimensions:
        request.update(width=int(dimensions[1]), height=int(dimensions[2]))
    steps = re.search(r"(?i)\b(\d+)\s+steps\b", value)
    seed = re.search(r"(?i)\bseed\s+(-?\d+)\b", value)
    if steps:
        request["steps"] = int(steps[1])
    if seed:
        request["seed"] = int(seed[1])
    return request


class ChatImageActions:
    def __init__(self, cfg: Any, memory: Any, turns: Any, workspace: Any) -> None:
        self.cfg, self.memory, self.turns, self.workspace = cfg, memory, turns, workspace
        self.operations: Any = None
        self._owns_operations = False
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._lock = threading.RLock()
        with memory._db_lock, memory.db:
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_image_actions ("
                "id TEXT PRIMARY KEY, session TEXT NOT NULL, turn_id TEXT NOT NULL UNIQUE, "
                "message_row INTEGER NOT NULL, state TEXT NOT NULL, specs TEXT NOT NULL, "
                "position INTEGER NOT NULL DEFAULT 0, assets TEXT NOT NULL DEFAULT '[]', "
                "error TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 0, "
                "lease REAL NOT NULL DEFAULT 0, operation_id TEXT NOT NULL DEFAULT '', "
                "created REAL NOT NULL)"
            )
            memory.db.execute(
                "CREATE INDEX IF NOT EXISTS image_action_session ON "
                "application_image_actions(session,created)"
            )
            memory.db.execute(
                "CREATE INDEX IF NOT EXISTS image_action_state ON "
                "application_image_actions(state,created)"
            )
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_image_sources ("
                "session TEXT NOT NULL, artifact TEXT NOT NULL, PRIMARY KEY(session,artifact))"
            )

    def _operations(self) -> Any:
        with self._lock:
            if self.operations is None:
                from .library_management import LibraryManagement

                self.operations = LibraryManagement(self.cfg, self.workspace)
                self._owns_operations = True
            return self.operations

    def _read(self, identity: str, session: str | None = None) -> dict[str, Any] | None:
        with self.memory._db_lock:
            cursor = self.memory.db.execute(
                "SELECT * FROM application_image_actions WHERE id=?",
                (identity,),
            )
            row = cursor.fetchone()
            result = (
                dict(zip([item[0] for item in cursor.description], row, strict=True))
                if row
                else None
            )
        return result if result and (session is None or result["session"] == session) else None

    def _required(self, identity: str) -> dict[str, Any]:
        row = self._read(identity)
        if row is None:
            raise ValueError("Image action no longer exists")
        return row

    def for_turn(self, turn: str) -> dict[str, Any] | None:
        with self.memory._db_lock:
            row = self.memory.db.execute(
                "SELECT id FROM application_image_actions WHERE turn_id=?",
                (turn,),
            ).fetchone()
        return self._read(row[0]) if row else None

    def public(self, row: dict[str, Any]) -> dict[str, Any]:
        specs = json.loads(row["specs"])
        assets = []
        store = ArtifactStore(self.cfg.data_dir / "library")
        for identity in json.loads(row["assets"]):
            try:
                item = store.get(identity)
                if item["archived"] or item["session"] != row["session"]:
                    continue
                assets.append(
                    {
                        key: item[key]
                        for key in (
                            "id",
                            "revision",
                            "mime",
                            "width",
                            "height",
                            "size",
                        )
                    }
                )
            except (OSError, ValueError):
                continue
        return {
            "id": row["id"],
            "state": row["state"],
            "assets": assets,
            "count": len(specs),
            "outputs": [{"width": spec["width"], "height": spec["height"]} for spec in specs],
            "position": row["position"],
            "error": row["error"],
            "cancellable": row["state"] in {"queued", "starting", "running"},
            "recoverable": row["state"] == "unknown",
        }

    def project(self, snapshot: dict[str, Any]) -> None:
        with self.memory._db_lock:
            rows = self.memory.db.execute(
                "SELECT id,message_row FROM application_image_actions WHERE session=? "
                "ORDER BY created DESC LIMIT 100",
                (snapshot["session_id"],),
            ).fetchall()
        indexed = {f"stored:{message}": identity for identity, message in rows}
        for message in snapshot["messages"]:
            if message["id"] in indexed:
                row = self._read(indexed[message["id"]], snapshot["session_id"])
                if row:
                    message["image_action"] = self.public(row)
        if any(
            row and row["state"] not in TERMINAL
            for row in (self._read(identity) for identity, _ in rows)
        ):
            self.start()

    def galleries(self, session: str) -> list[list[str]]:
        with self.memory._db_lock:
            rows = self.memory.db.execute(
                "SELECT assets FROM application_image_actions WHERE session=? AND assets<>'[]' "
                "ORDER BY created DESC LIMIT 10",
                (session,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def recent(self, session: str) -> bool:
        with self.memory._db_lock:
            return bool(
                self.memory.db.execute(
                    "SELECT 1 FROM application_image_actions WHERE session=? AND message_row=("
                    "SELECT max(rowid) FROM turns WHERE session_id=? AND role='assistant')",
                    (session, session),
                ).fetchone()
            )

    def _source(self, session: str, prompt: str, identity: str = "") -> tuple[dict, dict]:
        galleries = self.galleries(session)
        permitted = {asset for gallery in galleries for asset in gallery}
        if not identity:
            if not galleries:
                raise ValueError(
                    "Attach a source image or generate an image in this conversation first."
                )
            gallery = galleries[0]
            ordinal = re.search(r"(?i)\b(first|second|third|last)\b", prompt)
            index = {"first": 0, "second": 1, "third": 2, "last": -1}.get(
                ordinal[1].lower() if ordinal else "", 0
            )
            if len(gallery) > 1 and ordinal is None:
                raise ValueError("Which image should I edit: first, second, or third?")
            if index >= len(gallery):
                raise ValueError("That image is not in the most recent gallery.")
            identity = gallery[index]
        if identity not in permitted:
            with self.memory._db_lock:
                historical = self.memory.db.execute(
                    "SELECT 1 FROM application_image_actions WHERE session=? "
                    "AND instr(assets,?)>0 LIMIT 1",
                    (session, json.dumps(identity)),
                ).fetchone()
                attached = self.memory.db.execute(
                    "SELECT 1 FROM application_image_sources WHERE session=? AND artifact=?",
                    (session, identity),
                ).fetchone()
            if not historical and not attached:
                raise ValueError(ERRORS["source"])
        item = ArtifactStore(self.cfg.data_dir / "library").get(identity)
        reference = {key: item[key] for key in ("id", "revision", "sha256")}
        generation.source_pixels(self.cfg, reference, session)
        return reference, item

    def reserve(self, handle: Any, worker: str, fence: int, arguments: dict[str, Any]) -> dict:
        existing = self.for_turn(handle.turn_id)
        if existing:
            return existing
        allowed = {
            "prompt",
            "operation",
            "source",
            "count",
            "width",
            "height",
            "steps",
            "seed",
            "strength",
            "negative_prompt",
        }
        if set(arguments) - allowed:
            raise ValueError("Unsupported image parameters")
        prompt = arguments.get("prompt", "")
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000:
            raise ValueError("Image prompt must contain 1–2000 characters")
        operation = arguments.get("operation", "generate")
        if not isinstance(operation, str) or operation not in {"generate", "edit", "variation"}:
            raise ValueError(
                "Choose generate, edit or variation; masked inpainting is not available"
            )
        if not isinstance(arguments.get("source", ""), str):
            raise ValueError("Choose a managed source image ID")
        count = arguments.get("count", 1)
        if type(count) is not int or not 1 <= count <= 3:
            raise ValueError("Generate between one and three images per request")
        options: dict[str, Any] = {
            key: arguments[key]
            for key in (
                "width",
                "height",
                "steps",
                "seed",
                "negative_prompt",
            )
            if key in arguments
        }
        if generation.read(self.cfg).get("provider", "sdcpp") != "sdcpp":
            raise ValueError(
                "Conversational images require the configured local Stable Diffusion service"
            )
        if operation != "generate":
            source, item = self._source(handle.session_id, prompt, arguments.get("source", ""))
            options.update(source=source, strength=arguments.get("strength", 0.35))
            options.setdefault("width", max(256, min(1024, round(item["width"] / 64) * 64)))
            options.setdefault("height", max(256, min(1024, round(item["height"] / 64) * 64)))
            info = ArtifactStore(self.cfg.data_dir / "library").generation_info(item["id"])
            if re.search(r"(?i)\bsame seed\b", prompt):
                if "seed" in info:
                    options["seed"] = info["seed"]
        elif arguments.get("source"):
            raise ValueError("Choose edit when supplying a source image")
        identity = hashlib.sha256(("chat-image:" + handle.turn_id).encode()).hexdigest()[:32]
        specs = []
        for index in range(count):
            effective = (
                str(info.get("prompt", ""))[:1400] + "\nRefinement: " + prompt
                if operation != "generate" and info.get("prompt")
                else prompt
            )
            child_options = dict(options)
            if child_options.get("seed", -1) == -1:
                child_options["seed"] = secrets.randbits(32)
            spec = generation.prepare(
                self.cfg, effective[:2000], session=handle.session_id, **child_options
            )
            spec["user_prompt"] = prompt
            spec["id"] = hashlib.sha256(f"{identity}:{index}".encode()).hexdigest()[:32]
            specs.append(spec)
        with self.memory._db_lock, self.memory.db:
            self.memory.db.execute("BEGIN IMMEDIATE")
            self.turns._assert_fence(handle.session_id, handle.turn_id, worker, fence)
            previous = self.memory.db.execute(
                "SELECT id FROM application_image_actions WHERE turn_id=?",
                (handle.turn_id,),
            ).fetchone()
            if previous:
                return self._required(previous[0])
            if (
                self.memory.db.execute(
                    "SELECT count(*) FROM application_image_actions WHERE state IN "
                    "('queued','starting','running','cancelling')",
                ).fetchone()[0]
                >= 8
            ):
                raise ValueError("The local image queue is full; wait for an image to finish")
            message = self.memory.db.execute(
                "INSERT INTO turns(session_id,ts,role,content) VALUES (?,?,?,?)",
                (handle.session_id, time.time(), "assistant", json.dumps("Image queued.")),
            ).lastrowid
            self.memory.db.execute(
                "INSERT INTO application_image_actions "
                "(id,session,turn_id,message_row,state,specs,created) VALUES (?,?,?,?,?,?,?)",
                (
                    identity,
                    handle.session_id,
                    handle.turn_id,
                    message,
                    "queued",
                    json.dumps(specs),
                    time.time(),
                ),
            )
            self.turns._append(
                handle.session_id, handle.turn_id, "image-owner", "image.changed", {}
            )
        self.start()
        return self._required(identity)

    def _update(
        self,
        row: dict,
        state: str,
        *,
        assets: list | None = None,
        error: str = "",
        position: int | None = None,
        operation_id: str | None = None,
    ) -> bool:
        with self.memory._db_lock, self.memory.db:
            self.memory.db.execute("BEGIN IMMEDIATE")
            self.turns._assert_not_deleted(row["session"])
            if (
                state == "starting"
                and self.memory.db.execute(
                    "SELECT 1 FROM application_image_actions WHERE id<>? AND "
                    "state IN ('starting','running','cancelling') LIMIT 1",
                    (row["id"],),
                ).fetchone()
            ):
                return False
            updated = self.memory.db.execute(
                "UPDATE application_image_actions SET state=?,assets=?,error=?,position=?,"
                "operation_id=?,version=version+1,lease=? WHERE id=? AND version=?",
                (
                    state,
                    json.dumps(assets if assets is not None else json.loads(row["assets"])),
                    error,
                    row["position"] if position is None else position,
                    row["operation_id"] if operation_id is None else operation_id,
                    time.time() + 60,
                    row["id"],
                    row["version"],
                ),
            )
            if not updated.rowcount:
                return False
            caption = {
                "completed": "Generated image"
                + ("s." if len(json.loads(row["specs"])) > 1 else "."),
                "failed": ERRORS["failed"],
                "unknown": ERRORS["unknown"],
                "cancelled": "Image generation cancelled.",
            }.get(state, "Generating image…")
            if state == "completed":
                caption += "\nLibrary assets: " + ", ".join(assets or json.loads(row["assets"]))
            self.memory.db.execute(
                "UPDATE turns SET content=? WHERE rowid=? AND session_id=?",
                (json.dumps(caption), row["message_row"], row["session"]),
            )
            self.turns._append(row["session"], row["turn_id"], "image-owner", "image.changed", {})
            return True

    def start(self) -> None:
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._monitor, daemon=True, name="klaude-chat-images"
                )
                self._worker.start()

    def _monitor(self) -> None:
        while not self._stop.wait(0.5):
            try:
                self.tick()
                with self._lock, self.memory._db_lock:
                    if not self.memory.db.execute(
                        "SELECT 1 FROM application_image_actions WHERE state IN "
                        "('queued','starting','running','cancelling') LIMIT 1",
                    ).fetchone():
                        self._worker = None
                        return
            except Exception:
                # No automatic provider replay after a monitor/storage failure.
                continue

    def tick(self) -> None:
        with self.memory._db_lock:
            identities = self.memory.db.execute(
                "SELECT id FROM application_image_actions WHERE state IN "
                "('queued','starting','running','cancelling') ORDER BY created LIMIT 8",
            ).fetchall()
        for (identity,) in identities:
            row = self._read(identity)
            if not row or row["state"] in TERMINAL:
                continue
            specs = json.loads(row["specs"])
            spec = specs[row["position"]]
            opid = row["operation_id"] or spec["id"]
            ops = self._operations()
            if row["state"] == "queued":
                with self.memory._db_lock:
                    busy = self.memory.db.execute(
                        "SELECT 1 FROM application_image_actions WHERE id<>? AND "
                        "state IN ('starting','running','cancelling') LIMIT 1",
                        (identity,),
                    ).fetchone()
                if busy:
                    continue
                if not self._update(row, "starting", operation_id=spec["id"]):
                    continue
                try:
                    ops.submit_image(spec, spec["id"])
                    current = self._required(identity)
                    if current["state"] == "starting":
                        self._update(current, "running")
                except Exception:
                    current = self._required(identity)
                    if current["state"] not in TERMINAL:
                        self._update(current, "unknown", error=ERRORS["unknown"])
                continue
            try:
                record = generation.job(self.cfg, spec["id"])
            except (OSError, ValueError):
                record = {}
            store = ArtifactStore(self.cfg.data_dir / "library")
            try:
                stored = store.generated_for_job(spec["id"])
                if stored:
                    record["artifact"] = stored["id"]
                artifact = store.get(record["artifact"]) if record.get("artifact") else None
            except ValueError:
                self._update(row, "failed", error="The saved image output is no longer available.")
                continue
            if artifact:
                if artifact["session"] != row["session"]:
                    self._update(row, "failed", error=ERRORS["source"])
                    continue
                assets = list(dict.fromkeys([*json.loads(row["assets"]), artifact["id"]]))
                more = row["position"] + 1 < len(specs) and row["state"] != "cancelling"
                self._update(
                    row,
                    "queued" if more else "completed",
                    assets=assets,
                    position=row["position"] + 1 if more else row["position"],
                    operation_id="" if more else opid,
                )
                continue
            if record.get("status") == "cancelled":
                self._update(row, "cancelled")
                continue
            if record.get("status") == "failed":
                self._update(row, "failed", error=ERRORS["failed"])
                continue
            if row["state"] == "cancelling" and opid == spec["id"] and record.get("remote_id"):
                self.control(identity, row["session"], "cancel")
                continue
            try:
                receipt = ops.status(opid)
            except ValueError:
                receipt = {}
            if receipt.get("state") in {"unknown", "failed", "cancelled", "completed"}:
                state = "failed" if receipt["state"] == "failed" and not record else "unknown"
                self._update(row, state, error=ERRORS[state])
            elif row["lease"] < time.time() and not receipt:
                self._update(row, "unknown", error=ERRORS["unknown"])

    def control(
        self,
        identity: str,
        session: str,
        operation: str,
        request_id: str = "original",
        *,
        _attempt: int = 0,
    ) -> dict:
        if _attempt >= 8:
            raise ValueError("Image state changed; check its saved outcome before trying again")
        row = self._read(identity, session)
        if not row:
            raise ValueError("Image action is not in this conversation")
        if operation not in {"cancel", "recover"}:
            raise ValueError("Choose cancel or recover")
        if row["state"] == "queued" and operation == "cancel":
            if not self._update(row, "cancelled"):
                return self.control(identity, session, operation, request_id, _attempt=_attempt + 1)
            return self.public(self._required(identity))
        if row["state"] in {"completed", "failed", "cancelled"}:
            return self.public(row)
        spec = json.loads(row["specs"])[row["position"]]
        opid = hashlib.sha256(
            f"{identity}:{row['position']}:{operation}:{request_id}".encode(),
        ).hexdigest()[:32]
        ops = self._operations()
        if operation == "cancel":
            try:
                acknowledged = generation.job(self.cfg, spec["id"]).get("remote_id")
            except (OSError, ValueError):
                acknowledged = None
            if not acknowledged:
                # Admission can finish before the disposable worker has saved its
                # native job ID. Retain the cancellation until exact-job cleanup
                # becomes possible; never issue a global interrupt.
                if not self._update(row, "cancelling"):
                    return self.control(
                        identity, session, operation, request_id, _attempt=_attempt + 1
                    )
                self.start()
                return self.public(self._required(identity))
        try:
            ops.status(opid)
        except ValueError:
            reviewed = ops.prepare(
                "chat-image",
                {
                    "operation": "image-cancel" if operation == "cancel" else "image-recover",
                    "target": spec["id"],
                },
            )
            ops.submit("chat-image", reviewed["review_id"], opid)
        self._update(row, "cancelling" if operation == "cancel" else "running", operation_id=opid)
        self.start()
        return self.public(self._required(identity))

    def wait(self, identity: str, cancelled: Any) -> dict:
        while not cancelled():
            row = self._required(identity)
            if row["state"] in TERMINAL:
                return self.public(row)
            time.sleep(0.2)
        return self.public(self._required(identity))

    def tool(
        self,
        handle: Any,
        worker: str,
        fence: int,
        agent: Any,
        attachments: Any = None,
        user_request: str = "",
    ) -> Tool:
        def execute(**arguments: Any) -> str:
            if handle is None:
                raise ValueError("Image actions require an admitted conversation turn")
            if agent.plan_mode:
                raise ValueError("Leave Plan mode before generating images")
            if NEGATIVE.search(user_request):
                raise ValueError("This message does not authorize raster image generation.")
            if re.search(r"(?i)\b(?:only the|inpaint|mask|keep everything else)\b", user_request):
                raise ValueError("Localized edits require a mask; chat inpainting is unavailable.")
            raw = read_settings(self.cfg.data_dir / "chat-preferences.json")
            if (
                raw.get("tool_availability", {}).get("generate_image") is False
                or "generate_image" in agent.disabled_tool_names
            ):
                raise ValueError("Image generation is disabled in Agent settings")
            files = [file for file in attachments.files if file.image] if attachments else []
            if (
                not self.for_turn(handle.turn_id)
                and files
                and not arguments.get("source")
                and arguments.get("operation") in {"edit", "variation"}
            ):
                if len(files) != 1:
                    raise ValueError("Attach one image to edit, or select an existing image.")
                from klaude_core.image_preparation import prepare_image

                _, pixels = prepare_image(files[0].data, preserve_alpha=True)
                source = ArtifactStore(self.cfg.data_dir / "library").store_chat_image_source(
                    pixels,
                    files[0].name,
                    handle.session_id,
                )
                with self.memory._db_lock, self.memory.db:
                    self.memory.db.execute(
                        "INSERT OR IGNORE INTO application_image_sources VALUES (?,?)",
                        (handle.session_id, source["id"]),
                    )
                arguments["source"] = source["id"]
            row = self.reserve(handle, worker, fence, arguments)
            result = self.wait(row["id"], handle.cancelled.is_set)
            return (
                "Generated image assets: " + ", ".join(asset["id"] for asset in result["assets"])
                if result["state"] == "completed"
                else result["error"]
                or "Image job continues independently. Use its image card for status."
            )

        return Tool(
            "generate_image",
            "Generate raster images with local Stable Diffusion. "
            "Use edit with an actual conversation source ID for refinements; variation uses "
            "a new seed. Never use for prompt writing, search, analysis, SVG or code. "
            "One durable action per turn; duplicate calls return the original action. "
            "Masked inpainting is unavailable.",
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["prompt"],
                "properties": {
                    "prompt": {"type": "string", "maxLength": 2000},
                    "operation": {"type": "string", "enum": ["generate", "edit", "variation"]},
                    "source": {"type": "string"},
                    "count": {"type": "integer", "minimum": 1, "maximum": 3},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "steps": {"type": "integer"},
                    "seed": {"type": "integer"},
                    "strength": {"type": "number", "minimum": 0.01, "maximum": 1},
                    "negative_prompt": {"type": "string", "maxLength": 2000},
                },
            },
            execute,
            return_direct=True,
        )

    def close(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=3)
        if self._owns_operations and self.operations is not None:
            self.operations.close()

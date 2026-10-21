"""Reviewed, bounded image analysis and explicit AI-tag application."""

from __future__ import annotations

from typing import Any

from klaude_core.ai_defaults import read_defaults
from klaude_core.config import Config
from klaude_core.image_preparation import MAX_SOURCE_BYTES
from klaude_core.image_tags import QUESTION, checked_tags
from klaude_core.library_artifacts import ArtifactStore
from klaude_core.research import model_binding
from klaude_core.vision import budget, question_text

from .browser_results import BrowserResults
from .operation_journal import OperationJournal
from .vision import VisionCommand

OPERATIONS = frozenset({"vision-analyze", "vision-tags", "vision-tags-apply"})
READ_OPERATIONS = frozenset({"vision-analyze", "vision-tags"})


def resource(identity: str) -> str:
    return "vision:" + identity


def _current(cfg: Config, identity: str, revision: int) -> dict[str, Any]:
    item = ArtifactStore(cfg.data_dir / "library").get(identity)
    if (type(revision) is not int or item["revision"] != revision or item["archived"]
            or item["mime"] not in {"image/png", "image/jpeg", "image/webp", "image/gif"}
            or item["size"] > MAX_SOURCE_BYTES):
        raise ValueError("Choose a current saved image up to 32 MiB")
    return item


def result(cfg: Config, identity: str) -> dict[str, Any]:
    item = BrowserResults(cfg.data_dir).get(identity)
    receipt = OperationJournal(cfg.data_dir / "operations.db").status(identity, "web-admin")
    if (receipt is None or receipt.state != "completed" or receipt.kind not in READ_OPERATIONS
            or receipt.resource != resource(item["artifact"])):
        raise ValueError("Completed image result unavailable")
    _current(cfg, item["artifact"], item["revision"])
    return item


def results(cfg: Config, identity: str, revision: int) -> dict[str, Any]:
    _current(cfg, identity, revision)
    items = []
    store = BrowserResults(cfg.data_dir)
    for identifier in store.listing(identity, revision):
        try:
            stored = result(cfg, identifier)
        except ValueError:
            continue
        payload = stored["payload"]
        public = {key: payload[key] for key in ("kind", "model", "text", "tags") if key in payload}
        items.append({"id": identifier, "created": stored["created"], **public})
    pending = None
    if (cfg.data_dir / "operations.db").exists():
        fenced = OperationJournal(cfg.data_dir / "operations.db").fenced_operation(
            resource(identity)
        )
        if fenced is not None:
            pending = {"request_id": fenced.receipt.request_id, "state": fenced.receipt.state}
    return {"items": items, "pending": pending, "available_hours": 24}


def prepare_vision_operation(
    cfg: Config, draft: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    operation = draft["operation"]
    if operation == "vision-tags-apply":
        if set(draft) != {"operation", "result", "selected"}:
            raise ValueError("Choose offered tags from a completed image result")
        stored = result(cfg, draft["result"])
        payload = stored["payload"]
        selected = checked_tags(draft["selected"])
        if payload["kind"] != "tags" or any(tag not in payload["tags"] for tag in selected):
            raise ValueError("Select only tags offered by this exact result")
        name = ArtifactStore(cfg.data_dir / "library").get(stored["artifact"])["name"]
        return {"proposal": payload["proposal"], "selected": selected}, (
            "artifact:" + stored["artifact"]
        ), f"Save AI tags for {name}: " + ", ".join(selected) + ". Manual tags are retained."
    fields = {"operation", "target", "revision", "context", "output_tokens"}
    if operation == "vision-analyze":
        fields.add("question")
    if operation not in READ_OPERATIONS or set(draft) != fields:
        raise ValueError("Invalid image analysis request")
    item = _current(cfg, draft["target"], draft["revision"])
    budget(draft["context"], draft["output_tokens"])
    question = question_text(draft["question"]) if operation == "vision-analyze" else QUESTION
    defaults = read_defaults(cfg)
    if not defaults.vision_enabled or not defaults.vision:
        raise ValueError("Choose and enable a Vision model in Settings → Model Defaults")
    models = []
    for reference in (defaults.vision, *defaults.vision_fallbacks):
        connection, _, credential = model_binding(cfg, reference)
        models.append({"reference": reference, "connection_revision": connection.revision,
                       "credential_revision": credential})
    verb = "Analyze" if operation == "vision-analyze" else "Suggest tags for"
    return {"artifact": item["id"], "revision": item["revision"], "sha256": item["sha256"],
            "question": question, "models": models,
            "context": draft["context"], "output_tokens": draft["output_tokens"]}, resource(
                item["id"]
            ), (f"{verb} {item['name']}.\n"
                f"Models in order: {', '.join(item['reference'] for item in models)}\n"
                f"Context: {draft['context']} tokens. Output: {draft['output_tokens']} tokens.\n"
                "Sends prepared image pixels after fresh capability checks. "
                "Configured providers may charge for requests. "
                "Tags are saved only after a separate review.")


def run_vision_operation(cfg: Config, request: dict[str, Any]) -> dict[str, bool]:
    operation = request["operation"]
    if operation == "vision-tags-apply":
        from klaude_core.image_tags import apply

        started = False

        def gate() -> None:
            nonlocal started
            OperationJournal(cfg.data_dir / "operations.db").check_effect(
                request["request_id"], "web-admin", request["fence"],
            )
            started = True

        try:
            apply(cfg, request["proposal"], request["selected"], before_publish=gate)
        except Exception as exc:
            if started:
                raise RuntimeError(
                    "AI tag save is unconfirmed; inspect its current revision"
                ) from exc
            if isinstance(exc, ValueError):
                return {"rejected": True}
            raise
        return {"ok": True}
    current = _current(cfg, request["artifact"], request["revision"])
    defaults = read_defaults(cfg)
    references = (defaults.vision, *defaults.vision_fallbacks)
    if (not defaults.vision_enabled or tuple(item["reference"] for item in request["models"])
            != references or current["sha256"] != request["sha256"]):
        return {"rejected": True}
    for expected in request["models"]:
        connection, _, credential = model_binding(cfg, expected["reference"])
        if (connection.revision != expected["connection_revision"]
                or credential != expected["credential_revision"]):
            return {"rejected": True}
    values = {"artifact": request["artifact"], "revision": request["revision"],
              "context": request["context"], "output_tokens": request["output_tokens"]}
    if operation == "vision-analyze":
        values["question"] = request["question"]
    prepared = VisionCommand.for_client(
        cfg, "prepare" if operation == "vision-analyze" else "tags_prepare", **values,
    ).execute()
    if "spec" not in prepared:
        return {"rejected": True}
    spec = prepared["spec"]
    for actual, expected in zip(spec["models"], request["models"], strict=True):
        if any(actual.get(key) != value for key, value in expected.items()):
            return {"rejected": True}
    analyzed = VisionCommand.for_client(
        cfg, "analyze" if operation == "vision-analyze" else "tags_suggest", spec=spec,
    ).execute()
    if analyzed.get("status") not in {None, "complete"} or "model" not in analyzed:
        return {"rejected": True}
    if operation == "vision-analyze":
        text = str(analyzed["text"])[:32_000]
        text = "".join(char for char in text if char in "\n\t" or char.isprintable())
        payload = {"kind": "analysis", "model": analyzed["model"], "text": text}
    else:
        payload = {"kind": "tags", "model": analyzed["model"],
                   "tags": analyzed["tags"], "proposal": analyzed}
    OperationJournal(cfg.data_dir / "operations.db").check_effect(
        request["request_id"], "web-admin", request["fence"],
    )
    BrowserResults(cfg.data_dir).put(request["request_id"], request["artifact"],
                                    request["revision"], payload)
    return {"ok": True}

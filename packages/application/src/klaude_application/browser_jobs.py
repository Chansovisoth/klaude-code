"""Reviewed Generated workflows using existing Research and image job stores."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from klaude_core.config import Config
from klaude_core.settings_store import read_settings

OPERATIONS = frozenset({"research-create", "research-run", "research-stop",
                        "image-generate", "image-cancel", "image-recover"})


def image_capabilities(cfg: Config) -> dict[str, Any]:
    """Explicit studio check, using only the saved opt-in service, never chat/Vision."""
    import httpx
    from klaude_core.image_generation import inspect, read

    settings = read(cfg)
    result: dict[str, Any] = {"backend": "stable-diffusion.cpp", "model": settings["model"],
                              "enabled": settings["enabled"], "available": False}
    if not settings["enabled"]:
        return {**result, "message": "Enable and test an image service in Settings → Models."}
    try:
        observed = inspect(settings["endpoint"])
        if observed["model"] != settings["model"] or not observed["cancel_queued"]:
            return {**result, "message": "Service capabilities changed; test and save in Settings."}
    except (ValueError, OSError, httpx.HTTPError):
        return {**result, "message": "Image service unavailable. Check the server, then retry."}
    return {**result, "available": True, "limits": observed["limits"],
            "cancel_generating": observed["cancel_generating"],
            "sampler": observed["sampler"], "scheduler": observed["scheduler"]}


def generated_jobs(cfg: Config) -> dict[str, Any]:
    from klaude_core.ai_defaults import read_defaults
    from klaude_core.image_generation import history, read
    from klaude_core.research import ResearchStore, read_research_defaults

    research = ResearchStore(cfg.data_dir / "library").listing()
    images = history(cfg)
    settings = read(cfg)
    return {
        "research": [{"id": item["id"], "question": item["question"],
                      "status": item["status"], "phase": item["phase"],
                      "revision": item["revision"], "round": item["round"],
                      "report": item.get("report", ""),
                      "sources": len(item.get("sources", []))}
                     for item in research["items"][:20]],
        "research_more": research["more"] or len(research["items"]) > 20,
        "research_defaults": read_research_defaults(cfg).public(),
        "research_model": read_defaults(cfg).research,
        "images": [{key: item.get(key, "") for key in ("job", "status", "created",
                                                        "model", "artifact")}
                   for item in images["items"][:20]],
        "images_more": images["more"] or len(images["items"]) > 20,
        "image_settings": {"enabled": settings["enabled"], "model": settings["model"]},
    }


def prepare_generated_operation(
    cfg: Config, draft: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    operation = draft["operation"]
    if operation == "research-create":
        from klaude_core.research import make_spec, read_research_defaults

        if set(draft) != {"operation", "question", "model", "format"}:
            raise ValueError("Invalid Research draft")
        preferences = read_settings(cfg.data_dir / "chat-preferences.json")
        availability = preferences.get("tool_availability", {})
        if availability.get("web_search") is False or availability.get("fetch_url") is False:
            raise ValueError("Enable Web search and Read web pages before creating Research")
        settings = read_research_defaults(cfg).public()
        spec = make_spec(cfg, draft["question"], draft["model"], settings,
                         format=draft["format"])
        spec["search_settings"] = preferences.get("search_settings", {})
        spec["fetch_settings"] = preferences.get("fetch_settings", {})
        identity = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        return {"spec": spec}, f"research-create:{identity}", (
            f"Queue Research: {spec['question']}\nModel: {spec['model']}\n"
            f"Up to {settings['queries']} searches, {settings['sources']} sources, "
            f"{settings['rounds']} rounds and {settings['timeout']} seconds. "
            "Starting the queued job requires a separate review."
        )
    if operation in {"research-run", "research-stop"}:
        from klaude_core.research import ResearchStore

        if set(draft) != {"operation", "target", "revision"}:
            raise ValueError("Choose an exact Research job")
        item = ResearchStore(cfg.data_dir / "library").get(draft["target"])
        if type(draft["revision"]) is not int or item["revision"] != draft["revision"]:
            raise ValueError("Research job changed; refresh before reviewing")
        if operation == "research-run":
            if item["status"] in {"running", "completed"}:
                raise ValueError("Research job is already running or completed")
            return {"target": item["id"], "revision": item["revision"], "spec": item["spec"]}, (
                f"research:{item['id']}"
            ), (f"Start Research: {item['question']}\nModel: {item['spec']['model']}\n"
                "Uses the saved search and model budgets, with fresh source retrieval. "
                "Configured providers may charge for requests.")
        if item["status"] not in {"running", "queued", "interrupted"}:
            raise ValueError("This Research job is no longer running or queued")
        return {"target": item["id"], "owner": item.get("owner", ""),
                "queued_only": item["status"] == "queued"}, f"research-control:{item['id']}", (
            f"Stop Research: {item['question']}. Stops at the next bounded work boundary."
        )
    if operation == "image-generate":
        from klaude_core.image_generation import prepare

        if set(draft) not in ({"operation", "prompt", "width", "height", "steps"},
                              {"operation", "prompt", "width", "height", "steps", "seed"}):
            raise ValueError("Invalid image generation draft")
        spec = prepare(cfg, draft["prompt"], width=draft["width"], height=draft["height"],
                       steps=draft["steps"], seed=draft.get("seed", -1))
        return {"spec": spec}, f"image:{spec['id']}", (
            f"Generate one image with {spec['settings']['model']}:\n{spec['prompt']}\n"
            f"{spec['width']} × {spec['height']}, {spec['steps']} steps, seed {spec['seed']}. "
            "Saves the output in Generated. Generation can take up to five minutes."
        )
    if set(draft) != {"operation", "target"}:
        raise ValueError("Choose an exact image job")
    from klaude_core.image_generation import job, recovery_review

    item = job(cfg, draft["target"])
    if operation == "image-recover":
        spec = recovery_review(cfg, item["id"])
        return {"target": item["id"], "spec": spec}, f"image-recovery:{item['id']}", (
            f"Recover completed image output for job {item['id']}. "
            "Checks only its acknowledged server job; no generation is submitted."
        )
    if operation != "image-cancel" or not item.get("remote_id"):
        raise ValueError("An acknowledged server job is required for cancellation")
    return {"target": item["id"], "remote_id": item["remote_id"]}, (
        f"image-control:{item['id']}"
    ), f"Cancel the acknowledged image job {item['id']}."


def run_generated_operation(cfg: Config, request: dict[str, Any]) -> dict[str, bool]:
    operation = request["operation"]
    if operation.startswith("research-"):
        from klaude_core.research import ResearchStore, make_spec

        from .research import ResearchRun, ResearchService, ResearchStop

        store = ResearchStore(cfg.data_dir / "library")
        if operation == "research-create":
            spec = request["spec"]
            current = make_spec(cfg, spec["question"], spec["model"], spec["settings"],
                                format=spec["format"])
            if any(current[key] != spec[key] for key in current):
                return {"rejected": True}
            store.create(spec)
            return {"ok": True}
        if operation == "research-stop":
            result = ResearchService().control(ResearchStop(
                request["target"], request["owner"], request["queued_only"],
            ))
            return {"ok": True} if "item" in result else {"rejected": True}
        item = store.get(request["target"])
        if item["revision"] != request["revision"] or item["spec"] != request["spec"]:
            return {"rejected": True}
        run_result = ResearchService().run(ResearchRun(item["id"], request["request_id"]))
        return {"ok": True} if isinstance(run_result, dict) and run_result.get("status") in {
            "completed", "partial", "cancelled", "failed"
        } else {"ok": False}
    from klaude_core.image_generation import job, reviewed_binding

    from .image_generation import ImageGenerationCommand

    if operation == "image-generate":
        reviewed_binding(cfg, request["spec"])

    if operation == "image-cancel" and job(cfg, request["target"]).get("remote_id") != request[
        "remote_id"
    ]:
        return {"rejected": True}
    action = {"image-generate": "run", "image-recover": "recover", "image-cancel": "cancel"}[
        operation
    ]
    values = {"spec": request["spec"]} if operation == "image-generate" else {
        "id": request["target"], **({"spec": request["spec"]} if action == "recover" else {}),
    }
    result = ImageGenerationCommand.for_client(cfg, action, **values).execute()
    return {"ok": True} if result.get("status") in {"complete", "cancelled"} else {"ok": False}


def operation_timeout(operation: str, fields: dict[str, Any]) -> int:
    if operation in {"vision-analyze", "vision-tags"}:
        return 300
    if operation == "research-run":
        return int(fields["spec"]["settings"]["timeout"]) + 30
    return 330 if operation == "image-generate" else 180

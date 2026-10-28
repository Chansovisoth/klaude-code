"""Opt-in bounded real SD chat generation/edit test; isolated chat/library state.

Run with uv run --frozen python scripts/chat_image_real_smoke.py. Uses the saved
local image endpoint/checkpoint without modifying settings or starting a server.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import time
from pathlib import Path

from klaude_application.service import HeadlessApplication
from klaude_core import config as config_module
from klaude_core import image_generation as generation
from klaude_core.config import Config
from klaude_core.image_preparation import prepare_image
from klaude_core.library_artifacts import ArtifactStore
from klaude_core.model_runtime import OllamaRuntime
from klaude_core.ollama import Ollama


def main():
    original = generation.read(Config())
    if original.get("provider", "sdcpp") != "sdcpp" or not original["enabled"]:
        raise RuntimeError("Configure the existing local Stable Diffusion service first")
    progress = generation.packet(original["endpoint"], "/sdapi/v1/progress")
    if progress.get("state", {}).get("job") or progress.get("state", {}).get("job_count"):
        raise RuntimeError("Service is busy; no inference submitted")
    root = Path(tempfile.mkdtemp(prefix="klaude-chat-image-real-"))
    config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
    cfg = Config()
    generation.save(
        cfg,
        {key: original[key] for key in ("endpoint", "model", "enabled")},
        generation.read(cfg)["revision"],
    )
    app = HeadlessApplication.open_local(
        Path.cwd(), OllamaRuntime(Ollama()), config=cfg, model="qwen3:0.6b"
    )
    app.turns.bind_workspace(app.session_id, str(Path.cwd()), expected_revision=0)
    store = ArtifactStore(cfg.data_dir / "library")
    results = []
    try:
        for text in [
            "Generate an image of a red apple on a wooden table, 512x512, 20 steps seed 42",
            "Make the last image darker with blue lighting, 20 steps seed 43",
        ]:
            start = time.monotonic()
            handle = app.submit(text)
            if not asyncio.run(handle.join(timeout=330)):
                handle.cancel()
                raise RuntimeError("Turn timed out; inspect original persisted job, do not retry")
            if handle.failure:
                raise RuntimeError(str(handle.failure))
            action = app.images.public(app.images.for_turn(handle.turn_id))
            print(json.dumps({"state": action["state"], "root": str(root)}), flush=True)
            if action["state"] != "completed" or len(action["assets"]) != 1:
                raise RuntimeError(f"No verified output: {action}")
            asset = action["assets"][0]
            pixels = store.read_content(asset["id"], asset["revision"])
            prepare_image(pixels, preserve_alpha=True)
            assert asset["width"] == asset["height"] == 512
            info = store.generation_info(asset["id"])
            if results:
                assert info["source"]["id"] == results[0]["asset"]
                assert hashlib.sha256(pixels).hexdigest() != results[0]["sha256"]
            (root / f"{'edit' if results else 'generated'}.png").write_bytes(pixels)
            results.append(
                {
                    "asset": asset["id"],
                    "sha256": hashlib.sha256(pixels).hexdigest(),
                    "bytes": len(pixels),
                    "width": asset["width"],
                    "height": asset["height"],
                    "seconds": round(time.monotonic() - start, 2),
                    "source": info.get("source", {}).get("id"),
                    "seed": info["seed"],
                }
            )
        session = app.session_id
        asyncio.run(app.close())
        app = HeadlessApplication.open_local(
            Path.cwd(), OllamaRuntime(Ollama()), config=cfg, model="qwen3:0.6b", session_id=session
        )
        projected = [m["image_action"] for m in app.snapshot()["messages"] if "image_action" in m]
        assert [a["assets"][0]["id"] for a in projected] == [r["asset"] for r in results]
        report = {
            "root": str(root),
            "model": original["model"],
            "results": results,
            "restart_projection": True,
            "chat_model": app.agent.model,
        }
        (root / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)
    finally:
        asyncio.run(app.close())


if __name__ == "__main__":
    main()

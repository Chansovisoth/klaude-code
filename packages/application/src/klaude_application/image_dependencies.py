"""Curated companion recommendations; metadata reads never install or load weights."""

from __future__ import annotations

import re

from klaude_web.huggingface import hub_gguf_files

from .image_model_selection import catalog

# Native stable-diffusion.cpp docs/flux3.md specifies Qwen3-VL 4B and FLUX.2 VAE.
# Deliberately do not infer dependencies from arbitrary model-card text or scripts.
FLUX3 = {
    "llm": ("Qwen 3 VL 4B Text Encoder", "Qwen/Qwen3-VL-4B-Instruct-GGUF",
            "Qwen3VL-4B-Instruct-Q4_K_M.gguf", "text_encoders"),
    "vae": ("FLUX.2 VAE", "Comfy-Org/Flux-2-Dev",
            "split_files/vae/flux2-vae.safetensors", "vae"),
}
RECIPES = {"flux3-klein": FLUX3, "flux3-klein-base": FLUX3}


def plan(cfg, url, recipe_id, models):
    data = catalog(cfg, url)
    recipe = next((item for item in data["recipes"] if item["id"] == recipe_id), None)
    if recipe is None or not isinstance(models, dict):
        raise ValueError("Choose an exact installed model setup")
    slots = {slot["id"]: slot for slot in recipe["slots"]}
    if set(models) - slots.keys():
        raise ValueError("Unknown model component")
    files = {item["id"]: item for item in data["files"]}
    for key, value in models.items():
        if not isinstance(value, str) or (value and (
            value not in files or files[value]["category"] not in slots[key]["categories"]
        )):
            raise ValueError("Selected component no longer matches the server inventory")
    missing = {key for key, slot in slots.items() if slot["required"] and not models.get(key)}
    for group in recipe["required_any"]:
        if not any(models.get(key) for key in group):
            missing.add("vae" if "vae" in group else group[0])
    recommendations = RECIPES.get(recipe_id, {})
    components = []
    for key in sorted(missing):
        if key not in recommendations:
            continue
        label, repo, filename, category = recommendations[key]
        if category not in slots[key]["categories"]:
            continue
        # Resolve public metadata again at review; no weights or mutations here.
        metadata = hub_gguf_files(cfg.huggingface_base_url, "", repo, image=True)
        row = next((item for item in metadata["files"] if item["filename"] == filename), None)
        if row is None or not re.fullmatch(r"[a-f0-9]{40}", str(metadata.get("revision", ""))):
            raise ValueError("Verified companion metadata is unavailable")
        relative = f"{category}/{repo}/{filename}"
        available = next((item["id"] for item in files.values() if
                          item["category"] == category and
                          (item["id"] == relative or item["id"].endswith("/" + relative))), "")
        components.append({
            "slot": key, "label": label, "filename": filename, "size": row["size"],
            "available": available,
            "source_url": f"https://huggingface.co/{repo}/blob/{metadata['revision']}/{filename}",
            "draft": {"operation": "model-image-download", "connection": "image:sdcpp",
                      "model": f"hf.co/{repo}:{filename}", "category": category},
        })
    return {"recipe": recipe_id, "components": components,
            "total_bytes": sum(item["size"] for item in components if not item["available"]),
            "unresolved": sorted(missing - {item["slot"] for item in components})}

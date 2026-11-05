"""Pinned control bundle and fixed graph; no installation or arbitrary workflows."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

COMFY_VERSION = "0.43.0"
COMFY_COMMIT = "426f5eea52a7ece1dd599fff4cb6cd1f352ddd24"


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ControlBundle:
    id: str = "sd15-control"
    version: int = 1
    architecture: str = "sd-1.5"
    repository: str = "stable-diffusion-v1-5/stable-diffusion-v1-5"
    revision: str = "451f4fe16113bff5a5d2269ed5ad43b0592e9a14"
    filename: str = "v1-5-pruned-emaonly.safetensors"
    sha256: str = "6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa"
    size: int = 4265146304
    license: str = "CreativeML OpenRAIL-M"

    @property
    def installed_name(self) -> str:
        family = "sd15" if self.architecture == "sd-1.5" else "sdxl"
        return f"klaude-{family}-{self.sha256}.safetensors"

    def public(self) -> dict:
        value = asdict(self)
        value.update(
            category="checkpoints",
            installed_name=self.installed_name,
            source_url=f"https://huggingface.co/{self.repository}/blob/"
            f"{self.revision}/{self.filename}",
            comfyui_version=COMFY_VERSION,
            comfyui_commit=COMFY_COMMIT,
            workflow_version=1,
            workflow_digest=digest(
                sd15_workflow("0" * 32, "Bundle template", checkpoint=self.installed_name)
            ),
            runtime_lock_verified=False,
            generation_verified=False,
            install_available=False,
        )
        return {**value, "manifest_digest": digest(value)}


CONTROL = ControlBundle()


def sd15_workflow(
    job_id: str,
    prompt: str,
    *,
    negative_prompt: str = "",
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    seed: int = 0,
    checkpoint: str | None = None,
) -> dict:
    """Build only the maintained graph; callers cannot inject paths or node types.

    A graph is not permission to submit. The application must first bind a
    verified installation, settings review and durable owned generation receipt.
    """
    from .image_generation import text

    if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Use an exact Klaude image job ID")
    if checkpoint is not None and not re.fullmatch(
        r"klaude-(?:sd15|sdxl)-[a-f0-9]{64}\.safetensors", checkpoint
    ):
        raise ValueError("Use a verified managed checkpoint")
    prompt = text(prompt, 2000)
    negative_prompt = text(negative_prompt, 2000, empty=True)
    if any(type(n) is not int or not 256 <= n <= 768 or n % 64 for n in (width, height)):
        raise ValueError("Control bundle dimensions must be multiples of 64 from 256 to 768")
    if type(steps) is not int or not 1 <= steps <= 50:
        raise ValueError("Control bundle steps must be 1–50")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("Choose an explicit unsigned 32-bit seed")
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": 8.0,
                "denoise": 1.0,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": "euler",
                "scheduler": "normal",
                "seed": seed,
                "steps": steps,
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint or CONTROL.installed_name},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"batch_size": 1, "height": height, "width": width},
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": prompt}},
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": negative_prompt},
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": f"klaude/{job_id}", "images": ["8", 0]},
        },
    }


# API primitive types and graph edges expected by the pinned built-in nodes.
NODE_INPUTS = {
    "CheckpointLoaderSimple": {"ckpt_name": "COMBO"},
    "EmptyLatentImage": {"batch_size": "INT", "height": "INT", "width": "INT"},
    "CLIPTextEncode": {"clip": "CLIP", "text": "STRING"},
    "VAEDecode": {"samples": "LATENT", "vae": "VAE"},
    "SaveImage": {"filename_prefix": "STRING", "images": "IMAGE"},
    "KSampler": {
        "cfg": "FLOAT",
        "denoise": "FLOAT",
        "latent_image": "LATENT",
        "model": "MODEL",
        "negative": "CONDITIONING",
        "positive": "CONDITIONING",
        "sampler_name": "COMBO",
        "scheduler": "COMBO",
        "seed": "INT",
        "steps": "INT",
    },
}
NODE_OUTPUTS = {
    "CheckpointLoaderSimple": ["MODEL", "CLIP", "VAE"],
    "EmptyLatentImage": ["LATENT"],
    "CLIPTextEncode": ["CONDITIONING"],
    "VAEDecode": ["IMAGE"],
    "KSampler": ["LATENT"],
    "SaveImage": ["IMAGE"],
}

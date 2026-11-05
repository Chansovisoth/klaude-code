"""Immutable maintained checkpoint recipes and bounded safetensors inspection."""

from __future__ import annotations

import json
import math
import re
import struct
from dataclasses import asdict
from pathlib import Path

from .comfyui_bundle import CONTROL, ControlBundle

LIMIT = 50


def key(bundle: ControlBundle) -> str:
    return f"{bundle.id}@{bundle.version}"


def parse(value: object) -> ControlBundle:
    if not isinstance(value, dict) or set(value) != set(asdict(CONTROL)):
        raise ValueError("Invalid managed checkpoint recipe")
    if any(
        not isinstance(value[k], str)
        for k in ("id", "architecture", "repository", "revision", "filename", "sha256", "license")
    ):
        raise ValueError("Invalid managed checkpoint recipe text")
    result = ControlBundle(**value)
    if (
        result.architecture not in {"sd-1.5", "sdxl"}
        or result.version != 1
        or not isinstance(result.id, str)
        or not re.fullmatch(r"[a-z0-9-]{1,90}", result.id)
        or not re.fullmatch(r"[a-f0-9]{64}", result.sha256)
        or type(result.size) is not int
        or not 0 < result.size < 32 * 1024**3
        or not re.fullmatch(r"[a-f0-9]{40}", result.revision)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", result.repository)
        or not re.fullmatch(r"[A-Za-z0-9_. /-]{1,200}", result.filename)
        or any(p in {"", ".", ".."} for p in result.filename.split("/"))
        or not isinstance(result.license, str)
        or len(result.license) > 200
    ):
        raise ValueError("Unsupported managed checkpoint recipe")
    return result


def _pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("Duplicate safetensors header key")
        result[k] = v
    return result


def architecture(path: Path) -> str:
    """Inspect shapes only; never deserialize pickle, execute config or load tensors."""
    from .comfyui_managed import signature

    before = signature(path)
    with path.open("rb") as stream:
        size = stream.read(8)
        if len(size) != 8:
            raise ValueError("Not a safetensors checkpoint")
        count = struct.unpack("<Q", size)[0]
        if not 2 <= count <= 8 * 1024**2 or count + 8 >= before[2]:
            raise ValueError("Safetensors header exceeds its bound")
        raw = size + stream.read(count)
    if signature(path) != before:
        raise ValueError("Checkpoint changed during metadata inspection")
    return inspect_header(raw, before[2])


def inspect_header(raw: bytes, file_size: int) -> str:
    """The same bounded parser for a pinned HTTP range and a local file."""
    if len(raw) < 8:
        raise ValueError("Not a safetensors checkpoint")
    count = struct.unpack("<Q", raw[:8])[0]
    if not 2 <= count <= 8 * 1024**2 or len(raw) != 8 + count or 8 + count >= file_size:
        raise ValueError("Safetensors header exceeds its bound")
    try:
        header = json.loads(raw[8:], object_pairs_hook=_pairs)
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("Invalid safetensors header") from None
    if not isinstance(header, dict) or len(header) > 100_000:
        raise ValueError("Invalid checkpoint tensor inventory")
    widths = {
        "F16": 2,
        "BF16": 2,
        "F32": 4,
        "F64": 8,
        "I64": 8,
        "I32": 4,
        "I16": 2,
        "I8": 1,
        "U8": 1,
        "BOOL": 1,
    }
    intervals, shapes = [], {}
    for name, tensor in header.items():
        if name == "__metadata__":
            if not isinstance(tensor, dict):
                raise ValueError("Invalid safetensors metadata")
            continue
        if not isinstance(tensor, dict):
            raise ValueError("Invalid checkpoint tensor")
        shape, offsets = tensor.get("shape"), tensor.get("data_offsets")
        dtype = widths.get(str(tensor.get("dtype")))
        if (
            not dtype
            or not isinstance(shape, list)
            or len(shape) > 8
            or any(type(n) is not int or not 0 < n <= 2**31 for n in shape)
            or not isinstance(offsets, list)
            or len(offsets) != 2
            or any(type(n) is not int or n < 0 for n in offsets)
            or offsets[1] - offsets[0] != math.prod(shape) * dtype
        ):
            raise ValueError("Invalid checkpoint tensor shape or range")
        intervals.append(offsets)
        shapes[name] = shape
    end = 0
    for start, stop in sorted(intervals):
        if start != end or stop <= start:
            raise ValueError("Checkpoint tensor ranges overlap or contain gaps")
        end = stop
    if end != file_size - 8 - count:
        raise ValueError("Checkpoint is truncated or has extra tensor data")
    unet = shapes.get("model.diffusion_model.input_blocks.0.0.weight")
    vae = shapes.get("first_stage_model.encoder.conv_in.weight")
    decoder = shapes.get("first_stage_model.decoder.conv_out.weight")
    context = shapes.get(
        "model.diffusion_model.input_blocks.1.1.transformer_blocks.0.attn2.to_k.weight"
    )
    if unet != [320, 4, 3, 3] or vae != [128, 3, 3, 3] or decoder != [3, 128, 3, 3]:
        raise ValueError("Setup not supported: use a complete SD1.5 or SDXL safetensors checkpoint")
    if context == [320, 768] and shapes.get(
        "cond_stage_model.transformer.text_model.embeddings.token_embedding.weight"
    ) == [49408, 768]:
        return "sd-1.5"
    if (
        any(
            shape == [640, 2048]
            for name, shape in shapes.items()
            if name.startswith("model.diffusion_model.") and name.endswith("attn2.to_k.weight")
        )
        and shapes.get("model.diffusion_model.label_emb.0.0.weight") == [1280, 2816]
        and shapes.get(
            "conditioner.embedders.0.transformer.text_model.embeddings.token_embedding.weight"
        )
        == [49408, 768]
        and shapes.get("conditioner.embedders.1.model.token_embedding.weight") == [49408, 1280]
    ):
        return "sdxl"
    raise ValueError("Setup not supported: missing encoders or an unsupported checkpoint family")

"""Bounded private image decoding and request-sized derivatives.

The decoder runs in a disposable subprocess with private binary pipes. It performs
no network/tool operations and receives no provider credentials; originals remain
in Media. Resource limits are not an OS security sandbox.
"""

from __future__ import annotations

import io
import json
import math
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

from .image_content import image_token_estimate
from .process_input import PrivateProcessInput

MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000
MAX_SOURCE_SIDE = 32768
MAX_PREPARED_BYTES = 7_500_000
PREPARATION_VERSION = 1
DETAILS = ("auto", "detailed", "original")


def dimensions(
    width: int,
    height: int,
    tokens: int,
    *,
    detail: str = "auto",
    backend: str = "",
    model: str = "",
) -> tuple[int, int]:
    if detail not in DETAILS or type(tokens) is not int or tokens <= 0:
        raise ValueError("Invalid image detail or available image budget")
    edge = 1024 if detail == "auto" else 2048 if detail == "detailed" else 4096
    if backend == "openai_api":
        edge = min(edge, 2048)
    scale = min(1.0, edge / max(width, height), math.sqrt(4_194_304 / (width * height)))
    w, h = max(1, int(width * scale)), max(1, int(height * scale))
    while image_token_estimate(w, h, backend=backend, model=model) > tokens:
        if max(w, h) <= 32:
            raise ValueError(
                "Image input cannot fit the allocated context after output reservation"
            )
        w, h = max(1, int(w * 0.85)), max(1, int(h * 0.85))
    return w, h


def prepare_image(
    data: bytes,
    *,
    tokens: int = 100_000,
    detail: str = "auto",
    backend: str = "",
    model: str = "",
    frame: int | None = None,
    crop: tuple[int, int, int, int] | None = None,
    thumbnail: bool = False,
    thumbnail_size: int = 128,
    preserve_alpha: bool = False,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[dict[str, Any], bytes]:
    if not data or len(data) > MAX_SOURCE_BYTES:
        raise ValueError("Image sources must fit in 32 MiB")
    if type(thumbnail_size) is not int or thumbnail_size not in {128, 320}:
        raise ValueError("Invalid thumbnail size")
    options = {
        "tokens": tokens,
        "detail": detail,
        "backend": backend,
        "model": model,
        "frame": frame,
        "crop": crop,
        "thumbnail": thumbnail,
        "thumbnail_size": thumbnail_size,
        "preserve_alpha": preserve_alpha,
    }
    payload = json.dumps(options).encode() + b"\n" + data
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "LANG", "LC_ALL", "SYSTEMROOT"}
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "klaude_core.image_preparation"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environment,
        start_new_session=True,
    )
    writer = None
    try:
        writer = PrivateProcessInput(process, payload)
        deadline = time.monotonic() + 15
        while not cancelled():
            if time.monotonic() >= deadline:
                raise ValueError("Image preparation timed out; the original is unchanged")
            try:
                output, _ = process.communicate(timeout=0.05)
                if len(output) > MAX_PREPARED_BYTES + 4096 or process.returncode:
                    raise ValueError("Image decoding failed or exceeded its resource limit")
                header, separator, prepared = output.partition(b"\n")
                if not separator or len(header) > 4096:
                    raise ValueError("Invalid image preparation result")
                metadata = json.loads(header)
                if metadata.get("error"):
                    raise ValueError(metadata["error"])
                if not prepared or len(prepared) > MAX_PREPARED_BYTES:
                    raise ValueError("Prepared image exceeds the delivery bound")
                return metadata, prepared
            except subprocess.TimeoutExpired as exc:
                if exc.output and len(exc.output) > MAX_PREPARED_BYTES + 4096:
                    raise ValueError("Image preparation output exceeded its bound") from None
        raise ValueError("Image preparation cancelled")
    finally:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
        for pipe in (process.stdin, process.stdout):
            if pipe:
                pipe.close()
        if writer is not None:
            writer.close()


def _decode(data: bytes, options: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    import warnings

    from PIL import Image, ImageOps, PngImagePlugin

    Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS
    PngImagePlugin.MAX_TEXT_CHUNK = 65536
    PngImagePlugin.MAX_TEXT_MEMORY = 262144
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    try:
        with Image.open(io.BytesIO(data)) as check:
            if check.format not in {"PNG", "JPEG", "GIF", "WEBP"}:
                raise ValueError("Use PNG, JPEG, WebP or GIF images")
            if max(check.size) > MAX_SOURCE_SIDE or check.width * check.height > MAX_SOURCE_PIXELS:
                raise ValueError("Image exceeds the 40-megapixel decoding bound")
            check.verify()
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            frames = getattr(source, "n_frames", 1)
            frame = options.get("frame")
            if frames > 1 and frame is None:
                raise ValueError("Animated images need an explicit frame: /attach --frame 0 PATH")
            if frame is not None:
                if type(frame) is not int or not 0 <= frame < min(frames, 256):
                    raise ValueError("Choose an available image frame between 0 and 255")
                source.seek(frame)
                source.load()
            original = source.size
            oriented = ImageOps.exif_transpose(source)
            oriented_size = oriented.size
            crop = options.get("crop")
            if crop is not None:
                if (
                    not isinstance(crop, (list, tuple))
                    or len(crop) != 4
                    or any(type(n) is not int or n < 0 for n in crop)
                ):
                    raise ValueError(
                        "Image crop must be x,y,width,height in oriented source pixels"
                    )
                x, y, w, h = crop
                if not w or not h or x + w > oriented.width or y + h > oriented.height:
                    raise ValueError("Image crop is outside the oriented source")
                oriented = oriented.crop((x, y, x + w, y + h))
            size = dimensions(
                oriented.width,
                oriented.height,
                options["tokens"],
                detail=options["detail"],
                backend=options["backend"],
                model=options["model"],
            )
            if options.get("thumbnail"):
                edge = options.get("thumbnail_size", 128)
                if type(edge) is not int or edge not in {128, 320}:
                    raise ValueError("Invalid thumbnail size")
                scale = min(1.0, edge / max(oriented.size))
                size = (max(1, int(oriented.width * scale)),
                        max(1, int(oriented.height * scale)))
            # Always encode pixels, even when dimensions already fit: an apparently
            # metadata-free container can still carry private trailing/unknown chunks.
            oriented = oriented.convert("RGBA")
            if oriented.size != size:
                oriented = oriented.resize(size, Image.Resampling.LANCZOS)
            if options.get("preserve_alpha"):
                rgb = oriented
            else:
                background = Image.new("RGBA", size, "white")
                background.alpha_composite(oriented)
                rgb = background.convert("RGB")
            rgb.info.clear()
            output = io.BytesIO()
            rgb.save(output, format="PNG")
            prepared, mime = output.getvalue(), "image/png"
            if len(prepared) > MAX_PREPARED_BYTES:
                output = io.BytesIO()
                if options.get("preserve_alpha"):
                    rgb.save(output, format="WEBP", quality=90, exif=b"", icc_profile=None)
                    prepared, mime = output.getvalue(), "image/webp"
                else:
                    rgb.save(output, format="JPEG", quality=90, exif=b"", icc_profile=None)
                    prepared, mime = output.getvalue(), "image/jpeg"
            return {
                "mime": mime,
                "width": size[0],
                "height": size[1],
                "source_width": original[0],
                "source_height": original[1],
                "oriented_width": oriented_size[0],
                "oriented_height": oriented_size[1],
                "frames": frames,
                "frame": frame,
                "crop": crop,
                "detail": options["detail"],
                "version": PREPARATION_VERSION,
            }, prepared
    except ValueError:
        raise
    except Exception:
        raise ValueError(
            "Image is corrupt, truncated, unsupported or exceeds decoding limits"
        ) from None


def _worker() -> None:
    import ctypes
    import resource

    # A killed TUI/owned parent must not leave a decoder running independently.
    if sys.platform == "linux":
        parent = os.getppid()
        ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0)
        if parent == 1 or os.getppid() != parent:
            raise SystemExit(1)
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    try:
        header = sys.stdin.buffer.readline(4097)
        if len(header) > 4096 or not header.endswith(b"\n"):
            raise ValueError("Invalid image preparation request")
        options = json.loads(header)
        data = sys.stdin.buffer.read(MAX_SOURCE_BYTES + 1)
        if not data or len(data) > MAX_SOURCE_BYTES:
            raise ValueError("Image sources must fit in 32 MiB")
        metadata, prepared = _decode(data, options)
        sys.stdout.buffer.write(json.dumps(metadata).encode() + b"\n" + prepared)
    except ValueError as exc:
        sys.stdout.buffer.write(json.dumps({"error": str(exc)}).encode() + b"\n")


if __name__ == "__main__":
    _worker()

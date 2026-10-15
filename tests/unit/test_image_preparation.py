"""Real bounded decoding, private pipes, resizing, orientation and crop behavior."""

import base64
import io
import time

import pytest
from klaude_core.chat_images import attachment_path
from klaude_core.image_preparation import prepare_image
from PIL import Image, PngImagePlugin


def picture(fmt="PNG", size=(864, 1184), mode="RGB"):
    output = io.BytesIO()
    Image.new(mode, size, "white").save(output, format=fmt)
    return output.getvalue()


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "GIF"])
def test_phone_images_are_decoded_and_fit_without_manual_resizing(fmt):
    source = picture(fmt, (3000, 4000))
    metadata, prepared = prepare_image(source, tokens=2500)
    assert (metadata["source_width"], metadata["source_height"]) == (3000, 4000)
    assert max(metadata["width"], metadata["height"]) <= 1024
    with Image.open(io.BytesIO(prepared)) as image:
        image.load()
        assert image.mode == "RGB"
        assert image.size == (metadata["width"], metadata["height"])
        assert image.format in {"PNG", "JPEG"}
    assert source == picture(fmt, (3000, 4000))


def test_metadata_orientation_alpha_and_explicit_crop_are_normalized():
    source = Image.new("RGB", (1600, 900), "red")
    exif = Image.Exif()
    exif[274] = 6
    output = io.BytesIO()
    source.save(output, format="JPEG", exif=exif)
    meta, prepared = prepare_image(output.getvalue(), crop=(0, 0, 100, 200))
    assert (meta["oriented_width"], meta["oriented_height"]) == (900, 1600)
    assert (meta["width"], meta["height"]) == (100, 200)
    with Image.open(io.BytesIO(prepared)) as image:
        assert not image.getexif() and not image.info
    transparent = io.BytesIO()
    Image.new("RGBA", (20, 30), (255, 0, 0, 0)).save(transparent, format="PNG")
    _, prepared = prepare_image(transparent.getvalue())
    with Image.open(io.BytesIO(prepared)) as image:
        assert image.getpixel((0, 0)) == (255, 255, 255)


def test_private_large_input_does_not_deadlock_short_polling_or_transmit_padding():
    source = picture(size=(1, 1)) + b"x" * 7_500_000
    started = time.monotonic()
    meta, prepared = prepare_image(source)
    assert time.monotonic() - started < 10
    assert len(prepared) < 1000 and meta["width"] == 1
    assert source.endswith(b"x" * 100)


def test_embedded_text_is_removed_and_original_bytes_remain_unchanged():
    text = PngImagePlugin.PngInfo()
    text.add_text("location", "private-location-canary")
    stream = io.BytesIO()
    Image.new("RGB", (20, 20)).save(stream, format="PNG", pnginfo=text)
    source = stream.getvalue()
    _, prepared = prepare_image(source)
    assert b"private-location-canary" in source
    assert b"private-location-canary" not in prepared


def test_small_valid_container_does_not_forward_private_trailing_bytes():
    source = picture(size=(17, 31)) + b"private-trailing-canary"
    metadata, prepared = prepare_image(source)
    assert (metadata["width"], metadata["height"]) == (17, 31)
    assert b"private-trailing-canary" not in prepared
    assert source.endswith(b"private-trailing-canary")


def test_animation_requires_a_selected_frame_and_crop_coordinates_are_checked():
    source = io.BytesIO()
    first, second = Image.new("RGB", (20, 20), "red"), Image.new("RGB", (20, 20), "blue")
    first.save(source, format="GIF", save_all=True, append_images=[second])
    with pytest.raises(ValueError, match="explicit frame"):
        prepare_image(source.getvalue())
    meta, prepared = prepare_image(source.getvalue(), frame=1)
    assert meta["frame"] == 1 and meta["frames"] == 2
    with Image.open(io.BytesIO(prepared)) as image:
        assert image.getpixel((0, 0)) == (0, 0, 255)
    with pytest.raises(ValueError, match="outside"):
        prepare_image(picture(size=(20, 20)), crop=(10, 10, 20, 20))


@pytest.mark.parametrize(
    "source",
    [
        b"GIF89a" + b"x" * 20,
        b"not an image",
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a/a0AAAAASUVORK5CYII="
        ),
    ],
)
def test_corruption_including_previous_invalid_fixture_is_rejected(source):
    with pytest.raises(ValueError):
        prepare_image(source)


def test_decode_can_be_cancelled_and_does_not_enlarge_small_images():
    with pytest.raises(ValueError, match="cancelled"):
        prepare_image(picture(), cancelled=lambda: True)
    meta, _ = prepare_image(picture(size=(17, 31)), detail="original")
    assert (meta["width"], meta["height"]) == (17, 31)


def test_attach_options_preserve_quoted_paths_and_oriented_crop(tmp_path):
    source = tmp_path / "screen shot.png"
    source.write_bytes(picture())
    parsed = attachment_path('--detail original --crop 0,0,100,200 "screen shot.png"', tmp_path)
    assert parsed == source
    assert parsed.image_options == {"detail": "original", "crop": [0, 0, 100, 200]}
    with pytest.raises(ValueError, match="attachment path"):
        attachment_path("--detail detailed", tmp_path)
    with pytest.raises(ValueError, match="Image crop"):
        attachment_path('--crop 0,0,0,10 "screen shot.png"', tmp_path)

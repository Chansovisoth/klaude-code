"""File-browser sorting and authenticated bounded image derivatives."""

import hashlib
import io
from urllib.parse import urlencode

import pytest
from klaude_webhost import library_images
from PIL import Image, PngImagePlugin

from .test_web_library import _bytes_request
from .test_web_library import browser_library as browser_library
from .test_webhost import _request


def image_url(item, size="thumbnail", **changes):
    return "/api/v1/library/image?" + urlencode({
        "id": item["id"], "revision": item["revision"], "size": size, **changes,
    })


def picture(size=(1600, 1000), format="PNG"):
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "metadata-canary")
    Image.new("RGB", size, "teal").save(output, format=format, pnginfo=metadata)
    return output.getvalue()


def test_input_output_provenance_filters_before_counts_search_and_paging(browser_library):
    host, service, auth = browser_library
    store = service.artifacts
    inputs = [store.import_bytes(b"User document", "document", f"generated-{n:02}.md")
              for n in range(45)]
    inputs.append(store.import_bytes(picture((8, 5)), "media", "research-report.png"))
    with store.database(write=True) as db:
        db.execute("INSERT INTO image_tags (artifact,generated_tags,provenance) VALUES (?,?,?)",
                   (inputs[-1]["id"], '["AI tagged"]', '{}'))
    outputs = [store.store_generated_image(picture((8, 5)), {
        "id": f"{n:032x}", "session": "private-session", "settings": {"model": "private-model"},
    }, "private-server-job") for n in range(26)]
    outputs += [store.store_report(f"research-{n:02}.md", "# Research result", job=str(n))
                for n in range(23)]
    for source, expected in (("input", inputs), ("output", outputs)):
        seen = []
        for offset in range(0, len(expected), 20):
            route = "/api/v1/library/items?" + urlencode({
                "kind": "all", "source": source, "sort": "name", "offset": offset,
            })
            status, _, data = _request(host, "GET", route, **auth)
            assert status == 200 and data["total"] == len(expected)
            seen.extend(data["items"])
        assert {item["id"] for item in seen} == {item["id"] for item in expected}
        assert all(not {"job", "session", "model", "origin"} & item.keys() for item in seen)
        assert len(seen) == len(expected)
    assert _request(host, "GET", "/api/v1/library/items?kind=all", **auth)[2]["total"] == 95
    counts = _request(host, "GET", "/api/v1/library/counts", **auth)[2]
    assert counts["files"]["total"] == 46 and counts["outputs"]["total"] == 49
    for source, total in (("input", 1), ("output", 26)):
        route = "/api/v1/library/items?kind=all&images=1&source=" + source
        assert _request(host, "GET", route, **auth)[2]["total"] == total
    assert _request(host, "GET", "/api/v1/library/items?source=input&query=generated-44",
                    **auth)[2]["total"] == 1
    assert _request(host, "GET", "/api/v1/library/items?kind=research&source=input",
                    **auth)[2]["total"] == 0
    for source, item in (("input", inputs[0]), ("output", outputs[0])):
        store.change(item["id"], item["revision"], "archive")
        data = _request(host, "GET", "/api/v1/library/items?kind=all&archived=true&source="
                        + source, **auth)[2]
        assert data["total"] == 1 and data["items"][0]["id"] == item["id"]
    counts = service.tab_counts()
    assert counts["files"]["total"] == 45 and counts["outputs"]["total"] == 48
    for invalid in ("unknown", "../", "INPUT"):
        assert _request(host, "GET", "/api/v1/library/items?source=" + invalid,
                        **auth)[0] == 400
    assert _request(host, "GET", "/api/v1/library/items?source=output")[0] == 401


def test_source_filter_reads_legacy_store_without_generated_image_table(browser_library):
    host, service, auth = browser_library
    document = service.artifacts.import_bytes(b"Saved", "document", "generated.md")
    report = service.artifacts.store_report("research.md", "Research", job="job")
    with service.artifacts.database(write=True) as db:
        db.execute("DROP TABLE generated_images")
    for source, item in (("input", document), ("output", report)):
        data = _request(host, "GET", "/api/v1/library/items?kind=all&source=" + source,
                        **auth)[2]
        assert data["total"] == 1 and data["items"][0]["id"] == item["id"]
    with service.artifacts.database() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='generated_images'").fetchone()
        assert not exists


def test_gallery_filters_supported_images_before_pagination_and_counting(browser_library):
    host, service, auth = browser_library
    for index in range(25):
        service.artifacts.import_bytes(picture((8, 5)), "document", f"photo-{index:02}.png")
    service.artifacts.import_bytes(b"<svg/>", "document", "vector.svg")
    service.artifacts.import_bytes(b"Other document", "document", "notes.txt")
    first = _request(host, "GET", "/api/v1/library/items?kind=all&images=1&sort=name", **auth)[2]
    last = _request(host, "GET", "/api/v1/library/items?kind=all&images=1&sort=name&offset=20",
                    **auth)[2]
    assert first["total"] == last["total"] == 25
    assert len(first["items"]) == 20 and len(last["items"]) == 5
    assert all(item["mime"] == "image/png" for item in first["items"] + last["items"])
    search = _request(host, "GET", "/api/v1/library/items?kind=all&images=1&query=photo-24",
                      **auth)[2]
    assert search["total"] == 1 and search["items"][0]["name"] == "photo-24.png"
    for invalid in ("true", "yes", "../"):
        assert _request(host, "GET", "/api/v1/library/items?images=" + invalid, **auth)[0] == 400


@pytest.mark.parametrize("sort,names", [
    ("name", ["a.txt", "b.json", "z.txt"]),
    ("name_desc", ["z.txt", "b.json", "a.txt"]),
    ("largest", ["z.txt", "b.json", "a.txt"]),
    ("smallest", ["a.txt", "b.json", "z.txt"]),
    ("type", ["b.json", "a.txt", "z.txt"]),
])
def test_file_sorts_use_real_inventory_fields(browser_library, sort, names):
    host, service, auth = browser_library
    for name, size in [("z.txt", 500), ("a.txt", 10), ("b.json", 200)]:
        service.artifacts.import_bytes(b"x" * size, "document", name)
    data = _request(host, "GET", "/api/v1/library/items?sort=" + sort, **auth)[2]
    assert [item["name"] for item in data["items"]] == names
    assert all("modified" not in item and "created" in item for item in data["items"])


def test_image_derivatives_cache_strip_metadata_and_keep_original(browser_library, monkeypatch):
    host, service, auth = browser_library
    original = picture((4097, 1000))  # Exceeds the old original-inline preview limit.
    item = service.artifacts.import_bytes(original, "media", "large.png")
    calls = []
    prepare = library_images.prepare_image

    def decode(*args, **kwargs):
        calls.append(kwargs)
        return prepare(*args, **kwargs)

    monkeypatch.setattr(library_images, "prepare_image", decode)
    path = image_url(item)
    status, headers, thumbnail = _bytes_request(host, path, auth["cookie"])
    assert status == 200 and headers["Content-Type"] == "image/png"
    assert headers["Cache-Control"] == "no-store"
    assert "Content-Disposition" not in headers
    assert len(thumbnail) < len(original) and b"metadata-canary" not in thumbnail
    with Image.open(io.BytesIO(thumbnail)) as image:
        assert max(image.size) == 320 and not image.info
    assert _bytes_request(host, path, auth["cookie"])[2] == thumbnail
    assert len(calls) == 1
    status, _, expanded = _bytes_request(host, image_url(item, "preview"), auth["cookie"])
    assert status == 200
    with Image.open(io.BytesIO(expanded)) as image:
        assert max(image.size) == 2048
    assert len(calls) == 2
    download = "/api/v1/library/content?" + urlencode({
        "id": item["id"], "revision": item["revision"],
    })
    assert _bytes_request(host, download, auth["cookie"])[2] == original
    assert service.artifacts.get(item["id"])["sha256"] == hashlib.sha256(original).hexdigest()
    service.artifacts.change(item["id"], item["revision"], "archive")
    assert _bytes_request(host, path, auth["cookie"])[0] == 400
    archived = service.artifacts.get(item["id"])
    assert _bytes_request(host, image_url(archived), auth["cookie"])[0] == 200
    service.artifacts.change(archived["id"], archived["revision"], "delete")
    assert _bytes_request(host, image_url(archived), auth["cookie"])[0] == 400


def test_image_route_rejects_anonymous_paths_formats_and_corruption(browser_library):
    host, service, auth = browser_library
    item = service.artifacts.import_bytes(picture((12, 8)), "media", "safe.png")
    assert _bytes_request(host, image_url(item), "")[0] == 401
    assert _request(host, "GET", image_url(item), fetch_site="cross-site", **auth)[0] == 403
    for changes in ({"id": "../../config/.env"}, {"revision": 100}, {"size": "original"},
                    {"path": "/etc/passwd"}):
        assert _bytes_request(host, image_url(item, **changes), auth["cookie"])[0] == 400
    svg = service.artifacts.import_bytes(b"<svg onload='alert(1)'/>", "document", "unsafe.svg")
    assert _bytes_request(host, image_url(svg), auth["cookie"])[0] == 400
    with service.artifacts.database(write=True) as db:
        db.execute("UPDATE artifacts SET content=? WHERE id=?", (b"corrupt", item["id"]))
    assert _bytes_request(host, image_url(item), auth["cookie"])[0] == 400


def test_decode_cannot_publish_after_revision_change_or_logout(browser_library, monkeypatch):
    host, service, auth = browser_library
    item = service.artifacts.import_bytes(picture((12, 8)), "media", "safe.png")
    prepare = library_images.prepare_image

    def change_while_decoding(*args, **kwargs):
        result = prepare(*args, **kwargs)
        service.artifacts.change(item["id"], item["revision"], "tags", "changed")
        return result

    monkeypatch.setattr(library_images, "prepare_image", change_while_decoding)
    assert _bytes_request(host, image_url(item), auth["cookie"])[0] == 400
    assert not host.library_images._cache
    changed = service.artifacts.get(item["id"])

    def logout_while_decoding(*args, **kwargs):
        result = prepare(*args, **kwargs)
        host.logout(hashlib.sha256(auth["cookie"].split("=", 1)[1].encode()).hexdigest())
        return result

    monkeypatch.setattr(library_images, "prepare_image", logout_while_decoding)
    assert _bytes_request(host, image_url(changed), auth["cookie"])[0] == 400
    assert not host.library_images._cache


def test_corrupt_supported_image_fails_without_source_exposure(browser_library):
    host, service, auth = browser_library
    # The bounded header is recognizable, but the image cannot fully decode.
    item = service.artifacts.import_bytes(picture((12, 8))[:24], "media", "broken.png")
    status, headers, body = _bytes_request(host, image_url(item), auth["cookie"])
    assert status == 400 and "application/json" in headers["Content-Type"]
    assert b"PNG" not in body and not host.library_images._cache

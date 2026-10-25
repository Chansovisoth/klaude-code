"""Local AI-logo asset provenance and fixed HTTP serving boundary."""

from __future__ import annotations

import hashlib
import http.client
import json
import threading
import xml.etree.ElementTree as ET

import pytest
from klaude_webhost.host import AI_ICON_NAMES, STATIC, LocalWebHost

from tests.unit.test_webhost import _app


def test_ai_logo_assets_and_serving_boundary(tmp_path):
    root = STATIC / "icons" / "ai"
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["packages"]["lobe"]["license"] == "MIT"
    assert "Copyright (c) 2023 LobeHub" in (root / "LICENSE").read_text()
    for name in AI_ICON_NAMES:
        content = (root / f"{name}.svg").read_bytes()
        svg = ET.fromstring(content)
        assert svg.tag == "{http://www.w3.org/2000/svg}svg"
        for node in svg.iter():
            assert node.tag.rsplit("}", 1)[-1].lower() not in {
                "script",
                "foreignobject",
                "image",
                "use",
            }
            assert not any(
                key.lower().startswith("on") or key.endswith("href") for key in node.attrib
            )
        if name in manifest["icons"]:
            assert hashlib.sha256(content).hexdigest() == manifest["icons"][name]["sha256"]
    host = LocalWebHost(_app(tmp_path))
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        for name in AI_ICON_NAMES:
            conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
            conn.request("GET", f"/icons/ai/{name}.svg")
            response = conn.getresponse()
            assert response.status == 200
            assert response.getheader("Content-Type") == "image/svg+xml; charset=utf-8"
            assert response.getheader("X-Content-Type-Options") == "nosniff"
            assert "default-src 'none'" in response.getheader("Content-Security-Policy")
            assert response.read() == (root / f"{name}.svg").read_bytes()
            conn.close()
        for path in ("/icons/ai/../../host.py", "/icons/ai/manifest.json", "/icons/ai/missing.svg"):
            conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
            conn.request("GET", path)
            assert conn.getresponse().status == 401
            conn.close()
    finally:
        host.stop()
        thread.join(3)
        host.application.memory.db.close()


def test_ai_registry_bundle_and_sanitizer(monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from bundle_ai_icons import bundle, validate_svg
    from vendor_ai_icons import sanitize

    bundle(check=True)
    safe = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<path fill="currentColor" d="M0 0h24v24H0z"/></svg>'
    )
    validate_svg(sanitize(safe))
    for payload in [
        b"<script>alert(1)</script>",
        b'<image href="https://evil.invalid/a"/>',
        b"<foreignObject/>",
        b'<path onclick="alert(1)"/>',
        b'<path fill="url(https://evil.invalid/a)"/>',
        b'<path style="fill:url(https://evil.invalid/a)"/>',
        b'<path xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="https://evil.invalid/a"/>',
    ]:
        with pytest.raises(ValueError):
            sanitize(
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                + payload
                + b"</svg>"
            )

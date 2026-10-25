"""Lens stays browser-owned and exposes only fixed local assets."""

from __future__ import annotations

import hashlib
import http.client
import json
import threading
import xml.etree.ElementTree as ET

from klaude_webhost.host import STATIC, LocalWebHost

from tests.unit.test_webhost import _app


def test_lens_assets_and_handoff_policy(tmp_path):
    source = json.loads((STATIC / "icons/google-lens-source.json").read_text())
    content = (STATIC / "icons/google-lens.svg").read_bytes()
    assert hashlib.sha256(content).hexdigest() == source["sha256"]
    assert source["source"] == "Original SVG drawn for Klaude"
    assert ET.fromstring(content).get("viewBox") == "0 0 24 24"
    host = LocalWebHost(_app(tmp_path))
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        for path, mime in (
            ("/lens.js", "text/javascript; charset=utf-8"),
            ("/icons/google-lens.svg", "image/svg+xml; charset=utf-8"),
        ):
            conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
            conn.request("GET", path)
            response = conn.getresponse()
            assert response.status == 200
            assert response.getheader("Content-Type") == mime
            assert response.getheader("X-Content-Type-Options") == "nosniff"
            policy = response.getheader("Content-Security-Policy")
            assert "connect-src 'self'" in policy
            assert "form-action 'self' https://lens.google.com https://www.google.com;" in policy
            assert "script-src 'self'" in policy
            assert "img-src 'self'" in policy
            assert response.read()
            conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.request("GET", "/icons/google-lens-source.json")
        assert conn.getresponse().status == 401
        conn.close()
    finally:
        host.stop()
        thread.join(3)
        host.application.memory.db.close()

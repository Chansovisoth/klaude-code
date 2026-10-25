"""Passive assistant documents retain drawings without active page privileges."""

import http.client
import json
import threading

import pytest
from klaude_webhost.chat_previews import ChatPreviews, preview_document
from klaude_webhost.host import LocalWebHost

from tests.unit.test_webhost import _app, _request


def test_preview_preserves_shapes_styles_and_text_but_removes_active_content():
    source = """<!doctype html><html><head><meta http-equiv="refresh" content="0;url=/leak">
    <style>.shape { fill: rebeccapurple }</style></head><body>
    <svg viewBox="0 0 100 100" onload="alert(1)"><defs><path id="a" d="M0 0L1 1"/>
    </defs><use href="#a"/><foreignObject><iframe srcdoc="&lt;script&gt;"/></foreignObject>
    <rect class="shape" width="50" height="50"/></svg>
    <a href="https://example.com/leak" ping="/leak">Open &amp; close</a>
    <img src="https://example.com/leak" srcset="https://example.com/leak 2x">
    <script>parent.executed=true</script><form action="/api/v1/turns"><input autofocus>
    </form></body></html>"""
    output = preview_document(source).decode()
    assert 'viewbox="0 0 100 100"' in output
    assert '<use href="#a"></use>' in output
    assert ".shape { fill: rebeccapurple }" in output
    assert "Open &amp; close" in output
    for active in (
        "<script",
        "<iframe",
        "<foreignobject",
        "http-equiv",
        "onload=",
        "https://example.com",
        "srcdoc=",
        "srcset=",
        "<form",
        "autofocus",
    ):
        assert active not in output


def test_preview_quota_expiry_and_owner_revocation(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("klaude_webhost.chat_previews.time.monotonic", lambda: clock[0])
    store = ChatPreviews()
    first = store.create("one", "<p>Private</p>")
    with pytest.raises(FileNotFoundError):
        store.read("two", first)
    assert b"Private" in store.read("one", first)
    for _ in range(8):
        second = store.create("two", "<p>Second</p>")
    with pytest.raises(FileNotFoundError):
        store.read("one", first)
    store.revoke("one")
    assert store.read("two", second)
    clock[0] += 301
    with pytest.raises(FileNotFoundError):
        store.read("two", second)
    with pytest.raises(ValueError):
        store.create("one", "a" * 128_001)
    with pytest.raises(ValueError):
        store.create("one", "<b>" * 10_001)


def test_preview_routes_require_owner_csrf_origin_and_sandbox(tmp_path):
    host = LocalWebHost(_app(tmp_path))
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        status, headers, login = _request(
            host,
            "POST",
            "/api/v1/auth/exchange",
            origin=host.origin,
            body={"code": host.bootstrap_url.partition("#")[2]},
        )
        assert status == 200
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        request = {"cookie": cookie, "origin": host.origin}
        assert (
            _request(host, "POST", "/api/v1/chat-previews", body={"source": "x"}, **request)[0]
            == 403
        )
        request["csrf"] = login["csrf"]
        assert (
            _request(host, "POST", "/api/v1/chat-previews", body={"source": []}, **request)[0]
            == 400
        )
        status, _, result = _request(
            host,
            "POST",
            "/api/v1/chat-previews",
            body={"source": "<svg><circle r='5'/></svg>"},
            **request,
        )
        assert status == 201
        url = result["url"]
        assert _request(host, "GET", url)[0] == 401
        other, _ = host.exchange(host.new_bootstrap_url().partition("#")[2])
        assert _request(host, "GET", url, cookie=f"klaude_webui_session={other}")[0] == 404
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.request("GET", url, headers={"Cookie": cookie})
        response = conn.getresponse()
        assert response.status == 200
        assert "circle" in response.read().decode()
        policy = response.getheader("Content-Security-Policy")
        for directive in (
            "script-src 'none'",
            "connect-src 'none'",
            "frame-src 'none'",
            "frame-ancestors 'self'",
            "sandbox",
        ):
            assert directive in policy
        assert response.getheader("X-Frame-Options") is None
        assert response.getheader("Cache-Control") == "no-store"
        conn.close()
        host.logout(cookie.split("=", 1)[1])
        with pytest.raises(FileNotFoundError):
            host.chat_previews.read(cookie.split("=", 1)[1], url.rsplit("/", 1)[-1])
    finally:
        host.stop()
        thread.join(3)


def test_math_bundle_is_pinned_and_fixed_asset_only(tmp_path):
    import hashlib

    from klaude_webhost.host import STATIC

    manifest = json.loads((STATIC / "vendor/math-manifest.json").read_text())
    for name, digest in manifest["assets"].items():
        assert hashlib.sha256((STATIC / "vendor" / name).read_bytes()).hexdigest() == digest
    host = LocalWebHost(_app(tmp_path))
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.request("GET", "/vendor/katex.min.js")
        response = conn.getresponse()
        assert response.status == 200
        assert response.read() == (STATIC / "vendor/katex.min.js").read_bytes()
        conn.close()
        assert _request(host, "GET", "/vendor/math-manifest.json")[0] == 401
    finally:
        host.stop()
        thread.join(3)

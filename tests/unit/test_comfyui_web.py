"""Managed bundle metadata and mutation authorization through the real web host."""

import json

from .test_web_management import _review
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request


def test_bundle_inventory_and_review_do_not_install(profile_browser):
    host, service, _, auth = profile_browser
    route = "/api/v1/settings/models/image-bundles"
    status, _, data = _request(host, "POST", route, body={"action": "list"}, **auth)
    assert status == 200 and not data["installed"] and data["bundle"]["id"] == "sd15-control@1"
    review = _review(host, auth, {"operation": "comfy-install"})
    assert "CreativeML OpenRAIL-M" in review["summary"]
    assert "Does not load weights" in review["summary"]
    assert not (service.cfg.data_dir / "comfyui").exists()
    assert _request(host, "POST", route, body={"action": "install"}, **auth)[0] == 400
    unsafe = {**auth, "origin": "http://untrusted.invalid"}
    assert _request(host, "POST", route, body={"action": "list"}, **unsafe)[0] == 403
    assert (
        _request(
            host,
            "POST",
            "/api/v1/settings/models/image-bundle-pause",
            body={"request_id": "a" * 32},
            **unsafe,
        )[0]
        == 403
    )
    status, _, result = _request(
        host,
        "POST",
        "/api/v1/library/review",
        body={"draft": {"operation": "comfy-install", "source": "/private"}},
        **auth,
    )
    assert status == 400 and "/private" not in json.dumps(result)
    assert (
        _request(
            host,
            "POST",
            "/api/v1/settings/models/image-test",
            body={
                "provider": "comfyui",
                "endpoint": "https://arbitrary.invalid",
                "model": "sd15-control@1",
            },
            **auth,
        )[0]
        == 400
    )

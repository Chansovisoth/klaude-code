"""UI glyph provenance, offline bundle freshness and semantic-name coverage."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "apps/webhost/src/klaude_webhost/static"


def test_ui_icon_bundle_and_declared_controls(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from bundle_ui_icons import bundle

    bundle(check=True)
    registry = json.loads((STATIC / "icons/ui/registry.json").read_text())
    manifest = json.loads((STATIC / "icons/ui/manifest.json").read_text())
    assert manifest["source"]["package"] == "@fortawesome/free-solid-svg-icons"
    assert manifest["source"]["version"] == registry["release"]
    assert "# Icons: CC BY 4.0" in (STATIC / "icons/ui/LICENSE.txt").read_text()
    known = set(registry["aliases"]) | set(registry["custom"])
    seen = []

    class Controls(HTMLParser):
        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            if tag == "svg" and "data-ui-icon" in attrs:
                seen.append(attrs["data-ui-icon"])

    Controls().feed((STATIC / "index.html").read_text())
    assert seen and set(seen) <= known
    # The two chat suggestions retain different semantic artwork when migrated.
    assert 'data-ui-icon="vision"' in (STATIC / "index.html").read_text()
    assert "window.KlaudeUIIcons =" in (STATIC / "app.js").read_text()
    assert "window.KlaudeUIIconData =" in (STATIC / "app.js").read_text()


@pytest.mark.parametrize(
    "path", ["", "<script>alert(1)</script>", "url(https://example.com)", "M0 0" * 6000]
)
def test_ui_icon_bundle_rejects_non_path_data(monkeypatch, path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from bundle_ui_icons import validate_path

    with pytest.raises(ValueError, match="Invalid SVG path"):
        validate_path(path)

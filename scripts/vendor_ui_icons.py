"""Vendor the reviewed Font Awesome Solid subset without executing npm code."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from vendor_webui_markdown import package

ROOT = Path(__file__).resolve().parents[1] / "apps/webhost/src/klaude_webhost/static/icons/ui"


def main() -> None:
    registry = json.loads((ROOT / "registry.json").read_text())
    read, record = package(registry["package"], registry["release"])
    icons = {}
    for name in sorted(set(registry["aliases"].values())):
        module = "fa" + "".join(word.capitalize() for word in name.split("-")) + ".js"
        source = read(module).decode()
        width = re.search(r"var width = (\d+);", source)
        height = re.search(r"var height = (\d+);", source)
        path = re.search(r"var svgPathData = '([MmZzLlHhVvCcSsQqTtAaEe0-9.,+\s-]+)';", source)
        if not width or not height or not path:
            raise ValueError(f"Unrecognized upstream icon format: {name}")
        icons[name] = [int(width[1]), int(height[1]), path[1]]
    payload = (json.dumps(icons, indent=2) + "\n").encode()
    license_text = read("LICENSE.txt")
    (ROOT / "fontawesome.json").write_bytes(payload)
    (ROOT / "LICENSE.txt").write_bytes(license_text)
    (ROOT / "manifest.json").write_text(
        json.dumps(
            {
                "reviewed": "2026-11-06",
                "source": record,
                "license": "Font Awesome Free icons: CC BY 4.0; code: MIT",
                "assets": {
                    "fontawesome.json": hashlib.sha256(payload).hexdigest(),
                    "LICENSE.txt": hashlib.sha256(license_text).hexdigest(),
                },
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Vendored {len(icons)} Font Awesome Free Solid icons with verified archive integrity")


if __name__ == "__main__":
    main()

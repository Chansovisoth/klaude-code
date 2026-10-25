"""Vendor the pinned KaTeX browser build for local native MathML rendering."""

import hashlib
import json

from vendor_webui_markdown import ROOT, package


def main() -> None:
    read, record = package("katex", "0.19.1")
    assets = {
        "katex.min.js": read("dist/katex.min.js"),
        "katex-LICENSE.txt": read("LICENSE"),
    }
    for name, content in assets.items():
        (ROOT / name).write_bytes(content)
    (ROOT / "math-manifest.json").write_text(
        json.dumps(
            {
                "reviewed": "2026-10-25",
                "packages": [record],
                "output": "mathml",
                "assets": {
                    name: hashlib.sha256(content).hexdigest() for name, content in assets.items()
                },
            },
            indent=2,
        )
        + "\n"
    )
    print("Vendored KaTeX with verified archive integrity and license")


if __name__ == "__main__":
    main()

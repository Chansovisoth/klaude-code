"""Refresh pinned, locally served WebUI Markdown assets and copyright notices.

Maintenance only: downloads npm release archives and verifies their published
SHA-512 integrity before reading fixed archive members. No npm scripts execute.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / "apps/webhost/src/klaude_webhost/static/vendor"
REVIEWED = "2026-10-25"
COMPONENTS = [
    "core",
    "markup",
    "css",
    "clike",
    "javascript",
    "typescript",
    "jsx",
    "tsx",
    "c",
    "cpp",
    "csharp",
    "java",
    "gdscript",
    "python",
    "bash",
    "json",
    "json5",
    "sql",
    "diff",
    "yaml",
    "toml",
    "markdown",
    "php",
    "ruby",
    "go",
    "rust",
    "swift",
    "kotlin",
    "scala",
    "dart",
    "lua",
    "r",
    "matlab",
    "julia",
    "perl",
    "powershell",
    "batch",
    "docker",
    "makefile",
    "cmake",
    "ini",
    "nginx",
    "apacheconf",
    "graphql",
    "protobuf",
    "regex",
    "latex",
    "csv",
    "hcl",
    "nix",
    "zig",
    "fsharp",
    "vbnet",
    "objectivec",
    "glsl",
    "hlsl",
    "sass",
    "scss",
    "less",
    "shell-session",
    "git",
    "http",
    "wasm",
    "nasm",
    "haxe",
    "ocaml",
    "elixir",
    "erlang",
    "fortran",
    "groovy",
    "solidity",
    "vhdl",
    "verilog",
    "lisp",
    "clojure",
    "haskell",
    "pascal",
    "cobol",
]
# Copyright/license sources for libraries bundled into markdown-it's UMD build.
# argparse is CLI-only and is not part of the browser bundle.
NOTICES = {
    "mdurl": "2.1.0",
    "entities": "8.0.0",
    "uc.micro": "3.0.0",
    "linkify-it": "6.0.0",
    "punycode.js": "2.3.1",
}


def fetch(url: str) -> bytes:
    with urlopen(
        Request(url, headers={"User-Agent": "klaude-webui-vendor-review"}), timeout=30
    ) as response:
        content = response.read(6_000_001)
    if len(content) > 6_000_000:
        raise ValueError("Vendor download exceeds bound")
    return content


def package(name: str, version: str):
    metadata = json.loads(fetch(f"https://registry.npmjs.org/{name}/{version}"))
    data = fetch(metadata["dist"]["tarball"])
    kind, expected = metadata["dist"]["integrity"].split("-", 1)
    actual = base64.b64encode(hashlib.sha512(data).digest()).decode()
    if kind != "sha512" or expected != actual:
        raise ValueError(f"Integrity verification failed for {name}")
    archive = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")

    def read(path: str) -> bytes:
        member = archive.getmember("package/" + path)
        if not member.isfile() or member.size > 2_000_000:
            raise ValueError("Invalid vendor archive member")
        stream = archive.extractfile(member)
        if stream is None:
            raise ValueError("Missing vendor archive member")
        return stream.read()

    record = {
        "package": name,
        "version": metadata["version"],
        "tarball": metadata["dist"]["tarball"],
        "integrity": metadata["dist"]["integrity"],
    }
    return read, record


def prism_components(metadata: dict, requested: list[str]) -> list[str]:
    """Include required grammars and respect selected optional/modified grammars."""
    languages = metadata["languages"]
    selected: set[str] = set()

    def names(value):
        return [value] if isinstance(value, str) else value or []

    def include(name):
        if name in selected or name == "core":
            return
        if name not in languages:
            raise ValueError(f"Unknown Prism grammar: {name}")
        selected.add(name)
        for required in names(languages[name].get("require")):
            include(required)

    for name in requested:
        include(name)
    ordered = ["core"]
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name):
        if name in visited or name == "core":
            return
        if name in visiting:
            raise ValueError(f"Circular Prism grammar dependency: {name}")
        visiting.add(name)
        for relation in ("require", "optional", "modify"):
            for dependency in names(languages[name].get(relation)):
                if dependency in selected:
                    visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(name)

    for name in requested:
        visit(name)
    return ordered


def main() -> None:
    ROOT.mkdir(exist_ok=True)
    markdown, markdown_record = package("markdown-it", "15.0.2")
    prism, prism_record = package("prismjs", "1.30.0")
    components = prism_components(json.loads(prism("components.json")), COMPONENTS)
    assets = {
        "markdown-it.min.js": markdown("dist/browser/markdown-it.umd.min.js"),
        "markdown-it-LICENSE.txt": markdown("LICENSE"),
        "prism-LICENSE.txt": prism("LICENSE"),
    }
    prefix = (
        "/* PrismJS 1.30.0, MIT. Manual tokenization only; see prism-LICENSE.txt. */\n"
        "globalThis.Prism={manual:true,disableWorkerMessageHandler:true};\n"
    )
    assets["prism.min.js"] = b"\n".join(
        [
            prefix.encode(),
            *(prism(f"components/prism-{name}.min.js") for name in components),
        ]
    )
    notices = []
    notice_records = []
    for name, version in NOTICES.items():
        read, record = package(name, version)
        for filename in (
            "LICENSE",
            "LICENSE.txt",
            "LICENSE.md",
            "LICENSE-MIT.txt",
            "license",
            "license.txt",
        ):
            try:
                license_text = read(filename).decode()
                break
            except KeyError:
                continue
        else:
            raise ValueError(f"Missing license for {name}")
        notices.append(f"{name}\n{'=' * len(name)}\n{license_text}\n")
        notice_records.append(record)
    assets["markdown-it-THIRD-PARTY.txt"] = "\n".join(notices).encode()
    for name, content in assets.items():
        (ROOT / name).write_bytes(content)
    (ROOT / "manifest.json").write_text(
        json.dumps(
            {
                "reviewed": REVIEWED,
                "packages": [markdown_record, prism_record],
                "license_sources": notice_records,
                "prism_components": components,
                "assets": {
                    name: hashlib.sha256(content).hexdigest() for name, content in assets.items()
                },
            },
            indent=2,
        )
        + "\n"
    )
    print("Vendored pinned Markdown and Prism assets with verified integrity and licenses")


if __name__ == "__main__":
    main()

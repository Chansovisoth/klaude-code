#!/usr/bin/env python3
"""Vendor pinned, reviewed icons without installing npm packages or running scripts.

Requires --cache-dir containing the integrity-checked research archives and pinned
first-party files documented in docs/webui/ai-model-icons.md. No arbitrary URL input.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import urlopen

from bundle_ai_icons import ASSETS, ROOT, bundle, validate_svg

PACKAGES = {
    "lobe": (
        "@lobehub/icons-static-svg",
        "1.98.0",
        "MIT",
        "sha512-soyLV2g74ujV+9BBymPwXrorJ+kQsEz7WvVd4uzhN2wZnd4Jbyc2FsmyjZBosGaufOirCs1RGJQlLe6l9bjwLg==",
    ),
    "simple": (
        "simple-icons",
        "16.35.0",
        "CC0-1.0",
        "sha512-TCfl/2+GTrx0nCo4pEWGvxhOb8c6NsqOU1OpwjtF4lwJAthB8IYVD0fuIMjLMg6JFuG1YBO0t1iETQqJLqkoJA==",
    ),
}
OFFICIAL = {
    "llamacpp": (
        "llamacpp-svg.txt",
        "ggml-org/llama.cpp",
        "78a8ae14be559b45f5f13ddee82c188b683d5d8d",
        "media/llama1-icon-transparent.svg",
        "llamacpp-license.txt",
        "MIT",
    ),
    "gpt4all": (
        "gpt4all-svg.txt",
        "nomic-ai/gpt4all",
        "b666d16db5aeab8b91aaf7963adcee9c643734d7",
        "gpt4all-chat/icons/gpt4all_transparent.svg",
        "gpt4all-license.txt",
        "MIT",
    ),
    "nomic": (
        "nomic-svg.txt",
        "nomic-ai/gpt4all",
        "b666d16db5aeab8b91aaf7963adcee9c643734d7",
        "gpt4all-chat/icons/nomic_logo.svg",
        "gpt4all-license.txt",
        "MIT",
    ),
}


def sanitize(raw: bytes) -> bytes:
    if len(raw) > 262144 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Unsafe source SVG")
    root = ET.fromstring(raw)
    # Inkscape editor metadata has no visual content. CSS class fills are inlined
    # before removing the style node, preserving the original vector geometry.
    classes = {}
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == "style":
            for name, color in re.findall(
                r"\.([\w-]+)\s*\{\s*fill:\s*(#[0-9a-fA-F]+);?\s*\}", node.text or ""
            ):
                classes[name] = color
    for parent in root.iter():
        for child in list(parent):
            if child.tag.rsplit("}", 1)[-1] in {"style", "namedview", "metadata"}:
                parent.remove(child)
        for key in list(parent.attrib):
            if key.rsplit("}", 1)[-1].lower() == "href" or key.lower().startswith("on"):
                raise ValueError("Active SVG attributes are forbidden")
            if key.startswith("{"):
                del parent.attrib[key]
        if "class" in parent.attrib:
            name = parent.attrib.pop("class")
            if name not in classes:
                raise ValueError(f"Unsupported source class: {name}")
            parent.set("fill", classes[name])
        if "style" in parent.attrib:
            for declaration in parent.attrib.pop("style").split(";"):
                if not declaration.strip():
                    continue
                key, value = declaration.split(":", 1)
                if key.strip() in {
                    "fill",
                    "stroke",
                    "opacity",
                    "fill-opacity",
                    "stroke-width",
                    "fill-rule",
                    "clip-rule",
                    "mask-type",
                }:
                    parent.set(key.strip(), value.strip())
                elif key.strip() not in {"flex", "line-height"}:
                    raise ValueError(f"Unsupported source style: {key}")
    if "viewBox" not in root.attrib:
        width, height = root.attrib["width"], root.attrib["height"]
        if not re.fullmatch(r"[\d.]+", width + height):
            raise ValueError("Non-numeric source dimensions")
        root.set("viewBox", f"0 0 {width} {height}")
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    result = ET.tostring(root, encoding="utf-8") + b"\n"
    validate_svg(result)
    return result


def vendor(cache: Path, download: bool = False) -> None:
    sources = json.loads(Path(__file__).with_name("ai_icons").joinpath("sources.json").read_text())
    cache.mkdir(parents=True, exist_ok=True)
    for file, spec in sources.items():
        target = cache / file
        if download and not target.exists():
            with urlopen(spec["url"], timeout=40) as response:
                content = response.read(12 * 1024 * 1024)
            if hashlib.sha256(content).hexdigest() != spec["sha256"]:
                raise ValueError(f"Source download hash mismatch: {file}")
            target.write_bytes(content)
        if hashlib.sha256(target.read_bytes()).hexdigest() != spec["sha256"]:
            raise ValueError(f"Source cache hash mismatch: {file}")
    archives = {}
    for key, (_, _, _, integrity) in PACKAGES.items():
        data = (cache / f"{key}.tgz").read_bytes()
        if "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode() != integrity:
            raise ValueError(f"{key} archive integrity mismatch")
        archives[key] = tarfile.open(cache / f"{key}.tgz")
    registry = json.loads((ASSETS / "registry.json").read_text())
    refs = {
        r["icon"]
        for group in ("providers", "families", "platforms")
        for r in registry[group]
        if r["icon"]
    }
    # Keep earlier public filenames compatible while using creator identities now.
    aliases = {"gpt": "openai", "phi": "microsoft", "llama": "meta"}
    refs.update(aliases.values())
    manifest = {
        "sources": sources,
        "packages": {
            key: {"name": name, "version": version, "license": license_id, "integrity": integrity}
            for key, (name, version, license_id, integrity) in PACKAGES.items()
        },
        "icons": {},
    }

    def save(name: str, raw: bytes, source: str, license_id: str, **extra) -> None:
        clean = sanitize(raw)
        (ASSETS / f"{name}.svg").write_bytes(clean)
        manifest["icons"][name] = {
            "source": source,
            "license": license_id,
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "sha256": hashlib.sha256(clean).hexdigest(),
            **extra,
        }

    for name in sorted(refs):
        if name in OFFICIAL:
            file, repo, commit, member, license_file, license_id = OFFICIAL[name]
            save(
                name,
                (cache / file).read_bytes(),
                f"https://raw.githubusercontent.com/{repo}/{commit}/{member}",
                license_id,
            )
            (ASSETS / f"{name}-LICENSE.txt").write_bytes((cache / license_file).read_bytes())
            manifest["icons"][name]["license_file"] = f"{name}-LICENSE.txt"
            continue
        package = "simple" if name in {"databricks", "xiaomi"} else "lobe"
        archive = archives[package]
        member = f"package/icons/{name}.svg"
        source = f"{PACKAGES[package][0]}@{PACKAGES[package][1]}/{member}"
        raw = archive.extractfile(member).read()
        save(name, raw, source, PACKAGES[package][2], package=package)
        color_member = f"package/icons/{name}-color.svg"
        if color_member in archive.getnames():
            color = f"{name}-color"
            save(
                color,
                archive.extractfile(color_member).read(),
                f"{PACKAGES[package][0]}@{PACKAGES[package][1]}/{color_member}",
                PACKAGES[package][2],
                package=package,
            )
            manifest["icons"][name]["color"] = color
    for alias, canonical in aliases.items():
        (ASSETS / f"{alias}.svg").write_bytes((ASSETS / f"{canonical}.svg").read_bytes())
        manifest["icons"][alias] = {**manifest["icons"][canonical], "alias_of": canonical}
    generic = (ASSETS / "generic.svg").read_bytes()
    validate_svg(generic)
    manifest["icons"]["generic"] = {
        "source": "Klaude existing generic model artwork",
        "license": "MIT",
        "license_file": "generic-LICENSE.txt",
        "sha256": hashlib.sha256(generic).hexdigest(),
    }
    (ASSETS / "LICENSE").write_bytes((cache / "lobe-license.txt").read_bytes())
    (ASSETS / "generic-LICENSE.txt").write_bytes((ROOT / "LICENSE").read_bytes())
    (ASSETS / "simple-icons-LICENSE.txt").write_bytes(
        archives["simple"].extractfile("package/LICENSE.md").read()
    )
    (ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    bundle()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="Fetch only the pinned source URLs")
    args = parser.parse_args()
    vendor(args.cache_dir, args.download)

"""Validate the single editable offline quote collection and refresh its metadata.

Edit static/lockscreen-quotes.json directly, then run this script and the bundle
script. Optional --source-dir verifies the unchanged HF proverbs against pinned
source downloads. This script never uses the network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "apps/webhost/src/klaude_webhost/static"
DATASET = "geosfero/positivequotation-public-domain-quotes"
REVISION = "4c8151903a29476f8fc66b26237c5911e1199835"
HASHES = {
    "README.md": "df6dc3cec4e1e1f849341e8c6759d78f0aae77d8e9d1d70c7863cfccdf424b12",
    "LICENSE": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "data.json": "f9e8db216cc7e83dbb21dc24735d2d828a6047c709381ed4240e5e049e2bd7c4",
    "gutenberg-39281.txt": "1ae9bc98d49be7ec3d78d2015fa34951c3733f138230545ea89dc1af401d9f9e",
}
SELECTED_IDS = (4591, 4592, 4594, 4595, 4597, 4599, 4600, 4602, 4603,
                4604, 4605, 4606, 4608, 4609, 4610, 4612, 4615, 4616,
                4617)


def curate(source_dir: Path | None, check: bool) -> None:
    path = STATIC / "lockscreen-quotes.json"
    collection = json.loads(path.read_text())
    if collection.get("version") != 1:
        raise ValueError("Unsupported quote collection")
    quotes = collection["quotes"]
    if not quotes or any(not isinstance(row.get("id"), int) or row["id"] <= 0
                         or not isinstance(row.get("quote"), str)
                         or not 0 < len(row["quote"].strip()) <= 80
                         or re.search(r"[\x00-\x1f\x7f]", row["quote"])
                         or not isinstance(row.get("attribution"), str)
                         or not row["attribution"].strip() for row in quotes):
        raise ValueError("Quotes need positive IDs, attribution and 1–80 characters")
    if len({row["id"] for row in quotes}) != len(quotes) or len({row["quote"] for row in quotes}) != len(quotes):
        raise ValueError("Quotes must have unique IDs and text")
    proverbs = [row for row in quotes if "source_kind" not in row]
    easter_eggs = [row for row in quotes if row.get("source_kind") == "easter_egg"]
    if len(proverbs) + len(easter_eggs) != len(quotes):
        raise ValueError("Unknown quote source kind")
    for row in easter_eggs:
        if (row.get("category") not in {"pop_culture", "meme", "greeting"}
                or row.get("origin") not in {"user_prompt", "original_microcopy"}
                or row.get("source_entry") or row.get("source_url")):
            raise ValueError(f"Invalid Easter egg metadata: {row['id']}")
    if {row["id"] for row in proverbs} != set(SELECTED_IDS):
        raise ValueError("Reviewed proverb IDs changed")
    if source_dir is not None:
        for name, expected in HASHES.items():
            actual = hashlib.sha256((source_dir / name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"Pinned source mismatch: {name}")
        original = {row["id"]: row for row in json.loads((source_dir / "data.json").read_text())}
        book = (source_dir / "gutenberg-39281.txt").read_text(encoding="utf-8-sig")
        for row in proverbs:
            entry = re.search(rf"(?m)^{row['source_entry']}\. [A-Z ()'-]+\. (.+)$", book)
            if row != original.get(row["id"]) or not entry or entry[1] != row["quote"]:
                raise ValueError(f"Quote {row['id']} differs from its reviewed source")
    digest = hashlib.sha256(json.dumps(quotes, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    collection["collection_id"] = f"klaude-quotes-{digest[:16]}"
    collection["dataset"]["selected_rows"] = len(proverbs)
    collection["easter_eggs"] = {
        "source_file": "lockscreen-quotes.json",
        "selected_rows": len(easter_eggs),
        "pop_culture_rows": sum(row["category"] == "pop_culture" for row in easter_eggs),
        "meme_rows": sum(row["category"] == "meme" for row in easter_eggs),
        "greeting_rows": sum(row["category"] == "greeting" for row in easter_eggs),
        "notice": "User supplied examples and original Klaude microcopy; not part of the proverb dataset.",
    }
    notice = (
        "Klaude lockscreen quote collection\n\n"
        f"Source: https://huggingface.co/datasets/{DATASET}\n"
        f"Pinned revision: {REVISION}\n"
        f"data.json SHA-256: {HASHES['data.json']}\n\n"
        "19 unmodified English proverbs selected from the 30 reviewed records.\n"
        "Every selected row retains all original attribution and provenance fields.\n"
        f"Separately, {len(easter_eggs)} local Easter eggs include user supplied lines and\n"
        f"{sum(row['origin'] == 'original_microcopy' for row in easter_eggs)} original Klaude microcopy lines. They are not dataset records or\n"
        "attributed to any game, film, artist or meme creator. No third-party\n"
        "assets are included. All entries and their origin metadata are stored in\n"
        "lockscreen-quotes.json.\n"
        "Thomas Preston is the source compiler, not the author of these proverbs.\n"
        "Hugging Face license metadata is 'other'. The upstream LICENSE file is\n"
        "empty; this collection does not claim CC0 or a universal public-domain\n"
        "license. The source edition is marked public domain in the USA.\n"
        "The fallback 'Make a little room for a new idea.' is original Klaude copy\n"
        "under Klaude's MIT license; it is not part of the source collection.\n\n"
        f"Dataset card: https://huggingface.co/datasets/{DATASET}/blob/{REVISION}/README.md\n"
        f"Dataset card SHA-256: {HASHES['README.md']}\n\n"
        "The dataset card requests that attribution, source entry numbers and\n"
        "source URLs be retained for provenance. These fields are preserved in\n"
        "lockscreen-quotes.json and its bundled copy. The quote container retains\n"
        "attribution in an accessible, visually hidden cite element, source title\n"
        "and entry in its tooltip, and source URL in its cite attribute.\n\n"
        "Book: A Dictionary of English Proverbs and Proverbial Phrases\n"
        "Compiler: Thomas Preston\n"
        "Source catalog: https://www.gutenberg.org/ebooks/39281\n"
        "Source edition status: Public domain in the USA. Other jurisdictions\n"
        "and rights may differ; the dataset does not claim a universal license.\n"
        "Only the underlying proverb text and factual provenance are included;\n"
        "the Gutenberg eBook, trademarked wrapper and dataset card are not copied.\n"
    )
    outputs = {
        STATIC / "lockscreen-quotes.json": (
            json.dumps(collection, ensure_ascii=False, indent=2) + "\n"
        ),
        STATIC / "vendor/lockscreen-quotes-NOTICE.txt": notice,
    }
    for path, content in outputs.items():
        if check:
            if path.read_text() != content:
                raise ValueError(f"Regenerate {path.name}")
        else:
            path.write_text(content)
    print(f"{'Verified' if check else 'Curated'} {len(proverbs)} source-matched proverbs "
          f"and {len(easter_eggs)} local Easter eggs (max 80 characters)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, help="Optional pinned downloads for source verification")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    curate(args.source_dir, args.check)

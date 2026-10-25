"""Bundle the shared Expressive CSS using the existing static route.

Preserves all existing rules outside its owned block. No runtime build system.
"""

from __future__ import annotations

import argparse
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "apps/webhost/src/klaude_webhost/static"
START = "/* BEGIN KLAUDE EXPRESSIVE: python3 scripts/bundle_webui_expressive.py */"
END = "/* END KLAUDE EXPRESSIVE */"


def bundle(check: bool = False) -> None:
    target = STATIC / "style.css"
    original = target.read_text()
    base = original
    after = "\n"
    if START in base:
        assert base.count(START) == base.count(END) == 1
        before, owned = base.split(START, 1)
        after = owned.split(END, 1)[1]
        base = before
    output = (
        base.rstrip()
        + "\n\n"
        + START
        + "\n"
        + (STATIC / "vendor/material-progress.css").read_text().rstrip()
        + "\n"
        + (STATIC / "vendor/material-tabs.css").read_text().rstrip()
        + "\n"
        + (STATIC / "expressive.css").read_text().rstrip()
        + "\n"
        + END
        + after
    )
    if check:
        assert output == original, "Run python3 scripts/bundle_webui_expressive.py"
    else:
        target.write_text(output)
    print("Verified Klaude Expressive CSS" if check else "Bundled Klaude Expressive CSS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    bundle(parser.parse_args().check)

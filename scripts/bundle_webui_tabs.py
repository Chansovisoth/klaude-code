"""Bundle the upstream md3.io tab indicator into the existing Library route."""
from __future__ import annotations

import argparse
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "apps/webhost/src/klaude_webhost/static"
START = "/* BEGIN MD3 TABS: python3 scripts/bundle_webui_tabs.py */"
END = "/* END MD3 TABS */"


def bundle(check: bool = False) -> None:
    target = STATIC / "library.js"
    original = target.read_text()
    controller = original
    if START in controller:
        before, block = controller.split(START, 1)
        assert before.strip() in {'', '"use strict";'}
        controller = block.split(END, 1)[1].lstrip("\n")
    indicator = (STATIC / "vendor/material-tabs-indicator.js").read_text()
    indicator = indicator.replace("export const createTabIndicator", "const createTabIndicator", 1)
    output = ('"use strict";\n\n' + START + "\n/* material@3.2.4 | MIT | Copyright 2025 floor */\n"
              + "window.KlaudeMD3Tabs = (() => {\n" + indicator
              + "\nreturn Object.freeze({ createTabIndicator });\n})();\n"
              + END + "\n\n" + controller)
    if check:
        assert original == output, "Run python3 scripts/bundle_webui_tabs.py"
    else:
        target.write_text(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    bundle(parser.parse_args().check)

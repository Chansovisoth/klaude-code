"""Bundle the indicator into the app asset served by current and legacy hosts.

No JS build dependency. Edit loading-indicator.js / the generated geometry, then
run this script. The controller outside the marked block is preserved verbatim.
"""

from __future__ import annotations

import argparse
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "apps/webhost/src/klaude_webhost/static"
START = "/* BEGIN BUNDLED MATERIAL LOADING: python3 scripts/bundle_webui_loading.py */"
END = "/* END BUNDLED MATERIAL LOADING */"


def bundle(check: bool = False) -> None:
    app = STATIC / "app.js"
    source = app.read_text()
    assert source.startswith('"use strict";\n')
    controller = source[len('"use strict";\n'):]
    if START in controller:
        assert controller.count(START) == controller.count(END) == 1
        before, block = controller.split(START, 1)
        assert not before.strip()
        controller = block.split(END, 1)[1]
    controller = controller.lstrip("\n")
    dependencies = [STATIC / "vendor/material-loading-shapes.js", STATIC / "loading-indicator.js"]
    output = ('"use strict";\n\n' + START + "\n" +
              "\n".join(path.read_text().rstrip() for path in dependencies) +
              "\n" + END + "\n\n" + controller)
    if check:
        assert source == output, "Run python3 scripts/bundle_webui_loading.py"
    else:
        app.write_text(output)
    print("Verified app indicator bundle" if check else "Bundled official indicator into app.js")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    bundle(parser.parse_args().check)

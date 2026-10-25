"""Bundle the indicator into the app asset served by current and legacy hosts.

No JS build dependency. Edit loading-indicator.js / the generated geometry, then
run this script. The controller outside the marked block is preserved verbatim.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "apps/webhost/src/klaude_webhost/static"
START = "/* BEGIN BUNDLED MATERIAL LOADING: python3 scripts/bundle_webui_loading.py */"
END = "/* END BUNDLED MATERIAL LOADING */"
COLOR_START = "/* BEGIN EARLY MATERIAL COLORS: python3 scripts/bundle_webui_loading.py */"
COLOR_END = "/* END EARLY MATERIAL COLORS */"
GEOMETRY_START = "/* BEGIN EARLY MATERIAL GEOMETRY: python3 scripts/bundle_webui_loading.py */"
GEOMETRY_END = "/* END EARLY MATERIAL GEOMETRY */"
PROGRESS_START = "/* BEGIN EARLY MATERIAL PROGRESS: python3 scripts/bundle_webui_loading.py */"
PROGRESS_END = "/* END EARLY MATERIAL PROGRESS */"


def bundle(check: bool = False) -> None:
    # Restore complete generated colors before CSS/first paint, including custom
    # and image-derived seeds. The same source remains inside app.js so older
    # hosts can still run it without a newly introduced static route.
    loading = STATIC / "loading-indicator.js"
    loading_source = loading.read_text()
    runtime = loading_source
    for start, end in ((COLOR_START, COLOR_END), (GEOMETRY_START, GEOMETRY_END),
                       (PROGRESS_START, PROGRESS_END)):
        if start in runtime:
            assert runtime.count(start) == runtime.count(end) == 1
            before, owned = runtime.split(start, 1)
            assert not before.strip()
            runtime = owned.split(end, 1)[1].lstrip("\n")
    colors = [STATIC / "vendor/material-colors.js", STATIC / "expressive-colors.js"]
    # Startup uses the same renderer before app.js downloads. Keep its existing
    # matched geometry in this public asset, without another blocking request or
    # a new static route that would require a running host to restart.
    geometry = (STATIC / "vendor/material-loading-shapes.js").read_text().rstrip()
    progress = (STATIC / "vendor/material-progress.min.js").read_text().rstrip()
    early = (COLOR_START + "\n" + "\n".join(p.read_text().rstrip() for p in colors)
             + "\n" + COLOR_END + "\n\n" + GEOMETRY_START + "\n" + geometry
             + "\n" + GEOMETRY_END + "\n\n" + PROGRESS_START + "\n" + progress
             + "\n" + PROGRESS_END + "\n\n" + runtime)
    if check:
        assert loading_source == early, "Run python3 scripts/bundle_webui_loading.py"
    else:
        loading.write_text(early)
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
    # Offline quote data travels in the existing app route. No runtime fetch or
    # additional public route is needed, including on a running legacy host.
    quote_data = json.loads((STATIC / "lockscreen-quotes.json").read_text())
    quote_source = ("window.KlaudeLockQuoteCollection = "
                    + json.dumps(quote_data, ensure_ascii=True, separators=(",", ":")) + ";")
    dependencies = [STATIC / "loading-indicator.js", STATIC / "expressive.js"]
    lockscreen = [STATIC / "lockscreen-quotes.js", STATIC / "lockscreen.js"]
    output = ('"use strict";\n\n' + START + "\n" +
              "\n".join(path.read_text().rstrip() for path in dependencies) +
              "\n" + quote_source + "\n" +
              "\n".join(path.read_text().rstrip() for path in lockscreen) +
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

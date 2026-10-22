"""Real mouse/touch backdrop dismissal with isolated stores and no model work.

Run: .venv/bin/python scripts/webui_dialogs_smoke.py
Optional: KLAUDE_TEST_CHROME=/path/to/headless-chrome
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools import Workspace
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402


async def verify(host, root, chrome):
    profile = root / "chrome"
    process = subprocess.Popen(
        [chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
         f"--user-data-dir={profile}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            await asyncio.sleep(0.05)
        port = int(active.read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Emulation.setTouchEmulationEnabled", {
                "enabled": True, "maxTouchPoints": 2,
            })
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait("typeof latest !== 'undefined' && authenticated && latest")
            await tab.wait("Boolean(messages.querySelector('[aria-label=\"Share message\"]'))")
            # The full-review reader needs an actual Vision result and is covered
            # by webui_inspector_smoke; opening it without one correctly closes it.
            ids = await tab.js("[...document.querySelectorAll('dialog')].map(d => d.id)"
                               ".filter(id=>id!=='vision-full-review')")

            async def geometry(selector):
                return await tab.js("""(() => {
                    const d = document.querySelector(""" + json.dumps(selector) + """);
                    const r = d.getBoundingClientRect();
                    const outside = [{x:r.left/2,y:innerHeight/2},
                      {x:(r.right+innerWidth)/2,y:innerHeight/2},
                      {x:innerWidth/2,y:r.top/2},
                      {x:innerWidth/2,y:(r.bottom+innerHeight)/2}].find(p =>
                        p.x>0 && p.x<innerWidth && p.y>0 && p.y<innerHeight &&
                        (p.x<r.left || p.x>r.right || p.y<r.top || p.y>r.bottom));
                    return {inside:{x:r.left+r.width/2,y:r.top+8},outside};
                })()""")

            async def tap(point, mode):
                if mode == "touch":
                    await tab.command("Input.dispatchTouchEvent", {
                        "type": "touchStart", "touchPoints": [{**point, "id": 1}],
                    })
                    await tab.command("Input.dispatchTouchEvent", {
                        "type": "touchEnd", "touchPoints": [],
                    })
                else:
                    for kind in ("mousePressed", "mouseReleased"):
                        await tab.command("Input.dispatchMouseEvent", {
                            "type": kind, **point, "button": "left", "clickCount": 1,
                        })

            async def drag(start, end, mode):
                if mode == "touch":
                    await tab.command("Input.dispatchTouchEvent", {
                        "type": "touchStart", "touchPoints": [{**start, "id": 1}],
                    })
                    await tab.command("Input.dispatchTouchEvent", {
                        "type": "touchMove", "touchPoints": [{**end, "id": 1}],
                    })
                    await tab.command("Input.dispatchTouchEvent", {
                        "type": "touchEnd", "touchPoints": [],
                    })
                else:
                    await tab.command("Input.dispatchMouseEvent", {
                        "type": "mousePressed", **start, "button": "left", "clickCount": 1,
                    })
                    await tab.command("Input.dispatchMouseEvent", {
                        "type": "mouseMoved", **end, "buttons": 1,
                    })
                    await tab.command("Input.dispatchMouseEvent", {
                        "type": "mouseReleased", **end, "button": "left", "clickCount": 1,
                    })

            checked, fullscreen = [], []
            for width, height in [(320, 568), (390, 844), (768, 1024), (1440, 900)]:
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1,
                    "mobile": False,
                })
                for mode in ("mouse", "touch"):
                    for identity in ids:
                        selector = "#" + identity
                        await tab.js(f"byId({json.dumps(identity)}).showModal()")
                        await tab.js(f"Promise.all(byId({json.dumps(identity)}).getAnimations()"
                                     ".map(a => a.finished.catch(()=>{})))")
                        points = await geometry(selector)
                        if not points.get("outside"):
                            fullscreen.append([width, mode, identity])
                            await tab.js(f"byId({json.dumps(identity)}).close()")
                            continue
                        await tap(points["inside"], mode)
                        assert await tab.js(f"byId({json.dumps(identity)}).open"), identity
                        if identity == "session-management":
                            await drag(points["inside"], points["outside"], mode)
                            assert await tab.js("byId('session-management').open")
                            await drag(points["outside"], points["inside"], mode)
                            assert await tab.js("byId('session-management').open")
                        await tap(points["outside"], mode)
                        await tab.wait(f"!byId({json.dumps(identity)}).open")
                        checked.append([width, mode, identity])

                    # Message dialogs are created after the shared handler is installed.
                    for label in ("Share message", "Sources"):
                        await tab.click(f'[aria-label="{label}"]')
                        await tab.wait("Boolean(document.querySelector('.message-dialog[open]'))")
                        await tab.js("Promise.all(document.querySelector('.message-dialog[open]')"
                                     ".getAnimations().map(a=>a.finished.catch(()=>{})))")
                        points = await geometry(".message-dialog")
                        await tap(points["inside"], mode)
                        assert await tab.js("document.querySelector('.message-dialog').open")
                        await tap(points["outside"], mode)
                        await tab.wait("!document.querySelector('.message-dialog').open")
                        checked.append([width, mode, label])

            # Only the top dialog closes, even when its backdrop overlaps its parent.
            await tab.js("byId('image-generate-panel').showModal();"
                         "byId('artifact-import-panel').showModal()")
            points = await geometry("#artifact-import-panel")
            await tap(points["outside"], "touch")
            await tab.wait("!byId('artifact-import-panel').open")
            assert await tab.js("byId('image-generate-panel').open")
            await tab.js("byId('image-generate-panel').close();showView('library')")

            # An actual destructive review dismisses as Cancel, without deleting the file.
            item = host.library.artifacts.import_bytes(
                b"Private saved copy", "document", "saved.txt"
            )
            draft = {"operation": "delete", "target": item["id"], "revision": item["revision"]}
            await tab.js("prepareChange(" + json.dumps(draft) + ").then(() => true)")
            await tab.wait("reviewDialog.open && managementReview !== null")
            points = await geometry("#domain-review")
            await tap(points["outside"], "touch")
            await tab.wait("!reviewDialog.open && managementReview === null")
            assert host.library.artifacts.get(item["id"])["revision"] == item["revision"]
            assert host.library.operations()["items"] == []
            assert not tab.errors, tab.errors
            print(json.dumps({
                "backdrop_checks": len(checked), "fullscreen_without_backdrop": fullscreen,
                "inside_taps_preserved": True, "inside_outside_drags_preserved": True,
                "dynamic_message_dialogs": True, "top_dialog_only": True,
                "destructive_review_cancelled": True, "console_errors": 0,
            }))
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    ))
    with tempfile.TemporaryDirectory(prefix="klaude-dialogs-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace = root, Workspace(root)
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        app.memory.log_turn(app.session_id, "assistant", "A saved [reference](https://example.com).")
        host = LocalWebHost(app, library=LibraryManagement(cfg, root))
        host.local_models = lambda: []
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome), 120))
        finally:
            host.stop()
            thread.join(timeout=3)


if __name__ == "__main__":
    main()

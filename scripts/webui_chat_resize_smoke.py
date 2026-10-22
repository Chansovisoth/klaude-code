"""Real browser checks for chat-edge resizing and borderless side panels.

Uses an isolated profile and local HTTP fixture, without model requests.
Run: .venv/bin/python scripts/webui_chat_resize_smoke.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
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
from klaude_tools.toolkit import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab

OUT = Path("/tmp/klaude-chat-resize-preview")
PREFERENCE = "klaude.webui.chat-width.v1"


async def verify(host, root, chrome):
    OUT.mkdir(exist_ok=True)
    profile = root / "chrome"
    process = subprocess.Popen(
        [
            chrome,
            "--no-sandbox",
            "--disable-gpu",
            "--remote-debugging-port=0",
            "--blink-settings=primaryHoverType=2,availableHoverTypes=2,primaryPointerType=4,availablePointerTypes=4",
            f"--user-data-dir={profile}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(0.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(
            Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        ) as response:
            target = json.load(response)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=6_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")

            async def viewport(width, height=900):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": width <= 768,
                    },
                )
                await asyncio.sleep(0.15)

            async def geometry():
                return await tab.js("""(()=>{
                  const rect=id=>{const r=byId(id).getBoundingClientRect();
                    return {left:r.left,right:r.right,width:r.width};};
                  return {chat:rect('main-content'),left:rect('session-sidebar'),
                    right:rect('inspector'),leftHidden:byId('chat-resize-left').hidden,
                    rightHidden:byId('chat-resize-right').hidden,
                    fits:document.documentElement.scrollWidth<=innerWidth,
                    dragging:document.documentElement.classList.contains('resizing-chat')};
                })()""")

            async def drag(side, delta, cancel=False):
                point = await tab.js(f"""(()=>{{
                  const r=byId('chat-resize-{side}').getBoundingClientRect();
                  return {{x:r.left+r.width/2,y:r.top+r.height/2}};}})()""")
                await tab.command("Input.dispatchMouseEvent", {"type": "mouseMoved", **point})
                await tab.command(
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mousePressed",
                        "button": "left",
                        "buttons": 1,
                        "clickCount": 1,
                        **point,
                    },
                )
                for step in range(1, 6):
                    await tab.command(
                        "Input.dispatchMouseEvent",
                        {
                            "type": "mouseMoved",
                            "button": "left",
                            "buttons": 1,
                            "x": point["x"] + delta * step / 5,
                            "y": point["y"],
                        },
                    )
                if cancel:
                    await tab.command(
                        "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape"}
                    )
                await tab.command(
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mouseReleased",
                        "button": "left",
                        "buttons": 0,
                        "clickCount": 1,
                        "x": point["x"] + delta,
                        "y": point["y"],
                    },
                )
                await asyncio.sleep(0.08)

            async def key(side, value, **fields):
                await tab.js(f'byId("chat-resize-{side}").focus()')
                await tab.command(
                    "Input.dispatchKeyEvent", {"type": "keyDown", "key": value, **fields}
                )
                await asyncio.sleep(0.05)

            await viewport(1440)
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js(
                'byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await tab.wait("window.ChatLayoutUI && latest?.session_id && !layout.inert")
            await tab.js(
                'toggleSessions(true);setContextPanel(true);prompt.value="Keep this draft"'
            )
            await tab.wait('!byId("chat-resize-left").hidden && !byId("chat-resize-right").hidden')
            initial = await geometry()
            session = await tab.js("latest.session_id")
            assert initial["fits"] and initial["chat"]["width"] >= 400, initial
            await drag("left", 70)
            left = await geometry()
            assert abs(left["chat"]["left"] - initial["chat"]["left"] - 70) <= 1, left
            assert abs(left["chat"]["right"] - initial["chat"]["right"]) <= 1, left
            await drag("right", -90)
            right = await geometry()
            assert abs(right["chat"]["right"] - left["chat"]["right"] + 90) <= 1, right
            assert abs(right["chat"]["left"] - left["chat"]["left"]) <= 1, right
            saved = await tab.js(f"localStorage.getItem({json.dumps(PREFERENCE)})")
            await drag("left", 50, cancel=True)
            cancelled = await geometry()
            assert abs(cancelled["chat"]["left"] - right["chat"]["left"]) <= 1, cancelled
            assert not cancelled["dragging"]
            assert await tab.js(f"localStorage.getItem({json.dumps(PREFERENCE)})") == saved
            assert await tab.js("prompt.value") == "Keep this draft"
            assert await tab.js("latest.session_id") == session

            await key("right", "ArrowRight")
            keyboard = await geometry()
            assert abs(keyboard["chat"]["right"] - right["chat"]["right"] - 10) <= 1, keyboard
            for side in ("right", "left"):
                await key(side, "Home")
            limited = await geometry()
            assert limited["chat"]["width"] >= 399 and limited["fits"], limited
            assert limited["left"]["width"] >= 216 and limited["right"]["width"] >= 268
            for side in ("left", "right"):
                values = await tab.js(f"""(()=>{{const h=byId('chat-resize-{side}');return [
                  +h.getAttribute('aria-valuemin'),+h.getAttribute('aria-valuenow'),
                  +h.getAttribute('aria-valuemax')];}})()""")
                assert values[0] <= values[1] <= values[2], values
            stored = await tab.js(f"localStorage.getItem({json.dumps(PREFERENCE)})")
            await viewport(1241)
            constrained = await geometry()
            assert constrained["fits"] and constrained["chat"]["width"] >= 399, constrained
            assert await tab.js(f"localStorage.getItem({json.dumps(PREFERENCE)})") == stored
            await viewport(1920)
            restored = await geometry()
            expected = json.loads(stored)
            assert abs(restored["left"]["width"] - expected["left"]) <= 1, restored
            assert abs(restored["right"]["width"] + 12 - expected["right"]) <= 1, restored

            await tab.js("window.beforeResizeReload=true")
            await tab.command("Page.reload")
            await tab.wait(
                "!window.beforeResizeReload && window.ChatLayoutUI && "
                "latest?.session_id && !layout.inert"
            )
            await tab.js("toggleSessions(true);setContextPanel(true)")
            await asyncio.sleep(0.1)
            reloaded = await geometry()
            assert abs(reloaded["left"]["width"] - restored["left"]["width"]) <= 1
            assert abs(reloaded["right"]["width"] - restored["right"]["width"]) <= 1

            await tab.js("toggleSessions(false)")
            await tab.wait('byId("chat-resize-left").hidden')
            assert not (await geometry())["rightHidden"]
            await tab.js("setContextPanel(false)")
            await tab.wait('byId("chat-resize-right").hidden')
            both_closed = await geometry()
            assert both_closed["fits"] and both_closed["chat"]["width"] > reloaded["chat"]["width"]
            await tab.js("toggleSessions(true);setContextPanel(true)")
            await tab.wait('!byId("chat-resize-left").hidden && !byId("chat-resize-right").hidden')
            await key("left", "Enter")
            assert abs((await geometry())["left"]["width"] - 260) <= 1
            await key("right", "Enter")
            assert abs((await geometry())["right"]["width"] - 328) <= 1

            await tab.js(
                "window.resizeSetItem=Storage.prototype.setItem;"
                'Storage.prototype.setItem=()=>{throw new Error("Fixture storage blocked")};'
            )
            await key("left", "ArrowRight")
            assert abs((await geometry())["left"]["width"] - 270) <= 1
            await tab.js("Storage.prototype.setItem=resizeSetItem")
            await key("left", "Enter")

            layouts = []
            for theme in ("light", "dark"):
                await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                for width, height in (
                    (1920, 900),
                    (1440, 900),
                    (1000, 800),
                    (768, 844),
                    (390, 640),
                    (320, 480),
                ):
                    await viewport(width, height)
                    await tab.js("setContextPanel(true);document.activeElement.blur()")
                    await tab.command(
                        "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 10, "y": 10}
                    )
                    await asyncio.sleep(0.2)
                    state = await geometry()
                    assert state["fits"] and state["leftHidden"] is (width <= 850), state
                    assert state["rightHidden"] is (width <= 1240), state
                    borders = await tab.js("""['inspector']
                      .concat(['cp-task','cp-header','cp-library-controls','cp-pagination'].map(x=>'.'+x))
                      .map(x=>{const node=x.startsWith('.')?document.querySelector(x):byId(x);
                        const s=getComputedStyle(node);return [s.borderLeftWidth,s.borderRightWidth,
                          s.borderTopWidth,s.borderBottomWidth].every(v=>parseFloat(v)===0)}).every(Boolean)""")
                    assert borders, (width, theme)
                    if width > 1240:
                        assert (
                            await tab.js(
                                'getComputedStyle(byId("chat-resize-right"),"::after").opacity'
                            )
                            == "0"
                        )
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (OUT / f"chat-{theme}-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                    layouts.append((theme, width))
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "native_edge_drag": True,
                        "opposite_edge_stable": True,
                        "keyboard_and_cancel": True,
                        "bounds_and_preference_restore": True,
                        "collapse_and_storage_failure": True,
                        "borderless_panels": True,
                        "responsive_layouts": len(layouts),
                        "console_errors": 0,
                        "screenshots": str(OUT),
                    },
                    indent=2,
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or shutil.which("chromium")
    if not chrome:
        chrome = str(
            next(
                (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                    "*/chrome-headless-shell-linux64/chrome-headless-shell"
                )
            )
        )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.unit.test_webhost import _app

    with tempfile.TemporaryDirectory(prefix="klaude-chat-resize-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        library = LibraryManagement(cfg, root)
        library.artifacts.import_bytes(b"Library fixture", "document", "note.txt")
        host = LocalWebHost(app, accounts=accounts, library=library, staging_dir=root / "staging")
        host.local_models = lambda: []
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome), 100))
        finally:
            host.stop()
            serving.join(3)


if __name__ == "__main__":
    main()

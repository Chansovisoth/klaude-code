"""First-paint/theme/auth startup checks with a real isolated host and Chrome.

Delays real asset/auth/snapshot responses to expose flashes deterministically.
No user profile, model requests, new dependencies or production data are used.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import websockets
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.webui_control_smoke import Tab  # noqa: E402
from tests.unit.test_webhost import _app  # noqa: E402

OUT = Path("/tmp/klaude-startup-preview")


async def verify(host, root, gates, failures):
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    profile = root / "chrome"
    process = subprocess.Popen(
        [
            chrome,
            "--no-sandbox",
            "--disable-gpu",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    OUT.mkdir(exist_ok=True)

    def hold(path):
        gates[path] = (threading.Event(), threading.Event())

    def release(path):
        gates.pop(path)[1].set()

    async def entered(path):
        for _ in range(100):
            if gates[path][0].is_set():
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"No request to delayed {path}")

    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(0.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=8_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Network.enable")
            await tab.command(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
              window.startupLeaks=[];
              function inspectStartup(){
                const shell=document.querySelector('.shell');
                if(shell && document.documentElement?.dataset.startup==='loading' &&
                   (getComputedStyle(shell).visibility!=='hidden' || !shell.inert))
                  startupLeaks.push('shell exposed before readiness');
                if(document.documentElement?.dataset.startup!=='ready')
                  requestAnimationFrame(inspectStartup);
              }
              requestAnimationFrame(inspectStartup);
            """
                },
            )

            async def loading():
                await tab.wait(
                    "!!document.querySelector('#app-startup') && !!document.styleSheets.length"
                )
                assert await tab.js("""(() => {
                  const shell=document.querySelector('.shell');
                  const screen=document.querySelector('#app-startup');
                  return document.documentElement?.dataset.startup==='loading' && shell.inert &&
                    shell.getAttribute('aria-hidden')==='true' &&
                    getComputedStyle(shell).visibility==='hidden' &&
                    !screen.hidden && getComputedStyle(screen).opacity==='1' &&
                    document.querySelector('.layout').hidden &&
                    document.querySelector('.startup-progress')
                      .getAttribute('role')==='progressbar' &&
                    !document.querySelector('.startup-progress').hasAttribute('aria-valuenow') &&
                    !!document.querySelector('.startup-progress > .material-loading svg path') &&
                    !document.querySelector('#startup-wave') &&
                    document.documentElement.scrollWidth<=innerWidth && !startupLeaks.length;
                })()""")

            async def ready(signed_in=False):
                await tab.wait(
                    "document.documentElement?.dataset.startup==='ready' && "
                    "document.querySelector('#app-startup').hidden"
                )
                assert await tab.js(
                    "!document.querySelector('.shell').inert && !startupLeaks.length && "
                    "!document.querySelector('.startup-progress').children.length"
                )
                if signed_in:
                    await tab.wait(
                        "authenticated && latest?.session_id && sessionsLoaded && pollTimer!==null"
                    )
                    assert await tab.js("byId('local-access').hidden && !layout.hidden")
                else:
                    assert await tab.js(
                        "!byId('local-access').hidden && layout.hidden && layout.inert"
                    )

            async def screenshot(name):
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (OUT / name).write_bytes(base64.b64decode(shot["data"]))

            # Establish the origin, then exercise saved preferences before app.js
            # executes. System dark, corrupt JSON and denied storage are included.
            await tab.command("Page.navigate", {"url": host.origin})
            await ready()
            cases = [
                (320, "dark", "ocean", False, "expressive", False),
                (390, "light", "peach", True, "expressive", False),
                (768, "system", "slate", False, "expressive", True),
                (1440, "dark", "lavender", False, "expressive", False),
                (390, "dark", "sage", False, "classic", False),
            ]
            for width, theme, palette, reduced, loading_style, system_reduced in cases:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 820,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                await tab.command(
                    "Emulation.setEmulatedMedia",
                    {
                        "features": [
                            {"name": "prefers-color-scheme", "value": "dark"},
                            {"name": "prefers-reduced-motion",
                             "value": "reduce" if system_reduced else "no-preference"},
                        ]
                    },
                )
                saved = {
                    "version": 1,
                    "theme": theme,
                    "palette": palette,
                    "reduced": reduced,
                    "chatDensity": "compact",
                    "loadingStyle": loading_style,
                }
                await tab.js(
                    "localStorage.setItem('klaude.webui.appearance.v1',"
                    + json.dumps(json.dumps(saved))
                    + ")"
                )
                hold("/app.js")
                hold("/api/v1/auth/method")
                await tab.command("Page.reload", {"ignoreCache": True})
                await entered("/app.js")
                await loading()
                assert await tab.js(
                    f"document.documentElement.dataset.theme==={json.dumps(theme)} && "
                    f"document.documentElement.dataset.palette==={json.dumps(palette)}"
                )
                before = await tab.js("getComputedStyle(document.documentElement).backgroundColor")
                assert before not in ("rgba(0, 0, 0, 0)", "rgb(255, 255, 255)"), before
                await tab.command(
                    "Input.dispatchKeyEvent",
                    {"type": "keyDown", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
                )
                await tab.command(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
                )
                assert await tab.js("!document.activeElement.closest('.shell')")
                await tab.js(
                    "window.startupIndicator="
                    "document.querySelector('.startup-progress > .material-loading');"
                    "window.startupRenderer=MaterialLoading"
                )
                motion = (
                    "getComputedStyle(startupIndicator,'::after').transform"
                    if loading_style == "classic" else
                    "startupIndicator.querySelector('g').getAttribute('transform')"
                )
                first = await tab.js(motion)
                await asyncio.sleep(0.2)
                second = await tab.js(motion)
                assert (first == second) == (reduced or system_reduced), (
                    reduced, system_reduced, loading_style, first, second
                )
                if width == 1440:
                    path = await tab.js("startupIndicator.querySelector('path').getAttribute('d')")
                    await asyncio.sleep(.9)
                    assert path != await tab.js(
                        "startupIndicator.querySelector('path').getAttribute('d')"
                    ), "The early indicator must morph before app.js is released"
                await screenshot(f"startup-{theme}-{palette}-{width}.png")
                release("/app.js")
                await entered("/api/v1/auth/method")
                await loading()
                assert await tab.js(
                    "MaterialLoading===startupRenderer && "
                    "document.querySelector('.startup-progress > .material-loading')"
                    "===startupIndicator"
                ), "The deferred app must retain the early renderer and indicator"
                assert (
                    await tab.js("getComputedStyle(document.documentElement).backgroundColor")
                    == before
                )
                release("/api/v1/auth/method")
                await ready()
                assert (
                    await tab.js("getComputedStyle(document.documentElement).backgroundColor")
                    == before
                )
            print(
                "Pre-paint themes, delayed scripts/auth, keyboard isolation, "
                "shared early Material loader/reduced motion and logged-out refresh passed",
                flush=True,
            )

            # Sign in using the existing real account endpoint, then delay the
            # first session snapshot on refresh. Keep the cover until it exists.
            await tab.js(
                "byId('login-password').value="
                + json.dumps(host.accounts.initial_password())
                + ";byId('account-login').requestSubmit()"
            )
            await ready(True)
            link = await tab.js(
                "location.origin+'/?'+new URLSearchParams({session:latest.session_id,"
                "message:latest.messages.find(m=>m.role==='assistant').id})"
            )
            hold("/api/v1/session")
            await tab.command("Page.navigate", {"url": link})
            await entered("/api/v1/session")
            await tab.wait("typeof authenticated!=='undefined' && authenticated")
            assert await tab.js(
                "document.documentElement?.dataset.startup==='loading' && "
                "getComputedStyle(document.querySelector('.shell')).visibility==='hidden'"
            )
            release("/api/v1/session")
            await ready(True)
            assert await tab.js("messages.textContent.includes('Saved fixture reply')")
            assert await tab.js(
                "document.activeElement.dataset.id==="
                "latest.messages.find(m=>m.role==='assistant').id"
            ), "Shared message focus must follow startup"
            await screenshot("ready-signed-in.png")
            await tab.js("byId('logout').click()")
            await tab.wait("!authenticated && !byId('local-access').hidden")
            await tab.command("Page.reload", {"ignoreCache": True})
            await ready()
            print(
                "Authenticated refresh, initial snapshot gate, saved chat and logout/reload passed",
                flush=True,
            )

            await tab.js("localStorage.setItem('klaude.webui.appearance.v1','{broken')")
            await tab.command("Page.reload", {"ignoreCache": True})
            await ready()
            assert await tab.js(
                "document.documentElement.dataset.theme==='system' && "
                "document.documentElement.dataset.palette==='lavender'"
            )
            blocked_storage = await tab.command(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": "Object.defineProperty(window,'localStorage',"
                    "{get(){throw new DOMException('Blocked','SecurityError')}})"
                },
            )
            await tab.command("Page.reload", {"ignoreCache": True})
            await ready()
            assert await tab.js("document.documentElement.dataset.theme==='system'")
            await tab.command(
                "Page.removeScriptToEvaluateOnNewDocument",
                {"identifier": blocked_storage["identifier"]},
            )
            failures.add("/api/v1/auth/method")
            await tab.command("Page.reload", {"ignoreCache": True})
            await ready()
            assert await tab.js("byId('access-status').textContent.includes('Fixture unavailable')")
            failures.clear()
            await tab.command("Page.reload", {"ignoreCache": True})
            await ready()

            # The early public entry still offers Reload if app.js cannot load.
            await tab.command(
                "Network.setBlockedURLs",
                {
                    "urls": [
                        "*/app.js",
                        "*/library.js",
                        "*/management.js",
                        "*/media.js",
                        "*/attachments.js",
                    ]
                },
            )
            await tab.command("Page.reload", {"ignoreCache": True})
            await tab.wait(
                "!!document.querySelector('#startup-retry') && "
                "!document.querySelector('#startup-retry').hidden"
            )
            await loading()
            await tab.command("Network.setBlockedURLs", {"urls": []})
            await tab.js("document.querySelector('#startup-retry').click()")
            await ready()
            assert not tab.errors, tab.errors
            print(
                "Corrupt/blocked storage, connection failure, missing app recovery, "
                "zero browser exceptions passed",
                flush=True,
            )
    finally:
        for _, gate in gates.values():
            gate.set()
        process.terminate()
        process.wait(timeout=5)


def main():
    with tempfile.TemporaryDirectory(prefix="klaude-startup-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(cfg.data_dir)
        app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        app.memory.log_turn(app.session_id, "user", "Saved fixture question")
        app.memory.log_turn(app.session_id, "assistant", "Saved fixture reply")
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts)
        host.local_models = lambda: []
        gates, failures = {}, set()
        original_handler = host.http.RequestHandlerClass

        class DelayedHandler(original_handler):
            def do_GET(self):
                path = urlsplit(self.path).path
                if path in failures:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE, "fixture_unavailable", "Fixture unavailable"
                    )
                    return
                gate = gates.get(path)
                if gate:
                    gate[0].set()
                    gate[1].wait(20)
                super().do_GET()

        host.http.RequestHandlerClass = DelayedHandler
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, gates, failures), 100))
        finally:
            host.stop()
            thread.join(3)


if __name__ == "__main__":
    main()

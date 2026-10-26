"""Isolated Downloads observation walkthrough; no real model weights or inference."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_core.ollama_activity import track_transfer
from klaude_core.ollama_manager import endpoint
from webui_control_smoke import Tab
from webui_model_store_smoke import Native
from webui_model_store_smoke import main as fixture_main


async def verify(host, root):
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell")))
    profile = root / "activity-chrome"
    process = subprocess.Popen(
        [chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
         f"--user-data-dir={profile}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    captures = Path("/tmp/klaude-model-activity-evidence")
    captures.mkdir(exist_ok=True)
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(0.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait("document.documentElement?.dataset.access==='locked'")
            await tab.js("byId('login-username').value='admin';byId('login-password').value="
                         + json.dumps(host.accounts.initial_password())
                         + ";byId('account-login').requestSubmit()")
            await tab.wait("typeof latest!=='undefined' && authenticated && "
                           "document.documentElement.dataset.startup==='ready'")
            await tab.js("showView('models')")
            await tab.wait("byId('store-endpoint').options.length===1")
            await tab.click("[data-section=downloads]")
            await tab.wait("byId('store-content').textContent.includes('No downloads yet')")
            cfg = host.library.cfg
            connection, _ = endpoint(cfg, "default-ollama")
            blobs = root / "fixture-blobs"
            blobs.mkdir()
            partial = blobs / ("sha256-" + "f" * 64 + "-partial")
            observer = host.library._model_activity
            observer._store = (blobs, url_port(connection.base_url))
            observer._discovered = time.monotonic()
            with partial.open("wb") as handle:
                handle.truncate(10**10)
            await tab.wait("byId('store-content').textContent.includes('Ollama transfer')")
            assert await tab.js("!byId('store-content').querySelector('progress') && "
                                "!byId('store-content')"
                                ".querySelector('button:not([data-download-action=info])') && "
                                "!byId('store-content').classList.contains('is-empty')")
            assert Native.pulls == 0
            with (
                track_transfer(cfg, connection, "outside-klaude:1b", lambda _: None) as report,
                track_transfer(cfg, connection,
                    "hf.co/mudler/locate-anything.cpp-gguf:locate-anything-q4_k.gguf",
                    lambda _: None) as long_report,
            ):
                report({"stage": "Downloading file", "completed": 42, "total": 100})
                long_report({"stage": "Downloading file", "completed": 42, "total": 100})
                await tab.wait("byId('store-content').textContent.includes('outside-klaude:1b')")
                assert await tab.js("!byId('store-content').textContent.includes('mudler')")
                await tab.wait("byId('store-content').querySelector('[role=progressbar]')"
                               "?.getAttribute('aria-valuenow')==='42'")
                assert await tab.js(
                    "byId('store-content').querySelector('.model-download-progress')"
                    ".dataset.thickness==='thin'")
                assert await tab.js(
                    "!byId('store-content').querySelector('button:not([data-download-action=info])')")
                await tab.click('[data-download-action=info]')
                await tab.wait("byId('store-download-info').open")
                assert await tab.js("byId('store-download-info-note').textContent"
                                    ".includes('another Klaude client')")
                origin = await tab.js("byId('store-content')"
                                      ".querySelector('[data-download-action=info]').id")
                await asyncio.sleep(2.2)
                assert await tab.js("document.activeElement===byId('store-download-info-close')")
                await tab.command('Input.dispatchKeyEvent', {
                    'type':'keyDown', 'key':'Escape', 'code':'Escape', 'windowsVirtualKeyCode':27})
                await tab.wait("!byId('store-download-info').open")
                await tab.wait("document.activeElement.id===" + json.dumps(origin))
                await asyncio.sleep(2.2)
                assert await tab.js("document.activeElement.id===" + json.dumps(origin))
                await tab.click('[data-download-action=info]')
                await tab.wait("byId('store-download-info').open")
                for event in ('mousePressed', 'mouseReleased'):
                    await tab.command('Input.dispatchMouseEvent', {
                        'type':event, 'x':2, 'y':2, 'button':'left', 'clickCount':1})
                await tab.wait("!byId('store-download-info').open")
                for style in ["material", "material-static", "classic", "expressive"]:
                    await tab.js("applyAppearance({...appearance,loadingBarStyle:"
                                 + json.dumps(style) + "});ModelStoreUI.render()")
                    await tab.wait("byId('store-content').querySelector('[role=progressbar]')"
                                   "?.getAttribute('aria-valuenow')==='42'")
                    await asyncio.sleep(0.25)
                    assert await tab.js(
                        "byId('store-content').querySelector('[role=progressbar]')"
                        ".getAttribute('aria-valuenow')==='42'"), style
                await tab.js("applyAppearance({...appearance,loadingBarStyle:'material'});"
                             "ModelStoreUI.render()")
                for width in [320, 390, 1440]:
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": 844, "deviceScaleFactor": 1, "mobile": False})
                    for theme in ["light", "dark"]:
                        await tab.js(f"applyAppearance({{...appearance,theme:'{theme}'}})")
                        assert await tab.js("document.documentElement.scrollWidth<=innerWidth")
                        shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (captures / f"downloads-{width}-{theme}.png").write_bytes(
                            base64.b64decode(shot["data"]))
                await tab.command("Page.reload")
                await tab.wait("typeof authenticated!=='undefined' && authenticated && "
                               "byId('store-content').textContent.includes('outside-klaude:1b')")
            partial.unlink()
            await tab.wait("byId('store-content').textContent.includes('No downloads yet')")
            assert Native.pulls == 0
            async def download(tag):
                await tab.click("[data-section=discover]")
                await tab.click("#store-filters-open")
                await tab.wait("!byId('store-download-open').disabled")
                await tab.click("#store-download-open")
                await tab.js("byId('store-download-tag').value=" + json.dumps(tag)
                             + ";byId('store-download-form').requestSubmit()")
                await tab.wait("reviewDialog.open")
                await tab.click("#domain-review-confirm")

            Native.pull_error = "unexpected EOF private-provider-diagnostic"
            await download("failed-fixture:1b")
            await tab.wait("byId('store-content').textContent.includes('Failed')")
            assert await tab.js("!byId('store-content').querySelector('p') && "
                                "!byId('store-content').textContent.includes('transfer;')")
            await tab.click('[data-download-action=info]')
            await tab.wait("byId('store-download-info').open")
            assert await tab.js("byId('store-download-info-note').textContent.includes('transfer')")
            await tab.click('#store-download-info-close')
            await tab.click('[data-download-action=remove]')
            await tab.wait("byId('store-content').textContent.includes('No downloads yet')")
            await tab.command("Page.reload")
            await tab.wait("typeof authenticated!=='undefined' && authenticated && "
                           "byId('store-content').textContent.includes('No downloads yet')")
            Native.pull_error = ""
            Native.slow = True
            await download("stopped-fixture:1b")
            await tab.wait("byId('store-content').querySelector('[role=progressbar]')"
                           "?.getAttribute('aria-valuenow')==='42'")
            await tab.click('[data-download-action=stop]')
            await tab.wait("byId('store-content').textContent.includes('Needs check') && "
                           "Boolean(byId('store-content').querySelector('[data-download-action=info]'))")
            assert not host.library._active
            await tab.click('[data-download-action=info]')
            await tab.wait("byId('store-download-info').open && "
                           "!byId('store-download-info-remove').hidden")
            await tab.click('#store-download-info-remove')
            await tab.wait(
                "Boolean(byId('store-content').querySelector('.model-dismissed-notice'))")
            await tab.click('#store-download-info-close')
            assert await tab.js("!byId('store-content').querySelector('p') && "
                                "byId('store-content').textContent.includes('Needs check')")
            assert host.library.model_busy()
            await tab.command("Page.reload")
            await tab.wait("typeof authenticated!=='undefined' && authenticated && "
                           "Boolean(byId('store-content').querySelector('.model-dismissed-notice'))")
            assert Native.pulls == 2
            await tab.click('[data-download-action=info]')
            await tab.wait("byId('store-download-info').open")
            await tab.js("byId('logout').click()")
            await tab.wait("!authenticated")
            assert await tab.js("!byId('store-download-info').open && "
                                "byId('store-download-info-name').textContent===''")
            assert await tab.js("!byId('store-content').textContent.includes('outside-klaude')")
            assert not tab.errors, tab.errors
            print(json.dumps({"downloads_observation": "passed", "widths": [320, 390, 1440],
                              "themes": ["light", "dark"], "fixture_pulls": Native.pulls,
                              "controls": "failed Remove; active Stop; unknown recovery retained",
                              "bar_styles": 4, "console_errors": len(tab.errors),
                              "screenshots": str(captures)}))
    finally:
        Native.slow = False
        Native.pull_error = ""
        process.terminate()
        process.wait(timeout=5)


def url_port(url):
    from urllib.parse import urlsplit

    return urlsplit(url).port or 80


if __name__ == "__main__":
    fixture_main(verify, admin_lan=True)

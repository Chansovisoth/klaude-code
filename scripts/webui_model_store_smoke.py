"""Isolated Chrome Model Store and Image Studio walkthrough; no real weights or inference."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
from tests.unit.test_image_generation import enable, generation_lab  # noqa: E402
from tests.unit.test_webhost import _app  # noqa: E402


class Native(BaseHTTPRequestHandler):
    models: list[dict] = []
    pulls = 0
    offline = False
    gguf_files = [{"rfilename": "small-Q4_K_M.gguf", "size": 1024}]
    detail_offline = False
    pull_error = ""
    slow = False
    pull_closed = threading.Event()

    def log_message(self, *_):
        pass

    def reply(self, value, status=200):
        data = json.dumps(value).encode()
        self.send_response(503 if self.offline else status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/models":
            self.reply(
                [
                    {
                        "id": "fixture/Small-GGUF",
                        "downloads": 1234,
                        "lastModified": "2026-10-25T00:00:00Z",
                    }
                ]
            )
            return
        if path.startswith("/api/models/fixture/"):
            self.reply(
                {
                    "id": path.removeprefix("/api/models/"),
                    "cardData": {"license": "apache-2.0"},
                    "siblings": self.gguf_files,
                },
                status=503 if self.detail_offline else 200,
            )
            return
        self.reply(
            {"version": "fixture-1"}
            if self.path == "/api/version"
            else {"models": self.models if self.path == "/api/tags" else []}
        )

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/show":
            self.reply({"capabilities": ["completion", "tools", "thinking"]})
            return
        assert self.path.split("?", 1)[0] == "/api/pull"
        Native.pulls += 1
        self.send_response(200)
        self.end_headers()
        if Native.pull_error:
            self.wfile.write(json.dumps({"error": Native.pull_error}).encode() + b"\n")
            return
        try:
            self.wfile.write(b'{"status":"pulling manifest"}\n')
            self.wfile.flush()
            while Native.slow:
                self.wfile.write(
                    b'{"status":"pulling file","digest":"test","completed":42,"total":100}\n'
                )
                self.wfile.flush()
                time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError):
            Native.pull_closed.set()
            return
        Native.models.append(
            {
                "name": body["model"],
                "digest": "a" * 64,
                "size": 2500000000,
                "details": {"parameter_size": "4B", "quantization_level": "Q4_K_M"},
            }
        )
        self.wfile.write(b'{"status":"success"}\n')


async def verify(host, root):
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
    captures = Path("/tmp/klaude-model-store-evidence")
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

            async def check_store_tabs(selected):
                await tab.wait("byId('store-sections').hasAttribute('data-segment-layout')")
                await tab.js(
                    "Promise.all(byId('store-sections').getAnimations({subtree:true})"
                    ".filter(a=>a.effect.getTiming().iterations!==Infinity)"
                    ".map(a=>a.finished.catch(()=>{})))"
                )
                measured = await tab.js("""(() => {
                  const nav=byId('store-sections'), buttons=[...nav.children];
                  const styles=buttons.map(b=>getComputedStyle(b));
                  const library=[...byId('library-sections').children];
                  return {shared:nav.classList.contains('section-chips'),
                    outer:parseFloat(styles[0].getPropertyValue('--segment-outer-radius')),
                    inner:(parseFloat(styles[0].getPropertyValue('--round-xs'))+
                      parseFloat(styles[0].getPropertyValue('--round-sm')))/2,
                    activeColor:getComputedStyle(library.find(b=>b.ariaPressed==='true'))
                      .backgroundColor,
                    idleColor:getComputedStyle(library.find(b=>b.ariaPressed==='false'))
                      .backgroundColor,
                    buttons:buttons.map((b,i)=>({selected:b.ariaSelected==='true',
                      start:b.hasAttribute('data-segment-start'),
                      end:b.hasAttribute('data-segment-end'),height:b.offsetHeight,
                      color:styles[i].backgroundColor,
                      left:parseFloat(styles[i].borderTopLeftRadius),
                      right:parseFloat(styles[i].borderTopRightRadius)}))};
                })()""")
                assert measured["shared"]
                for i, item in enumerate(measured["buttons"]):
                    active = i == selected
                    assert item["selected"] == active
                    assert item["start"] == (i == 0) and item["end"] == (i == 2)
                    left = item["height"] / 2 if active else measured[
                        "outer" if i == 0 else "inner"]
                    right = item["height"] / 2 if active else measured[
                        "outer" if i == 2 else "inner"]
                    assert abs(item["left"] - left) < 0.2, measured
                    assert abs(item["right"] - right) < 0.2, measured
                    assert item["color"] == measured["activeColor" if active else "idleColor"]

            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            if host.accounts:
                await tab.wait("document.documentElement?.dataset.access === 'locked'")
                await tab.js(
                    "byId('login-username').value='admin'; byId('login-password').value="
                    + json.dumps(host.accounts.initial_password())
                    + "; byId('account-login').requestSubmit()"
                )
            await tab.wait(
                "typeof latest !== 'undefined' && authenticated && latest && "
                "document.documentElement.dataset.startup==='ready'"
            )
            await tab.js("showView('store')")
            await tab.wait("byId('store-content').querySelectorAll('.store-feature').length===3")
            await tab.wait("byId('store-endpoint').options.length===1")
            await tab.js(
                "window.storeCapability=latest.model_store; delete latest.model_store; "
                "ModelStoreUI.render()"
            )
            assert await tab.js(
                "byId('store-status').textContent.includes('Restart') && "
                "!byId('store-content').textContent.includes('Loading') && "
                "byId('store-sections').querySelector('[data-section=installed]')"
                ".disabled && "
                "byId('store-content').textContent.includes('Open model settings')"
            )
            await tab.js("latest.model_store=window.storeCapability; ModelStoreUI.render()")
            await tab.click("[data-section=discover]")
            for width, height in [
                (320, 568),
                (360, 740),
                (390, 844),
                (430, 932),
                (768, 1024),
                (1440, 900),
            ]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                )
                for theme in ["light", "dark"]:
                    await tab.js(f"applyAppearance({{...appearance, theme:'{theme}'}})")
                    await tab.js(
                        "Promise.all(byId('store-view').getAnimations({subtree:true})"
                        ".filter(a=>a.effect.getTiming().iterations!==Infinity)"
                        ".map(a=>a.finished.catch(()=>{})))"
                    )
                    assert await tab.js("document.documentElement.scrollWidth<=innerWidth"), width
                    await check_store_tabs(0)
                    assert await tab.js(
                        "[...byId('store-sections').children].every(b => "
                        "b.getBoundingClientRect().height>=43.9)"
                    ), await tab.js(
                        "[...byId('store-sections').children].map(b=>"
                        "({text:b.textContent,height:b.getBoundingClientRect().height,"
                        "layoutHeight:b.offsetHeight}))"
                    )
                    assert await tab.js("""(() => {
                      const tabs=[...byId('store-sections').children]
                        .map(b=>b.getBoundingClientRect());
                      const view=byId('store-view').getBoundingClientRect();
                      const art=byId('store-content').querySelector('.store-feature')
                        .getBoundingClientRect();
                      return tabs.length===3 &&
                        Math.max(...tabs.map(b=>b.width))-Math.min(...tabs.map(b=>b.width))<1 &&
                        tabs[2].right<=view.right && art.top<innerHeight-120 &&
                        !byId('store-view').querySelector('.models-current') &&
                        !byId('store-endpoint-label').getClientRects().length &&
                        byId('store-content').querySelectorAll('.store-cover-art').length===3;
                    })()"""), (width, theme, "V2 hierarchy")
                    result = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (captures / f"store-{width}-{theme}.png").write_bytes(
                        base64.b64decode(result["data"])
                    )
            await tab.click("#store-filters-open")
            await tab.wait("byId('store-filters-dialog').open")
            await tab.command(
                "Input.dispatchKeyEvent",
                {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
            )
            await tab.wait(
                "!byId('store-filters-dialog').open && "
                "document.activeElement===byId('store-filters-open')"
            )
            await tab.js("byId('store-tab-discover').focus()")
            await tab.command(
                "Input.dispatchKeyEvent",
                {"type": "keyDown", "key": "End", "code": "End", "windowsVirtualKeyCode": 35},
            )
            assert await tab.js(
                "byId('store-tab-downloads').getAttribute('aria-selected')==='true'"
            )
            await check_store_tabs(2)
            await tab.click("[data-section=downloads]")
            assert await tab.js(
                "byId('store-content').classList.contains('is-empty') && "
                "byId('store-content').textContent.includes('No downloads yet') && "
                "!byId('store-search-row').getClientRects().length && "
                "!byId('store-endpoint-label').getClientRects().length"
            )
            assert await tab.js("""(() => {
              const box=byId('store-content').getBoundingClientRect();
              const message=byId('store-content').querySelector('.collection-empty')
                .getBoundingClientRect();
              return Math.abs((message.top+message.bottom-box.top-box.bottom)/2)<90;
            })()""")
            shot = await tab.command("Page.captureScreenshot", {"format": "png"})
            (captures / "downloads-empty.png").write_bytes(base64.b64decode(shot["data"]))
            await tab.click("[data-section=discover]")
            await tab.click("#store-refresh")
            await tab.click("#store-filters-open")
            await tab.wait("!byId('store-download-open').disabled")
            await tab.click("#store-download-open")
            await tab.js(
                "byId('store-download-tag').value='manual:tag'; "
                "byId('store-download-form').requestSubmit()"
            )
            await tab.wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-summary').textContent.includes('manual:tag')")
            await tab.click("#domain-review-cancel")
            assert Native.pulls == 0
            await tab.click("[data-section=discover]")
            await tab.click(".store-category[data-category=Coding]")
            assert await tab.js("byId('store-content').querySelectorAll('.store-row').length===1")
            await tab.click(".store-row")
            await tab.wait("!byId('store-detail').hidden")
            assert await tab.js("location.search.includes('models-detail=qwen2.5-coder')")
            await tab.command("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27,
            })
            await tab.command("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27,
            })
            await tab.wait("byId('store-detail').hidden")
            await tab.wait("document.activeElement.dataset.storeModel==='qwen2.5-coder'")
            await tab.js("history.forward()")
            await tab.wait("!byId('store-detail').hidden")
            await tab.click("#store-detail-back")
            await tab.wait("byId('store-detail').hidden")
            await tab.click("[data-section=discover]")
            await tab.click("#store-filters-open")
            await tab.js(
                "byId('store-capability').value='vision';"
                "byId('store-capability').dispatchEvent(new Event('change'))"
            )
            assert await tab.js(
                "byId('store-content').querySelectorAll('.store-row').length===1 && "
                "byId('store-content').textContent.includes('Gemma 3') && "
                "location.search.includes('models-capability=vision')"
            )
            await tab.js(
                "byId('store-capability').value='all';"
                "byId('store-capability').dispatchEvent(new Event('change'))"
            )
            await tab.click("#store-filters-close")
            await tab.click(".store-feature[data-store-model=qwen3]")
            await tab.wait("!byId('store-detail').hidden")
            await tab.js(
                "[...byId('store-variant-list').querySelectorAll('input')]"
                ".find(input=>input.value==='qwen3:4b').click()"
            )
            await tab.wait(
                "[...byId('store-detail-body').querySelectorAll('button')].some(b=>b"
                ".textContent==='Install'&&!b.disabled)"
            )
            await tab.js(
                "[...byId('store-detail-body').querySelectorAll('button')].find(b=>b"
                ".textContent==='Install').click()"
            )
            await tab.wait("reviewDialog.open")
            assert await tab.js(
                "document.activeElement===byId('domain-review-cancel') && "
                "byId('domain-review-summary').textContent.includes('qwen3:4b')"
            )
            await tab.click("#domain-review-confirm")
            await tab.wait("byId('store-content').textContent.includes('Complete')")
            assert Native.pulls == 1
            await tab.command("Page.reload")
            await tab.wait(
                "typeof authenticated !== 'undefined' && authenticated && "
                "document.documentElement.dataset.startup==='ready' && "
                "byId('store-content').textContent.includes('Complete')"
            )
            assert host.application.agent.model != "qwen3:4b"
            await tab.click("[data-section=installed]")
            await tab.wait("byId('store-content').textContent.includes('qwen3:4b')")
            await check_store_tabs(1)
            original_models = Native.models[:]
            Native.models.extend(
                {
                    "name": f"fixture-{i:03}:latest",
                    "digest": f"{i + 2:064x}",
                    "size": 1000,
                    "details": {},
                }
                for i in range(140)
            )
            await tab.click("#store-refresh")
            await tab.wait(
                "!byId('store-installed-pages').hidden && "
                "byId('store-installed-numbers').dataset.last==='8'"
            )
            assert await tab.js(
                "byId('store-installed-previous').disabled && "
                "!byId('store-installed-next').disabled && "
                "byId('store-installed-previous').querySelector('svg') !== null && "
                "byId('store-content').querySelectorAll('.store-row').length===20"
            )
            await tab.click("#store-installed-next")
            assert await tab.js("byId('store-installed-page').textContent==='Page 2 of 8'")
            await tab.js("byId('store-installed-numbers').lastElementChild.focus()")
            await tab.click('#store-installed-numbers [data-page="8"]')
            assert await tab.js(
                "byId('store-installed-next').disabled && "
                "byId('store-content').querySelectorAll('.store-row')"
                ".length===1 && "
                "document.activeElement.dataset.page==='8'"
            ), await tab.js(
                "({page:byId('store-installed-page').textContent, "
                "next:byId('store-installed-next').disabled, "
                "rows:byId('store-content').querySelectorAll('.store-row').length, "
                "active:document.activeElement.outerHTML})"
            )
            for width in [320, 390, 768, 1440]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": 844, "deviceScaleFactor": 1, "mobile": False},
                )
                assert await tab.js(
                    "document.documentElement.scrollWidth<=innerWidth && "
                    "getComputedStyle(byId('store-installed-next')).width === "
                    "getComputedStyle(byId('models-next')).width"
                )
            await tab.js(
                "byId('store-query').value='fixture-139'; "
                "byId('store-query').dispatchEvent(new Event('input'))"
            )
            assert await tab.js(
                "byId('store-installed-pages').hidden && "
                "byId('store-content').querySelectorAll('.store-row').length===1"
            )
            Native.models = original_models
            await tab.js(
                "byId('store-query').value=''; "
                "byId('store-query').dispatchEvent(new Event('input'))"
            )
            await tab.click("#store-refresh")
            await tab.wait("byId('store-content').querySelectorAll('.store-row').length===1")
            Native.offline = True
            await tab.click("#store-refresh")
            await tab.wait("byId('store-content').textContent.includes('Cached')")
            assert await tab.js("byId('store-content').textContent.includes('qwen3:4b')")
            Native.offline = False
            await tab.click("[data-section=discover]")
            await tab.js(
                "[...byId('store-content').querySelectorAll('button')]"
                ".find(b=>b.textContent==='See all').click()"
            )
            await tab.wait("byId('store-content').textContent.includes('1,234 Hub downloads')")
            await tab.click(".store-row")
            await tab.wait("byId('store-variant-list')?.textContent.includes('small-Q4_K_M.gguf')")
            assert Native.pulls == 1
            await tab.click("#store-detail-back")
            await tab.wait("byId('store-detail').hidden")
            await tab.command(
                "Emulation.setEmulatedMedia",
                {
                    "features": [
                        {"name": "prefers-reduced-motion", "value": "reduce"},
                        {"name": "forced-colors", "value": "active"},
                    ]
                },
            )
            await tab.click("[data-section=discover]")
            assert await tab.js("document.documentElement.scrollWidth<=innerWidth")
            await tab.command("Emulation.setEmulatedMedia", {"features": []})
            await tab.js("showView('library')")
            await tab.click("[data-section=outputs]")
            await tab.wait("!byId('image-add').disabled")
            await tab.click("#image-add")
            await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
            for width, height in [
                (320, 568),
                (360, 740),
                (390, 844),
                (430, 932),
                (768, 1024),
                (1440, 900),
            ]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                )
                await tab.js("byId('image-advanced').open=true")
                await asyncio.sleep(0.1)
                assert await tab.js(
                    "byId('image-generate-panel')"
                    ".scrollWidth <= byId('image-generate-panel').clientWidth && "
                    "document.documentElement.scrollWidth<=innerWidth"
                ), width
                result = await tab.command("Page.captureScreenshot", {"format": "png"})
                (captures / f"studio-{width}.png").write_bytes(base64.b64decode(result["data"]))
            await tab.js("byId('image-ratio-quick').querySelector('[value=\"3:2\"]').click()")
            assert await tab.js(
                "byId('image-width').value==='768' && byId('image-height').value==='512'"
            )
            await tab.js(
                "byId('image-prompt').value='Watercolor mountain';byId('image-seed').value='42'"
            )
            await tab.click("#generation-tab-research")
            await tab.click("#generation-tab-image")
            assert await tab.js(
                "byId('image-prompt').value==='Watercolor mountain' "
                "&& byId('image-seed').value==='42'"
            )
            # Fixture output is a verified 512-square PNG.
            await tab.click("#image-reset-options")
            await tab.js("byId('image-seed').value='42';byId('image-generate').requestSubmit()")
            await tab.wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-summary').textContent.includes('seed 42')")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "byId('image-jobs').textContent.includes('Completed') "
                "&& !BrowserManagement.hasPending()"
            )
            await tab.click("#image-add")
            assert await tab.js("byId('image-prompt').value==='Watercolor mountain'")
            await tab.js(
                "[...byId('image-jobs').querySelectorAll('button')].find(b=>b"
                ".textContent==='Generate again').click()"
            )
            assert await tab.js("byId('image-seed').value==='42'")
            await tab.js("byId('image-jobs').querySelector('details').open=true")
            await tab.click("#image-jobs button")
            await tab.wait("byId('artifact-detail').open")
            await tab.click("#artifact-close")
            await tab.click("#logout")
            await tab.wait("!authenticated")
            assert await tab.js(
                "!byId('image-prompt').value && !byId('store-detail-body').textContent"
            )
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "model_store": "browse/detail/download/history/offline passed",
                        "studio": "service, seed, generation, output and draft cleanup passed",
                        "widths": [320, 360, 390, 430, 768, 1440],
                        "console_errors": 0,
                        "screenshots": str(captures),
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


def main(verify_fn=verify, *, admin_lan=False):
    with tempfile.TemporaryDirectory(prefix="klaude-store-smoke-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config()
        native = ThreadingHTTPServer(("127.0.0.1", 0), Native)
        threading.Thread(target=native.serve_forever, daemon=True).start()
        cfg.ollama_url = f"http://127.0.0.1:{native.server_port}"
        cfg.huggingface_base_url = cfg.ollama_url
        cfg.config_dir.mkdir(parents=True)
        (cfg.config_dir / "config.toml").write_text(f'[services]\nollama_url="{cfg.ollama_url}"\n')
        fixture = generation_lab.__wrapped__(root)
        lab = next(fixture)
        enable(lab)
        app = _app(cfg.data_dir)
        app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        service = LibraryManagement(cfg, root)
        accounts = None
        if admin_lan:
            from klaude_webhost.accounts import AccountStore

            accounts = AccountStore(cfg.config_dir)
            accounts.initialize()
        host = LocalWebHost(app, library=service, accounts=accounts)
        # Exercise LAN authorization on the isolated fixture listener; no real
        # private-network binding or production credential is needed.
        host.http.host_lan = admin_lan
        host.local_models = lambda: []
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(verify_fn(host, root))
        finally:
            host.stop()
            thread.join(timeout=3)
            fixture.close()
            native.shutdown()
            native.server_close()


if __name__ == "__main__":
    main(admin_lan=os.environ.get("KLAUDE_TEST_ADMIN_LAN") == "1")

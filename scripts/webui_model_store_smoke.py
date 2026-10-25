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

    def log_message(self, *_):
        pass

    def reply(self, value):
        data = json.dumps(value).encode()
        self.send_response(503 if self.offline else 200)
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
        if path == "/api/models/fixture/Small-GGUF":
            self.reply(
                {
                    "id": "fixture/Small-GGUF",
                    "cardData": {"license": "apache-2.0"},
                    "siblings": [{"rfilename": "small-Q4_K_M.gguf", "size": 1024}],
                }
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
        assert self.path == "/api/pull"
        Native.pulls += 1
        Native.models.append(
            {
                "name": body["model"],
                "digest": "a" * 64,
                "size": 2500000000,
                "details": {"parameter_size": "4B", "quantization_level": "Q4_K_M"},
            }
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"pulling manifest"}\n{"status":"success"}\n')


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
            await tab.js("showView('models')")
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
                "!byId('store-sections').querySelector('[data-section=connections]').disabled"
            )
            await tab.click("[data-section=connections]")
            assert await tab.js("!byId('models-configured').hidden")
            await tab.js("latest.model_store=window.storeCapability; ModelStoreUI.render()")
            await tab.click("[data-section=discover]")
            for width, height in [(320, 568), (390, 844), (768, 1024), (1440, 900)]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                )
                for theme in ["light", "dark"]:
                    await tab.js(f"applyAppearance({{...appearance, theme:'{theme}'}})")
                    await tab.js(
                        "Promise.all(byId('models-view').getAnimations({subtree:true})"
                        ".filter(a=>a.effect.getTiming().iterations!==Infinity)"
                        ".map(a=>a.finished.catch(()=>{})))"
                    )
                    assert await tab.js("document.documentElement.scrollWidth<=innerWidth"), width
                    assert await tab.js(
                        "[...byId('store-sections').children].every(b => "
                        "b.getBoundingClientRect().height>=43.9)"
                    ), await tab.js(
                        "[...byId('store-sections').children].map(b=>"
                        "({text:b.textContent,height:b.getBoundingClientRect().height,"
                        "layoutHeight:b.offsetHeight}))"
                    )
                    result = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (captures / f"store-{width}-{theme}.png").write_bytes(
                        base64.b64decode(result["data"])
                    )
            await tab.click("#models-refresh")
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
            await tab.click("[data-section=categories]")
            await tab.js(
                "[...byId('store-content').querySelectorAll('button')].find(b=>b"
                ".textContent==='Coding').click()"
            )
            assert await tab.js("byId('store-content').querySelectorAll('.store-row').length===1")
            await tab.click(".store-row")
            await tab.wait("byId('store-detail').open")
            assert await tab.js("location.search.includes('models-detail=qwen2.5-coder')")
            await tab.click("#store-detail-close")
            assert await tab.js("document.activeElement.dataset.storeModel==='qwen2.5-coder'")
            await tab.js("history.back()")
            await tab.wait("byId('store-detail').open")
            await tab.click("#store-detail-close")
            await tab.click("[data-section=discover]")
            await tab.click(".store-feature")
            await tab.wait("byId('store-detail').open")
            await tab.js(
                "byId('store-variant').value='qwen3:4b';"
                "byId('store-variant').dispatchEvent(new Event('change'))"
            )
            await tab.wait(
                "[...byId('store-detail-body').querySelectorAll('button')].some(b=>b"
                ".textContent==='Get'&&!b.disabled)"
            )
            await tab.js(
                "[...byId('store-detail-body').querySelectorAll('button')].find(b=>b"
                ".textContent==='Get').click()"
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
            await tab.click("#models-refresh")
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
            await tab.click("#models-refresh")
            await tab.wait("byId('store-content').querySelectorAll('.store-row').length===1")
            Native.offline = True
            await tab.click("#models-refresh")
            await tab.wait("byId('store-content').textContent.includes('Cached')")
            assert await tab.js("byId('store-content').textContent.includes('qwen3:4b')")
            Native.offline = False
            await tab.click("[data-section=charts]")
            await tab.wait("byId('store-content').textContent.includes('1,234 Hub downloads')")
            await tab.click(".store-row")
            await tab.wait(
                "byId('store-variant') && byId('store-variant').value.includes('small-Q4_K_M.gguf')"
            )
            assert Native.pulls == 1
            await tab.click("#store-detail-close")
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
            for width, height in [(320, 568), (390, 844), (768, 1024), (1440, 900)]:
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
            await tab.js(
                "byId('image-ratio').value='768,512';"
                "byId('image-ratio').dispatchEvent(new Event('change'))"
            )
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
                "byId('image-jobs').textContent.includes('complete') "
                "&& !BrowserManagement.hasPending()"
            )
            await tab.click("#image-add")
            assert await tab.js("byId('image-prompt').value==='Watercolor mountain'")
            await tab.js(
                "[...byId('image-jobs').querySelectorAll('button')].find(b=>b"
                ".textContent==='Generate again').click()"
            )
            assert await tab.js("byId('image-seed').value==='42'")
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
                        "widths": [320, 390, 768, 1440],
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

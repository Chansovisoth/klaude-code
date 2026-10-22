"""Chrome checks against real local catalog/capability HTTP fixtures, no inference.

Run: .venv/bin/python scripts/webui_model_defaults_smoke.py
All profiles, connections and reviewed saves are temporary.
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.ai_defaults import read_defaults
from klaude_core.config import Config
from klaude_core.model_connections import ModelConnection, connection_registry
from klaude_tools import Workspace
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402


class Models(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, value, status=200):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except BrokenPipeError:
            pass

    def do_GET(self):
        assert self.path == "/api/tags"
        self.server.calls.append(self.path)
        self.reply({"models": [{"name": name} for name in self.server.models]},
                   503 if self.server.fail else 200)

    def do_POST(self):
        assert self.path == "/api/show"
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.calls.append(self.path)
        self.reply({"capabilities": self.server.models[body["model"]]})


async def verify(host, root, cfg, servers):
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    ))
    profile = root / "chrome"
    process = subprocess.Popen([
        chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    output = Path("/tmp/klaude-model-defaults-preview")
    output.mkdir(exist_ok=True)
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"]) as ws:
            tab = Tab(ws)
            async def saved():
                deadline = asyncio.get_running_loop().time() + 30
                while asyncio.get_running_loop().time() < deadline:
                    state = await tab.js("({hidden:byId('models-save-bar').hidden, "
                                         "saving:SettingsDrafts.category('models').saving, "
                                         "status:byId('models-save-status').textContent})")
                    if state["hidden"]:
                        return
                    if not state["saving"]:
                        raise AssertionError(state)
                    await asyncio.sleep(.1)
                raise AssertionError(await tab.js("byId('models-save-status').textContent"))

            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait("typeof latest!=='undefined' && authenticated && latest")
            await tab.js("showView('settings',{section:'models'})")
            await tab.wait("byId('media-settings-status').textContent.includes('Compatible')")
            get_options = """Object.fromEntries([...byId('default-model-fields').querySelectorAll(
              'select')].map(select=>[select.id,[...select.options].map(option=>option.value)]))"""
            options = await tab.js(get_options)
            prefix = "ollama@alpha/"
            assert options["default-value-chat"] == ["", prefix + "text-tools", "ollama/fixture"]
            assert options["default-value-research"] == ["", prefix + "text-tools"]
            for role in ("utility", "fallbacks-0"):
                assert options[f"default-value-{role}"] == [
                    "", prefix + "portrait", prefix + "text-tools",
                ]
            for role in ("vision", "vision_fallbacks-0"):
                assert options[f"default-value-{role}"] == ["", prefix + "portrait"]
            assert not (cfg.data_dir / "chat-preferences.json").exists()

            # Connection changes populate automatically and preserve all drafts.
            await tab.js("byId('default-value-vision').value='ollama@alpha/portrait';"
                         "byId('default-output-tokens').value='256';"
                         "byId('image-service-url').value='http://127.0.0.1:1234';"
                         "byId('default-value-vision').dispatchEvent(new Event('change'));"
                         "byId('default-output-tokens').dispatchEvent(new Event('input'));"
                         "byId('image-service-url').dispatchEvent(new Event('input'));"
                         "byId('default-model-connection').value='beta';"
                         "byId('default-model-connection').dispatchEvent(new Event('change'))")
            await tab.wait("[...byId('default-value-vision').options].some("
                           "option=>option.value==='ollama@beta/photo')")
            assert await tab.js("byId('default-value-vision').value==='ollama@alpha/portrait' && "
                               "byId('default-output-tokens').value==='256' && "
                               "byId('image-service-url').value==='http://127.0.0.1:1234'")
            # A failed refresh keeps the populated list and unsaved selections.
            servers[1].fail = True
            await tab.js("byId('default-model-catalog').requestSubmit()")
            await tab.wait("byId('media-settings-status').textContent.includes('Previously')")
            assert await tab.js("[...byId('default-value-vision').options].some("
                               "option=>option.value==='ollama@beta/photo') && "
                               "byId('default-value-vision').value==='ollama@alpha/portrait' && "
                               "!byId('default-value-vision').options[0].text.includes('Loading')")
            servers[1].fail = False
            await tab.js("byId('default-value-vision').value='ollama@beta/photo';"
                         "byId('default-value-vision').closest('form').requestSubmit()")
            assert read_defaults(cfg).vision is None
            assert await tab.js("!reviewDialog.open && !byId('models-save-bar').hidden")
            await tab.click("#models-discard")
            assert await tab.js("!byId('default-value-vision').value && "
                               "byId('models-save-bar').hidden")
            await tab.js("byId('default-value-vision').value='ollama@beta/photo';"
                         "byId('default-value-vision').dispatchEvent(new Event('change'));"
                         "byId('default-output-tokens').value='256';"
                         "byId('default-output-tokens').dispatchEvent(new Event('input'));"
                         "byId('image-service-url').value='http://127.0.0.1:1234';"
                         "byId('image-service-url').dispatchEvent(new Event('input'))")
            await tab.click("#models-save")
            await saved()
            assert read_defaults(cfg).vision == "ollama@beta/photo"
            assert await tab.js("byId('default-output-tokens').value==='256' && "
                               "byId('image-service-url').value==='http://127.0.0.1:1234'")
            # Existing saved models remain visible even outside the active catalog.
            await tab.js("byId('default-model-connection').value='alpha';"
                         "byId('default-model-connection').dispatchEvent(new Event('change'))")
            await tab.wait("byId('media-settings-status').textContent.includes('Compatible') && "
                           "[...byId('default-value-vision').options].some("
                           "option=>option.value==='ollama@alpha/portrait')")
            assert await tab.js("byId('default-value-vision').value==='ollama@beta/photo'")
            await tab.js("byId('model-fallbacks').open=true;document.fonts.ready")
            layouts = []
            for theme in ("light", "dark"):
                await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                for width in (320, 390, 768, 1440):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": 844, "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    })
                    await asyncio.sleep(.1)
                    assert await tab.js("byId('settings-view').scrollWidth<="
                                       "byId('settings-view').clientWidth && "
                                       "document.documentElement.scrollWidth<=innerWidth")
                    assert await tab.js("[...byId('default-model-fields').querySelectorAll("
                                       "'select')].every(input=>document.querySelector("
                                       "'label[for=\"'+input.id+'\"]'))")
                    layouts.append([theme, width])
                    if width in (390, 1440):
                        capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (output / f"{theme}-{width}.png").write_bytes(
                            base64.b64decode(capture["data"])
                        )
            # Vision activation is a focused data-access confirmation; cancelling
            # keeps the draft and never enables the backend implicitly.
            await tab.click("#default-vision-enabled")
            await tab.click("#models-save")
            await tab.wait("byId('settings-security')?.open")
            assert await tab.js("byId('settings-security-details').textContent.includes('images')")
            await tab.click("#settings-security-cancel")
            await tab.wait("!byId('models-save').disabled")
            assert not read_defaults(cfg).vision_enabled
            await tab.click("#models-save")
            await tab.wait("byId('settings-security').open")
            await tab.click("#settings-security-confirm")
            await saved()
            assert read_defaults(cfg).vision_enabled
            for order in (("portrait", "text-tools"), ("text-tools", "portrait")):
                for index, name in enumerate(order):
                    await tab.js(f"byId('default-value-fallbacks-{index}').value="
                                 + json.dumps(f"ollama@alpha/{name}") + ";"
                                 f"byId('default-value-fallbacks-{index}')"
                                 ".dispatchEvent(new Event('change'))")
                await tab.click("#models-save")
                await saved()
                assert read_defaults(cfg).fallbacks == tuple(
                    f"ollama@alpha/{name}" for name in order
                )
            # An obsolete catalog response cannot restore private choices after logout.
            await tab.js("""window.originalFetch=fetch.bind(window);window.fetch=(input,options)=>
              String(input).includes('/models/catalog') ? new Promise(resolve=>{
                window.releaseCatalog=()=>resolve(originalFetch(input,options));
              }) : originalFetch(input,options);""")
            await tab.js("byId('default-model-catalog').requestSubmit()")
            await tab.wait("typeof releaseCatalog==='function'")
            await tab.click("#logout")
            await tab.wait("!authenticated")
            await tab.js("releaseCatalog();window.fetch=originalFetch")
            await asyncio.sleep(.2)
            assert await tab.js("!byId('default-model-fields').children.length && "
                               "!byId('default-model-connection').children.length")
            assert not tab.errors, tab.errors
            assert all(path in {"/api/tags", "/api/show"}
                       for server in servers for path in server.calls)
            return {"automatic_role_lists": "passed", "connection_refresh_drafts": "passed",
                    "staged_discard_save": "passed", "vision_confirmation": "passed",
                    "ordered_fallback_saves": "passed", "logout_race": "passed",
                    "layouts": layouts, "inference_calls": 0, "console_errors": 0}
    finally:
        process.terminate()
        process.wait(timeout=10)


def main():
    with tempfile.TemporaryDirectory(prefix="klaude-model-defaults-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        servers = []
        for models in ({"portrait": ["completion", "vision"],
                        "text-tools": ["completion", "tools"], "embedding": ["embedding"]},
                       {"photo": ["completion", "vision", "tools"]}):
            server = ThreadingHTTPServer(("127.0.0.1", 0), Models)
            server.models, server.fail, server.calls = models, False, []
            threading.Thread(target=server.serve_forever, daemon=True).start()
            servers.append(server)
        cfg.config_dir.mkdir(parents=True)
        cfg.ollama_url = f"http://127.0.0.1:{servers[0].server_port}"
        (cfg.config_dir / "config.toml").write_text(
            f'[services]\nollama_url="{cfg.ollama_url}"\n[models.override]\ncoder="fixture"\n'
        )
        registry = connection_registry(cfg)
        for identity, server in zip(("alpha", "beta"), servers, strict=True):
            registry.add(ModelConnection(identity, identity.title(), "ollama",
                                         f"http://127.0.0.1:{server.server_port}"))
        app = _app(cfg.data_dir)
        app.agent.workdir, app.agent.workspace = root, Workspace(root)
        app.agent.tool_config = cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        host = LocalWebHost(app, library=LibraryManagement(cfg, root))
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            result = asyncio.run(asyncio.wait_for(verify(host, root, cfg, servers), 100))
            print(json.dumps(result))
        finally:
            host.stop()
            thread.join(3)
            app.memory.db.close()
            for server in servers:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main()

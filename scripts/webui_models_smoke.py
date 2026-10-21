"""Isolated Chrome checks for the Models catalog and existing runtime controls.

Run: .venv/bin/python scripts/webui_models_smoke.py
Catalog/runtime fixtures never contact a provider or alter the user's profile.
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
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

import websockets
from klaude_application.browser_models import BrowserModels
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_core.model_connections import ModelConnection, connection_registry
from klaude_core.model_runtime import ModelCapabilities, ModelInfo
from klaude_tools import Workspace
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app, _Runtime  # noqa: E402


async def verify(host, root, state, *, legacy=False):
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
    output = Path("/tmp/klaude-models-mcp-preview")
    output.mkdir(exist_ok=True)
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait("typeof latest !== 'undefined' && authenticated && latest")
            await tab.click("#nav-models")
            await tab.wait("byId('models-items').querySelectorAll('.models-model').length===20")
            assert await tab.js("currentView==='models' && location.search.includes('view=models')")
            assert await tab.js("byId('models-numbers').querySelectorAll('button').length===2")
            await tab.click("#models-next")
            assert await tab.js("byId('models-items').querySelectorAll('.models-model').length===5")
            await tab.click("#models-previous")
            await tab.js("byId('models-query').value='model-01';"
                         "byId('models-query').dispatchEvent(new Event('input'))")
            assert await tab.js("byId('models-items').querySelectorAll('.models-model').length===1")
            if legacy:
                assert await tab.js("byId('models-connections').textContent"
                                    ".includes('Local models')")
                await tab.js("byId('models-query').value='missing';"
                             "byId('models-query').dispatchEvent(new Event('input'))")
                assert await tab.js("byId('models-items').textContent"
                                    ".includes('No matching models')")
                assert not tab.errors, tab.errors
                return {"legacy": "local catalog/search/pagination passed", "console_errors": 0}

            # Real configured-model HTTP action, revision checks and persisted runtime.
            await tab.js("byId('models-items').querySelector('button').click();"
                         "byId('models-items').querySelector('button').click()")
            await tab.wait("!runtimeChoiceInFlight && latest.model_ref.endsWith('/model-01')")
            assert host.application.agent.model_info.model_id == "model-01"
            assert state["runtime_calls"] == 1
            assert not (host.library.data / "chat-preferences.json").exists()
            assert await tab.js("byId('models-items').querySelector('button').disabled && "
                               "byId('models-status').textContent.includes('ready')")
            await tab.click("#nav-chat")
            await tab.js("byId('effort-choice').value='high';"
                         "byId('effort-choice').dispatchEvent(new Event('change'))")
            await tab.wait("!runtimeChoiceInFlight && latest.effort==='high'")
            assert host.application.agent.reasoning_effort == "high"
            await tab.click("#nav-models")
            await tab.wait("!byId('models-refresh').disabled")
            await tab.js("byId('models-query').value='model-02';"
                         "byId('models-query').dispatchEvent(new Event('input'))")
            state["runtime_error"] = True
            await tab.click("#models-items .models-model > button")
            await tab.wait("!runtimeChoiceInFlight && "
                           "byId('models-status').textContent.length>0")
            assert host.application.agent.model_info.model_id == "model-01"
            assert await tab.js("byId('models-current-name').textContent.includes('model-01') && "
                               "!byId('models-items').querySelector('button').disabled")
            state["runtime_error"] = False
            await tab.js("byId('models-query').value='';"
                         "byId('models-query').dispatchEvent(new Event('input'))")
            state["catalog_error"] = True
            await tab.click("#models-refresh")
            await tab.wait("!byId('models-refresh').disabled && "
                           "byId('models-status').textContent.includes('Previously loaded')")
            assert await tab.js("byId('models-items').querySelectorAll('.models-model')"
                                ".length===20")
            state["catalog_error"] = False
            await tab.click("#models-connections [data-row-key=empty]")
            await tab.wait("!byId('models-refresh').disabled && "
                           "byId('models-items').textContent.includes('No models available')")
            assert await tab.js("byId('models-connections')"
                                ".querySelector('[data-row-key=disabled]').disabled")
            await tab.click("#models-connections [data-row-key=alpha]")
            await tab.wait("byId('models-items').querySelectorAll('.models-model').length===20")
            # Exercise locking without inference; actual busy-turn admission has unit coverage.
            await tab.js("window.modelsSnapshot=latest;latest={...latest,active_turn_id:'fixture'};"
                         "renderModelOptions()")
            assert await tab.js("[...byId('models-items').querySelectorAll('button')]"
                                ".every(b=>b.disabled)")
            await tab.js("latest=modelsSnapshot;renderModelOptions()")

            geometry = []
            for theme in ("light", "dark"):
                await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                for width in (320, 390, 768, 1024, 1440):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": 568 if width == 320 else 900,
                        "deviceScaleFactor": 1, "mobile": width < 600,
                    })
                    await asyncio.sleep(.15)
                    layout = await tab.js("""(() => {
                      const view=byId('models-view');
                      return {width:innerWidth,fits:view.scrollWidth<=view.clientWidth &&
                        document.documentElement.scrollWidth<=innerWidth,
                        pairs:[...view.querySelectorAll('.models-model')].every(row=>{
                          const r=row.getBoundingClientRect();
                          const b=row.querySelector('button').getBoundingClientRect();
                          return b.width>=44 && b.height>=44 && b.right<=r.right+1;
                        }),phoneNav:innerWidth>560 ||
                          getComputedStyle(byId('nav-models')).display==='none'};
                    })()""")
                    assert layout["fits"] and layout["pairs"] and layout["phoneNav"], layout
                    geometry.append({"theme": theme, **layout})
                    if width in (390, 1440):
                        await tab.js("Promise.all(byId('models-view').getAnimations().map("
                                     "a=>a.finished.catch(()=>{})))")
                        capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (output / f"{theme}-{width}-models.png").write_bytes(
                            base64.b64decode(capture["data"])
                        )
            await tab.js("byId('models-query').value='model-03';"
                         "byId('models-query').dispatchEvent(new Event('input'))")
            await tab.click("#models-defaults")
            await tab.wait("currentView==='settings' && settingsSection==='models'")
            await tab.js("history.back()")
            await tab.wait("currentView==='models'")
            assert await tab.js("byId('models-query').value==='model-03'")
            await tab.command("Page.reload")
            try:
                await tab.wait("typeof latest!=='undefined' && authenticated && "
                               "currentView==='models' && "
                               "Boolean(byId('models-items').querySelector('.models-model'))")
            except AssertionError as error:
                raise AssertionError(await tab.js("({view:currentView,url:location.href,"
                                     "status:byId('models-status').textContent,"
                                     "rows:byId('models-items').textContent,"
                                     "connections:byId('models-connections').textContent})"
                                     )) from error
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True,
            })
            await tab.click("#nav-chat")
            await tab.click("#nav-more")
            await tab.wait("navigationMore.matches(':popover-open')")
            await tab.js("navigationMore.querySelector('[data-app-view=models]').focus()")
            for kind in ("keyDown", "keyUp"):
                await tab.command("Input.dispatchKeyEvent", {
                    "type": kind, "key": "Enter", "code": "Enter",
                    "windowsVirtualKeyCode": 13,
                    **({"text": "\r"} if kind == "keyDown" else {}),
                })
            await tab.wait("currentView==='models' && !navigationMore.matches(':popover-open')")
            await tab.wait("!byId('models-refresh').disabled")

            # A late catalog response cannot restore private data after sign-out.
            await tab.js("""window.modelsFetch=fetch.bind(window);window.fetch=(input,options)=>
              String(input).includes('/models/catalog') ? new Promise(resolve=>{
                window.releaseModels=()=>resolve(modelsFetch(input,options));
              }) : modelsFetch(input,options);""")
            await tab.click("#models-refresh")
            await tab.wait("typeof releaseModels==='function'")
            assert await tab.js("byId('models-refresh').getAttribute('aria-busy')==='true' && "
                               "byId('models-status').textContent.includes('Loading')")
            await tab.click("#logout")
            await tab.wait("!authenticated")
            await tab.js("releaseModels();window.fetch=modelsFetch")
            await asyncio.sleep(.2)
            assert await tab.js("!byId('models-items').textContent && "
                               "!byId('models-connections').textContent && "
                               "!byId('models-current-name').title && !byId('models-query').value")
            assert not tab.errors, tab.errors
            return {"configured": "catalog/search/pagination/select/dedup/thinking-effort/failure/"
                    "refresh/empty/disabled/busy/history/reload/keyboard/navigation/logout passed",
                    "layouts": geometry, "console_errors": 0}
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    results = []
    for legacy in (False, True):
        with tempfile.TemporaryDirectory(prefix="klaude-models-smoke-") as temporary:
            root = Path(temporary)
            config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
            cfg = Config(models={"coder": "fixture"})
            cfg.config_dir.mkdir(parents=True)
            service = LibraryManagement(cfg, root)
            app = _app(cfg.data_dir)
            app.agent.workdir, app.agent.workspace = root, Workspace(root)
            app.agent.tool_config = cfg
            app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
            registry = connection_registry(cfg)
            registry.add(ModelConnection("alpha", "Development model connection with a long name",
                                         "openai_compatible", "http://127.0.0.1:1/v1"))
            registry.add(ModelConnection("empty", "Empty connection", "openai_compatible",
                                         "http://127.0.0.1:1/v1"))
            registry.add(ModelConnection("disabled", "Disabled connection", "openai_compatible",
                                         "http://127.0.0.1:1/v1", enabled=False))
            state = {"runtime_calls": 0, "catalog_error": False, "runtime_error": False}

            def discover(connection, _key, state=state):
                if state["catalog_error"]:
                    raise RuntimeError("Fixture catalog unavailable")
                if connection.id != "alpha":
                    return []
                return [ModelInfo(connection.backend, f"model-{i:02}", (
                    "A long model name with lots of descriptive information" if i == 0 else
                    f"model-{i:02}"
                ), ModelCapabilities(), connection_id=connection.id,
                    connection_revision=connection.revision, connection_source=connection.source)
                    for i in range(25)]

            def runtime(_self, _info, state=state):
                if state["runtime_error"]:
                    raise ValueError("Fixture runtime unavailable")
                state["runtime_calls"] += 1
                result = _Runtime()
                result.backend = "openai_compatible"
                return result

            if not legacy:
                app.agent.browser_models = BrowserModels(cfg)
            host = LocalWebHost(app, library=service)
            host.local_models = lambda: [{"id": f"model-{i:02}", "name": f"model-{i:02}"}
                                         for i in range(25)]
            thread = threading.Thread(target=host.serve_forever, daemon=True)
            thread.start()
            try:
                with patch("klaude_application.browser_models.discover_connection", discover), \
                        patch.object(BrowserModels, "runtime", runtime):
                    results.append(asyncio.run(verify(host, root, state, legacy=legacy)))
            finally:
                host.stop()
                thread.join(timeout=3)
                app.memory.db.close()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

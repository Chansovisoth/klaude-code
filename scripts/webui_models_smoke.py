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
            await tab.wait("typeof latest !== 'undefined' && authenticated && latest && document.documentElement.dataset.startup==='ready'")
            assert await tab.js("""(() => {
                const cases=[['gpt-4o','','openai'], ['openrouter@router/anthropic/claude-sonnet-4','','claude'],
                    ['gemini-2.5-pro','','gemini'], ['kimi-k2','','kimi'], ['phi4:latest','','microsoft'],
                    ['gemma:latest','ollama','gemma'], ['gemma2:9b','ollama','gemma'],
                    ['gemma3:12b','ollama','gemma'], ['gemma3n:e4b','ollama','gemma'],
                    ['GEMMA3:4B','ollama','gemma'], ['google/gemma-3-12b-it','ollama','gemma'],
                    ['ollama@local/gemma3:4b','','gemma'],
                    ['ollama@local/hf.co/google/gemma3-12b-it-GGUF:Q4_K_M','','gemma'],
                    ['gemmatic','ollama','generic'], ['my-gemma-notes','ollama','generic'],
                    ['meta-llama/llama-3.3','','meta'], ['qwen3.5:4b','','qwen'],
                    ['deepseek-r1:8b','','deepseek'], ['custom','ollama','generic'],
                    ['custom','openrouter','generic'], ['custom','openai_api','generic'],
                    ['unknown','','generic'], ['gpt-not-a-family-lookalike','','openai'],
                    ['my-gpt-notes','','generic']];
                return cases.every(([ref,provider,expected])=>modelLogoBrand(ref,provider)===expected);
            })()""")
            assert await tab.js("""(async () => {
                for(const name of ['gpt','gemini','gemma','ollama','openrouter',
                    'claude','kimi','phi','llama','generic']) {
                    const response=await fetch('/icons/ai/'+name+'.svg');
                    if(!response.ok || !response.headers.get('Content-Type').startsWith('image/svg+xml')) return false;
                }
                return getComputedStyle(byId('model-logo')).width==='16px' &&
                    getComputedStyle(byId('model-logo')).maskImage.includes('/icons/ai/');
            })()""")
            # Exercise every bundled asset in all supported sizes and both themes.
            assert await tab.js("""(async () => {
                const stage=document.createElement('div'); document.body.append(stage);
                stage.style.cssText='position:fixed;inset:0;z-index:99999;overflow:auto;background:var(--surface);color:var(--on-surface);display:flex;align-content:flex-start;flex-wrap:wrap;gap:8px';
                for(const name of Object.keys(AIIcons.catalog.icons)) {
                    const response=await fetch('/icons/ai/'+name+'.svg');
                    if(!response.ok) throw Error(name+' missing');
                    const image=new Image(); image.src='/icons/ai/'+name+'.svg';
                    await image.decode();
                    if(!image.naturalWidth || !image.naturalHeight) throw Error(name+' invalid');
                }
                for(const theme of ['light','dark']) {
                    stage.style.color=theme==='dark'?'#f0f0f0':'#202020';
                    stage.style.background=theme==='dark'?'#202020':'#f0f0f0';
                    for(const provider of AIIcons.catalog.providers) for(const size of [16,20,24,32]) {
                        const box=document.createElement('span'); box.className='model-brand-icon';
                        AIIcons.setModelIcon(box,provider.namespaces[0]+'/unknown',{size});
                        stage.append(box);
                        const r=box.getBoundingClientRect();
                        if(r.width!==size || r.height!==size) throw Error(provider.id+' sizing');
                    }
                    stage.replaceChildren();
                }
                stage.remove(); return true;
            })()""")
            await tab.click("#nav-models")
            if await tab.js("Boolean(window.ModelStoreUI)"):
                await tab.js("showView('settings', {section:'models'}); byId('models-configured').open=true")
            await tab.wait("byId('models-items').querySelectorAll('.models-model').length===20")
            assert await tab.js("currentView==='settings' && location.search.includes('settings=models')")
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
            assert await tab.js("!byId('thinking-control').hidden && "
                "byId('thinking-menu').contains(byId('effort-choice')) && "
                "!byId('model-menu').contains(byId('effort-choice'))")
            for width in (320, 390, 768, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 844, "deviceScaleFactor": 1, "mobile": False,
                })
                for control, menu_id in (("model-picker", "model-menu"), ("thinking-menu summary", "thinking-menu")):
                    await tab.click("#" + control)
                    await tab.wait(f"byId('{menu_id}').open")
                    await asyncio.sleep(.1)
                    assert await tab.js(f"""(() => {{
                        const popup=byId('{menu_id}').querySelector('.model-row').getBoundingClientRect();
                        const composer=byId('composer');
                        const model=byId('model-picker').getBoundingClientRect();
                        const thinking=byId('mode-toggle').getBoundingClientRect();
                        return popup.left>=15 && popup.right<=innerWidth-15 &&
                            document.documentElement.scrollWidth<=innerWidth &&
                            byId('thinking-control').getBoundingClientRect().right<=innerWidth &&
                            byId('model-control').getBoundingClientRect().left>=0 &&
                            model.height===32 && thinking.height===32 &&
                            byId('plan-toggle').getBoundingClientRect().height===32;
                    }})()"""), await tab.js(f"""(() => {{
                        const r=byId('{menu_id}').querySelector('.model-row').getBoundingClientRect();
                        return {{width:innerWidth,popup:{{left:r.left,right:r.right}},
                        composer:[byId('composer').scrollWidth,byId('composer').clientWidth],
                        model:byId('model-picker').getBoundingClientRect().height,
                        thinking:byId('mode-toggle').getBoundingClientRect().height}};
                    }})()""")
                    assert await tab.js(f"""(() => {{
                        const popup=byId('{menu_id}').querySelector('.model-row');
                        const r=popup.getBoundingClientRect();
                        return popup.matches(':popover-open') &&
                            [[r.left+16,r.top+16],[r.right-16,r.bottom-16]].every(([x,y])=>
                                popup.contains(document.elementFromPoint(x,y)));
                    }})()""")
                    if width == 1440:
                        assert await tab.js(f"""(() => {{
                            const popup=byId('{menu_id}').querySelector('.model-row');
                            const edge=byId('main-content').getBoundingClientRect().left;
                            popup.style.left=(edge-40)+'px';
                            const r=popup.getBoundingClientRect();
                            const visible=popup.contains(document.elementFromPoint(edge-8,r.top+32));
                            positionChatSelector(byId('{menu_id}'));
                            return visible;
                        }})()""")
                    capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"chat-{menu_id}-{width}.png").write_bytes(base64.b64decode(capture["data"]))
                    await tab.js(f"byId('{menu_id}').querySelector('select').focus()")
                    for event in ("keyDown", "keyUp"):
                        await tab.command("Input.dispatchKeyEvent", {"type": event, "key": "Escape",
                            "code": "Escape", "windowsVirtualKeyCode": 27})
                    assert await tab.js(f"!byId('{menu_id}').open && "
                        f"document.activeElement===byId('{menu_id}').querySelector('summary')")
            await tab.js("""(() => {
                const saved=latest.effort_levels;
                latest.effort_levels=['off']; renderModelOptions();
                if(!byId('thinking-control').hidden) throw Error('Unsupported Thinking remains visible');
                latest.effort_levels=saved; renderModelOptions();
            })()""")
            await tab.click("#thinking-menu summary")
            await tab.js("byId('effort-choice').value='high';"
                         "byId('effort-choice').dispatchEvent(new Event('change'))")
            await tab.wait("!runtimeChoiceInFlight && latest.effort==='high'")
            assert host.application.agent.reasoning_effort == "high"
            assert await tab.js("!byId('thinking-menu').open && document.activeElement===byId('mode-toggle')")
            await tab.click("#mode-toggle")
            await tab.wait("!runtimeChoiceInFlight && latest.mode==='standard'")
            await asyncio.sleep(.3)
            assert await tab.js("getComputedStyle(byId('mode-toggle')).backgroundColor===getComputedStyle(byId('plan-toggle')).backgroundColor && "
                "getComputedStyle(byId('thinking-menu').querySelector('summary')).backgroundColor===getComputedStyle(byId('plan-toggle')).backgroundColor")
            await tab.js("window.offModeColor=getComputedStyle(byId('mode-toggle')).backgroundColor")
            await tab.click("#mode-toggle")
            await tab.wait("!runtimeChoiceInFlight && latest.mode==='thinking'")
            await tab.click("#plan-toggle")
            await tab.wait("latest.plan_mode===true")
            await asyncio.sleep(.3)
            assert await tab.js("getComputedStyle(byId('mode-toggle')).backgroundColor===getComputedStyle(byId('plan-toggle')).backgroundColor && "
                "getComputedStyle(byId('mode-toggle')).backgroundColor!==offModeColor && "
                "getComputedStyle(byId('thinking-menu').querySelector('summary')).backgroundColor===getComputedStyle(byId('plan-toggle')).backgroundColor")
            await tab.click("#plan-toggle")
            await tab.wait("latest.plan_mode===false")
            await tab.click("#nav-models")
            if await tab.js("Boolean(window.ModelStoreUI)"):
                await tab.js("showView('settings', {section:'models'}); byId('models-configured').open=true")
            await tab.wait("!byId('configured-models-refresh').disabled")
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
            await tab.click("#configured-models-refresh")
            await tab.wait("!byId('configured-models-refresh').disabled && "
                           "byId('models-status').textContent.includes('Previously loaded')")
            assert await tab.js("byId('models-items').querySelectorAll('.models-model')"
                                ".length===20")
            state["catalog_error"] = False
            await tab.click("#models-connections [data-row-key=empty]")
            await tab.wait("!byId('configured-models-refresh').disabled && "
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
                      const view=byId('models-settings');
                      return {width:innerWidth,fits:view.scrollWidth<=view.clientWidth &&
                        document.documentElement.scrollWidth<=innerWidth,
                        pairs:[...view.querySelectorAll('.models-model')].every(row=>{
                          const r=row.getBoundingClientRect();
                          const b=row.querySelector('button').getBoundingClientRect();
                          return b.width>=44 && b.height>=44 && b.right<=r.right+1;
                        }),phoneNav:innerWidth>560 ||
                          getComputedStyle(byId('nav-models')).display==='none'};
                    })()""")
                    if not layout["fits"]:
                        print(await tab.js("""(() => {
                          const view=byId('models-settings'), bounds=view.getBoundingClientRect();
                          return {view:{width:view.clientWidth,scroll:view.scrollWidth},
                            doc:{width:innerWidth,scroll:document.documentElement.scrollWidth},
                            outside:[...view.querySelectorAll('*')].filter(n=>{
                              const r=n.getBoundingClientRect();
                              return r.width>0 && r.right>bounds.right+1;
                            }).map(n=>({id:n.id,tag:n.tagName,cls:n.className,
                              right:n.getBoundingClientRect().right})).slice(0,12)};
                        })()"""))
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
            await tab.click("#nav-chat")
            await tab.js("history.back()")
            await tab.wait("currentView==='settings' && settingsSection==='models'")
            assert await tab.js("byId('models-query').value==='model-03'")
            await tab.command("Page.reload")
            try:
                await tab.wait("typeof latest!=='undefined' && authenticated && "
                               "currentView==='settings' && "
                               "Boolean(byId('models-items').querySelector('.models-model'))")
            except AssertionError as error:
                raise AssertionError(await tab.js("({view:currentView,url:location.href,"
                                     "status:byId('models-status').textContent,"
                                     "rows:byId('models-items').textContent,"
                                     "connections:byId('models-connections').textContent})"
                                     )) from error
            await tab.wait("document.documentElement.dataset.startup==='ready'")
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True,
            })
            await tab.click("#nav-chat")
            await tab.click("#nav-more")
            await tab.wait("navigationMore.matches(':popover-open')")
            await tab.js("navigationMore.querySelector('[data-app-view=models]').focus()")
            await asyncio.sleep(.1)
            assert await tab.js("document.activeElement===navigationMore.querySelector('[data-app-view=models]')"), await tab.js("({active:document.activeElement.id,view:currentView,open:navigationMore.matches(':popover-open')})")
            for kind in ("keyDown", "keyUp"):
                await tab.command("Input.dispatchKeyEvent", {
                    "type": kind, "key": "Enter", "code": "Enter",
                    "windowsVirtualKeyCode": 13,
                    **({"text": "\r"} if kind == "keyDown" else {}),
                })
            await tab.wait("currentView==='models' && !navigationMore.matches(':popover-open')")
            await tab.wait("!byId('configured-models-refresh').disabled")

            await tab.js("showView('settings', {section:'models'}); byId('models-configured').open=true")
            await tab.wait("!byId('configured-models-refresh').disabled")

            # A late catalog response cannot restore private data after sign-out.
            await tab.js("""window.modelsFetch=fetch.bind(window);window.fetch=(input,options)=>
              String(input).includes('/models/catalog') ? new Promise(resolve=>{
                window.releaseModels=()=>resolve(modelsFetch(input,options));
              }) : modelsFetch(input,options);""")
            await tab.click("#configured-models-refresh")
            await tab.wait("typeof releaseModels==='function'")
            assert await tab.js("byId('configured-models-refresh').getAttribute('aria-busy')==='true' && "
                               "byId('models-items').getAttribute('aria-busy')==='true'")
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

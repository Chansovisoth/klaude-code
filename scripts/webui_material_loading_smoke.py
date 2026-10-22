"""Real-browser official Material geometry/motion/lifecycle and theme checks.

Uses an isolated host/profile, no models. Optional KLAUDE_M3_REFERENCE_VIDEO
captures frames from the official overview MP4 for visual comparison only.
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
from urllib.request import Request, urlopen

import websockets
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools.toolkit import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402

OUT = Path("/tmp/klaude-material-loading")


async def verify(host, root, chrome):
    OUT.mkdir(exist_ok=True)
    profile = root / "chrome"
    process = subprocess.Popen([
        chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=8_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js('byId("login-password").value=' + json.dumps(
                host.accounts.initial_password()
            ) + ';byId("account-login").requestSubmit()')
            await tab.wait('latest?.session_id && MaterialLoading && '
                           'pollTimer!==null && sessionsLoaded && '
                           '!loadingStates.has(byId("model-status"))')
            await tab.js('clearInterval(pollTimer);stream?.close();stream=null;'
                         'window.loadingFrameWrites=0;window.loadingLongTasks=[];'
                         'new PerformanceObserver(list=>loadingLongTasks.push('
                         '...list.getEntries().map(e=>e.duration)))'
                         '.observe({type:"longtask",buffered:false});'
                         'new MutationObserver(records=>loadingFrameWrites+=records.filter('
                         'r=>r.attributeName==="d").length).observe(document.body,'
                         '{attributes:true,subtree:true,attributeFilter:["d"]})')
            # Current end-4 source: 800ms cadence, 90-degree/350ms quadratic
            # leaps, 12-second continuous rotation and a 750ms zoom envelope.
            samples = await tab.js('Array.from({length:8},(_,i)=>MaterialLoading.frameAt(i*800))')
            assert [s["index"] for s in samples] == [0, 0, 1, 2, 3, 4, 5, 6]
            assert all(s["progress"] == 0 for s in samples)
            assert await tab.js('MaterialLoading.frameAt(900).progress>0 && '
                                'MaterialLoading.frameAt(900).progress<1 && '
                                'MaterialLoading.frameAt(1000).progress===1 && '
                                'MaterialLoading.frameAt(900).zoom>1 && '
                                'Math.abs(MaterialLoading.frameAt(1150).rotation-124.5)<.0001')

            async def shot(name):
                result = await tab.command("Page.captureScreenshot", {"format": "png"})
                (OUT / name).write_bytes(base64.b64decode(result["data"]))

            for theme in ("light", "dark"):
                await tab.js('applyAppearance({...appearance,theme:' +
                             json.dumps(theme) + '},true)')
                for width in (360, 390, 768, 1280):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": 820, "deviceScaleFactor": 1, "mobile": False,
                    })
                    await tab.js('renderAgentActivity({turn_id:"fixture",label:"Writing code",'
                                 'lifecycle:"running",active_count:1,timeline:[]})')
                    await asyncio.sleep(.2)
                    assert await tab.js('byId("agent-activity").querySelector('
                                        '".material-loading[data-contained=false]")!==null && '
                                        'document.documentElement.scrollWidth<=innerWidth'), {
                        "theme": theme, "width": width, "state": await tab.js(
                            '({activity:byId("agent-activity").outerHTML,'
                            'pageWidth:document.documentElement.scrollWidth})'
                        ),
                    }
                    await shot(f"chat-{theme}-{width}.png")
            await tab.js('showView("chat");renderAgentActivity({turn_id:"fixture",'
                         'label:"Running tests",lifecycle:"running",timeline:[]})')
            await tab.js('window.runningIndicator=byId("agent-activity").querySelector('
                         '".material-loading");window.firstPath=runningIndicator.querySelector("path")'
                         '.getAttribute("d")')
            # The 200ms morph holds its target until the next 800ms leap;
            # wait through that interval instead of sampling a fixed 150ms gap.
            await tab.wait('runningIndicator.querySelector("path").getAttribute("d")'
                           '!==firstPath')
            await tab.js('renderAgentActivity({turn_id:"fixture",label:"Running tests",'
                         'lifecycle:"running",timeline:[]})')
            assert await tab.js('runningIndicator===byId("agent-activity").querySelector('
                                '".material-loading")')
            for label, lifecycle in (("Needs input", "running"), ("Done", "completed"),
                                     ("Error", "failed"), ("Cancelled", "cancelled")):
                await tab.js('renderAgentActivity(' + json.dumps({
                    "turn_id": "fixture", "label": label, "lifecycle": lifecycle,
                }) + ')')
                assert await tab.js('!byId("agent-activity").querySelector(".material-loading")')

            # Exercise real page-loader ownership and cleanup while retaining its
            # existing static skeleton shape and meaningful status description.
            await tab.click("#nav-library")
            await tab.wait('filePage && !loadingStates.has(byId("library-items"))')
            await tab.js('window.finishMaterial=beginLoading(byId("library-items"),'
                         '{kind:"rows",count:3,preserve:false,label:"Loading uploads…"})')
            await tab.wait('byId("library-items").querySelector(".material-loading")!==null')
            assert await tab.js('byId("library-items").textContent.includes("Loading uploads") && '
                                'byId("library-items").querySelector('
                                '".material-loading[data-size=large][data-contained=true]")!==null')
            await shot("page-loading-dark-1280.png")
            # A contained static strip of the seven canonical frames makes curve
            # provenance and outlines easy to inspect at a useful magnification.
            await tab.js('''(() => {
              const strip=document.createElement('div');strip.id='m3-shape-strip';
              strip.style.cssText='position:fixed;inset:20px;z-index:20;display:flex;'
                +'flex-wrap:wrap;align-content:center;gap:20px;background:var(--surface);padding:24px';
              for(let i=0;i<7;i++){
                const box=document.createElement('div'),shape=MaterialLoading.create({
                  size:'large',contained:true,label:MaterialLoading.names[i]});
                shape.style.cssText='width:112px;height:112px';
                shape.querySelector('path').setAttribute('d',MaterialLoading.pathAt(
                  MaterialLoading.frameAt(i===0?0:i*800+200)));
                shape.querySelector('g').setAttribute('transform','rotate(-90)');
                box.append(shape,document.createTextNode(MaterialLoading.names[i]));strip.append(box);
              }
              document.body.append(strip);
            })()''')
            # Freeze the strip immediately through the user's real setting.
            await tab.js('document.documentElement.dataset.motion="reduced"')
            await asyncio.sleep(.05)
            await tab.js('''[...byId('m3-shape-strip').querySelectorAll('path')].forEach((path,i)=>{
              path.setAttribute('d',MaterialLoading.pathAt(MaterialLoading.frameAt(i===0?0:i*800+200)));
            })''')
            await shot("seven-official-shapes.png")
            await tab.js('byId("m3-shape-strip").remove()')
            await asyncio.sleep(.05)
            writes = await tab.js('loadingFrameWrites')
            await asyncio.sleep(.25)
            assert await tab.js('loadingFrameWrites') == writes
            await tab.js('document.documentElement.dataset.motion="full"')
            # Held shapes do not rewrite their identical path during rotation.
            # Resume must reach the next 800ms leap, not write within 150ms.
            await tab.wait(f'loadingFrameWrites>{writes}')
            await tab.command("Emulation.setEmulatedMedia", {"features": [
                {"name": "prefers-reduced-motion", "value": "reduce"},
            ]})
            await asyncio.sleep(.05)
            writes = await tab.js('loadingFrameWrites')
            await asyncio.sleep(.25)
            assert await tab.js('loadingFrameWrites') == writes
            await tab.command("Emulation.setEmulatedMedia", {"features": []})
            await tab.js('window.loaderPath=byId("library-items").querySelector("path");'
                         'window.realSetAttribute=loaderPath.setAttribute.bind(loaderPath);'
                         'window.loaderWrites=0;loaderPath.setAttribute=(...args)=>{'
                         'loaderWrites++;return realSetAttribute(...args)};'
                         'byId("library-items").hidden=true')
            await asyncio.sleep(.15)
            writes = await tab.js('loaderWrites')
            await asyncio.sleep(.2)
            assert await tab.js('loaderWrites') == writes
            await tab.js('byId("library-items").hidden=false;finishMaterial();'
                         'renderAgentActivity(null)')
            await tab.wait('MaterialLoading.activeCount()===0')
            await tab.js('loadLibrary()')
            await tab.wait('!loadingStates.has(byId("library-items"))')
            await tab.js('''window.retainedUploads=byId('library-items').firstElementChild;
              window.refreshFetch=fetch;window.materialRefreshRequests=0;
              window.fetch=(input,options)=>String(input).startsWith('/api/v1/library/items?') ?
                new Promise(resolve=>{materialRefreshRequests++;
                  window.releaseMaterialRefresh=()=>resolve(refreshFetch(input,options));}) :
                refreshFetch(input,options);
              refreshDomain('library');true;
            ''')
            await tab.wait('byId("library-refresh").querySelector(".material-loading")!==null')
            assert await tab.js('retainedUploads.isConnected && '
                                'byId("library-refresh").getAttribute("aria-label")'
                                '==="Refresh Library" && '
                                'byId("library-refresh").querySelector("svg")!==null')
            await tab.js('refreshDomain("library")')
            assert await tab.js('materialRefreshRequests===1')
            await tab.js('releaseMaterialRefresh()')
            await tab.wait('!domainRefreshes.has("library") && !byId("library-refresh")'
                           '.querySelector(".material-loading")')
            await tab.js('window.fetch=refreshFetch')
            await tab.click("#nav-activity")
            await tab.wait('!operationPollBusy')
            await tab.js('''window.materialFetch=fetch;window.operationFixture={
              request_id:'fixture-operation',kind:'skill-enabled',state:'running'};
              window.fetch=(input,options)=>String(input).includes('/library/operations') ?
                Promise.resolve(new Response(JSON.stringify({items:[operationFixture]}),{
                  headers:{'Content-Type':'application/json'}})) : materialFetch(input,options);
            ''')
            await tab.js('loadOperations()')
            await tab.wait('byId("domain-operations").querySelector(".material-loading")!==null')
            await tab.js('window.operationIndicator=byId("domain-operations").querySelector('
                         '".material-loading")')
            await tab.js('loadOperations()')
            assert await tab.js('operationIndicator===byId("domain-operations")'
                                '.querySelector(".material-loading")')
            await tab.js('operationFixture.state="completed";loadOperations()')
            await tab.wait('!operationPollBusy && !byId("domain-operations")'
                           '.querySelector(".material-loading")')
            await tab.js('window.fetch=materialFetch')
            await tab.wait('MaterialLoading.activeCount()===0')
            # No orphaned animation states after repeated short page loads.
            await tab.js('''for(let i=0;i<100;i++){
              const el=MaterialLoading.create();document.body.append(el);el.remove();
            }''')
            await tab.wait('MaterialLoading.activeCount()===0')
            assert await tab.js('!performance.getEntriesByType("resource").some('
                                'entry=>new URL(entry.name).origin!==location.origin)')
            assert not tab.errors, tab.errors
            result = {"responsive_chat_layouts": 8, "official_shape_order": True,
                      "end4_cadence_rotation_zoom_and_morph": True,
                      "reduced_motion_app_and_system": True,
                      "hidden_and_removed_cleanup": True, "page_loader_ownership": True,
                      "operation_poll_identity_and_completion": True,
                      "refresh_content_identity_and_deduplication": True,
                      "long_tasks_ms": await tab.js('loadingLongTasks'),
                      "browser_exceptions": 0, "external_requests": 0,
                      "screenshots": str(OUT)}
            (OUT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))

            reference = os.environ.get("KLAUDE_M3_REFERENCE_VIDEO")
            if reference:
                page = root / "reference.html"
                page.write_text('<style>body{margin:0}video{width:100vw;height:100vh;'
                                'object-fit:contain}</style><video muted src="' +
                                Path(reference).resolve().as_uri() + '"></video>')
                await tab.command("Page.navigate", {"url": page.as_uri()})
                await tab.wait('document.querySelector("video")?.readyState>=2')
                for index, time in enumerate((0.1, .75, 1.4, 2.05, 2.7, 3.35, 4.0)):
                    await tab.js('document.querySelector("video").currentTime=' + str(time))
                    await asyncio.sleep(.15)
                    await shot(f"official-video-{index}.png")
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    ))
    with tempfile.TemporaryDirectory(prefix="klaude-m3-loading-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        app = _app(root)
        app.agent.workdir, app.agent.workspace = root, Workspace(root)
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        host = LocalWebHost(app, accounts=accounts,
                            library=LibraryManagement(cfg, root), staging_dir=root / "staging")
        host.local_models = lambda: []
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome), 120))
        finally:
            host.stop()
            serving.join(3)


if __name__ == "__main__":
    main()

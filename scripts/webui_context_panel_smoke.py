"""Isolated Chrome checks for Context Panel events, Library and attachment reuse.

Run: .venv/bin/python scripts/webui_context_panel_smoke.py
Uses real local HTTP/SSE and file reads; never contacts a model or owner profile.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools.toolkit import Workspace, build_tools
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from PIL import Image
from webui_activity_smoke import Runtime
from webui_control_smoke import Tab

OUT = Path("/tmp/klaude-context-panel-preview")


async def verify(host, root, chrome, runtime, files):
    OUT.mkdir(exist_ok=True)
    profile = root / "chrome"
    process = subprocess.Popen(
        [
            chrome,
            "--no-sandbox",
            "--disable-gpu",
            "--blink-settings=primaryHoverType=2,availableHoverTypes=2,primaryPointerType=4,availablePointerTypes=4",
            "--remote-debugging-port=0",
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
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=6_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 1440,
                    "height": 900,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js(
                'byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await tab.wait("latest?.context_panel && window.ContextPanel")
            assert await tab.js('!byId("cp-refresh")')
            assert await tab.js('!byId("cp-close") && !byId("cp-scope-description")')
            assert await tab.js('byId("cp-scope-current").textContent') == "Current"
            await tab.js("setContextPanel(true)")
            assert await tab.js('byId("cp-status").textContent') == "Idle"
            await tab.send("Read note.txt")
            await tab.wait('byId("cp-status").textContent==="Awaiting Approval"')
            assert await tab.js('!byId("cp-approvals").hidden && latest.approvals.length===1')
            await tab.click("#inspector-toggle")
            assert await tab.js('byId("inspector").inert && !byId("approvals").hidden')
            await tab.js("window.beforeContextReload=true")
            await tab.command("Page.reload")
            await tab.wait(
                "!window.beforeContextReload && window.ContextPanel && latest?.context_panel"
            )
            await tab.wait('typeof latest!=="undefined" && latest?.approvals.length===1')
            assert await tab.js('byId("inspector").inert')
            await tab.click("#approvals button")
            await tab.idle()
            await tab.wait('byId("cp-status").textContent==="Completed"')
            await tab.js("setContextPanel(true)")
            assert await tab.js('byId("cp-tool-count").textContent') == "1 tool call"
            assert await tab.js('byId("cp-activity").textContent.includes("Approval accepted")')
            assert (
                await tab.js(
                    'byId("cp-activity").querySelectorAll("[data-event-key*=tool]").length'
                )
                == 1
            )
            await tab.js('byId("cp-activity").querySelector("[data-event-key*=tool]").open=true')
            await tab.js("stream.close();stream=null;snapshot()")
            assert await tab.js('byId("cp-activity").querySelector("[data-event-key*=tool]").open')
            shot = await tab.command("Page.captureScreenshot", {"format": "png"})
            (OUT / "inspector-completed.png").write_bytes(base64.b64decode(shot["data"]))
            assert await tab.js('!byId("cp-activity").textContent.includes("PRIVATE read result")')
            await tab.js("""window.originalInspector=structuredClone(latest);
              const replay=structuredClone(latest);
              replay.inspector.events=[...replay.inspector.events.reverse(),...replay.inspector.events];
              ContextPanel.render(replay);""")
            assert (
                await tab.js(
                    'byId("cp-activity").querySelectorAll("[data-event-key*=tool]").length'
                )
                == 1
            )
            await tab.js("""const hostile=structuredClone(latest);
              hostile.inspector.events.push({id:'999999',turn_id:latest.inspector.turn_id,
                kind:'tool.finished',tool:'<img src=x onerror=window.inspectorExecuted=true>',
                execution_id:'hostile',executed:true,status:'failed',
                arguments:{secret:'PRIVATE ARGUMENT'},result:'PRIVATE RESULT'.repeat(20000),
                inspection:{path:'src/'+'very-long-path-'.repeat(50)+'.txt'}});
              ContextPanel.render(hostile);""")
            assert await tab.js(
                '!window.inspectorExecuted && !byId("cp-activity").querySelector("img")'
            )
            assert await tab.js(
                '!byId("cp-activity").innerHTML.includes("PRIVATE ARGUMENT") && '
                '!byId("cp-activity").innerHTML.includes("PRIVATE RESULT")'
            )
            await tab.js("snapshot()")
            await tab.click("#cp-tab-details")
            assert await tab.js('byId("cp-task-label").textContent') == "Read note.txt"
            assert await tab.js('byId("cp-details").textContent.includes(latest.session_id)')
            await tab.click("#cp-tab-changes")
            assert await tab.js(
                'byId("cp-changes").textContent.includes("No verified workspace edits")'
            )
            # Rendering fixtures are distinct from the real edit evidence in Python tests.
            await tab.js("""const changed=structuredClone(originalInspector);
              changed.inspector.file_changes=[{path:'note.txt',status:'modified'}];
              ContextPanel.render(changed);""")
            await tab.click("#cp-changes .cp-change button")
            await tab.wait('byId("workspace-result").textContent.includes("PRIVATE read result")')
            assert await tab.js('currentView==="workspace"')
            await tab.js('showView("chat");snapshot()')
            assert await tab.js(
                'fetch("/api/v1/workspace/file?path=../outside").then(r=>r.status>=400)'
            )
            assert (
                await tab.js('fetch("/api/v1/workspace/diff?path=note.txt").then(r=>r.status)')
                == 400
            )
            await tab.send("Read note.txt")
            await tab.wait("latest.approvals.length===1")
            await tab.js('byId("approvals").querySelectorAll("button")[1].click()')
            await tab.idle()
            assert await tab.js('byId("cp-activity").textContent.includes("Approval denied")')
            await tab.send("Wait")
            await tab.wait(
                'byId("cp-status").textContent==="Running" && !pending && !byId("cancel").disabled'
            )
            assert runtime.entered.wait(2)
            await tab.click("#cancel")
            await tab.idle()
            await tab.wait('byId("cp-status").textContent==="Cancelled"')
            await tab.send("Fail")
            await tab.idle()
            await tab.wait('byId("cp-status").textContent==="Failed"')
            await tab.js("window.beforeContextReload=true")
            await tab.command("Page.reload")
            await tab.wait(
                "!window.beforeContextReload && window.ContextPanel && latest?.context_panel"
            )
            await tab.wait('typeof latest!=="undefined" && latest?.activity.lifecycle==="failed"')
            await tab.js("setContextPanel(true)")
            assert await tab.js('byId("cp-status").textContent') == "Failed"

            await tab.click("#cp-tab-library")
            for query in (
                "scope=workspace",
                "scope=current&session=other",
                "references=../private",
            ):
                assert (
                    await tab.js(f'fetch("/api/v1/library/items?{query}").then(r=>r.status)') == 400
                )
            await tab.wait('byId("cp-file-items").children.length===1')
            assert await tab.js('byId("cp-file-items").textContent.includes("current.txt")')
            await tab.click("#cp-scope-all")
            await tab.wait('byId("cp-file-items").children.length===6')
            await tab.js("""window.contextFetch=fetch;
              window.fetch=(input,options)=>String(input).startsWith('/api/v1/library/items?') ?
                Promise.resolve(new Response(JSON.stringify({error:{message:'Fixture offline'}}),
                  {status:503,headers:{'Content-Type':'application/json'}})) :
                contextFetch(input,options);
              byId('cp-search').value='current';
              byId('cp-search-form').requestSubmit();""")
            await tab.wait(
                'byId("cp-library-status").textContent.includes("Select Library to retry")'
            )
            await tab.js(
                "fetch=contextFetch;byId('cp-search').value='';byId('cp-tab-library').click()"
            )
            await tab.wait('byId("cp-file-items").children.length===6')
            await tab.js("document.activeElement.blur()")
            assert await tab.js('matchMedia("(hover: hover) and (pointer: fine)").matches')
            assert await tab.js('!byId("cp-file-items").querySelector(".cp-file-attach")')
            await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Tab"})
            await tab.js('document.querySelector(".cp-file-preview").focus()')
            assert await tab.js('document.activeElement.matches(".cp-file-preview")')
            await tab.js("document.activeElement.blur()")
            await tab.click('[data-cp-view="grid"]')
            await tab.wait('byId("cp-file-items").children.length===6')
            await tab.click('[data-cp-view="gallery"]')
            await tab.wait('byId("cp-file-items").querySelectorAll(".cp-file").length===3')
            assert await tab.js('byId("cp-file-items").querySelector("img").loading') == "lazy"
            assert (
                await tab.js('byId("cp-file-items").querySelectorAll(".gallery-month").length') == 2
            )
            await tab.js("""window.galleryStyle=selector=>{
              const root=document.querySelector(selector), tile=root.querySelector('.file-item');
              const art=tile.querySelector('.file-artwork'),
                caption=tile.querySelector('.file-name-group');
              return {gap:getComputedStyle(root).gap, radius:getComputedStyle(tile).borderRadius,
                artAspect:getComputedStyle(art).aspectRatio,
                padding:getComputedStyle(tile.querySelector('.file-open')).padding,
                captionPosition:getComputedStyle(caption).position,
                captionOpacity:getComputedStyle(caption).opacity,
                metadata:getComputedStyle(tile.querySelector('.file-secondary')).display};
            };window.sidebarGalleryStyle=galleryStyle('#cp-file-items');showView('library');""")
            await tab.click('[data-file-view="gallery"]')
            await tab.wait('byId("library-items").querySelectorAll(".file-item").length===3')
            sidebar_style = await tab.js("sidebarGalleryStyle")
            main_gallery_style = await tab.js('galleryStyle("#library-items")')
            assert main_gallery_style == sidebar_style, (main_gallery_style, sidebar_style)
            await tab.js("showView('chat');setContextPanel(true)")
            await tab.js('document.querySelector(".cp-file-preview").focus()')
            await tab.wait(
                'getComputedStyle(document.querySelector(".cp-file-caption")).opacity==="1"'
            )
            await tab.js("document.activeElement.blur()")
            await tab.click('[data-cp-view="list"]')
            await tab.wait('byId("cp-file-items").children.length===6')
            await tab.js('byId("cp-search").value="shared";byId("cp-search-form").requestSubmit()')
            await tab.wait('byId("cp-file-items").children.length===1')
            await tab.click(".cp-file-preview")
            await tab.wait('selectedArtifact?.name==="shared.txt"')
            assert await tab.js(
                'byId("artifact-preview").textContent.includes("PRIVATE shared document")'
            )
            await tab.click("#artifact-close")
            await tab.js('prompt.value="Unsent draft"')
            await tab.command(
                "Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 1}
            )
            assert await tab.js('!byId("cp-file-items").querySelector(".cp-file-attach")')
            assert await tab.js('byId("cp-library-status").textContent.includes("Drag a file")')
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 390, "height": 760, "deviceScaleFactor": 1, "mobile": True,
            })
            await tab.wait('byId("cp-library-status").textContent.includes("chat attachment menu")')
            # Context rows only preview. Keyboard/touch attachment uses the composer picker.
            await tab.js("setContextPanel(false)")
            await tab.click("#attach-file")
            await tab.click("#attach-library")
            await tab.js('byId("attach-search").value="shared.txt";'
                         'byId("attach-search-form").requestSubmit()')
            await tab.wait('byId("attach-library-items").children.length===1 && '
                           'byId("attach-library-items").textContent.includes("shared.txt")')
            await tab.click(".attachment-library-item button")
            await tab.wait("ChatAttachmentsUI.ids().length===1")
            await tab.click("#attach-close")
            assert await tab.js('byId("inspector").inert')
            await tab.js("setContextPanel(true)")
            assert await tab.js("prompt.value") == "Unsent draft"
            assert not await tab.js("latest.active_turn_id")
            assert await tab.js("ChatAttachmentsUI.artifactIds()[0]") == files["shared"]["id"]
            await tab.click("#cp-scope-current")
            await tab.js('byId("cp-search").value="";byId("cp-search-form").requestSubmit()')
            await tab.wait('byId("cp-file-items").children.length===2')
            await tab.click("#cp-scope-all")
            await tab.wait('byId("cp-file-items").children.length===6')
            await tab.command("Emulation.setTouchEmulationEnabled", {"enabled": False})
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False,
            })
            await asyncio.sleep(.15)
            # A real native internal drag uses the same MIME payload emitted by dragstart.
            await tab.js("""const row=[...byId('cp-file-items').children]
              .find(r=>r.textContent.includes('other.txt'));
              const transfer=new DataTransfer();
              row.dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:transfer}));
              window.dragPayload=transfer.getData('application/x-klaude-library-artifact');""")
            point = await tab.js("""(()=>{const r=byId('composer').getBoundingClientRect();
              return {x:r.left+r.width/2,y:r.top+20}})()""")
            drag_data = {
                "items": [
                    {
                        "mimeType": "application/x-klaude-library-artifact",
                        "data": await tab.js("dragPayload"),
                    }
                ],
                "dragOperationsMask": 1,
            }
            for event in ("dragEnter", "dragOver"):
                await tab.command(
                    "Input.dispatchDragEvent", {"type": event, **point, "data": drag_data}
                )
            assert await tab.js('!document.querySelector(".file-drop-overlay").hidden')
            await tab.command(
                "Input.dispatchDragEvent", {"type": "drop", **point, "data": drag_data}
            )
            await tab.wait("ChatAttachmentsUI.ids().length===2")
            await tab.wait("!ChatAttachmentsUI.preparing()")
            assert not await tab.js("latest.active_turn_id")
            assert await tab.js("prompt.value") == "Unsent draft"
            assert host.library.listing(kind="all")["total"] == 6
            stale_data = {
                **drag_data,
                "items": [
                    {
                        "mimeType": "application/x-klaude-library-artifact",
                        "data": json.dumps(
                            {**json.loads(await tab.js("dragPayload")), "session": "old-session"}
                        ),
                    }
                ],
            }
            for event in ("dragEnter", "dragOver", "drop"):
                await tab.command(
                    "Input.dispatchDragEvent", {"type": event, **point, "data": stale_data}
                )
            assert await tab.js("ChatAttachmentsUI.ids().length") == 2
            assert await tab.js(
                'byId("chat-attachment-status").textContent.includes("current conversation")'
            )

            layouts = []
            for theme in ("light", "dark"):
                await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                for width, height in ((1440, 900), (768, 844), (390, 640), (320, 480)):
                    await tab.command(
                        "Emulation.setTouchEmulationEnabled",
                        {"enabled": width <= 768, "maxTouchPoints": 1},
                    )
                    await tab.command(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": width,
                            "height": height,
                            "deviceScaleFactor": 1,
                            "mobile": width < 600,
                        },
                    )
                    await tab.js("setContextPanel(true)")
                    await asyncio.sleep(0.25)
                    for mode in ("list", "grid", "gallery"):
                        await tab.click(f'[data-cp-view="{mode}"]')
                        await tab.wait('!byId("cp-files").hasAttribute("aria-busy")')
                        await tab.js("document.activeElement.blur()")
                        assert await tab.js(
                            '!byId("cp-file-items").querySelector(".cp-file-attach")'
                        )
                        assert await tab.js(
                            '[...byId("cp-file-items").querySelectorAll(".cp-file")].every('
                            'row=>row.querySelectorAll("button").length===1 && '
                            'row.querySelector("button").matches(".cp-file-preview"))'
                        )
                        if width <= 768:
                            assert await tab.js('matchMedia("(any-pointer: coarse)").matches')
                        if mode == "gallery":
                            tiles = await tab.js("""[...document.querySelectorAll(
                              '#cp-file-items .cp-file')].map(tile=>{
                              const art=tile.querySelector('.file-artwork').getBoundingClientRect(),
                                rect=tile.getBoundingClientRect();
                              return {square:Math.abs(art.width-art.height)<1,
                                compact:Math.abs(rect.height-art.height-2)<1,
                                metadata:getComputedStyle(tile.querySelector('.file-secondary')).display,
                                position:getComputedStyle(tile.querySelector('.file-name-group')).position};})""")
                            assert len(tiles) == 3 and all(
                                t["square"] and t["compact"] and t["metadata"] == "none"
                                and t["position"] == "absolute" for t in tiles
                            ), (width, tiles)
                        fits = await tab.js("""(()=>{
                          const p=byId('inspector'),r=p.getBoundingClientRect();
                          return {page:document.documentElement.scrollWidth<=innerWidth,
                            panel:p.scrollWidth<=p.clientWidth+1,left:r.left,right:r.right,
                            toggle:byId('inspector-toggle').getBoundingClientRect().width>0};})()""")
                        assert fits["page"] and fits["panel"] and fits["toggle"], (
                            width,
                            mode,
                            fits,
                        )
                        assert fits["left"] >= 0 and fits["right"] <= width, fits
                        if height < 600:
                            assert await tab.js('byId("cp-files").clientHeight>=100')
                        layouts.append((theme, width, mode))
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (OUT / f"library-{theme}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                    await tab.click("#cp-tab-agent")
                    await tab.click("#cp-tab-activity")
                    assert await tab.js('byId("cp-task-label").textContent') == "Fail"
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (OUT / f"inspector-{theme}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                    await tab.click("#cp-tab-library")
            await tab.js("window.beforeContextReload=true")
            await tab.command("Page.reload")
            await tab.wait(
                "!window.beforeContextReload && window.ContextPanel && latest?.context_panel"
            )
            await tab.wait(
                'typeof latest!=="undefined" && latest?.context_panel && window.ContextPanel'
            )
            assert await tab.js('byId("cp-tab-library").getAttribute("aria-selected")') == "true"
            assert await tab.js('byId("cp-file-items").dataset.view') == "gallery"
            await tab.wait('!document.querySelector(".shell").inert')
            await tab.js('byId("cp-tab-library").focus()')
            await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "ArrowLeft"})
            assert await tab.js("document.activeElement.id") == "cp-tab-agent", await tab.js(
                '({focus:document.activeElement.id,inert:byId("inspector").inert,open:contextPanelOpen})'
            )
            await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape"})
            assert await tab.js(
                'byId("inspector").inert && document.activeElement.id==="inspector-toggle"'
            )
            await tab.js(
                'setContextPanel(true);byId("cp-tab-activity").click();'
                "window.oldSession=latest.session_id;ChatAttachmentsUI.clear()"
            )
            await tab.js('switchSession("")')
            await tab.wait("latest.session_id!==oldSession")
            assert (
                await tab.js('byId("cp-activity").querySelectorAll("[data-event-key]").length') == 0
            )
            assert await tab.js('byId("cp-status").textContent') == "Idle"
            await tab.js("switchSession(oldSession)")
            await tab.wait("latest.session_id===oldSession")
            assert await tab.js('byId("cp-activity").textContent.includes("read_file")')
            await tab.click("#logout")
            await tab.wait("!authenticated")
            assert await tab.js('!byId("cp-activity").textContent.includes("read_file")')
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "real_execution_lifecycle": True,
                        "approval_shared_state": True,
                        "replay_order_dedup_expansion": True,
                        "session_isolation": True,
                        "authorized_file_inspection": True,
                        "library_scope_preview": True,
                        "native_artifact_drag_and_attach": True,
                        "context_attach_buttons_removed": True,
                        "mobile_composer_library_picker": True,
                        "gallery_matches_library": True,
                        "responsive_layouts": len(layouts),
                        "keyboard": True,
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

    with tempfile.TemporaryDirectory(prefix="klaude-context-panel-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        app.agent.tools = {
            tool.name: tool for tool in build_tools(app.agent.workspace) if tool.name == "read_file"
        }
        app.agent.gate.policies.update(read_file="ask", request_user_input="allow")
        app.allow_approvals = app.allow_user_input_tool = True
        runtime = Runtime()
        app.agent.runtime = app.agent.ollama = runtime
        (root / "note.txt").write_text("PRIVATE read result\n")
        library = LibraryManagement(cfg, root)
        files = {
            key: library.artifacts.import_bytes(
                f"PRIVATE {key} document".encode(), "document", f"{key}.txt"
            )
            for key in ("current", "shared", "other")
        }
        image = io.BytesIO()
        Image.new("RGB", (48, 32), "purple").save(image, "PNG")
        files["image"] = library.artifacts.import_bytes(image.getvalue(), "media", "picture.png")
        for key, size, color in (("portrait", (32, 64), "teal"), ("older", (64, 32), "orange")):
            image = io.BytesIO()
            Image.new("RGB", size, color).save(image, "PNG")
            files[key] = library.artifacts.import_bytes(image.getvalue(), "media", f"{key}.png")
        with library.artifacts.database(write=True) as db:
            db.execute(
                "UPDATE artifacts SET session=? WHERE id=?",
                (app.session_id, files["current"]["id"]),
            )
            db.execute("UPDATE artifacts SET created=? WHERE id=?", (
                datetime(2025, 1, 15, tzinfo=UTC).timestamp(), files["older"]["id"],
            ))
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts, library=library, staging_dir=root / "staging")
        host.local_models = lambda: []
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome, runtime, files), 150))
        finally:
            runtime.release.set()
            host.stop()
            serving.join(3)


if __name__ == "__main__":
    main()

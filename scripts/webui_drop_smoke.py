"""Real Chrome file drags into Chat and Uploads using isolated local stores.

Run: .venv/bin/python scripts/webui_drop_smoke.py
No owner-profile changes, external models or external network requests.
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
from PIL import Image
from webui_control_smoke import Fixture, Tab

OUT = Path("/tmp/klaude-file-drop-preview")


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
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js('byId("login-password").value=' + json.dumps(
                host.accounts.initial_password()
            ) + ';byId("account-login").requestSubmit()')
            await tab.wait('latest?.attachments && window.FileDropUI && window.ChatAttachmentsUI')
            await tab.js('''window.dropFetch=fetch;window.dropUploads=0;
              window.fetch=(input,options)=>{
                if(String(input)==='/api/v1/uploads') dropUploads++;
                return dropFetch(input,options);
              };''')

            async def drag(names, kind="hover"):
                point = await tab.js('''(()=>{
                  const r=byId('main-content').getBoundingClientRect();
                  return {x:r.left+r.width/2,y:r.top+r.height/2};
                })()''')
                data = {"items": [], "files": [str(root / name) for name in names],
                        "dragOperationsMask": 1}
                for event in (() if kind == "cancel" else ("dragEnter", "dragOver")):
                    await tab.command("Input.dispatchDragEvent", {
                        "type": event, **point, "data": data,
                    })
                if kind != "hover":
                    await tab.command("Input.dispatchDragEvent", {
                        "type": "drop" if kind == "drop" else "dragCancel", **point, "data": data,
                    })

            layouts = []
            for view in ("chat", "library"):
                await tab.js("showView(" + json.dumps(view) + ")")
                for theme in ("light", "dark"):
                    await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                    for width, height in ((1440, 900), (768, 844), (390, 640), (320, 480)):
                        await tab.command("Emulation.setDeviceMetricsOverride", {
                            "width": width, "height": height, "deviceScaleFactor": 1,
                            "mobile": width < 600,
                        })
                        # Let responsive drawer/view transitions settle before the OS drag.
                        await asyncio.sleep(.3)
                        await drag(["first.txt"])
                        await asyncio.sleep(.35)
                        state = await tab.js('''(()=>{
                          const overlay=document.querySelector('.file-drop-overlay');
                          const r=overlay.getBoundingClientRect(),card=overlay.firstElementChild;
                          const c=card.getBoundingClientRect(),host=byId('main-content')
                            .getBoundingClientRect();
                          return {visible:!overlay.hidden && overlay.dataset.allowed==='true',
                            fits:r.left>=host.left && r.right<=host.right && r.top>=host.top &&
                              r.bottom<=host.bottom && c.left>=r.left && c.right<=r.right &&
                              c.top>=r.top && c.bottom<=r.bottom &&
                              overlay.scrollWidth<=overlay.clientWidth &&
                              document.documentElement.scrollWidth<=innerWidth,
                            live:overlay.getAttribute('role')==='status',
                            noUpload:dropUploads===0};
                        })()''')
                        assert all(state.values()), (view, theme, width, state, await tab.js(
                            '({currentView,librarySection,dialogs:[...document.querySelectorAll('
                            '"dialog[open]")].map(node=>node.id)})'
                        ))
                        capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (OUT / f"{view}-{theme}-{width}.png").write_bytes(
                            base64.b64decode(capture["data"])
                        )
                        await drag(["first.txt"], "cancel")
                        await tab.wait('document.querySelector(".file-drop-overlay").hidden')
                        layouts.append([view, theme, width, height])
            await tab.command("Emulation.clearDeviceMetricsOverride")
            await tab.js("showView('chat');prompt.value='Keep my draft'")
            await asyncio.sleep(.3)
            await drag(["first.txt"])
            assert await tab.js('''(()=>{
              const data=new DataTransfer();data.items.add(new File(['a'],'first.txt'));
              FileDropUI.reset();
              byId('chat-view').dispatchEvent(new DragEvent('dragenter',{
                bubbles:true,cancelable:true,dataTransfer:data}));
              prompt.dispatchEvent(new DragEvent('dragenter',{
                bubbles:true,cancelable:true,dataTransfer:data}));
              prompt.dispatchEvent(new DragEvent('dragleave',{
                bubbles:true,cancelable:true,dataTransfer:data,relatedTarget:byId('send'),
                clientX:100,clientY:100}));
              return !document.querySelector('.file-drop-overlay').hidden;
            })()''')
            await tab.js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
            assert await tab.js('document.querySelector(".file-drop-overlay").hidden')
            # Ordinary text/link drags retain native insertion and never show a file target.
            assert await tab.js('''(()=>{
              const data=new DataTransfer();data.setData('text/plain','A dragged sentence');
              data.setData('text/uri-list','https://example.com/');
              return ['dragenter','dragover','drop'].every(type=>prompt.dispatchEvent(
                new DragEvent(type,{bubbles:true,cancelable:true,dataTransfer:data}))) &&
                document.querySelector('.file-drop-overlay').hidden;
            })()''')
            await drag(["first.txt", "second.md"], "drop")
            await tab.wait('ChatAttachmentsUI.ids().length===2 && !ChatAttachmentsUI.preparing()')
            assert await tab.js('prompt.value==="Keep my draft" && latest.messages.length===0 && '
                                '!byId("attach-dialog").open && '
                                'byId("chat-attachments").querySelectorAll(".attachment-card")'
                                '.length===2')
            assert not host.library.listing()["items"], "Chat drops must not import Library files"
            count = await tab.js("dropUploads")
            await drag(["first.txt", "second.md", "third.txt"], "drop")
            await tab.wait('byId("chat-attachment-status").textContent.includes("four files")')
            assert await tab.js("dropUploads===" + str(count))
            await tab.js("ChatAttachmentsUI.clear()")
            await drag(["oversized.txt"], "drop")
            await tab.wait('byId("chat-attachment-status").textContent.includes("32 MiB")')
            assert await tab.js("dropUploads===" + str(count))
            await drag(["one.png", "two.png", "three.png"], "drop")
            await tab.wait('!ChatAttachmentsUI.preparing() && ChatAttachmentsUI.ids().length===3')
            await drag(["four.png"], "drop")
            await tab.wait('!ChatAttachmentsUI.preparing() && ChatAttachmentsUI.ids().length===4')
            assert await tab.js('byId("chat-attachments").querySelectorAll(".attachment-card")'
                                '.length===4')
            count = await tab.js("dropUploads")
            await drag(["one.png"])
            assert await tab.js('document.querySelector(".file-drop-overlay").dataset.allowed'
                                '==="false" && document.querySelector(".file-drop-overlay")'
                                '.textContent.includes("Remove an attachment")')
            await drag(["one.png"], "drop")
            assert await tab.js("dropUploads===" + str(count) +
                                " && ChatAttachmentsUI.ids().length===4")
            await tab.js("ChatAttachmentsUI.clear()")
            # Folder drops are rejected before any upload (including mixed drops).
            count = await tab.js("dropUploads")
            await drag(["folder"], "drop")
            await tab.wait('byId("chat-attachment-status").textContent'
                           '.includes("instead of folders")')
            assert await tab.js("dropUploads===" + str(count))
            # A rejected upload preserves the draft and reports an inline actionable error.
            await tab.js('''window.liveDropFetch=fetch;
              window.fetch=(input,options)=>String(input)==='/api/v1/uploads' ?
                Promise.resolve(new Response(JSON.stringify({error:{
                  message:'Fixture upload failed'}}),
                  {status:503,headers:{'Content-Type':'application/json'}})) :
                liveDropFetch(input,options);''')
            await drag(["first.txt"], "drop")
            await tab.wait('!ChatAttachmentsUI.preparing() && '
                           'byId("chat-attachment-status").textContent.includes("upload failed")')
            assert await tab.js('prompt.value==="Keep my draft" && !ChatAttachmentsUI.ids().length')
            await tab.js("window.fetch=liveDropFetch")
            # A delayed prepared attachment cannot leak into a subsequently cleared chat.
            await tab.js('''window.fetch=async(input,options)=>{
              const result=await liveDropFetch(input,options);
              if(String(input)==='/api/v1/uploads') await new Promise(resolve=>{
                window.releaseDropUpload=resolve;
              });return result;
            };''')
            await drag(["first.txt"], "drop")
            await tab.wait('typeof releaseDropUpload==="function"')
            await tab.js("document.dispatchEvent(new Event('klaude-chat-session-changed'));"
                         "releaseDropUpload();window.fetch=liveDropFetch")
            await tab.wait("!ChatAttachmentsUI.preparing() && !ChatAttachmentsUI.ids().length")

            await tab.js("showView('library')")
            await tab.wait("librarySection==='files'")
            # A failed upload retains the first file and the batch for an explicit retry.
            await tab.js('''window.fetch=(input,options)=>String(input)==='/api/v1/uploads' ?
              Promise.resolve(new Response(JSON.stringify({error:{
                message:'Fixture import failed'}}),
                {status:503,headers:{'Content-Type':'application/json'}})) :
              liveDropFetch(input,options);''')
            await drag(["first.txt", "second.md", "third.txt"], "drop")
            await tab.wait('importDialog.open && byId("artifact-import-status").textContent'
                           '.includes("Fixture import failed")')
            assert await tab.js('byId("artifact-file").files[0].name==="first.txt" && '
                                'droppedImports.files.length===3')
            await tab.js('window.fetch=liveDropFetch;byId("artifact-import").requestSubmit()')
            await tab.wait('byId("domain-review").open && '
                           'byId("domain-review-status").textContent.includes("File 1 of 3")')
            assert not host.library.listing()["items"], "Drop bypassed import confirmation"
            await tab.click("#domain-review-confirm")
            await tab.wait('byId("domain-review").open && '
                           'byId("domain-review-status").textContent.includes("File 2 of 3")')
            await tab.click("#domain-review-cancel")
            await tab.wait('!byId("domain-review").open && droppedImports===null')
            for _ in range(100):
                items = host.library.listing()["items"]
                if items:
                    break
                await asyncio.sleep(.05)
            assert [item["filename"] for item in items] == ["first.txt"], items
            # Complete a two-file batch, with independent exact confirmations.
            await drag(["second.md", "third.txt"], "drop")
            for index in (1, 2):
                await tab.wait('byId("domain-review").open && '
                               'byId("domain-review-status").textContent.includes('
                               + json.dumps(f"File {index} of 2") + ')')
                await tab.click("#domain-review-confirm")
            await tab.wait('!byId("domain-review").open && droppedImports===null')
            await tab.wait("filePage?.total===3")
            # A lost submit acknowledgement must not advance or replay the remaining files.
            await tab.js('''window.dropDomainRequest=domainRequest;
              domainRequest=async(path,method,body,options)=>{
                const result=await dropDomainRequest(path,method,body,options);
                if(path==='/api/v1/library/submit') throw new Error('Fixture acknowledgement lost');
                return result;
              };''')
            await drag(["uncertain.txt", "never.txt"], "drop")
            await tab.wait('reviewDialog.open && byId("domain-review-status").textContent'
                           '.includes("File 1 of 2")')
            await tab.click("#domain-review-confirm")
            await tab.wait('byId("domain-review-status").textContent'
                           '.includes("Fixture acknowledgement lost")')
            assert await tab.js('reviewDialog.open && droppedImports.index===0 && '
                                '!droppedImports.accepted')
            await tab.click("#domain-review-cancel")
            await tab.wait("droppedImports===null && !reviewDialog.open")
            await tab.js("domainRequest=dropDomainRequest")
            # Generated and unrelated destinations never receive Uploads imports.
            await tab.click('#library-sections [data-section="outputs"]')
            await drag(["first.txt"])
            assert await tab.js('document.querySelector(".file-drop-overlay").hidden')
            await drag(["first.txt"], "drop")
            assert await tab.js('!byId("artifact-import-panel").open && '
                                '!byId("domain-review").open')
            await tab.js("showView('settings')")
            await drag(["first.txt"], "drop")
            assert await tab.js('document.querySelector(".file-drop-overlay").hidden')
            await tab.js("showView('chat')")
            await drag(["first.txt"])
            await tab.js("showView('settings')")
            assert await tab.js('document.querySelector(".file-drop-overlay").hidden')
            await tab.js("showView('chat');window.releaseLogoutUpload=null;"
                         "window.fetch=async(input,options)=>{"
                         "const result=await liveDropFetch(input,options);"
                         "if(String(input)==='/api/v1/uploads') await new Promise(resolve=>{"
                         "window.releaseLogoutUpload=resolve;});return result;};")
            await drag(["first.txt"], "drop")
            await tab.wait('typeof releaseLogoutUpload==="function"')
            await tab.click("#logout")
            await tab.wait("!authenticated")
            await tab.js("releaseLogoutUpload()")
            await tab.wait("!ChatAttachmentsUI.preparing() && !ChatAttachmentsUI.ids().length")
            await drag(["first.txt"], "drop")
            assert await tab.js('document.querySelector(".file-drop-overlay").hidden')
            assert not host.transfers._records
            assert not host.attachments._items
            assert not tab.errors, tab.errors
            print(json.dumps({"real_file_drags": True, "overlay_layouts": len(layouts),
                              "chat_limits_errors_drafts": True, "stale_chat_cleanup": True,
                              "reviewed_library_batches": True, "cancel_stops_remaining": True,
                              "failed_import_retry_and_uncertain_submit": True,
                              "text_folder_and_page_guards": True, "logout_cleanup": True,
                              "console_errors": 0, "screenshots": str(OUT)}, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or shutil.which("chromium")
    if not chrome:
        chrome = str(next((Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.unit.test_webhost import _app

    with tempfile.TemporaryDirectory(prefix="klaude-file-drop-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        runtime = Fixture()
        app.agent.runtime = app.agent.ollama = runtime
        for name in ("first.txt", "second.md", "third.txt", "uncertain.txt", "never.txt"):
            (root / name).write_text("Private dropped text in " + name)
        for name in ("one.png", "two.png", "three.png", "four.png"):
            Image.new("RGB", (24, 24), "purple").save(root / name)
        (root / "folder").mkdir()
        (root / "folder" / "nested.txt").write_text("Folders are not expanded")
        with (root / "oversized.txt").open("wb") as stream:
            stream.truncate(33 * 1024 * 1024)
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts, library=LibraryManagement(cfg, root),
                            staging_dir=root / "staging")
        host.local_models = lambda: []
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome), 100))
        finally:
            runtime.release.set()
            host.stop()
            serving.join(3)


if __name__ == "__main__":
    main()

"""Library dropdown-chip interaction and responsive checks in isolated Chrome."""

from __future__ import annotations

import asyncio
import io
import json
import subprocess
from urllib.request import Request, urlopen

import websockets
import webui_sessions_smoke as fixture
from PIL import Image
from webui_control_smoke import Tab


async def verify(host, root, chrome):
    artifacts = host.library.artifacts
    artifacts.import_bytes(b"Saved note", "document", "saved.txt")
    archived = artifacts.import_bytes(b"Archived note", "document", "archived.txt")
    artifacts.change(archived["id"], archived["revision"], "archive")
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "teal").save(image, format="PNG")
    artifacts.import_bytes(image.getvalue(), "media", "picture.png")
    artifacts.store_report("saved-report.md", "# Saved report", job="saved")
    archived = artifacts.store_report("archived-report.md", "# Archived report", job="archived")
    artifacts.change(archived["id"], archived["revision"], "archive")
    profile = root / "chrome-filter-chips"
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
        async with websockets.connect(target["webSocketDebuggerUrl"]) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")

            async def click(selector):
                point = await tab.js("(()=>{const n=document.querySelector(" +
                                     json.dumps(selector) + ");n.scrollIntoView({block:'nearest'});"
                                     "const r=n.getBoundingClientRect();"
                                     "return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
                await tab.wait("document.querySelector(" + json.dumps(selector) + ")"
                               ".contains(document.elementFromPoint(" + str(point["x"]) + "," +
                               str(point["y"]) + "))")
                for kind in ["mousePressed", "mouseReleased"]:
                    await tab.command("Input.dispatchMouseEvent", {
                        "type": kind, **point, "button": "left", "clickCount": 1,
                    })

            async def key(value):
                for kind in ["keyDown", "keyUp"]:
                    await tab.command("Input.dispatchKeyEvent", {
                        "type": kind, "key": value,
                        "windowsVirtualKeyCode": {"Enter": 13, "Escape": 27,
                                                  "ArrowDown": 40, "End": 35}.get(value, 0),
                        **({"text": "\r"} if kind == "keyDown" and value == "Enter" else {}),
                    })

            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait("typeof latest!=='undefined' && latest?.session_id")
            await tab.wait("document.documentElement.dataset.startup==='ready' && "
                           "!document.querySelector('.shell').inert")
            await tab.js("document.fonts.ready")
            await tab.js("showView('library')")
            cases = []
            for width in [320, 390, 768, 1440]:
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 760, "deviceScaleFactor": 1, "mobile": width < 600,
                })
                for section in ["files", "outputs"]:
                    await click(f'[data-section="{section}"]')
                    await tab.wait("librarySection===" + json.dumps(section))
                    assert await tab.js("!byId('file-options-toggle') && "
                                        "['kind','status','sort'].every(k=>"
                                        "byId('artifact-'+k+'-chip').getClientRects().length)")
                    await click("#artifact-kind-chip")
                    await tab.wait("byId('artifact-kind-menu').matches(':popover-open')")
                    await click('#artifact-kind-menu [data-value="document"]')
                    saved_name = "saved.txt" if section == "files" else "saved-report.md"
                    await tab.wait("fileKind==='document' && filePage?.total===1 && "
                                   "filePage.items[0].name===" + json.dumps(saved_name))
                    await tab.js("byId('artifact-status-chip').focus()")
                    await key("ArrowDown")
                    await key("End")
                    await key("Enter")
                    archived_name = "archived.txt" if section == "files" else "archived-report.md"
                    await tab.wait("fileStatus==='archived' && filePage?.total===1 && "
                                   "filePage.items[0].name===" + json.dumps(archived_name))
                    await click("#artifact-sort-chip")
                    await tab.wait("byId('artifact-sort-menu').matches(':popover-open')")
                    await key("End")
                    await key("Enter")
                    await tab.wait("byId('artifact-sort').value==='type'")
                    await click("#artifact-sort-chip")
                    await key("Escape")
                    assert await tab.js("!byId('artifact-sort-menu').matches(':popover-open') && "
                                        "document.activeElement===byId('artifact-sort-chip')")
                    await click("#artifact-sort-chip")
                    await click("#artifact-sort-chip")
                    assert await tab.js("!byId('artifact-sort-menu').matches(':popover-open')")
                    await click("#artifact-sort-chip")
                    await key("n")
                    assert await tab.js("document.activeElement.dataset.value==='name'")
                    await key("n")
                    assert await tab.js("document.activeElement.dataset.value==='name_desc'")
                    await key("Escape")
                    await click("#artifact-kind-chip")
                    bounds = await tab.js("(()=>{const r=byId('artifact-kind-menu')"
                                          ".getBoundingClientRect();return r.left>=0 && "
                                          "r.right<=innerWidth && r.top>=0 && "
                                          "r.bottom<=innerHeight})()")
                    assert bounds
                    await click("#artifact-query")
                    assert await tab.js("!byId('artifact-kind-menu').matches(':popover-open')")
                    assert await tab.js("document.documentElement.scrollWidth<=innerWidth && "
                                        "[...document.querySelectorAll('.library-filter-chip')]"
                                        ".every(n=>{const r=n.getBoundingClientRect(),"
                                        "f=n.firstChild.getBoundingClientRect();"
                                        "return r.height>=48 && "
                                        "r.width>=48 && f.height===32})")
                    assert await tab.js("(()=>{const row=byId('file-option-fields'),"
                                        "ys=[...row.querySelectorAll('.library-filter-chip')]"
                                        ".map(n=>n.getBoundingClientRect().top);"
                                        "return Math.max(...ys)-Math.min(...ys)<1 && "
                                        "row.scrollHeight<=row.clientHeight && "
                                        "getComputedStyle(row).scrollbarWidth==='none'})()")
                    cases.append({"width": width, "section": section})
                    # Reset via the existing native state seam for the next case.
                    await tab.js("for(const [id,value] of [['kind','all'],['status','saved'],"
                                 "['sort','newest']]){const s=byId('artifact-'+id);s.value=value;"
                                 "s.dispatchEvent(new Event('change'))}")
            await click("#artifact-kind-chip")
            await tab.js("showView('chat')")
            assert await tab.js("!document.querySelector('.library-filter-menu:popover-open')")
            assert not tab.errors, tab.errors
            print(json.dumps({"dropdown_chip_cases": cases, "console_errors": 0}))
    except Exception:
        if "tab" in locals():
            print(await tab.js("JSON.stringify({section:librarySection,kind:fileKind,"
                               "status:fileStatus,sort:byId('artifact-sort').value,"
                               "page:filePage,focus:document.activeElement?.outerHTML,"
                               "open:[...document.querySelectorAll(':popover-open')].map(n=>n.id)})"))
        raise
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    fixture.verify = verify
    fixture.main()

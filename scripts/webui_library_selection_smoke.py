"""Isolated Chrome checks for Library selection and reviewed bulk deletion."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from PIL import Image
from webui_control_smoke import Tab
from webui_model_store_smoke import main


async def verify(host, root):
    store = host.library.artifacts
    for index in range(27):
        store.import_bytes(f"Selection {index}".encode(), "document", f"upload-{index:02}.txt")
    image = io.BytesIO()
    Image.new("RGB", (30, 20), "teal").save(image, format="PNG")
    store.import_bytes(image.getvalue(), "media", "upload-image.png")
    for index in range(3):
        store.store_report(f"generated-{index}.md", f"Report {index}", job=f"fixture-{index}")
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell")))
    profile = root / "chrome"
    process = subprocess.Popen([
        chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    evidence = Path("/tmp/klaude-library-selection-evidence")
    evidence.mkdir(exist_ok=True)
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
            await tab.wait("typeof authenticated!=='undefined' && authenticated && latest && "
                           "document.documentElement.dataset.startup==='ready'")
            await tab.js("showView('library')")
            await tab.wait("filePage?.total===28 && !byId('library-edit').disabled")
            assert await tab.js("byId('library-edit').parentElement.nextElementSibling.id==="
                                "'library-refresh'")
            assert await tab.js("""(() => {
              const edit=byId('library-edit');
              const view=document.querySelector('[data-file-view="list"]');
              const grid=document.querySelector('[data-file-view="grid"]').getBoundingClientRect();
              const gallery=document.querySelector('[data-file-view="gallery"]')
                .getBoundingClientRect();
              const a=edit.getBoundingClientRect(), b=view.getBoundingClientRect();
              return a.width===b.width && a.height===b.height &&
                Math.abs((a.left-gallery.right)-(grid.left-b.right))<0.5 &&
                getComputedStyle(edit).backgroundColor===getComputedStyle(view).backgroundColor;
            })()""")
            await tab.click("#library-edit")
            await asyncio.sleep(.3)
            assert await tab.js("getComputedStyle(byId('library-edit')).backgroundColor==="
                                "getComputedStyle(document.querySelector("
                                "'[data-file-view=\"grid\"]')).backgroundColor")
            assert await tab.js("!byId('library-selection').hidden && "
                                "byId('library-delete-selected').disabled")
            # Native keyboard activation selects a file without opening its preview.
            await tab.js("document.querySelector('#library-items .file-open').focus()")
            for kind in ("keyDown", "keyUp"):
                await tab.command("Input.dispatchKeyEvent", {
                    "type": kind, "key": " ", "code": "Space", "windowsVirtualKeyCode": 32,
                })
            await tab.wait("fileSelection.size===1")
            assert await tab.js("!artifactDialog.open && "
                                "document.activeElement.ariaPressed==='true'")
            await tab.js("[...byId('library-items').querySelectorAll("
                         "'.file-open[aria-pressed=\"false\"]')].forEach(b=>b.click())")
            await tab.wait("fileSelection.size===filePage.items.length")
            selected = await tab.js("fileSelection.size")
            await tab.click("#library-next")
            await tab.wait("libraryOffset>0 && filePage.offset===libraryOffset")
            await tab.click("#library-items .file-open")
            assert await tab.js(f"fileSelection.size==={selected + 1}")
            await tab.click("#library-delete-selected")
            await tab.wait("reviewDialog.open")
            assert await tab.js(
                "byId('domain-review-title').textContent.includes('selected files')")
            await tab.command("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27,
            })
            await tab.command("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27,
            })
            await tab.wait("!reviewDialog.open")
            assert store.listing("all", source="input", include_total=True)["total"] == 28
            assert await tab.js(f"fileEditing && fileSelection.size==={selected + 1}")
            await tab.command("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27,
            })
            await tab.command("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27,
            })
            assert await tab.js("fileSelection.size===0 && !fileEditing && "
                                "document.activeElement===byId('library-edit')")
            # Exercise real mouse range selection, reversal, Shift-click and deselection.
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 1440, "height": 1100, "deviceScaleFactor": 1, "mobile": False,
            })
            await tab.click('[data-file-view="list"]')
            await tab.wait("fileView==='list' && filePage?.items.length>=4 && "
                           "byId('library-items').dataset.view==='list'")
            assert await tab.js("""(() => {
              const header=byId('library-items').querySelector('.file-list-header');
              const row=byId('library-items').querySelector('.file-open');
              const labels=[...header.querySelectorAll('button')];
              const fields=['.file-name-group','.file-type','.file-size','.file-added']
                .map(selector=>row.querySelector(selector));
              return header.getBoundingClientRect().height<=45 && labels.every((label,i)=>
                Math.abs(label.getBoundingClientRect().left +
                  parseFloat(getComputedStyle(label).paddingLeft) -
                  fields[i].getBoundingClientRect().left)<1);
            })()""")
            await tab.click(".file-list-header button:first-child")
            await tab.wait("byId('artifact-sort').value==='name' && "
                           "!!document.querySelector("
                           "'.file-list-header button:first-child.is-sorted')")
            await tab.click(".file-list-header button:first-child")
            await tab.wait("byId('artifact-sort').value==='name_desc' && "
                           "document.querySelector('.file-list-header button')"
                           "?.textContent.includes('↑')")
            await tab.js("byId('artifact-sort').value='newest'; "
                         "libraryOffset=24; rememberLibraryLocation(); loadLibrary()")
            await tab.wait("filePage?.offset===24 && filePage.items.length>=4 && "
                           "byId('library-items').getAttribute('aria-busy')==='false' && "
                           "byId('library-items').dataset.contentKey?.includes('newest')")
            await tab.click("#library-edit")
            await tab.js("byId('library-view').scrollTop=0")
            points = await tab.js("""[...document.querySelectorAll('#library-items .file-open')]
              .slice(0,4).map(b=>{const r=b.getBoundingClientRect();
                return {x:r.left+r.width/2,y:r.top+r.height/2}})""")
            async def mouse(kind, point, *, buttons=0, modifiers=0):
                await tab.command("Input.dispatchMouseEvent", {
                    "type": kind, **point, "button": "left", "buttons": buttons,
                    "clickCount": 1, "modifiers": modifiers,
                })
            await mouse("mousePressed", points[0], buttons=1)
            assert await tab.js("getComputedStyle(document.querySelector("
                                "'#library-items .file-open:active')).transform==='none'")
            await mouse("mouseMoved", points[3], buttons=1)
            assert await tab.js("fileSelection.size===4")
            await mouse("mouseMoved", points[1], buttons=1)
            assert await tab.js("fileSelection.size===2")
            await mouse("mouseReleased", points[1])
            await asyncio.sleep(.05)
            assert await tab.js("fileSelection.size===2 && !artifactDialog.open")
            await mouse("mousePressed", points[3], buttons=1, modifiers=8)
            await mouse("mouseReleased", points[3], modifiers=8)
            await asyncio.sleep(.05)
            assert await tab.js("fileSelection.size===4")
            await mouse("mousePressed", points[0], buttons=1)
            await mouse("mouseMoved", points[2], buttons=1)
            await mouse("mouseReleased", points[2])
            await asyncio.sleep(.05)
            drag_result = await tab.js("({size:fileSelection.size, "
                                       "selected:filePage.items.slice(0,4)"
                                       ".map(item=>fileSelection.has(item.id))})")
            assert drag_result == {"size": 1, "selected": [False, False, False, True]}, drag_result
            await tab.click("#library-edit-done")
            await tab.click("#library-previous")
            await tab.wait("libraryOffset===0 && filePage?.items.length===24")
            await tab.click('[data-file-view="grid"]')
            await tab.wait("fileView==='grid' && byId('library-items').dataset.view==='grid'")
            await tab.click("#library-edit")
            points = await tab.js("""[...document.querySelectorAll('#library-items .file-open')]
              .slice(0,3).map(b=>{const r=b.getBoundingClientRect();
                return {x:r.left+r.width/2,y:r.top+r.height/2}})""")
            await mouse("mousePressed", points[0], buttons=1)
            await mouse("mouseMoved", points[2], buttons=1)
            await mouse("mouseReleased", points[2])
            await asyncio.sleep(.05)
            assert await tab.js("fileSelection.size===3")
            await tab.click("#library-edit-done")
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 900, "height": 740, "deviceScaleFactor": 1, "mobile": False,
            })
            await tab.click('[data-file-view="list"]')
            await tab.wait("fileView==='list' && byId('library-items').dataset.view==='list'")
            await tab.click("#library-edit")
            await tab.js("byId('library-view').scrollTop=0")
            coords = await tab.js("""(() => {
              const row=document.querySelector('#library-items .file-open').getBoundingClientRect();
              const pane=byId('library-view').getBoundingClientRect();
              return {start:{x:row.left+20,y:row.top+row.height/2},
                edge:{x:row.left+20,y:pane.bottom-12}};
            })()""")
            await mouse("mousePressed", coords["start"], buttons=1)
            await mouse("mouseMoved", coords["edge"], buttons=1)
            await asyncio.sleep(.5)
            assert await tab.js("byId('library-view').scrollTop>0")
            await mouse("mouseReleased", coords["edge"])
            await tab.click("#library-edit-done")
            await tab.js("byId('library-view').scrollTop=0")
            # The same selection controls fit all views at phone and desktop widths.
            for theme in ("light", "dark"):
                await tab.js("applyAppearance(appearance={...appearance,theme:"
                             + json.dumps(theme) + "},true)")
                for width in (1440, 768, 390, 320):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": 740, "deviceScaleFactor": 1, "mobile": False,
                    })
                    for view in ("list", "grid", "gallery"):
                        await tab.click(f'[data-file-view="{view}"]')
                        await tab.wait(f"fileView==='{view}' && !!filePage && "
                                       "!!document.querySelector('#library-items .file-open') && "
                                       "byId('library-items').getAttribute('aria-busy')==='false'")
                        if not await tab.js("fileEditing"):
                            await tab.click("#library-edit")
                        await tab.click("#library-items .file-open")
                        await asyncio.sleep(.2)
                        geometry = await tab.js("""(() => {
                          const controls=[...document.querySelectorAll(
                            '.library-heading-actions button, #library-selection button')];
                          const selected=document.querySelector(
                            '#library-items .file-open[aria-pressed="true"]');
                          const art=selected?.querySelector('.file-artwork')
                            .getBoundingClientRect();
                          const mark=selected?.querySelector('.file-selection-mark > .icon')
                            .getBoundingClientRect();
                          const bar=byId('library-selection').getBoundingClientRect();
                          const pane=byId('library-view').getBoundingClientRect();
                          const rail=document.querySelector('.rail').getBoundingClientRect();
                          return {fits:document.documentElement.scrollWidth<=innerWidth,
                            controls:controls.filter(b=>b.getClientRects().length).every(b=>{
                              const r=b.getBoundingClientRect();
                              return r.left>=0 && r.right<=innerWidth && r.height>=44;
                            }), barFits:bar.left>=pane.left && bar.right<=pane.right &&
                              bar.bottom<=pane.bottom && (innerWidth>640 || bar.bottom<=rail.top),
                            selected:!!selected, centered:!!art && !!mark &&
                              Math.abs(art.left+art.width/2-mark.left-mark.width/2)<1 &&
                              Math.abs(art.top+art.height/2-mark.top-mark.height/2)<1};
                        })()""")
                        assert all(geometry.values()), (theme, width, view, geometry)
                        if width in (1440, 320):
                            shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                            (evidence / f"{theme}-{width}-{view}.png").write_bytes(
                                base64.b64decode(shot["data"]))
                        if width == 320 and view == "grid":
                            await tab.js("byId('library-view').scrollTop="
                                         "byId('library-view').scrollHeight")
                            await asyncio.sleep(.1)
                            assert await tab.js("""(() => {
                              const bar=byId('library-selection').getBoundingClientRect();
                              const pages=byId('library-pages').getBoundingClientRect();
                              return !byId('library-pages').hidden && pages.bottom <= bar.top;
                            })()""")
                            await tab.js("byId('library-view').scrollTop=0")
                        await tab.click("#library-edit-done")
            await tab.click('[data-section="outputs"]')
            await tab.click('[data-file-view="grid"]')
            await tab.wait("filePage?.total===3 && librarySection==='outputs'")
            await tab.click("#library-edit")
            await tab.js("[...byId('library-items').querySelectorAll('.file-open')]"
                         ".forEach(b=>b.click())")
            await tab.click("#library-delete-selected")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait("!reviewDialog.open && !fileEditing")
            for _ in range(100):
                if store.listing("all", source="output", include_total=True)["total"] == 0:
                    break
                await asyncio.sleep(.1)
            assert store.listing("all", source="output", include_total=True)["total"] == 0
            assert store.listing("all", source="input", include_total=True)["total"] == 28
            await tab.click('[data-section="files"]')
            await tab.click('[data-file-view="grid"]')
            await tab.wait("filePage?.total===28")
            await tab.click("#library-edit")
            await tab.click("#library-items .file-open")
            await tab.js("byId('artifact-query').value='upload-00'; "
                         "byId('artifact-filter').requestSubmit()")
            await tab.wait("filePage?.total===1")
            assert await tab.js("!fileEditing && fileSelection.size===0")
            await tab.click("#library-edit")
            await tab.click("#library-items .file-open")
            await tab.js("showView('chat')")
            assert await tab.js("!fileEditing && fileSelection.size===0")
            # Older running hosts offer clear restart guidance and cannot submit.
            await tab.js("latest.library_bulk_delete=false; renderFileToolbar()")
            assert await tab.js("byId('library-edit').disabled && "
                                "byId('library-edit').title.includes('Restart')")
            await tab.js("latest.library_bulk_delete=true; showView('library')")
            await tab.wait("!!filePage && !byId('library-edit').disabled")
            await tab.click("#library-edit")
            await tab.click("#library-items .file-open")
            await tab.click("#logout")
            await tab.wait("!authenticated")
            assert await tab.js("!fileEditing && fileSelection.size===0 && "
                                "byId('library-selection').hidden")
            assert not tab.errors, tab.errors
            print(json.dumps({"responsive_views": True, "keyboard_selection": True,
                              "cross_page_selection": True, "review_cancel_delete": True,
                              "cleanup": True, "browser_errors": 0, "evidence": str(evidence)}))
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    main(verify)

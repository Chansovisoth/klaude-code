"""Real Chrome checks for the paged Library list/grid/gallery and image viewer.

Run: uv run --frozen --offline python scripts/webui_library_browser_smoke.py
Uses an isolated profile, private fixtures, and no model/provider generation.
KLAUDE_TEST_GENERATED_FILTERS_ONLY=1 runs just the Generated filter checks.
KLAUDE_TEST_LIBRARY_VIEWS_ONLY=1 runs through responsive views and image previews.
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
from klaude_tools.toolkit import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from PIL import Image, ImageDraw
from webui_control_smoke import Tab

CODE_PREVIEW = ('# Unicode 設計 stays literal\ndef greeting(name):\n'
                '    markup = "<script>window.previewExecuted = true</script>"\n'
                '    return "Hello, " + name\n\nLONG_VALUE = "' + 'long value ' * 36 + '"\n')


async def verify_code_preview(tab, activate, output):
    async def open_file(name):
        await tab.js('byId("artifact-query").value=' + json.dumps(name) + ';'
                     'byId("artifact-filter").requestSubmit()')
        await tab.wait('filePage?.total===1 && filePage.items[0].name===' + json.dumps(name))
        await activate(".file-item button")
        await tab.wait('selectedArtifact?.name===' + json.dumps(name))

    await open_file("sample.py")
    await tab.wait('byId("artifact-wrap")?.ariaPressed==="true"')
    expected = json.dumps(CODE_PREVIEW)
    assert await tab.js('byId("artifact-preview").querySelector("pre").textContent===' + expected)
    assert await tab.js('!window.previewExecuted && '
                        '!byId("artifact-preview").querySelector("script")')
    for theme in ("light", "dark"):
        await tab.js('document.documentElement.dataset.theme=' + json.dumps(theme))
        for width in (1440, 768, 390, 320):
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": 760, "deviceScaleFactor": 1, "mobile": False,
            })
            await asyncio.sleep(.1)
            for wrapped in (False, True):
                await activate("#artifact-wrap" if wrapped else "#artifact-no-wrap")
                # Measure after the existing expressive press/release transform.
                await asyncio.sleep(.2)
                state = await tab.js('''(() => {
                  const preview=byId('artifact-preview'), text=preview.querySelector('pre');
                  const dialog=byId('artifact-detail'), toolbar=byId('image-toolbar');
                  const line=text.querySelector('.source-line-text');
                  return {whiteSpace:getComputedStyle(line).whiteSpace, width:innerWidth,
                    textColor:getComputedStyle(text).color,
                    themeColor:getComputedStyle(document.documentElement).color,
                    overflow:preview.scrollWidth>preview.clientWidth+1,
                    pageFits:document.documentElement.scrollWidth<=innerWidth &&
                      dialog.scrollWidth<=dialog.clientWidth,
                    controlsFit:[...toolbar.querySelectorAll('button')]
                      .filter(button=>button.getClientRects().length).every(button=>{
                        const r=button.getBoundingClientRect();
                        return r.left>=0 && r.right<=innerWidth && r.width>=44 && r.height>=44;
                      }), controls:[...toolbar.querySelectorAll('button')]
                        .filter(b=>b.getClientRects().length).map(b=>({id:b.id,
                          width:b.getBoundingClientRect().width,
                          height:b.getBoundingClientRect().height})),
                    scrollLeft:preview.scrollLeft};
                })()''')
                assert state["whiteSpace"] == ("pre-wrap" if wrapped else "pre"), state
                assert state["textColor"] == state["themeColor"], state
                assert state["overflow"] is not wrapped, state
                assert state["pageFits"] and state["controlsFit"], state
                if wrapped:
                    assert state["scrollLeft"] == 0, state
                else:
                    await tab.js('byId("artifact-preview").scrollLeft=100')
                    assert await tab.js('byId("artifact-preview").scrollLeft>0')
                    await tab.js('byId("artifact-preview").scrollLeft=0')
                if width in (1440, 320):
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    mode = "wrap" if wrapped else "no-wrap"
                    (output / f"code-{mode}-{theme}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
    # The clipboard API and HTTP fallback both copy only the displayed text.
    await tab.js('Object.defineProperty(navigator,"clipboard",{configurable:true,'
                 'value:{writeText:async text=>{window.copiedPreview=text}}})')
    await activate("#artifact-copy")
    await tab.wait('window.copiedPreview===' + expected)
    await tab.wait('byId("artifact-copy").textContent==="Copied"')
    await tab.js('Object.defineProperty(navigator,"clipboard",{value:undefined,configurable:true});'
                 'window.fallbackPreview="";document.addEventListener("copy",event=>{'
                 'fallbackPreview=event.clipboardData?.getData("text/plain")},{once:true})')
    await activate("#artifact-copy")
    await tab.wait('window.fallbackPreview===' + expected)
    clipboard_state = await tab.js('({temporary:!!document.querySelector(".clipboard-source"),'
                                   'focused:document.activeElement?.id})')
    assert clipboard_state == {"temporary": False, "focused": "artifact-copy"}, clipboard_state
    await tab.js('delete navigator.clipboard')
    await activate("#artifact-close")
    await open_file("sample.py")
    assert await tab.js('byId("artifact-wrap").ariaPressed==="true" && '
                        'byId("artifact-copy").textContent==="Copy"')
    await activate("#artifact-close")
    for name in ("image-49.webp", "unknown.bin"):
        await open_file(name)
        assert await tab.js('byId("preview-text-controls").hidden && '
                            '!byId("preview-text-controls").children.length')
        await activate("#artifact-close")


async def verify(host, root, chrome):
    profile = root / "chrome"
    output = Path("/tmp/klaude-library-browser-preview")
    output.mkdir(exist_ok=True)
    process = subprocess.Popen([
        chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            await asyncio.sleep(.05)
        port = int(active.read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")

            async def activate(selector):
                await tab.wait('!document.querySelector(".shell").inert')
                point = await tab.js('''(() => {
                  const button=document.querySelector(''' + json.dumps(selector) + ''');
                  button.scrollIntoView({block:'nearest'});
                  const r=button.getBoundingClientRect(), x=r.x+r.width/2, y=r.y+r.height/2;
                  if (!r.width || !r.height || !button.contains(document.elementFromPoint(x,y)))
                    throw Error('Control is obscured: '+button.id);
                  return {x,y};
                })()''')
                for event_type in ("mousePressed", "mouseReleased"):
                    await tab.command("Input.dispatchMouseEvent", {
                        "type": event_type, **point, "button": "left", "clickCount": 1,
                    })

            await tab.command("Page.addScriptToEvaluateOnNewDocument", {"source": '''
              window.fileLongTasks=[];
              new PerformanceObserver(list=>fileLongTasks.push(...list.getEntries()
                .map(entry=>entry.duration))).observe({type:'longtask',buffered:false});
            '''})
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False,
            })
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId !== "undefined" && !byId("local-access").hidden')
            await tab.js('byId("login-password").value=' + json.dumps(
                host.accounts.initial_password()
            ) + ';byId("account-login").requestSubmit()')
            await tab.wait('latest?.session_id && pollTimer !== null')
            # Keep the main Library unobscured when the viewport becomes a drawer layout.
            await tab.js('setContextPanel(false)')
            await tab.js('''window.fileRequests=[];window.originalFetch=window.fetch;
              window.fetch=(input,options)=>{fileRequests.push(String(input));
                return originalFetch(input,options);};''')
            await tab.click("#nav-library")
            await tab.wait('filePage?.items.length===24 && '
                           '!byId("library-items").classList.contains("is-loading")')
            assert await tab.js('filePage.total===1058 && fileView==="grid"')
            assert await tab.js('filePage.items.every(item=>item.kind!=="research") && '
                                '![...byId("artifact-kind").options].some(o=>o.value==="research")')
            await tab.js('window.uploadTypeChoices=[...byId("artifact-kind").options]'
                         '.map(option=>[option.value,option.textContent])')
            await activate('[data-section="outputs"]')
            await tab.wait('librarySection==="outputs" && filePage?.total===6 && '
                           '!byId("library-items").classList.contains("is-loading")')
            assert await tab.js('byId("file-add").hidden && fileParameters().source==="output" && '
                                'byId("artifact-query").value===""')
            assert await tab.js('JSON.stringify([...byId("artifact-kind").options]'
                                '.map(option=>[option.value,option.textContent]))'
                                '===JSON.stringify(uploadTypeChoices)')
            if os.environ.get("KLAUDE_TEST_GENERATED_FILTERS_ONLY") == "1":
                await activate('[data-file-view="list"]')
                await tab.js("document.fonts.ready")
                for width in (320, 390, 768, 1440):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": 820, "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    })
                    await asyncio.sleep(.2)
                    compact = await tab.js(
                        "byId('file-options-toggle').getClientRects().length>0"
                    )
                    if compact:
                        await activate("#file-options-toggle")
                    assert await tab.js('''['artifact-kind','artifact-status','artifact-sort']
                      .every(id=>byId(id).getClientRects().length>0 && !byId(id).disabled)''')
                    for kind, expected in (("document", "research"), ("media", "media")):
                        await tab.js(f"byId('artifact-kind').value='{kind}';"
                                     "byId('artifact-kind').dispatchEvent(new Event('change'))")
                        await tab.wait("filePage?.total===3 && filePage.items.every(item=>"
                                       f"item.kind==='{expected}')")
                    await tab.js("byId('artifact-kind').value='all';"
                                 "byId('artifact-kind').dispatchEvent(new Event('change'))")
                    await tab.wait("filePage?.total===6")
                    await tab.js("byId('artifact-sort').value='name_desc';"
                                 "byId('artifact-sort').dispatchEvent(new Event('change'))")
                    await tab.wait('filePage?.total===6 && '
                                   'filePage.items.map(item=>item.name).join("|")==='
                                   'filePage.items.map(item=>item.name).sort().reverse().join("|")')
                    assert await tab.js("document.documentElement.scrollWidth<=innerWidth && "
                                        "byId('library-view').scrollWidth<="
                                        "byId('library-view').clientWidth")
                    capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"generated-filters-{width}.png").write_bytes(
                        base64.b64decode(capture["data"]))
                    if compact:
                        await activate("#file-options-toggle")
                assert not tab.errors, tab.errors
                print(json.dumps({"generated_filters": "visibility/types/sort passed",
                                  "widths": [320, 390, 768, 1440], "browser_exceptions": 0}))
                return
            await tab.js('byId("artifact-kind").value="document";'
                         'byId("artifact-kind").dispatchEvent(new Event("change"))')
            await tab.wait('filePage?.total===3 && '
                           'filePage.items.every(item=>item.kind==="research")')
            assert await tab.js('fileKind==="document" && '
                                'byId("artifact-kind").selectedOptions[0].textContent==="Documents"')
            await activate(".file-item button")
            await tab.wait('byId("artifact-detail").open && '
                           'byId("artifact-preview").textContent.includes("Fixture research")')
            await activate("#artifact-close")
            await tab.js('byId("artifact-kind").value="media";'
                         'byId("artifact-kind").dispatchEvent(new Event("change"))')
            await tab.wait('filePage?.total===3 && filePage.items.every(isLibraryImage)')
            assert await tab.js('byId("artifact-kind").selectedOptions[0].textContent==="Media"')
            await tab.js('byId("artifact-kind").value="all";'
                         'byId("artifact-kind").dispatchEvent(new Event("change"))')
            await tab.wait('filePage?.total===6')
            await activate('[data-section="files"]')
            await tab.wait('librarySection==="files" && filePage?.total===1058')
            await tab.js('history.back()')
            await tab.wait('librarySection==="outputs" && filePage?.total===6')
            await tab.js('history.forward()')
            await tab.wait('librarySection==="files" && filePage?.total===1058')
            # Older explicit Reports URLs migrate, then reload directly into Generated.
            await tab.js('history.pushState(null,"","?library=files&files-type=research");'
                         'dispatchEvent(new PopStateEvent("popstate"))')
            await tab.wait('librarySection==="outputs" && filePage?.total===3')
            await tab.command("Page.reload")
            await tab.wait('typeof latest!=="undefined" && latest?.library_artifact_sources && '
                           'typeof filePage!=="undefined" && filePage?.total===3')
            assert await tab.js('librarySection==="outputs" && fileKind==="document" && '
                                'new URL(location.href).searchParams.get("library")==="outputs"')
            await activate('[data-section="files"]')
            await tab.wait('librarySection==="files" && filePage?.total===1058')
            await tab.js('''window.fileRequests=[];window.originalFetch=window.fetch;
              window.fetch=(input,options)=>{fileRequests.push(String(input));
                return originalFetch(input,options);};''')
            count_requests = ('fileRequests.filter(url=>'
                              'url.startsWith("/api/v1/library/items?")).length')
            requests = await tab.js(count_requests)
            await tab.js('latest.library_images=false;refreshLibraryCapabilities()')
            await tab.wait('document.querySelector("[data-file-view=gallery]").disabled')
            assert await tab.js('document.querySelector("[data-file-view=gallery]").title'
                                '.includes("Restart")')
            await tab.js('latest.library_images=true;refreshLibraryCapabilities()')
            await tab.wait('!document.querySelector("[data-file-view=gallery]").disabled')
            await tab.js('latest.library_artifact_sources=false;refreshLibraryCapabilities()')
            await tab.wait('byId("library-status").textContent.includes("Restart Web UI")')
            await tab.js('latest.library_artifact_sources=true;refreshLibraryCapabilities()')
            await tab.wait('byId("library-status").textContent==="" && filePage?.total===1058')
            await tab.click('[data-file-view="list"]')
            await tab.wait('fileView==="list" && byId("library-items").dataset.view==="list"')
            assert await tab.js(count_requests) == requests
            assert await tab.js('document.querySelectorAll(".file-item").length===24')
            assert await tab.js('document.querySelectorAll(".file-list-header button").length===4')
            await tab.click('[data-file-view="gallery"]')
            await tab.wait('fileView==="gallery" && filePage.total===50 && '
                           'filePage.items.length===24')
            await tab.wait('document.querySelector(".file-artwork img")?.naturalWidth > 0')
            assert await tab.js('document.querySelectorAll(".gallery-month").length===2')
            assert await tab.js('filePage.items.every(isLibraryImage)')
            assert await tab.js('document.querySelector(".gallery-month").textContent'
                                '.includes("Added to Uploads")')
            assert await tab.js('!fileRequests.some(url=>'
                                'url.startsWith("/api/v1/library/content?"))')

            await tab.js('history.back()')
            await tab.wait('fileView==="list" && byId("library-items").dataset.view==="list"')
            await tab.js('history.forward()')
            await tab.wait('fileView==="gallery" && byId("library-items").dataset.view==="gallery"')
            await tab.click(".file-item button")
            await tab.wait('selectedArtifact && !byId("image-navigation").hidden && '
                           'byId("artifact-preview").querySelector("img")?.naturalWidth > 0')
            first = await tab.js('selectedArtifact.id')
            await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "ArrowRight"})
            await tab.wait(f'selectedArtifact && selectedArtifact.id!=={json.dumps(first)} && '
                           '!previewNavigation')
            await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "ArrowLeft"})
            await tab.wait(f'selectedArtifact?.id==={json.dumps(first)} && !previewNavigation')
            await tab.click("#image-expand")
            assert await tab.js('byId("artifact-detail").classList.contains("image-expanded")')
            for event_type in ("keyDown", "keyUp"):
                await tab.command("Input.dispatchKeyEvent", {
                    "type": event_type, "key": "Escape", "code": "Escape",
                    "windowsVirtualKeyCode": 27,
                })
            await tab.wait('!byId("artifact-detail").open')
            await tab.wait('selectedArtifact===null && document.activeElement===previewOrigin')

            # Preview navigation can cross a page without moving the background grid.
            await tab.click(".file-item:last-child button")
            await tab.wait('selectedArtifact && !byId("image-next").disabled')
            await tab.click("#image-next")
            await tab.wait('imageSequenceOffset===24 && '
                           'selectedArtifact?.id===imageSequence[0].id && !previewNavigation')
            assert await tab.js('libraryOffset===0 && '
                                'document.querySelectorAll(".file-item").length===24')
            await tab.click("#artifact-close")

            # The date sort controls grouping; other orders show a flat gallery.
            await tab.js('byId("artifact-sort").value="name_desc";'
                         'byId("artifact-sort").dispatchEvent(new Event("change"))')
            await tab.wait('filePage?.items[0].name==="image-49.webp"')
            assert await tab.js('document.querySelectorAll(".gallery-month").length===0')
            await tab.js('byId("artifact-query").value="image-49";'
                         'byId("artifact-filter").requestSubmit()')
            await tab.wait('filePage?.total===1 && filePage.items[0].name==="image-49.webp"')
            await tab.command("Page.reload")
            await tab.wait('typeof latest!=="undefined" && latest?.session_id && '
                           'typeof filePage!=="undefined" && filePage?.total===1')
            assert await tab.js('fileView==="gallery" && '
                                'byId("artifact-query").value==="image-49" && '
                                'byId("artifact-sort").value==="name_desc"')
            # Leaving Library must retain the selected page on browser refresh.
            await tab.click("#nav-chat")
            assert await tab.js('!new URLSearchParams(location.search).has("library")')
            await tab.command("Page.reload")
            await tab.wait('typeof latest!=="undefined" && latest?.session_id')
            assert await tab.js('currentView==="chat"')
            await tab.click("#nav-library")
            await tab.click("#file-breadcrumbs button")
            await tab.wait('filePage?.total===50')
            await tab.js('byId("artifact-sort").value="newest";'
                         'byId("artifact-sort").dispatchEvent(new Event("change"))')
            await tab.wait('document.querySelectorAll(".gallery-month").length===2')

            # Fast search cancels obsolete reads, with no stale result publication.
            await tab.js('''byId('artifact-query').value='image-00';
              byId('artifact-filter').requestSubmit();
              byId('artifact-query').value='image-49';
              byId('artifact-filter').requestSubmit();''')
            await tab.wait('filePage?.total===1 && filePage.items[0].name==="image-49.webp"')
            await tab.click("#file-breadcrumbs button")
            await tab.wait('filePage?.total===50')

            layouts = []
            for theme in ("light", "dark"):
                await tab.js(f'document.documentElement.dataset.theme={json.dumps(theme)}')
                for width, height in ((1440, 1000), (850, 900), (768, 900),
                                      (560, 760), (390, 760), (320, 640)):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": height, "deviceScaleFactor": 1,
                        "mobile": False,
                    })
                    for mode in ("list", "grid", "gallery"):
                        await tab.click(f'[data-file-view="{mode}"]')
                        rendered_mode = ('JSON.parse(byId("library-items").dataset.'
                                         f'filesRendered)[0]==={json.dumps(mode)}')
                        await tab.wait(f'fileView==={json.dumps(mode)} && '
                                       f'{rendered_mode} && '
                                       'document.querySelectorAll(".file-item").length===24 && '
                                       '!byId("library-items").classList.contains("is-loading")')
                        await asyncio.sleep(.2)
                        state = await tab.js('''(() => {
                          const grid=byId('library-items');
                          const cards=[...grid.querySelectorAll('.file-item')];
                          const toolbar=byId('artifact-filter').getBoundingClientRect();
                          const compact=byId('artifact-tools').clientWidth<650;
                          return {width:innerWidth,view:fileView,compact,
                            overflow:document.documentElement.scrollWidth>innerWidth,
                            contentOverflow:grid.scrollWidth>grid.clientWidth,
                            cards:cards.length, columns:getComputedStyle(grid).gridTemplateColumns,
                            firstGap:cards[0].getBoundingClientRect().top-toolbar.bottom,
                            rowHeight:cards[0].getBoundingClientRect().height,
                            headerHeight:grid.querySelector('.file-list-header')?.getBoundingClientRect().height,
                            toolbarHeight:toolbar.height,
                            targets:[...byId('file-view-modes').children,
                              ...byId('artifact-filter').querySelectorAll('button')]
                              .filter(button=>button.getClientRects().length).every(button=>
                                button.getBoundingClientRect().width>=48 &&
                                button.getBoundingClientRect().height>=48)};
                        })()''')
                        assert not state["overflow"] and not state["contentOverflow"], state
                        assert state["targets"] and state["cards"] == 24, state
                        if mode == "gallery":
                            assert len(state["columns"].split()) >= 3, state
                        if mode == "list":
                            if state["compact"]:
                                assert state["headerHeight"] == 0, state
                                assert 64 <= state["rowHeight"] <= 72, state
                                assert 0 <= state["firstGap"] <= 6, state
                                assert state["toolbarHeight"] == 48, state
                            else:
                                assert state["headerHeight"] >= 44, state
                        layouts.append(state)
                        if state["compact"]:
                            await activate("#file-options-toggle")
                            assert await tab.js('byId("file-option-fields")'
                                                '.getClientRects().length>0')
                            assert await tab.js('document.documentElement.scrollWidth<=innerWidth')
                            await tab.command("Input.dispatchKeyEvent", {
                                "type": "keyDown", "key": "Escape", "code": "Escape",
                                "windowsVirtualKeyCode": 27,
                            })
                            assert await tab.js(
                                'byId("file-options-toggle").ariaExpanded==="false" && '
                                'document.activeElement===byId("file-options-toggle")'
                            )
                        shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (output / f"{mode}-{theme}-{width}.png").write_bytes(
                            base64.b64decode(shot["data"]))
                    await tab.click(".file-item button")
                    await tab.wait('selectedArtifact && '
                                   'byId("artifact-preview").querySelector("img")?.naturalWidth>0')
                    await tab.click("#image-expand")
                    assert await tab.js('''(() => {
                      const dialog=byId('artifact-detail'), rect=dialog.getBoundingClientRect();
                      return rect.left>=0 && rect.right<=innerWidth &&
                        dialog.scrollWidth<=dialog.clientWidth;
                    })()''')
                    await tab.click("#artifact-close")

            if os.environ.get("KLAUDE_TEST_LIBRARY_VIEWS_ONLY") == "1":
                assert not tab.errors, tab.errors
                print(json.dumps({"library_views": ["list", "grid", "gallery"],
                                  "responsive_layouts": len(layouts),
                                  "history_search_pagination_preview": True,
                                  "browser_exceptions": 0, "screenshots": str(output)}, indent=2))
                return

            await tab.js('document.documentElement.dataset.motion="reduced"')
            # Both sources reuse the adaptive browser without mixing collections.
            for width in (320, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 760, "deviceScaleFactor": 1, "mobile": False,
                })
                await activate('[data-section="outputs"]')
                await activate("#file-breadcrumbs button")
                await activate('[data-file-view="list"]')
                await tab.wait('filePage?.total===6 && fileView==="list"')
                compact = await tab.js("byId('file-options-toggle').getClientRects().length>0")
                if compact:
                    await activate("#file-options-toggle")
                assert await tab.js('''['artifact-kind','artifact-status','artifact-sort']
                  .every(id=>byId(id).getClientRects().length>0 &&
                    byId(id).getBoundingClientRect().height>=48)''')
                await tab.js('byId("artifact-sort").value="name_desc";'
                             'byId("artifact-sort").dispatchEvent(new Event("change"))')
                await tab.wait('filePage?.total===6 && '
                               'filePage.items.map(item=>item.name.toLowerCase()).join("|")==='
                               'filePage.items.map(item=>item.name.toLowerCase()).sort()'
                               '.reverse().join("|")')
                await tab.js('byId("artifact-sort").value="newest";'
                             'byId("artifact-sort").dispatchEvent(new Event("change"))')
                if compact:
                    await activate("#file-options-toggle")
                for mode, total in (("list", 6), ("grid", 6), ("gallery", 3)):
                    await activate(f'[data-file-view="{mode}"]')
                    await tab.wait(f'filePage?.total==={total} && '
                                   'JSON.parse(byId("library-items").dataset.filesRendered)[0]==='
                                   + json.dumps(mode))
                    assert await tab.js('byId("file-add").hidden && '
                                        'document.documentElement.scrollWidth<=innerWidth && '
                                        'byId("library-items").scrollWidth<='
                                        'byId("library-items").clientWidth')
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"outputs-{mode}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"]))
                await activate('[data-section="files"]')
                await tab.wait('librarySection==="files" && filePage?.total===50')
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 320, "height": 640, "deviceScaleFactor": 1, "mobile": False,
            })
            await tab.click('[data-file-view="list"]')
            await tab.wait('fileView==="list"')
            # The compact control exposes every existing order and direction.
            await activate("#file-options-toggle")
            for sort in ("name", "name_desc", "largest", "smallest", "oldest", "type", "newest"):
                await tab.js('byId("artifact-sort").value=' + json.dumps(sort) + ';'
                             'byId("artifact-sort").dispatchEvent(new Event("change"))')
                await tab.wait(
                    'JSON.parse(byId("library-items").dataset.filesRendered)[1]==='
                    + json.dumps(sort)
                    + ' && !byId("library-items").classList.contains("is-loading")'
                )
                assert await tab.js('new URL(location.href).searchParams.get("files-sort")==='
                                    + json.dumps(sort))
            await activate("#file-options-toggle")
            await verify_code_preview(tab, activate, output)
            await tab.js('byId("artifact-query").value="notes.txt";'
                         'byId("artifact-filter").requestSubmit()')
            await tab.wait('filePage?.total===1 && filePage.items[0].name==="notes.txt"')
            await tab.click(".file-item button")
            await tab.wait('byId("artifact-preview").textContent.includes("Fixture note")')
            assert await tab.js('byId("image-navigation").hidden && '
                                'byId("artifact-download").download==="notes.txt"')
            await tab.click("#artifact-tags-edit")
            await tab.js('byId("artifact-tag-new").value="smoke, reference";'
                         'byId("artifact-tags").requestSubmit()')
            await tab.wait('byId("domain-review").open')
            await tab.click("#domain-review-confirm")
            await tab.wait('!byId("domain-review").open')
            await tab.wait('filePage?.items[0].tags.includes("smoke")')
            await activate("#artifact-close")
            # Import from an unrelated search/type scope without choosing storage.
            await tab.js('byId("artifact-kind").value="document";'
                         'byId("artifact-kind").dispatchEvent(new Event("change"))')
            await tab.wait('fileKind==="document" && filePage?.total===1')
            await activate("#file-add")
            assert await tab.js('byId("artifact-import-panel").open && '
                                'document.activeElement===byId("artifact-file")')
            assert await tab.js('byId("artifact-import-panel").scrollWidth<='
                                'byId("artifact-import-panel").clientWidth')
            shot = await tab.command("Page.captureScreenshot", {"format": "png"})
            (output / "add-file-320.png").write_bytes(base64.b64decode(shot["data"]))
            await tab.command("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": "Escape", "code": "Escape",
                "windowsVirtualKeyCode": 27,
            })
            await tab.wait('!byId("artifact-import-panel").open && '
                           'document.activeElement===byId("file-add")')
            await activate("#file-add")
            assert await tab.js('!byId("artifact-import-kind") && !byId("artifact-file").accept')
            picture = io.BytesIO()
            Image.new("RGB", (32, 20), "purple").save(picture, format="WEBP")
            encoded = json.dumps(base64.b64encode(picture.getvalue()).decode())
            # Closing an in-flight import must discard its late review, not reopen a dialog.
            await tab.js('''window.savedDomainRequest=domainRequest;window.importReviewDiscards=0;
              domainRequest=async (path,method,payload)=>{
                if(path==='/api/v1/library/discard') importReviewDiscards++;
                const result=await savedDomainRequest(path,method,payload);
                if(path==='/api/v1/library/review' && payload?.draft?.operation==='import')
                  return new Promise(resolve=>{window.releaseImportReview=()=>resolve(result)});
                return result;
              };''')
            await tab.js('''(() => {
              const data=new DataTransfer();
              data.items.add(new File([Uint8Array.from(atob(''' + encoded + '''),
                char=>char.charCodeAt(0))], 'automatic-image.txt', {type:'text/plain'}));
              byId('artifact-file').files=data.files;
              byId('artifact-import').requestSubmit();
            })()''')
            await tab.wait('typeof releaseImportReview==="function"')
            await activate("#artifact-import-close")
            await tab.js('releaseImportReview()')
            await tab.wait('!byId("artifact-import").querySelector("button[type=submit]").disabled')
            assert await tab.js('!byId("domain-review").open && !managementReview')
            assert await tab.js('importReviewDiscards===1')
            await tab.js('domainRequest=savedDomainRequest')
            await activate("#file-add")
            await tab.js('byId("artifact-import").requestSubmit()')
            await tab.wait('byId("domain-review").open')
            assert await tab.js('!byId("artifact-import-panel").open && '
                                'document.activeElement===byId("domain-review-cancel")')
            assert await tab.js('byId("domain-review-summary").textContent.includes("as an image")')
            await tab.click("#domain-review-confirm")
            await tab.wait('!byId("domain-review").open')
            for _ in range(200):
                imported = host.library.listing(kind="media", query="automatic-image.txt")["items"]
                if imported:
                    break
                await asyncio.sleep(.05)
            assert len(imported) == 1 and imported[0]["mime"] == "image/webp"
            assert await tab.js('fileKind==="document" && '
                                'byId("artifact-query").value==="notes.txt"')
            await tab.js('byId("artifact-kind").value="all";'
                         'byId("artifact-query").value="automatic-image.txt";'
                         'byId("artifact-kind").dispatchEvent(new Event("change"))')
            await tab.click('[data-file-view="gallery"]')
            await tab.wait('filePage?.total===1 && '
                           'document.querySelector(".file-artwork img")?.naturalWidth===32')
            # A corrupt but recognizable image keeps a usable file tile and filename.
            damaged = io.BytesIO()
            Image.new("RGB", (8, 8), "teal").save(damaged, format="PNG")
            host.library.artifacts.import_bytes(damaged.getvalue()[:24], "media", "broken.png")
            await tab.click('[data-file-view="gallery"]')
            await tab.js('byId("artifact-query").value="broken.png";'
                         'byId("artifact-filter").requestSubmit()')
            await tab.wait('filePage?.total===1 && '
                           'document.querySelector(".file-artwork .image-fallback")!==null')
            assert await tab.js('document.querySelector(".file-open").getAttribute("aria-label")'
                                '.includes("broken.png")')
            await tab.click("#logout")
            await tab.wait('!authenticated && byId("library-items").children.length===0')
            assert not tab.errors, tab.errors
            print(json.dumps({"views": ["list", "grid", "gallery"], "inventory": 1058,
                              "image_inventory": 50, "mode_switch_reuses_reads": True,
                              "history_reload_search": True, "paged_image_navigation": True,
                              "keyboard_escape_focus": True, "reviewed_tags": True,
                              "automatic_reviewed_import": True,
                              "compact_toolbar_sort_upload_focus": True,
                              "closed_import_discards_late_review": True,
                              "inputs_outputs_separate_counts_history_preview": True,
                              "shared_types_documents_include_reports": True,
                              "code_preview_wrap_copy_http_fallback": True,
                              "corrupt_image_fallback": True,
                              "originals_used_as_thumbnails": False, "layouts": layouts,
                              "longest_task_ms": await tab.js('Math.max(0,...fileLongTasks)'),
                              "browser_exceptions": 0, "screenshots": str(output)}, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or shutil.which("chromium")
    if not chrome:
        chrome = str(list((Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"))[-1])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.unit.test_webhost import _app

    with tempfile.TemporaryDirectory(prefix="klaude-library-browser-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace = root, Workspace(root)
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        service = LibraryManagement(cfg, root)
        for index in range(50):
            size = [(640, 420), (320, 600), (400, 400)][index % 3]
            picture = Image.new("RGB", size, "#b8d8cd")
            drawing = ImageDraw.Draw(picture)
            drawing.rectangle((size[0] // 5, size[1] // 5, size[0] * 4 // 5,
                               size[1] * 4 // 5), fill=["#7b689d", "#967651", "#51768f"][index % 3])
            drawing.ellipse((20, 20, 120, 120), fill="#f3cb7d")
            data = io.BytesIO()
            picture.save(data, format="WEBP", lossless=True)
            item = service.artifacts.import_bytes(data.getvalue(),
                                                   "document" if index % 5 == 0 else "media",
                                                   f"image-{index:02}.webp")
            month = 10 if index < 10 else 9 if index < 30 else 8
            created = datetime(2026, month, 20, tzinfo=UTC).timestamp() - index
            with service.artifacts.database(write=True) as db:
                db.execute("UPDATE artifacts SET created=? WHERE id=?", (created, item["id"]))
        for name, content in (("notes.txt", b"Fixture note"),
                              ("sample.py", CODE_PREVIEW.encode()),
                              ("report.pdf", b"%PDF-1.4 fixture"), ("recording.mp3", b"audio"),
                              ("movie.mp4", b"video"), ("archive.zip", b"zip"),
                              ("unknown.bin", b"\0unknown"), ("vector.svg", b"<svg/>")):
            service.artifacts.import_bytes(content, "document", name)
        for index in range(1000):
            service.artifacts.import_bytes(b"Small fixture", "document", f"document-{index:04}.txt")
        for index in range(3):
            service.artifacts.store_report(f"research-{index}.md", "# Fixture research result",
                                           job=f"research-{index}")
            image = io.BytesIO()
            Image.new("RGB", (80, 64), "teal").save(image, format="PNG")
            service.artifacts.store_generated_image(image.getvalue(), {
                "id": f"{index:032x}", "session": "fixture", "settings": {"model": "fixture"},
            }, "fixture-job")
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts, library=service, staging_dir=root / "staging")
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

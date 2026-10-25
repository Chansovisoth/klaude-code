"""Isolated real-Chrome checks for compact collections and stateful refresh.

Use --baseline to capture the previous layout before implementing changes.
Use --accessibility for focused state restoration, keyboard, text scaling,
forced colors, reduced motion and sampled palette contrast checks.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sqlite3
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
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402


def fixtures(service):
    for index in range(34):
        service.artifacts.import_bytes(b"Fixture note", "document", f"note-{index:02}.txt")
    service.artifacts.import_bytes(
        b"<html>Inert document</html>", "document", "a-long-filename-" * 9 + ".html"
    )
    image = io.BytesIO()
    Image.new("RGB", (320, 180), "tan").save(image, format="WEBP")
    service.artifacts.import_bytes(image.getvalue(), "media", "image.webp")
    root = service.data / "knowledge.lance"
    root.mkdir(parents=True)
    with sqlite3.connect(root / "fts.db") as db:
        db.execute(
            "CREATE VIRTUAL TABLE chunks USING fts5("
            "id UNINDEXED, collection UNINDEXED, source UNINDEXED, text)"
        )
        for index in range(795):
            db.execute(
                "INSERT INTO chunks VALUES(?,?,?,?)",
                (
                    str(index),
                    f"library-{index:03}",
                    f"source-{index:03}",
                    "Fixture rainbow reference text",
                ),
            )
    for index in range(3):
        source = service.data / "docs-sources" / f"source-{index:03}"
        source.mkdir(parents=True)
        (source / "manifest.json").write_text(
            json.dumps(
                {
                    "name": source.name,
                    "library": "library-000",
                    "files": ["reference.md"],
                    "llms_url": "https://example.test/reference",
                }
            )
        )
    for index in range(26):
        name = f"skill-{index:02}"
        skill = service.data / "skills" / name
        skill.mkdir(parents=True)
        (skill / "manifest.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "library": "skills",
                    "state": "active",
                    "source": "fixture.zip",
                    "indexed_files": [],
                    "description": "A useful coding and review skill. " * 12,
                }
            )
        )


async def verify(host, root, service, chrome):
    baseline = "--baseline" in sys.argv
    output = Path("/tmp/klaude-refinement-" + ("before" if baseline else "after"))
    output.mkdir(exist_ok=True)
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
    try:
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            await asyncio.sleep(0.05)
        port = int(active.read_text().splitlines()[0])
        with urlopen(
            Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        ) as response:
            target = json.load(response)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")

            async def wait(expression):
                for _ in range(200):
                    if await tab.js(expression):
                        return
                    await asyncio.sleep(0.05)
                raise AssertionError(
                    {
                        "waiting": expression,
                        "errors": tab.errors,
                        "status": await tab.js(
                            "JSON.stringify({view:currentView,library:byId('library-status').textCont"
                            "ent,skills:byId('skills-status').textContent,knowledge:byId('knowledge-s"
                            "tatus').textContent})"
                        ),
                    }
                )

            tab.wait = wait

            async def click(selector):
                point = await tab.js(
                    """(() => {const e=document.querySelector("""
                    + json.dumps(selector)
                    + """);
                    e.scrollIntoView({block:'nearest'}); const r=e.getBoundingClientRect();
                    const p={x:r.x+r.width/2,y:r.y+r.height/2};
                    if (!r.width||!r.height||!e.contains(document.elementFromPoint(p.x,p.y)))
                      throw Error('Obscured '+e.id);
                    return p;})()"""
                )
                for kind in ("mousePressed", "mouseReleased"):
                    await tab.command(
                        "Input.dispatchMouseEvent",
                        {"type": kind, **point, "button": "left", "clickCount": 1},
                    )

            async def screenshot(name):
                await asyncio.sleep(0.25)
                capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / name).write_bytes(base64.b64decode(capture["data"]))

            await tab.command("Page.navigate", {"url": host.origin})
            await wait('typeof byId!=="undefined"&&!byId("local-access").hidden')
            await tab.js(
                'byId("login-username").value="admin";byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await wait("latest?.session_id && pollTimer!==null")
            if "--accessibility" in sys.argv:
                report = await accessibility_checks(tab, click, screenshot)
                print(json.dumps(report, indent=2))
                return
            layouts = []
            for theme in ("light", "dark"):
                await tab.js(f"document.documentElement.dataset.theme={json.dumps(theme)}")
                for width in (360, 390, 768, 1280):
                    await tab.command(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": width,
                            "height": 844,
                            "deviceScaleFactor": 1,
                            "mobile": width < 560,
                        },
                    )
                    for section in ("files", "knowledge", "skills"):
                        await tab.js(
                            "showView("
                            + json.dumps("library" if section == "files" else "integrations")
                            + ")"
                        )
                        if section == "files":
                            await wait("filePage?.items.length>0")
                            await tab.js('fileView="list";loadLibrary()')
                            await wait(
                                'byId("library-items").dataset.view==="list" && '
                                '!byId("library-items").matches("[aria-busy=true]")'
                            )
                        else:
                            await tab.click(f'[data-integration="{section}"]')
                            card = "knowledge-card" if section == "knowledge" else "skill-card"
                            await wait(f'document.querySelector(".{card}")!==null')
                            grid_id = "knowledge-items" if section == "knowledge" else "skill-items"
                            await wait(f'!byId("{grid_id}").matches("[aria-busy=true]")')
                        await screenshot(f"{section}-{width}-{theme}.png")
                        info = await tab.js("""(() => {
                            const row=[...document.querySelectorAll(
                              '.file-item,.knowledge-card,.skill-card')]
                              .find(e=>e.getClientRects().length);
                            return {rowHeight:row?.getBoundingClientRect().height,
                              overflow:document.documentElement.scrollWidth>innerWidth,
                              nav:[...document.querySelectorAll('.rail>button')]
                                .filter(e=>e.getClientRects().length).map(e=>({id:e.id,
                                  width:e.getBoundingClientRect().width,
                                  right:e.getBoundingClientRect().right}))};})()""")
                        layouts.append({"section": section, "width": width, "theme": theme, **info})
                        if not baseline:
                            assert not info["overflow"]
                            assert await tab.js("""(() => {
                              const rail=document.querySelector('.rail');
                              return rail.scrollWidth<=rail.clientWidth;})()""")
            checks = []
            if not baseline:
                await exercise(tab, click, screenshot, service, checks)
                assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "checks": checks,
                        "baseline": baseline,
                        "layouts": layouts,
                        "browser_exceptions": len(tab.errors),
                        "screenshots": str(output),
                    },
                    indent=2,
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


async def exercise(tab, click, screenshot, service, checks):
    await tab.js("""
      window.refineRequests=[]; window.refineFault=null;
      const original=fetch.bind(window);
      window.fetch=async (input, options) => {
        const path=new URL(String(input),location.href).pathname;
        refineRequests.push(path);
        const fault=refineFault;
        if (fault?.path===path) {
          if (fault.once) refineFault=null;
          await new Promise(resolve=>setTimeout(resolve,fault.delay||0));
          return new Response(JSON.stringify({error:{message:'Fixture request failed'}}),
            {status:fault.status||500,headers:{'Content-Type':'application/json'}});
        }
        return original(input,options);
      };
    """)
    await click("#nav-library")
    await tab.wait('filePage?.total===36 && !byId("library-items").matches("[aria-busy=true]")')
    assert await tab.js('!byId("file-search-submit")')
    await tab.js("""byId('artifact-query').value='note-0';
      byId('artifact-query').dispatchEvent(new Event('input',{bubbles:true}));""")
    await tab.wait("filePage?.total===10 && libraryOffset===0")
    await tab.js("""byId('artifact-kind').value='document';
      byId('artifact-kind').dispatchEvent(new Event('change'));
      byId('artifact-sort').value='name_desc';
      byId('artifact-sort').dispatchEvent(new Event('change'));""")
    await tab.wait('!byId("library-items").matches("[aria-busy=true]")')
    await tab.js("""window.beforeRefresh=JSON.stringify(fileParameters());
      window.beforeRow=byId('library-items').querySelector('.file-item');
      byId('library-view').scrollTop=120;
      window.beforeScroll=byId('library-view').scrollTop;
      window.refineFault={path:'/api/v1/library/items',delay:400,status:500,once:true};
      window.refreshReadStart=refineRequests.length;
      byId('library-refresh').click();byId('library-refresh').click();""")
    assert await tab.js("""byId('library-refresh').disabled &&
      byId('library-refresh').getAttribute('aria-busy')==='true' &&
      byId('library-items').contains(beforeRow)""")
    await tab.wait('!byId("library-refresh").disabled')
    assert await tab.js("""JSON.stringify(fileParameters())===beforeRefresh &&
      byId('library-items').contains(beforeRow) && byId('library-view').scrollTop===beforeScroll &&
      byId('library-status').textContent.includes('Fixture request failed') &&
      refineRequests.slice(refreshReadStart).filter(p=>p==='/api/v1/library/items').length===1""")
    service.artifacts.import_bytes(b"New backend data", "document", "note-00-added.txt")
    await tab.js("byId('library-refresh').click()")
    await tab.wait('!byId("library-refresh").disabled && filePage.total===11')
    assert await tab.js("JSON.stringify(fileParameters())===beforeRefresh")
    checks.append("Refresh re-fetches, deduplicates and retains content/scroll/state on failure")

    await tab.js(
        "byId('artifact-query').value='no-match-fixture';byId('artifact-filter').requestSubmit()"
    )
    await tab.wait("byId('library-items').textContent.includes('No files match this search')")
    await tab.js("""refineFault={path:'/api/v1/library/items',status:500,once:true};
      byId('artifact-query').value='failed-load-fixture';
      byId('artifact-filter').requestSubmit();""")
    await tab.wait("byId('library-items').textContent.includes('Files could not be loaded')")
    await screenshot("library-load-failed.png")
    await tab.js(
        "byId('artifact-query').value='';byId('artifact-status').value='archived'"
        ";byId('artifact-status').dispatchEvent(new Event('change'))"
    )
    await tab.wait("byId('library-items').textContent.includes('No files match these filters')")
    await click('[data-section="outputs"]')
    await tab.wait("byId('library-items').textContent.includes('No generated files yet')")
    await click("#library-refresh")
    await tab.wait("!byId('library-refresh').disabled")
    assert await tab.js("librarySection==='outputs' && fileView==='list'")
    await screenshot("generated-empty.png")
    checks.append("Distinct search, filtered and genuinely empty Generated states")

    await click("#nav-integrations")
    await click('[data-integration="knowledge"]')
    await tab.wait("byId('knowledge-items').querySelectorAll('.knowledge-card').length===20")
    assert await tab.js(
        "document.querySelector('[data-count-key=knowledge] .tab-count').textContent==='795'"
    )
    await click("#knowledge-items .collection-open")
    await tab.wait("byId('source-items').querySelectorAll('.source-row').length===3")
    await tab.js("byId('knowledge-query').value='rainbow';byId('knowledge-search').requestSubmit()")
    await tab.wait("byId('knowledge-items').querySelectorAll('.knowledge-hit').length===1")
    await tab.js(
        "byId('knowledge-query').value='absentfixture';byId('knowledge-search').requestSubmit()"
    )
    await tab.wait("byId('knowledge-status').textContent.includes('No indexed text')")
    await tab.js("byId('knowledge-query').value='';byId('knowledge-search').requestSubmit()")
    await tab.wait("byId('knowledge-items').querySelectorAll('.knowledge-card').length===20")
    await click("#knowledge-next")
    await tab.wait(
        "knowledgeOffset===20 && byId('knowledge-items').textContent.includes('library-020')"
    )
    await tab.command("Page.reload")
    await tab.wait(
        "typeof authenticated!=='undefined' && authenticated && currentView==='in"
        "tegrations' && knowledgeOffset===20 && byId('knowledge-items').querySele"
        "ctorAll('.knowledge-card').length===20"
    )
    checks.append(
        "795 libraries remain backend-paged; real indexed search/sources and page reload work"
    )
    # Page.reload deliberately removes the fault transport; reintroduce only where needed.
    await click('[data-integration="skills"]')
    await tab.wait(
        "installedSkills.length===20 && !byId('skill-items').matches('[aria-busy=true]')"
    )
    assert await tab.js("!byId('skill-items').querySelector('.danger')")
    await tab.js("byId('skills-query').value='absentfixture';byId('skills-filter').requestSubmit()")
    await tab.wait("byId('skill-items').textContent.includes('No Skills match this search')")
    await tab.js("byId('skills-query').value='skill-25';byId('skills-filter').requestSubmit()")
    await tab.wait("installedSkills.length===1 && installedSkills[0].name==='skill-25'")
    await tab.js("byId('skills-query').value='';byId('skills-filter').requestSubmit()")
    await tab.wait("installedSkills.length===20")
    await click("#skills-next")
    await tab.wait("installedSkills.length===6 && installedSkills[0].name==='skill-20'")
    await click("#skills-previous")
    await tab.wait("installedSkills.length===20 && installedSkills[0].name==='skill-00'")
    await click("#skill-items .collection-open")
    await tab.wait("skillDialog.open")
    assert await tab.js(
        "byId('skill-detail-metadata').textContent.includes('Local ZIP') && byId("
        "'skill-detail-description').textContent.length>100"
    )
    await click("#skill-detail-close")
    await tab.js("""window.submitFetch=fetch.bind(window);window.fetch=async(input,options)=>{
      if(String(input).endsWith('/library/submit')) {
        await new Promise(resolve=>setTimeout(resolve,350));
        return new Response(JSON.stringify({error:{message:'Fixture save rejected'}}),{status:400});
      }
      return submitFetch(input,options);
    };""")
    await click("#skill-items .skill-toggle")
    assert await tab.js(
        "byId('skill-items').querySelector('.skill-toggle').getAttribute('aria-ch"
        "ecked')==='true' && byId('skill-items').querySelector('.skill-toggle').d"
        "isabled && !reviewDialog.open && "
        "byId('skill-items').querySelector('.collection-metadata').textContent==='Updating…' && "
        "!byId('skill-items').querySelector('.skill-row-status').textContent"
    )
    await tab.wait("!byId('skill-items').querySelector('.skill-toggle').disabled")
    assert await tab.js("installedSkills[0].enabled")
    await tab.js("window.fetch=submitFetch")
    await tab.js("""window.beforeSlowReview=fetch.bind(window);window.slowReview=true;
      window.fetch=async (input,options)=>{
        if (slowReview && String(input).includes('/api/v1/library/review'))
          await new Promise(resolve=>setTimeout(resolve,350));
        return beforeSlowReview(input,options);
      };""")
    await click("#skill-items .skill-toggle")
    await click("#nav-library")
    await tab.wait("!skillChanges.size && !skillReviewPending")
    assert await tab.js("!reviewDialog.open && currentView==='library'")
    await tab.js("slowReview=false")
    await click("#nav-integrations")
    await tab.wait(
        "installedSkills.length===20 && !byId('skill-items').matches('[aria-busy=true]')"
    )
    await tab.js("""window.reviewFetch=fetch.bind(window); window.rejectReview=true;
      window.fetch=(input,options)=>rejectReview &&
        String(input).includes('/api/v1/library/review') ?
        Promise.resolve(new Response(JSON.stringify({error:{message:'Fixture review rejected'}}),
          {status:400})):
        reviewFetch(input,options);""")
    await click("#skill-items .skill-toggle")
    await tab.wait("byId('skills-status').textContent.includes('Fixture review rejected')")
    assert await tab.js(
        "!byId('skill-items').querySelector('.skill-toggle').disabled && installe"
        "dSkills[0].enabled && !reviewDialog.open"
    )
    await tab.js("rejectReview=false")
    checks.append("Direct Skill toggles retain confirmed state during pending and failed saves")

    await click("#skill-items .skill-toggle")
    await tab.wait("!reviewDialog.open && !installedSkills[0].enabled && !skillChanges.size")
    assert await tab.js(
        "byId('skill-items').querySelector('.skill-toggle').getAttribute('aria-checked')==='false'"
    )
    # Change the manifest after preparation to exercise a rejected owned worker.
    await tab.js("""window.staleFetch=fetch.bind(window);window.fetch=(input,options)=>
      String(input).endsWith('/library/submit') ? new Promise(resolve=>{
        window.releaseSkillSubmit=()=>resolve(staleFetch(input,options));
      }) : staleFetch(input,options);""")
    await click("#skill-items .skill-toggle")
    await tab.wait("typeof releaseSkillSubmit==='function'")
    manifest = service.data / "skills" / "skill-00" / "manifest.json"
    value = json.loads(manifest.read_text())
    value["description"] = "Changed after review"
    manifest.write_text(json.dumps(value))
    await tab.js("releaseSkillSubmit();window.fetch=staleFetch")
    await tab.wait(
        "!reviewDialog.open && !skillChanges.size && byId('skill-items').textCont"
        "ent.includes('Update rejected')"
    )
    assert await tab.js("!installedSkills[0].enabled")
    checks.append("Real owned enable/disable worker confirmed; failed worker never flips switch")

    await click("#skill-items .collection-open")
    await click("#skill-detail-delete")
    await tab.wait("reviewDialog.open")
    assert await tab.js(
        "document.activeElement===byId('domain-review-cancel') && byId('domain-re"
        "view-title').textContent.includes('Remove this item') && byId('domain-review"
        "-summary').textContent.includes('Original source files are retained')"
    )
    await click("#domain-review-cancel")
    assert manifest.exists()
    await click("#skill-items .collection-open")
    await click("#skill-detail-delete")
    await tab.wait("reviewDialog.open")
    await click("#domain-review-confirm")
    await tab.wait(
        "!reviewDialog.open && !skillChanges.size && installedSkills.every(s=>s.name!=='skill-00')"
    )
    assert not manifest.exists()
    checks.append(
        "Deletion is in details, Cancel-focused, reviewed, and verified through the real worker"
    )

    await tab.command(
        "Emulation.setDeviceMetricsOverride",
        {"width": 360, "height": 844, "deviceScaleFactor": 1, "mobile": True},
    )
    await tab.js("byId('prompt').value='Unsent draft survives navigation'")
    await click("#nav-more")
    await tab.wait("byId('navigation-more').matches(':popover-open')")
    await tab.wait("document.activeElement.dataset.appView==='models'")
    await screenshot("more-menu-360.png")
    await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "ArrowDown"})
    assert await tab.js("document.activeElement.dataset.appView==='activity'")
    await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "ArrowDown"})
    assert await tab.js("document.activeElement.dataset.appView==='settings'")
    await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape"})
    await tab.wait(
        "!byId('navigation-more').matches(':popover-open') && document.activeElem"
        "ent===byId('nav-more')"
    )
    await click("#nav-more")
    await click('[data-app-view="activity"]')
    assert await tab.js(
        "currentView==='activity' && byId('nav-more').getAttribute('aria-current')==='page'"
    )
    await tab.js("history.back()")
    await tab.wait("currentView==='integrations' && integrationSection==='skills'")
    await tab.js("history.forward()")
    await tab.wait("currentView==='activity'")
    await click("#nav-chat")
    assert await tab.js("byId('prompt').value==='Unsent draft survives navigation'")
    await click("#nav-more")
    await click('[data-app-view="settings"]')
    await screenshot("settings-more-360.png")
    await tab.command("Page.reload")
    await tab.wait(
        "typeof authenticated!=='undefined' && authenticated && currentView==='settings'"
    )
    checks.append(
        "Mobile More supports keyboard/Escape, routes, history, deep reload and unsent chat text"
    )

    # All existing palettes remain themed through the same semantic roles.
    for theme in ("light", "dark"):
        for palette in ("lavender", "sage", "peach", "ocean", "rose", "teal", "amber", "slate"):
            await tab.js(
                "document.documentElement.dataset.theme="
                + json.dumps(theme)
                + ";document.documentElement.dataset.palette="
                + json.dumps(palette)
            )
            await tab.js("showView('integrations')")
            await tab.wait("!byId('skill-items').matches('[aria-busy=true]')")
            assert await tab.js(
                "document.documentElement.scrollWidth<=innerWidth && [...document.querySe"
                "lectorAll('.rail .nav-item')].filter(e=>e.getClientRects().length).every"
                "(e=>e.getBoundingClientRect().width>=48)"
            )
            if palette in ("peach", "slate"):
                await screenshot(f"skills-360-{palette}-{theme}.png")
    checks.append("All eight palettes in light/dark retain geometry and 48px mobile nav targets")


async def accessibility_checks(tab, click, screenshot):
    checks = []
    observations = {}
    await tab.command(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": 390,
            "height": 844,
            "deviceScaleFactor": 1,
            "mobile": True,
        },
    )
    await click("#nav-integrations")
    await click('[data-integration="skills"]')
    await tab.wait(
        "installedSkills.length===20 && !byId('skill-items').matches('[aria-busy=true]')"
    )
    await tab.js("byId('skills-query').value='skill-';byId('skills-filter').requestSubmit()")
    await tab.wait(
        "installedSkills.length===20 && !byId('skill-items').matches('[aria-busy=true]')"
    )
    await click("#skills-next")
    await tab.wait("skillsOffset===20 && installedSkills.length===6")
    await tab.command("Page.reload")
    await tab.wait(
        "typeof authenticated!=='undefined' && authenticated && currentView==='integrations' && "
        "!byId('skill-items').matches('[aria-busy=true]') && installedSkills.length>0"
    )
    observations["skills_restored"] = await tab.js(
        "byId('skills-query').value==='skill-' && skillsOffset===20 && installedSkills.length===6"
    )
    assert observations["skills_restored"]
    await tab.js("history.back()")
    await tab.wait("skillsOffset===0 && installedSkills.length===20")
    await tab.js("history.forward()")
    await tab.wait("skillsOffset===20 && installedSkills.length===6")
    await tab.js("byId('skills-refresh').click()")
    await tab.wait("!byId('skills-refresh').disabled")
    assert await tab.js("skillsOffset===20 && byId('skills-query').value==='skill-'")
    await click('[data-integration="knowledge"]')
    assert await tab.js("!location.search.includes('skills-')")
    await click('[data-integration="skills"]')
    await tab.wait("skillsOffset===20 && installedSkills.length===6")
    checks.append("Skills search/page survive reload, Refresh, tab switching and Back/Forward")
    await tab.js("byId('skills-query').value='';byId('skills-filter').requestSubmit()")
    await tab.wait("installedSkills.length===20 && skillsOffset===0")
    # Focus remains on a stable row through a refresh, then native dialogs return it.
    await tab.js(
        "window.focusRow=byId('skill-items').querySelector('.collection-open');focusRow.focus()"
    )
    await tab.js("refreshDomain('integrations')")
    assert await tab.js("document.activeElement===focusRow")
    await tab.command(
        "Input.dispatchKeyEvent",
        {
            "type": "keyDown",
            "key": "Enter",
            "code": "Enter",
            "windowsVirtualKeyCode": 13,
            "text": "\r",
        },
    )
    await tab.command(
        "Input.dispatchKeyEvent",
        {
            "type": "keyUp",
            "key": "Enter",
            "code": "Enter",
            "windowsVirtualKeyCode": 13,
        },
    )
    await tab.wait("skillDialog.open")
    assert await tab.js("document.activeElement===byId('skill-detail-close')")
    for _ in range(5):
        await tab.command(
            "Input.dispatchKeyEvent",
            {"type": "keyDown", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
        )
        await tab.command(
            "Input.dispatchKeyEvent",
            {"type": "keyUp", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
        )
        assert await tab.js(
            "skillDialog.contains(document.activeElement) || document.activeElement===document.body"
        )
    await tab.command(
        "Input.dispatchKeyEvent",
        {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
    )
    await tab.command(
        "Input.dispatchKeyEvent",
        {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
    )
    await tab.wait("!skillDialog.open")
    assert await tab.js("document.activeElement===focusRow")
    await click("#skill-items .collection-open")
    await tab.wait("skillDialog.open")
    await tab.js("history.back()")
    await tab.wait(
        "!skillDialog.open && skillsOffset===20 && installedSkills.length===6 && "
        "!byId('skill-items').matches('[aria-busy=true]')"
    )
    await tab.js("history.forward()")
    await tab.wait(
        "skillsOffset===0 && installedSkills.length===20 && "
        "!byId('skill-items').matches('[aria-busy=true]')"
    )
    checks.append("Keyboard refresh retains row identity; native details trap and restore focus")

    await tab.command("Accessibility.enable")
    tree = await tab.command("Accessibility.getFullAXTree")
    actionable = [
        n
        for n in tree["nodes"]
        if not n.get("ignored")
        and n.get("role", {}).get("value")
        in ("button", "switch", "searchbox", "combobox", "menuitem")
    ]
    assert actionable and all(n.get("name", {}).get("value") for n in actionable)
    switches = [n for n in actionable if n.get("role", {}).get("value") == "switch"]
    assert len(switches) == 20 and all(
        any(p.get("name") == "checked" for p in n.get("properties", [])) for n in switches
    )
    checks.append("Chrome accessibility tree exposes named controls and checked Skill switches")

    await tab.command(
        "Emulation.setEmulatedMedia",
        {
            "features": [
                {"name": "prefers-reduced-motion", "value": "reduce"},
                {"name": "forced-colors", "value": "active"},
            ]
        },
    )
    await click("#nav-library")
    await tab.wait("filePage?.items.length>0 && !byId('library-items').matches('[aria-busy=true]')")
    assert await tab.js("!byId('library-view').getAnimations().length")
    await tab.js("byId('artifact-query').focus()")
    assert await tab.js("getComputedStyle(document.activeElement).outlineStyle!=='none'")
    await screenshot("a11y-forced-colors-390.png")
    await tab.command("Emulation.setEmulatedMedia", {"features": []})
    checks.append("Forced colors retain focus cues; reduced motion removes entry animation")

    # Text-only 200% stress: enlarge computed fonts/line heights on the scoped UI.
    # This is not physical-device/browser zoom certification.
    reset_scale = """(() => {
      for (const [e,size,line] of window.textScaleStyles||[]) {
        e.style.fontSize=size;e.style.lineHeight=line;
      }
      window.textScaleStyles=[];
    })()"""
    scale_js = """(() => {
      const selectors=['.collection-title','.collection-description','.collection-metadata',
        '.skill-row-status','#skill-detail-description','#skill-detail .preview-metadata',
        '#integrations-view .view-heading h1','#library-view .view-heading h1',
        '.section-chips button','.tab-count','.file-name','.file-secondary',
        '.file-breadcrumbs','#artifact-query','#skills-query','#knowledge-query',
        '#knowledge-library','#artifact-sort','#artifact-kind','#artifact-status',
        '.rail .nav-item','#skills-refresh','#library-refresh','.domain-form summary'];
      const elements=[...new Set(selectors.flatMap(s=>[...document.querySelectorAll(s)]))]
        .filter(e=>e.getClientRects().length);
      const values=elements.map(e=>{
        const s=getComputedStyle(e),size=parseFloat(s.fontSize),line=parseFloat(s.lineHeight);
        return {e,size,line};
      });
      window.textScaleStyles=values.map(({e})=>[e,e.style.fontSize,e.style.lineHeight]);
      for(const {e,size,line} of values) {
        e.style.fontSize=size*2+'px';
        e.style.lineHeight=Number.isFinite(line)?line*2+'px':'1.5';
      }
      return values.every(({e,size})=>parseFloat(getComputedStyle(e).fontSize)===size*2);
    })()"""
    scaled = []
    for width in (360, 390, 768, 1280):
        await tab.command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": 844,
                "deviceScaleFactor": 1,
                "mobile": width < 560,
            },
        )
        for section in ("files", "skills", "knowledge"):
            await tab.js(reset_scale)
            await tab.js(
                "showView(" + json.dumps("library" if section == "files" else "integrations") + ")"
            )
            if section == "files":
                await tab.wait("!byId('library-items').matches('[aria-busy=true]')")
            else:
                await tab.click(f'[data-integration="{section}"]')
                grid_id = "skill-items" if section == "skills" else "knowledge-items"
                await tab.wait(f'!byId("{grid_id}").matches("[aria-busy=true]")')
            assert await tab.js(scale_js)
            await screenshot(f"a11y-text-200-{section}-{width}.png")
            state = await tab.js("""(() => {
              const view=document.querySelector('.main-view:not([hidden])');
              const rail=document.querySelector('.rail');
              const heading=view.querySelector('.view-heading h1').getBoundingClientRect();
              const refresh=view.querySelector('.view-heading button').getBoundingClientRect();
              const intersects=(a,b)=>a.left<b.right && a.right>b.left &&
                a.top<b.bottom && a.bottom>b.top;
              return {headingOverlap:intersects(heading,refresh),
                navigationOverlap:innerWidth<=560 &&
                  view.getBoundingClientRect().bottom>rail.getBoundingClientRect().top,
                documentOverflow:document.documentElement.scrollWidth>innerWidth,
                contentOverflow:view.scrollWidth>view.clientWidth,
                railOverflow:rail.scrollWidth>rail.clientWidth,
                clippedLabels:[...document.querySelectorAll('.rail button')]
                  .filter(e=>e.getClientRects().length).flatMap(e=>{
                    const label=e.lastElementChild,r=label.getBoundingClientRect();
                    const b=e.getBoundingClientRect();
                    return r.right>b.right+1 || r.left<b.left-1?[e.id]:[];
                  })};})()""")
            scaled.append({"width": width, "section": section, **state})
    await tab.js(reset_scale)
    for state in scaled:
        assert not any(
            state[k]
            for k in (
                "documentOverflow",
                "contentOverflow",
                "railOverflow",
                "clippedLabels",
                "headingOverlap",
                "navigationOverlap",
            )
        ), state
    checks.append("Doubled text stays readable without heading/navigation overlap at four widths")
    observations["text_scale"] = scaled
    contrast = []
    for theme in ("light", "dark"):
        for palette in ("lavender", "sage", "peach", "ocean", "rose", "teal", "amber", "slate"):
            await tab.js(
                "document.documentElement.dataset.theme="
                + json.dumps(theme)
                + ";document.documentElement.dataset.palette="
                + json.dumps(palette)
            )
            ratios = await tab.js(r"""(() => {
              const rgb=role=>{
                const e=document.createElement('span');e.style.color='var('+role+')';
                document.body.append(e);
                const color=getComputedStyle(e).color;e.remove();
                return color.match(/[\d.]+/g).slice(0,3).map(Number);
              };
              const luminance=role=>rgb(role).map(c=>c/255)
                .map(c=>c<=.04045?c/12.92:((c+.055)/1.055)**2.4)
                .reduce((sum,c,i)=>sum+c*[.2126,.7152,.0722][i],0);
              return [['--on-surface','--surface'],['--muted','--surface'],
                ['--primary','--surface'],['--on-secondary-container','--secondary-container']]
                .map(([foreground,background])=>{
                  const a=luminance(foreground),b=luminance(background);
                  return {foreground,background,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
                });
            })()""")
            assert all(pair["ratio"] >= 4.5 for pair in ratios), (theme, palette, ratios)
            contrast.append(
                {"theme": theme, "palette": palette, "minimum": min(p["ratio"] for p in ratios)}
            )
    observations["text_contrast"] = contrast
    checks.append(
        "Sampled collection text color pairs meet 4.5:1 across all eight light/dark palettes"
    )
    return {"checks": checks, "observations": observations, "browser_exceptions": len(tab.errors)}


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    with tempfile.TemporaryDirectory(prefix="klaude-refinement-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace = root, Workspace(root)
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        service = LibraryManagement(cfg, root)
        fixtures(service)
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts, library=service, staging_dir=root / "staging")
        host.local_models = lambda: []
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, service, chrome), 180))
        finally:
            host.stop()
            thread.join(3)


if __name__ == "__main__":
    main()

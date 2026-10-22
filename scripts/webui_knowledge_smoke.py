"""Real HTTP/Chrome Knowledge browser with an isolated SQLite index and no model calls.

Screenshots and evidence: /tmp/klaude-knowledge-validation. Run with .venv/bin/python.
"""
# ruff: noqa: E501
from __future__ import annotations

import asyncio
import base64
import json
import os
import sqlite3
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
import webui_expressive_smoke as fixture
from webui_control_smoke import Tab

OUT = Path("/tmp/klaude-knowledge-validation")


def seed(root):
    root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(root / "fts.db") as db:
        db.executescript("""
            CREATE VIRTUAL TABLE chunks USING fts5(id UNINDEXED,collection UNINDEXED,source UNINDEXED,text);
            CREATE TABLE chunk_sources(id,collection,source,PRIMARY KEY(id,collection,source));
            CREATE TABLE active_sources(library,owner,source,version_id,PRIMARY KEY(library,owner,source));
            CREATE TABLE source_versions(version_id PRIMARY KEY,library,owner,source,checksum,status,chunk_count,operation_id,created_at,activated_at,error);
            CREATE TABLE disabled_skills(name PRIMARY KEY);
            CREATE VIRTUAL TABLE chunks_v2 USING fts5(id UNINDEXED,library UNINDEXED,owner UNINDEXED,source UNINDEXED,version_id UNINDEXED,text);
        """)
        for library, source, count in (("Engineering guides", "https://example.com/guides/atomic-indexing", 45),
                                       ("Engineering guides", "upload:team-notes.md", 2),
                                       ("Product handbook", "https://example.com/product", 1)):
            owner, version = "learn:" + source, "version:" + source
            db.execute("INSERT INTO active_sources VALUES(?,?,?,?)", (library, owner, source, version))
            db.execute("INSERT INTO source_versions VALUES(?,?,?,?,?,'active',?,'fixture',1,1,NULL)",
                       (version, library, owner, source, "checksum", count))
            for index in range(count):
                text = f"# Atomic indexing · section {index + 1}\n\nA library contains sources. Each source is split into readable chunks for retrieval.\n\n" + "Stable versions retain old content until replacement is complete.\n" * 16
                text += '\nDeep needle: C++ transactions.\n\t<script>window.chunkExecuted = true</script>\n'
                db.execute("INSERT INTO chunks_v2 VALUES(?,?,?,?,?,?)", (str(index), library, owner, source, version, text))


async def verify(host, root):
    seed(host.library.data / "knowledge.lance")
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next((Path.home() / ".cache/puppeteer/chrome-headless-shell").glob("*/chrome-headless-shell-linux64/chrome-headless-shell")))
    profile = root / "chrome-knowledge"
    process = subprocess.Popen([chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0", f"--user-data-dir={profile}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    OUT.mkdir(exist_ok=True)
    report = {"fixture_only": True, "layouts": []}
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as response:
            target = json.load(response)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=12_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js('byId("login-password").value=' + json.dumps(host.accounts.initial_password()) + ';byId("account-login").requestSubmit()')
            await tab.wait('latest?.session_id && document.documentElement.dataset.startup==="ready"')
            await tab.js('stream?.close();stream=null;clearInterval(pollTimer);showView("integrations")')
            await tab.click('[data-integration="knowledge"]')
            try:
                await tab.wait('byId("knowledge-items").querySelectorAll(".knowledge-card").length===2')
            except AssertionError:
                print(await tab.js('JSON.stringify({status:byId("knowledge-status").textContent,html:byId("knowledge-items").innerHTML,currentView,integrationSection})'))
                raise
            assert await tab.js('byId("knowledge-library").hidden')
            assert await tab.js('fetch("/api/v1/library/knowledge/contents?unexpected=1").then(r=>r.status)') == 400
            report["read_routes"] = True

            await tab.js('byId("knowledge-query").value="Deep needle";byId("knowledge-query").dispatchEvent(new Event("input"))')
            await tab.wait('knowledgeChunkPage?.total===48 && byId("knowledge-items").getAttribute("aria-busy")==="false"')
            assert await tab.js('byId("knowledge-items").querySelector("mark").textContent') == "Deep needle"
            await tab.click('#knowledge-items .knowledge-chunk-open')
            await tab.wait('byId("knowledge-chunk-reader").open && byId("knowledge-chunk-text").textContent.includes("<script>")')
            assert not await tab.js('window.chunkExecuted===true')
            assert await tab.js('document.activeElement.id') == "knowledge-chunk-title"
            await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
            await tab.command("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
            await tab.wait('!byId("knowledge-chunk-reader").open')
            await tab.wait('document.activeElement.classList.contains("knowledge-chunk-open")')
            await tab.js('knowledgeLocation("Engineering guides")')
            await tab.wait('knowledgeChunkPage?.total===47 && byId("source-items").querySelectorAll(".source-row").length===2')
            report["global_text_search_and_safe_reader"] = True

            # Reader pagination crosses backend pages while the underlying chunk list stays put.
            await tab.js('byId("knowledge-items").querySelectorAll(".knowledge-chunk-open")[19].click()')
            await tab.wait('byId("knowledge-chunk-text").textContent.includes("section 20")')
            await tab.js('byId("knowledge-chunk-next").focus()')
            await tab.click('#knowledge-chunk-next')
            await tab.wait('byId("knowledge-chunk-position").textContent==="21 of 47" && byId("knowledge-chunk-text").textContent.includes("section 21")')
            await tab.wait('document.activeElement.id==="knowledge-chunk-next"')
            await tab.click('#knowledge-chunk-previous')
            await tab.wait('byId("knowledge-chunk-position").textContent==="20 of 47"')
            await tab.click('#knowledge-chunk-close')
            report["reader_cross_page_navigation"] = True

            for width in (1440, 768, 390, 320):
                await tab.command("Emulation.setDeviceMetricsOverride", {"width": width, "height": 820 if width > 390 else 568, "deviceScaleFactor": 1, "mobile": width < 500})
                for theme in ("light", "dark"):
                    await tab.js('applyAppearance(appearance={...appearance,theme:' + json.dumps(theme) + '},true)')
                    await asyncio.sleep(.2)
                    assert await tab.js('document.documentElement.scrollWidth<=innerWidth'), (width, theme)
                    if width < 1000:
                        await tab.js('byId("knowledge-sources").open=true')
                    await tab.click('#source-items .collection-open')
                    await tab.wait('knowledgeSource.includes("atomic-indexing") && knowledgeChunkPage?.total===45 && byId("knowledge-items").getAttribute("aria-busy")==="false"')
                    assert await tab.js('byId("knowledge-delete").textContent') == "Delete source"
                    assert await tab.js('document.documentElement.scrollWidth<=innerWidth')
                    if width < 1000:
                        await tab.js('byId("knowledge-sources").open=false')
                    await tab.js('byId("knowledge-panel").scrollIntoView({block:"start"})')
                    await asyncio.sleep(.2)
                    screenshot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (OUT / f"knowledge-{theme}-{width}.png").write_bytes(base64.b64decode(screenshot["data"]))
                    await tab.click('#knowledge-items .knowledge-chunk-open')
                    await tab.wait('byId("knowledge-chunk-text").textContent.includes("Stable versions")')
                    await asyncio.sleep(.4)
                    geometry = await tab.js('(()=>{const d=byId("knowledge-chunk-reader").getBoundingClientRect(),t=byId("knowledge-chunk-text"),b=byId("knowledge-chunk-close").getBoundingClientRect();return {fits:d.left>=-1&&d.right<=innerWidth+1&&d.top>=-1&&d.bottom<=innerHeight+1,scrolls:t.scrollHeight>t.clientHeight,close:b.height>=43.5&&b.width>=43.5,buttonWidth:b.width,buttonHeight:b.height,box:{x:d.x,y:d.y,width:d.width,height:d.height,innerWidth,innerHeight}}})()')
                    assert all(geometry.values()), (width, theme, geometry)
                    screenshot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (OUT / f"reader-{theme}-{width}.png").write_bytes(base64.b64decode(screenshot["data"]))
                    await tab.click('#knowledge-chunk-close')
                    report["layouts"].append({"width": width, "theme": theme, **geometry})
                    await tab.js('knowledgeLocation("Engineering guides")')
                    await tab.wait('!knowledgeSource && knowledgeChunkPage?.total===47 && byId("knowledge-items").getAttribute("aria-busy")==="false"')

            await tab.js('knowledgeLocation("Engineering guides","upload:team-notes.md")')
            await tab.wait('knowledgeChunkPage?.total===2 && byId("knowledge-items").getAttribute("aria-busy")==="false"')
            await tab.click('#knowledge-delete')
            await tab.wait('byId("domain-review").open')
            assert await tab.js('document.activeElement.id') == "domain-review-cancel"
            assert await tab.js('byId("domain-review-summary").textContent.includes("2 active chunks")')
            await tab.click('#domain-review-cancel')
            await tab.wait('knowledgeDeletePending===null')
            assert host.library.knowledge_contents(library="Engineering guides", source="upload:team-notes.md")["total"] == 2
            report["delete_cancel_preserves_content"] = True

            # Source selection and text queries survive reload and browser history.
            await tab.js('byId("knowledge-query").value="C++";byId("knowledge-search").requestSubmit()')
            await tab.wait('knowledgeQuery==="C++" && knowledgeChunkPage?.total===2')
            await tab.command("Page.reload")
            await tab.wait('typeof latest!=="undefined" && latest?.session_id && knowledgeChunkPage?.total===2')
            assert await tab.js('knowledgeSource') == "upload:team-notes.md"
            await tab.js('stream?.close();stream=null;clearInterval(pollTimer);knowledgeLocation("Engineering guides")')
            await tab.wait('knowledgeChunkPage?.total===47')
            await tab.js('history.back()')
            await tab.wait('knowledgeSource==="upload:team-notes.md" && knowledgeQuery==="C++" && knowledgeChunkPage?.total===2')
            report["history_reload"] = True

            # Confirm deletion through the actual owner review and owned worker.
            await tab.click('#knowledge-delete')
            await tab.wait('byId("domain-review").open')
            await tab.click('#domain-review-confirm')
            await tab.wait('!byId("domain-review").open')
            for _ in range(100):
                await tab.js('loadOperations()')
                if await tab.js('knowledgeDeletePending===null && !knowledgeSource && knowledgeChunkPage?.total===45'):
                    break
                await asyncio.sleep(.1)
            assert host.library.knowledge_contents(library="Engineering guides", source="upload:team-notes.md")["total"] == 0
            assert await tab.js('knowledgeDeletePending===null && !knowledgeSource && knowledgeChunkPage?.total===45')
            report["confirmed_source_deletion"] = True

            # Deliberately ignore AbortSignal to prove obsolete results cannot win.
            await tab.js('window.knowledgeOriginalFetch=fetch.bind(window);window.knowledgeHeld=null;window.fetch=(input,options)=>String(input).includes("/knowledge/contents?")&&new URL(String(input),location.href).searchParams.get("query")==="slow"?new Promise(resolve=>{window.knowledgeHeld=()=>resolve(new Response(JSON.stringify({items:[],mode:"chunks",total:900,offset:0,page_size:20,summary:{sources:1,chunks:900},available:true}))) }):knowledgeOriginalFetch(input,options);byId("knowledge-query").value="slow";byId("knowledge-search").requestSubmit()')
            await tab.wait('knowledgeHeld!==null')
            await tab.js('byId("knowledge-query").value="missing phrase";byId("knowledge-search").requestSubmit()')
            await tab.wait('knowledgeChunkPage?.total===0 && knowledgeQuery==="missing phrase"')
            await tab.js('knowledgeHeld();window.fetch=knowledgeOriginalFetch')
            await asyncio.sleep(.1)
            assert await tab.js('knowledgeChunkPage?.total===0 && byId("knowledge-items").textContent.includes("No matching text")')
            report["obsolete_search_rejected"] = True
            # Whole-library deletion returns to the remaining library inventory.
            await tab.js('knowledgeLocation("Product handbook")')
            await tab.wait('knowledgeChunkPage?.total===1 && byId("knowledge-items").getAttribute("aria-busy")==="false"')
            await tab.click('#knowledge-delete')
            await tab.wait('byId("domain-review").open')
            assert await tab.js('byId("domain-review-title").textContent') == "Delete this knowledge?"
            await tab.click('#domain-review-confirm')
            for _ in range(100):
                await tab.js('loadOperations()')
                if await tab.js('knowledgeDeletePending===null && !byId("knowledge-library").value && byId("knowledge-items").querySelectorAll(".knowledge-card").length===1'):
                    break
                await asyncio.sleep(.1)
            assert host.library.knowledge_contents()["total"] == 1
            report["confirmed_library_deletion"] = True
            await tab.click('#logout')
            await tab.wait('!authenticated && knowledgeChunkPage===null && knowledgeSource===""')
            assert await tab.js('byId("knowledge-chunk-text").textContent==="" && byId("knowledge-breadcrumbs").textContent==="" && byId("knowledge-summary").textContent==="" && knowledgeSourceNames.size===0')
            assert not tab.errors, tab.errors
            report["browser_exceptions"] = tab.errors
            (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({**report, "layouts": len(report["layouts"])}))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    fixture.verify = verify
    fixture.main()

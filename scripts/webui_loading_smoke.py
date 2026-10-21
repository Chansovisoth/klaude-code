"""Isolated Chrome checks for delayed WebUI reads and skeleton lifecycle.

Run with the workspace development environment and websockets installed.
KLAUDE_TEST_CHROME optionally selects Chrome; screenshots go to
/tmp/klaude-loading-preview. Domain reads use controlled browser responses.
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
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools.toolkit import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.webui_control_smoke import Tab  # noqa: E402
from tests.unit.test_webhost import _app  # noqa: E402

TRANSPORT = """
(() => {
  // Exercise restoration from the old Library navigation as assets are upgraded.
  if (!sessionStorage.getItem('klaude.webui.navigation.v1.library-section') &&
      !sessionStorage.getItem('loading-tested-default'))
    sessionStorage.setItem('klaude.webui.navigation.v1.library-section', 'knowledge');
  const original = fetch.bind(window);
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  let firstSession = true;
  window.pendingReads = [];
  window.autoCounts = false;
  window.autoOperations = false;
  window.slowSnapshot = false;
  window.countData = Object.fromEntries(['knowledge','document','media','research',
    'files','outputs','archive','skills'].map(key => [key, {total: 1, limited: false}]));
  window.fetch = async (resource, options) => {
    const url = new URL(typeof resource === 'string' ? resource : resource.url, location.href);
    if (url.pathname === '/api/v1/session' && (firstSession || slowSnapshot)) {
      firstSession = false; await wait(650);
    }
    if (url.pathname === '/api/v1/sessions') await wait(500);
    if (url.pathname === '/api/v1/models/local') {
      await wait(500);
      return new Response(JSON.stringify({models:[{id:'fixture',name:'Fixture'}]}));
    }
    if (url.pathname.startsWith('/api/v1/library/') ||
        url.pathname.startsWith('/api/v1/integrations/') ||
        url.pathname.startsWith('/api/v1/workspace/')) {
      if (url.pathname.endsWith('/counts') && autoCounts)
        return new Response(JSON.stringify(countData));
      if (url.pathname.endsWith('/operations') && autoOperations)
        return new Response(JSON.stringify({items:[]}));
      return new Promise(resolve => {
        const entry = {path:url.pathname, search:url.search, done:false,
          body:options?.body ? JSON.parse(options.body) : null};
        entry.reply = (data, status) => {
          entry.done = true;
          resolve(new Response(JSON.stringify(data), {status,
            headers:{'Content-Type':'application/json'}}));
        };
        pendingReads.push(entry);
      });
    }
    return original(resource, options);
  };
  window.reply = (path, data, status=200, search='') => {
    const entry = pendingReads.find(item => !item.done && item.path === path &&
      item.search.includes(search));
    if (!entry) throw Error('No pending read: '+path+' '+search);
    entry.reply(data,status); return true;
  };
})();
"""


async def verify(host, profile, chrome):
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
    output = Path("/tmp/klaude-loading-preview")
    output.mkdir(exist_ok=True)
    try:
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            await asyncio.sleep(0.05)
        port = int(active.read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"]) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.addScriptToEvaluateOnNewDocument", {"source": TRANSPORT})
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 390,
                    "height": 760,
                    "deviceScaleFactor": 1,
                    "mobile": True,
                },
            )

            async def screenshot(name):
                await asyncio.sleep(0.25)
                result = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / name).write_bytes(base64.b64decode(result["data"]))

            async def reply(path, data, status=200, search=""):
                await tab.js(
                    f"reply({json.dumps(path)},{json.dumps(data)},{status},{json.dumps(search)})"
                )

            async def skeleton(target_id):
                await tab.wait(f'document.querySelector("#{target_id} .loading-skeleton")!==null')
                assert await tab.js(f'byId("{target_id}").getAttribute("aria-busy")==="true"')
                assert await tab.js("document.documentElement.scrollWidth<=innerWidth")

            def page(items):
                return {
                    "items": items,
                    "total": len(items),
                    "page_size": 20,
                    "known_total": len(items),
                    "more": False,
                }

            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait(
                'document.querySelector("#account-login")&&!document.querySelector("#local-access").hidden'
            )
            await tab.js(
                'byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await skeleton("chat-loading")
            assert await tab.js('getComputedStyle(byId("welcome")).display==="none"')
            await screenshot("conversation-390.png")
            await skeleton("session-list")
            await skeleton("model-status")
            await tab.wait("pollTimer!==null&&sessionsLoaded&&localModels.length===1")
            assert await tab.js(
                'byId("chat-loading").hidden&&messages.querySelector("strong")!==null'
            )
            await tab.js(
                'window.savedParagraph=messages.querySelector("p");'
                "slowSnapshot=true;void snapshot();true"
            )
            await asyncio.sleep(0.2)
            assert await tab.js(
                '!byId("chat-loading").querySelector(".loading-skeleton")&&savedParagraph.isConnected'
            )
            await tab.js("slowSnapshot=false")
            await asyncio.sleep(0.5)

            await tab.click("#nav-integrations")
            await skeleton("knowledge-items")
            await tab.wait('document.querySelector("#integration-sections .skeleton-count")!==null')
            assert await tab.js('byId("integration-sections").textContent.includes("Knowledge")')
            await screenshot("library-390.png")
            await reply(
                "/api/v1/library/counts",
                {
                    key: {"total": 1}
                    for key in ("knowledge", "document", "media", "research", "archive", "skills",
                                "files", "outputs")
                },
            )
            await tab.js("autoCounts=true")
            knowledge = {"id": "docs", "sources": 2, "chunks": 10}
            await reply("/api/v1/library/knowledge", page([knowledge]))
            await tab.wait('byId("knowledge-items").getAttribute("aria-busy")==="false"')
            await tab.js(
                'window.savedCard=byId("knowledge-items").firstElementChild;'
                'void loadKnowledge();true'
            )
            await asyncio.sleep(0.2)
            assert await tab.js(
                'savedCard.isConnected&&!byId("knowledge-items").querySelector(".loading-skeleton")'
            )
            await reply(
                "/api/v1/library/knowledge", {"error": {"message": "Fixture unavailable"}}, 503
            )
            await tab.wait('byId("knowledge-status").textContent.includes("Fixture unavailable")')
            assert await tab.js(
                'savedCard.isConnected&&byId("knowledge-items").getAttribute("aria-busy")==="false"'
            )

            assert await tab.js("""
              [...byId('library-sections').querySelectorAll('button')]
                .map(node=>node.dataset.section).join(',')==='files,outputs' &&
              byId('library-sections').querySelector('[data-count-key="files"] .tab-count')
                .textContent==='1'
            """)
            await tab.click("#nav-library")
            await tab.click('[data-section="files"]')
            await reply("/api/v1/library/items", page([]), search="kind=all")
            await tab.click('[data-file-view="list"]')
            await tab.wait('byId("library-items").getAttribute("aria-busy")==="false"')
            assert await tab.js('byId("library-items").textContent.includes("No uploads")')
            await screenshot("files-empty-list-390.png")
            await tab.js("""
              byId('artifact-kind').value='document';
              byId('artifact-kind').dispatchEvent(new Event('change'));true
            """)
            await skeleton("library-items")
            assert await tab.js('''(() => {
              const row=byId('library-items').querySelector('.skeleton-row');
              return row && row.getBoundingClientRect().height===68 &&
                byId('library-items').getBoundingClientRect().top-
                byId('artifact-filter').getBoundingClientRect().bottom<=6;
            })()''')
            await screenshot("files-loading-list-390.png")
            await tab.js("""
              byId('artifact-kind').value='media';
              byId('artifact-kind').dispatchEvent(new Event('change'));true
            """)
            await skeleton("library-items")
            await tab.js('window.newPlaceholder=byId("library-items").firstElementChild')
            await reply(
                "/api/v1/library/items", {"error": {"message": "Old failure"}}, 503, "kind=document"
            )
            assert await tab.js(
                'newPlaceholder.isConnected&&byId("library-items").getAttribute("aria-busy")==="true"'
            )
            await tab.command(
                "Emulation.setEmulatedMedia",
                {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]},
            )
            assert await tab.js(
                'getComputedStyle(newPlaceholder.querySelector(".skeleton-line")).animationName==="none"'
            )
            await tab.command("Emulation.setEmulatedMedia", {"features": []})
            item = {
                "id": "fixture",
                "revision": "v1",
                "name": "Saved file",
                "filename": "note.txt",
                "kind": "media",
                "mime": "text/plain",
                "size": 32,
                "created": 1792454400,
                "tags": [],
                "ai_tags": [],
                "archived": False,
                "width": 0,
                "height": 0,
            }
            await reply("/api/v1/library/items", page([item]), search="kind=media")
            await tab.wait('byId("library-items").textContent.includes("Saved file")')
            await tab.click('[data-section="outputs"]')
            await tab.js("""
              byId('artifact-status').value='archived';
              byId('artifact-status').dispatchEvent(new Event('change'));true
            """)
            await reply("/api/v1/library/items", page([]), search="archived=false")
            await skeleton("library-items")
            assert await tab.js("""
              pendingReads.some(item=>!item.done && item.search.includes('source=output') &&
                item.search.includes('archived=true')) &&
              sessionStorage.getItem('klaude.webui.navigation.v1.output-status')==='archived'
            """)
            report = {**item, "kind": "research", "archived": True}
            await reply("/api/v1/library/items", page([report]), search="archived=true")
            await tab.wait('byId("library-items").textContent.includes("Report") && '
                           'byId("file-breadcrumbs").textContent==="LibraryGenerated" && '
                           'byId("artifact-status").value==="archived"')
            for index, width in enumerate((320, 390, 768, 1440, 390)):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 760,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                await asyncio.sleep(0.3)
                await tab.js(
                    "pendingReads.filter(item=>!item.done&&item.path.endsWith('/items'))"
                    f".forEach(item=>item.reply({json.dumps(page([report]))},200));true"
                )
                await tab.wait('byId("library-items").getAttribute("aria-busy")==="false"')
                assert await tab.js("""
                  document.documentElement.scrollWidth<=innerWidth &&
                  byId('library-view').scrollWidth<=byId('library-view').clientWidth+1
                """)
                await screenshot(f"files-{width}.png")
                # Dense placeholders and empty results also adapt across the table breakpoint.
                query = f"empty-{width}-{index}"
                await tab.js(f'byId("artifact-query").value={json.dumps(query)};'
                             'byId("artifact-filter").requestSubmit()')
                await skeleton("library-items")
                assert await tab.js('byId("library-items").querySelector(".skeleton-row")'
                                    '.getBoundingClientRect().height===68')
                await screenshot(f"files-loading-list-{width}.png")
                await reply("/api/v1/library/items", page([]), search=f"query={query}")
                await tab.wait('byId("library-items").getAttribute("aria-busy")==="false"')
                assert await tab.js(
                    '''(() => {
                      const empty=byId('library-items').querySelector('.library-empty');
                      return empty?.textContent.includes('No files match') &&
                        empty.getAttribute('role')==='status' &&
                        empty.getBoundingClientRect().top>=
                          byId('artifact-filter').getBoundingClientRect().bottom &&
                        byId('library-status').textContent==='' &&
                        !byId('library-items').querySelector('.file-list-header') &&
                        document.documentElement.scrollWidth<=innerWidth;
                    })()'''
                )
                await screenshot(f"files-empty-list-{width}.png")
                await tab.js('byId("artifact-query").value="";'
                             'byId("artifact-filter").requestSubmit()')
                await tab.wait('byId("library-items").getAttribute("aria-busy")==="false"')
                assert await tab.js('!byId("library-items").querySelector(".library-empty")')
            assert await tab.js("!byId('artifact-import-panel').open")
            await tab.click("#file-add")
            assert await tab.js("!byId('artifact-import-kind') && !byId('artifact-file').accept")
            await tab.click("#artifact-import-close")

            await tab.js('void openArtifact("fixture");true')
            await skeleton("artifact-preview")
            assert await tab.js('artifactDialog.open&&byId("artifact-tags").hidden')
            await screenshot("preview-390.png")
            await tab.click("#artifact-close")
            await reply("/api/v1/library/item", {"item": item, "lines": ["Private preview"]})
            await asyncio.sleep(0.1)
            assert await tab.js("!artifactDialog.open&&selectedArtifact===null")
            await tab.js("""
              window.skeletonFlashed=false;
              window.previewObserver=new MutationObserver(records=>{
                if(records.some(record=>[...record.addedNodes].some(node=>
                  node.classList?.contains('loading-skeleton')))) skeletonFlashed=true;
              });
              previewObserver.observe(byId('artifact-preview'),{childList:true});
              void openArtifact('fixture');true
            """)
            await reply("/api/v1/library/item", {"item": item, "lines": ["Private preview"]})
            await tab.wait('byId("artifact-preview").textContent.includes("Private preview")')
            assert await tab.js('!byId("artifact-preview").querySelector(".loading-skeleton")')
            assert await tab.js("!skeletonFlashed")
            await tab.js("previewObserver.disconnect()")
            await tab.click("#artifact-close")

            await tab.js('byId("knowledge-library").value="docs"')
            await tab.click("#nav-integrations")
            await tab.click('[data-integration="knowledge"]')
            await reply("/api/v1/library/knowledge", page([knowledge]))
            await skeleton("source-items")
            await reply(
                "/api/v1/library/sources",
                page(
                    [
                        {
                            "id": "docs-source",
                            "url": "https://example.com/docs",
                            "kind": "llms",
                            "files": 2,
                            "library": "docs",
                            "identity": "fixture",
                        }
                    ]
                ),
            )
            await tab.wait('byId("source-items").textContent.includes("docs-source")')
            assert await tab.js('byId("knowledge-tools").closest("#integrations-view")!==null && '
                                'byId("library-sections").querySelectorAll("button").length===2')
            # The moved learning and refresh forms retain reviewed requests and cancellation.
            for operation in ("knowledge-url", "knowledge-refresh"):
                if operation == "knowledge-url":
                    await tab.click("#integration-add-knowledge")
                    await tab.js('byId("learn-library").value="docs";'
                                 'byId("learn-url").value="https://example.com/docs";'
                                 'byId("knowledge-learn").requestSubmit()')
                else:
                    await tab.click("#source-items button")
                await tab.wait('pendingReads.some(item=>!item.done && '
                               'item.path==="/api/v1/library/review")')
                assert await tab.js('pendingReads.find(item=>!item.done && '
                                    'item.path==="/api/v1/library/review").body.draft.operation==='
                                    + json.dumps(operation))
                await reply("/api/v1/library/review", {
                    "review_id": "knowledge-review", "summary": "Review Knowledge change",
                    "expires_at": 9999999999,
                })
                await tab.wait('reviewDialog.open')
                assert await tab.js('document.activeElement===byId("domain-review-cancel")')
                await tab.click("#domain-review-cancel")
                await tab.wait('!reviewDialog.open')
                await tab.wait('pendingReads.some(item=>!item.done && '
                               'item.path==="/api/v1/library/discard")')
                await reply("/api/v1/library/discard", {"discarded": True})
            await tab.click('[data-integration="skills"]')
            assert await tab.js("""
              document.querySelector('[data-count-key="mcp"]').textContent
                .includes('Connections') &&
              !document.querySelector('[data-count-key="mcp"]').disabled
            """)
            await skeleton("skill-items")
            await reply("/api/v1/integrations/skills", page([]))
            await tab.wait('byId("skills-status").textContent.includes("No installed Skills")')
            assert await tab.js('byId("skill-items").getAttribute("aria-busy")==="false"')
            await tab.click("#nav-activity")
            await skeleton("domain-operations")
            await reply("/api/v1/library/operations", {"items": []})
            await tab.js("autoOperations=true")
            await tab.wait('byId("domain-operations").textContent.includes("No Library")')

            await tab.click("#nav-workspace")
            await skeleton("workspace-result")
            await screenshot("workspace-390.png")
            await reply("/api/v1/workspace/files", {"text": "note.txt"})
            await tab.wait('byId("workspace-result").querySelector("pre")!==null')
            await tab.js('window.savedFile=byId("workspace-result").querySelector("pre")')
            await tab.click("#browse")
            await asyncio.sleep(0.2)
            assert await tab.js(
                'savedFile.isConnected&&!byId("workspace-result").querySelector(".loading-skeleton")'
            )
            await reply(
                "/api/v1/workspace/files", {"error": {"message": "Workspace unavailable"}}, 503
            )
            await tab.wait('byId("workspace-result").textContent.includes("Workspace unavailable")')
            assert await tab.js("savedFile.isConnected")
            await tab.js('byId("workspace-path").value="other"')
            await tab.click("#browse")
            await tab.js('byId("workspace-path").value="note.txt"')
            await tab.click("#read-file")
            await skeleton("workspace-result")
            await reply("/api/v1/workspace/files", {"text": "Stale listing"})
            assert await tab.js('byId("workspace-result").getAttribute("aria-busy")==="true"')
            await reply("/api/v1/workspace/file", {"text": "Current file"})
            await tab.wait('byId("workspace-result").textContent.includes("Current file")')
            assert await tab.js('!byId("workspace-result").textContent.includes("Stale listing")')

            for width in (320, 1440):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 760,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                await tab.js(
                    f'byId("workspace-path").value="width-{width}";void workspaceRead("files");true'
                )
                await skeleton("workspace-result")
                await screenshot(f"workspace-{width}.png")
                await reply("/api/v1/workspace/files", {"text": f"Ready at {width}"})
                await tab.wait('byId("workspace-result").getAttribute("aria-busy")==="false"')

            for old, kind, status in (
                ("media", "media", "saved"),
                ("archive", "all", "archived"),
                ("files", "research", "archived"),
                (None, "all", "saved"),
            ):
                await tab.js("""
                  saveNavigationChoice('page','library');
                  window.reloadMarker=true;
                """)
                if old is None:
                    await tab.js("""
                      for(const key of ['library-section','file-kind','file-status'])
                        sessionStorage.removeItem('klaude.webui.navigation.v1.'+key);
                    """)
                    # The transport's legacy fixture only seeds empty navigation on initial load.
                    await tab.js("sessionStorage.setItem('loading-tested-default','true')")
                else:
                    await tab.js(
                        f"saveNavigationChoice('library-section',{json.dumps(old)});"
                        f"saveNavigationChoice('file-kind',{json.dumps(kind)});"
                        f"saveNavigationChoice('file-status',{json.dumps(status)});"
                    )
                # Simulate an old stored tab with no explicit Library URL state.
                await tab.js('history.replaceState(null,"",location.pathname)')
                await tab.command("Page.reload")
                await tab.wait(
                    "typeof reloadMarker==='undefined' && "
                    "typeof pollTimer!=='undefined' && pollTimer!==null && authenticated"
                )
                await tab.wait("pendingReads.some(item=>item.path.endsWith('/items'))")
                section = "outputs" if kind == "research" else "files"
                filter_kind = "document" if kind == "research" else kind
                assert await tab.js(
                    "currentView==='library' && "
                    f"librarySection==={json.dumps(section)} && "
                    f"byId('artifact-kind').value==={json.dumps(filter_kind)} && "
                    f"byId('artifact-status').value==={json.dumps(status)} && "
                    "pendingReads.some(item=>item.search.includes("
                    f"'kind={kind}')&&item.search.includes('archived="
                    f"{str(status == 'archived').lower()}'))"
                )
                await reply(
                    "/api/v1/library/counts",
                    {"files": {"total": 3}, "outputs": {"total": 3}},
                )
                await reply("/api/v1/library/items", page([item]))
                await tab.js("""
                  autoCounts=true;autoOperations=true;
                  pendingReads.filter(item=>!item.done&&item.path.endsWith('/operations'))
                    .forEach(item=>item.reply({items:[]},200));true
                """)
                await tab.wait('byId("library-items").getAttribute("aria-busy")==="false"')
                assert await tab.js("""
                  byId('library-sections').querySelector('[data-count-key="files"] .tab-count')
                    .textContent==='3'
                """)

            await tab.click("#nav-integrations")
            await tab.click('[data-integration="knowledge"]')
            await reply("/api/v1/library/knowledge", page([knowledge]))
            await tab.js('knowledgeQuery="pending";void loadKnowledge();void refreshModels();true')
            await skeleton("knowledge-items")
            await tab.click("#logout")
            await tab.wait("!authenticated")
            await reply("/api/v1/library/knowledge", page([knowledge]))
            await asyncio.sleep(0.6)
            assert await tab.js(
                'activeLoading.size===0&&!document.querySelector(".loading-skeleton")'
            )
            assert await tab.js('!document.querySelector(".library-card")&&!artifactDialog.open')
            assert await tab.js('localModels.length===0&&byId("model-status").textContent===""')
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "passed": [
                            "initial chat, sessions and models",
                            "Library, Sources, Skills and operations",
                            "Integrations Knowledge learning and source-refresh reviews",
                            "Library files and Integrations Knowledge hierarchy and counts",
                            "independent archived report filters and stored navigation",
                            "automatic file import without a type selector or file restriction",
                            "Connections naming with existing availability",
                            "legacy Media/Archive migration and filter restoration on reload",
                            "Files default and Files layouts at 320/390/768/1440px",
                            "dense list loading and empty states at mobile/desktop breakpoints",
                            "Generated empty messages appear in content below the toolbar",
                            "workspace reads",
                            "immediate cancellable item preview",
                            "fast-read delay",
                            "retained content on refresh and errors",
                            "out-of-order response ownership",
                            "reduced motion",
                            "320/390/1440px layouts",
                            "sign-out and late-result cleanup",
                        ],
                        "console_errors": tab.errors,
                        "screenshots": str(output),
                    },
                    indent=2,
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=10)


def main():
    chrome = (
        os.environ.get("KLAUDE_TEST_CHROME")
        or shutil.which("chromium")
        or shutil.which("google-chrome")
    )
    if not chrome:
        candidates = list(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
        if not candidates:
            raise SystemExit("Set KLAUDE_TEST_CHROME to a Chrome executable")
        chrome = str(candidates[-1])
    with tempfile.TemporaryDirectory(prefix="klaude-loading-") as folder:
        root = Path(folder)
        config_module.DATA_DIR = root / "data"
        config_module.CONFIG_DIR = root / "config"
        accounts = AccountStore(Config().config_dir)
        accounts.initialize()
        app = _app(root)
        app.agent.workdir = root
        app.agent.workspace = Workspace(root)
        app.memory.log_turn(app.session_id, "user", "A saved question")
        app.memory.log_turn(app.session_id, "assistant", "A **saved** answer.")
        app.agent.restore_session(app.memory.load_session(app.session_id))
        host = LocalWebHost(app, accounts=accounts)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root / "chrome", chrome), 120))
        finally:
            host.stop()
            thread.join(3)


if __name__ == "__main__":
    main()

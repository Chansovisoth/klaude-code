"""Isolated Chrome validation for reviewed profile management.

KLAUDE_TEST_GENERATED_ONLY=1 stops after the Generated dialog and job checks.
KLAUDE_TEST_CONNECTIONS_ONLY=1 isolates the add/direct-toggle regression.
KLAUDE_TEST_SCREENSHOTS optionally saves Generated dialog screenshots.
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
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools import Workspace
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_image_generation import generation_lab  # noqa: E402
from tests.unit.test_webhost import _app  # noqa: E402


class Embeddings(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/embed":
            body = json.dumps({"embeddings": [[0.1, 0.2, 0.3] for _ in request["input"]]}).encode()
        elif self.path == "/api/show":
            body = json.dumps({"capabilities": ["completion", "tools", "vision"]}).encode()
        else:
            assert self.path == "/api/chat"
            text = ('["amber", "diagram"]' if request["messages"][1]["content"].startswith(
                "Suggest 2 to 8"
            ) else "Amber widget test image.")
            body = b"".join(json.dumps(item).encode() + b"\n" for item in [
                {"message": {"content": text}}, {"message": {"content": ""}, "done": True,
                                                 "done_reason": "stop"},
            ])
        self.reply(body)

    def do_GET(self):
        assert self.path == "/api/tags"
        self.reply(json.dumps({"models": [{"name": "vision", "model": "vision"}]}).encode())

    def reply(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


async def verify_integration_forms(tab):
    await tab.click("#nav-integrations")
    for width in (320, 390, 768, 1440):
        await tab.command("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": 820, "deviceScaleFactor": 1, "mobile": False,
        })
        await asyncio.sleep(.25)
        for section, form in (("skills", "skill-import"), ("knowledge", "knowledge-learn"),
                              ("connections", "connection-add")):
            await tab.click(f"[data-integration={section}]")
            await tab.wait(f"!byId('integration-add-{section}').disabled")
            await tab.js(f"byId('integration-add-{section}').focus()")
            await tab.click(f"#integration-add-{section}")
            await tab.wait("integrationAddDialog.open")
            assert await tab.js(
                f"byId('{form}').getClientRects().length > 0 && "
                "integrationAddDialog.scrollWidth <= integrationAddDialog.clientWidth"
            )
            if width == 390:
                await tab.js("Promise.all(integrationAddDialog.getAnimations()"
                             ".map(animation => animation.finished.catch(() => {})))")
                preview = Path("/tmp/klaude-integrations-preview")
                preview.mkdir(exist_ok=True)
                screenshot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (preview / f"{section}-add.png").write_bytes(base64.b64decode(screenshot["data"]))
            await tab.command("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": "Escape", "code": "Escape",
                "windowsVirtualKeyCode": 27,
            })
            await tab.command("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": "Escape", "code": "Escape",
                "windowsVirtualKeyCode": 27,
            })
            await tab.wait("!integrationAddDialog.open")
            assert await tab.js(f"document.activeElement === byId('integration-add-{section}')")
            geometry = await tab.js("""(() => {
                const panel = byId(`${integrationSection}-panel`);
                const plus = panel.querySelector('.integration-add').getBoundingClientRect();
                const search = panel.querySelector('input[type=search]').getBoundingClientRect();
                return {width:plus.width,height:plus.height,gap:plus.bottom-search.bottom,
                  right:plus.right,viewport:innerWidth,submit:Boolean(
                    panel.querySelector('button[type=submit]')),
                  pageWidth:document.documentElement.scrollWidth};
            })()""")
            assert (geometry["width"] == 48 and geometry["height"] == 48
                    and abs(geometry["gap"]) < 2 and geometry["right"] <= width
                    and not geometry["submit"] and geometry["pageWidth"] <= width), (
                        width, section, geometry
                    )

    await tab.click("[data-integration=skills]")
    await tab.click("#integration-add-skills")
    await tab.js("""(() => {
        byId('skill-name').value='modal-skill'; byId('skill-library').value='skills';
        const files = new DataTransfer();
        files.items.add(new File(['# Modal Skill. Use compact interfaces.'],
          'SKILL.md', {type:'text/markdown'}));
        byId('skill-file').files=files.files; byId('skill-import').requestSubmit();
    })()""")
    await tab.wait("reviewDialog.open && !integrationAddDialog.open")
    await tab.click("#domain-review-confirm")
    await tab.wait("byId('skill-items').textContent.includes('modal-skill')")

    await tab.click("[data-integration=knowledge]")
    await tab.click("#integration-add-knowledge")
    await tab.js("""(() => {
        byId('learn-library').value='modal-docs';
        const files = new DataTransfer();
        files.items.add(new File(['A rainbow appears after rain.'],
          'reference.txt', {type:'text/plain'}));
        byId('learn-file').files=files.files; byId('knowledge-learn').requestSubmit();
    })()""")
    await tab.wait("reviewDialog.open && !integrationAddDialog.open")
    await tab.click("#domain-review-confirm")
    await tab.wait("byId('knowledge-items').textContent.includes('modal-docs')")
    await tab.js("byId('knowledge-library').value='modal-docs';"
                 "byId('knowledge-library').dispatchEvent(new Event('change'));"
                 "byId('knowledge-query').value='rainbow';"
                 "byId('knowledge-query').dispatchEvent(new Event('input'))")
    await tab.wait("knowledgeQuery === 'rainbow' && "
                   "byId('knowledge-items').textContent.includes('rainbow')")

    # Closing a form during preparation must discard the late review.
    await tab.click("#integration-add-knowledge")
    await tab.js("""window.integrationFetch=fetch.bind(window);window.integrationDiscards=0;
      window.fetch=(input,options)=>{
        if(String(input).endsWith('/library/discard')) integrationDiscards++;
        return String(input).endsWith('/library/review') ?
          new Promise(resolve=>{window.releaseIntegrationReview=()=>
            resolve(integrationFetch(input,options));}) : integrationFetch(input,options);
      };
      byId('learn-library').value='modal-docs';
      byId('learn-url').value='https://example.com/docs';
      byId('knowledge-learn').requestSubmit();""")
    await tab.wait("typeof releaseIntegrationReview === 'function'")
    await tab.click("#integration-add-close")
    await tab.js("releaseIntegrationReview()")
    await tab.wait("integrationDiscards > 0")
    await tab.js("window.fetch=integrationFetch")
    assert await tab.js("!reviewDialog.open && !integrationAddDialog.open")
    await tab.click("[data-integration=connections]")
    await tab.wait("!byId('integration-add-connections').disabled")
    await tab.click("#integration-add-connections")
    await tab.js("byId('connection-name').value='modal-mcp';"
                 "byId('connection-url').value='https://example.test/mcp';"
                 "byId('connection-add').requestSubmit()")
    await tab.wait("reviewDialog.open && !integrationAddDialog.open")
    assert await tab.js("byId('domain-review-summary').textContent.includes('modal-mcp')")
    await tab.click("#domain-review-cancel")
    await tab.wait("!byId('integration-add-connections').disabled")


async def verify_connections(tab, host):
    await tab.click("#nav-integrations")
    await tab.click("[data-integration=connections]")
    await tab.wait("byId('connection-items').textContent.includes('No MCP connections')")
    await tab.click("#integration-add-connections")
    await tab.wait("integrationAddDialog.open")
    await tab.js(
        "byId('connection-name').value='fixture';"
        "byId('connection-url').value='https://example.test/mcp';"
        "byId('connection-add').requestSubmit()"
    )
    await tab.wait("byId('domain-review').open")
    await tab.click("#domain-review-confirm")
    await tab.wait(
        "byId('connection-items').textContent.includes('fixture') && "
        "!BrowserManagement.hasPending()"
    )
    assert await tab.js('''(()=>{
      const group=byId("connections-state-filter"),buttons=[...group.children];
      return !group.hasAttribute("data-segment-layout") && buttons.every(button=>{
        const face=button.querySelector(".filter-chip-face"),style=getComputedStyle(face);
        return button.getBoundingClientRect().height>=48 && face.getBoundingClientRect().height===32 &&
          style.borderTopLeftRadius==="8px" && style.borderTopRightRadius==="8px";
      }) && buttons.filter(button=>button.getAttribute("aria-pressed")==="true").length===1;
    })()''')
    assert not host.library.cfg.mcp_servers_file.is_symlink()
    await tab.wait("!byId('connection-items').querySelector('.connection-toggle').disabled")
    assert await tab.js(
        "byId('connection-items').querySelector('.connection-toggle')"
        ".getAttribute('aria-checked') === 'false' && "
        "!byId('connection-items').querySelector('.danger')"
    )
    await tab.click("#connection-items .collection-open")
    await tab.wait("byId('connection-detail').open")
    assert await tab.js(
        "byId('connection-detail-title').textContent === 'fixture' && "
        "byId('connection-detail-metadata').textContent.includes('Local configuration')"
    )
    await tab.click("#connection-detail-close")
    await tab.js("""window.toggleFetch=fetch.bind(window);window.fetch=(input,options)=>
      String(input).endsWith('/library/review') ? new Promise(resolve=>{
        window.releaseConnectionReview=()=>resolve(new Response(
          JSON.stringify({error:{message:'Fixture toggle rejected'}}),{status:400}));
      }) : toggleFetch(input,options);""")
    await tab.click("#connection-items .connection-toggle")
    await tab.wait("typeof releaseConnectionReview==='function'")
    assert await tab.js(
        "byId('connection-items').querySelector('.collection-metadata').textContent.startsWith('Updating… ·') && "
        "!byId('connection-items').querySelector('.integration-row-status').textContent"
    )
    await tab.js("releaseConnectionReview()")
    await tab.wait("!byId('connection-items').querySelector('.connection-toggle').disabled")
    assert await tab.js(
        "byId('connection-items').querySelector('.connection-toggle')"
        ".getAttribute('aria-checked') === 'false' && !reviewDialog.open && "
        "byId('connections-status').textContent.includes('Fixture toggle rejected')"
    )
    await tab.js("window.fetch=toggleFetch")


async def verify(host, root, chrome, session, image_url):
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
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(0.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
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
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait(
                "typeof authenticated !== 'undefined' && authenticated && latest && sessionsLoaded"
            )
            if os.environ.get("KLAUDE_TEST_CONNECTIONS_ONLY") == "1":
                await verify_connections(tab, host)
                await tab.click("#logout")
                await tab.wait("!authenticated")
                assert not tab.errors, tab.errors
                print(json.dumps({"connections": "add remains reviewed; direct toggle rejection "
                                  "retains confirmed state without a modal", "console_errors": 0}))
                return
            if os.environ.get("KLAUDE_TEST_INTEGRATIONS_ONLY") == "1":
                await verify_integration_forms(tab)
                await tab.click("#integration-add-connections")
                await tab.js("showView('chat')")
                assert await tab.js("!integrationAddDialog.open")
                await tab.js("showView('integrations')")
                await tab.wait("!byId('integration-add-connections').disabled")
                await tab.click("#integration-add-connections")
                await tab.js("byId('connection-name').value='Private draft'")
                await tab.click("#logout")
                await tab.wait("!authenticated && !integrationAddDialog.open")
                assert await tab.js("!byId('connection-name').value && !byId('skill-file').value")
                assert not tab.errors, tab.errors
                print(json.dumps({
                    "integrations": "plus/dialog/focus/import/learn/live-search/"
                                    "review-cancellation/navigation/logout passed",
                    "widths": [320, 390, 768, 1440], "console_errors": 0,
                }))
                return
            await tab.click("#nav-settings")
            await tab.click("#settings-tab-models")
            await tab.wait("!byId('memory-auto').disabled")
            await tab.wait("Boolean(byId('default-value-vision'))")
            await tab.js("byId('default-model-catalog').requestSubmit()")
            await tab.wait("[...byId('default-value-vision').options].some(item => "
                           "item.value.endsWith('/vision'))")
            for role in ["vision", "research"]:
                await tab.js(f"byId('default-value-{role}').value=[...byId('default-value-{role}')"
                             ".options].find(item => item.value.endsWith('/vision')).value;"
                             f"byId('default-value-{role}').closest('form').requestSubmit()")
                await tab.wait("byId('domain-review').open")
                await tab.click("#domain-review-confirm")
                await tab.wait("!byId('domain-review').open && "
                               f"!BrowserManagement.hasPending() && byId('default-value-{role}')"
                               ".value.endsWith('/vision')")
            await tab.click("#default-vision-enabled")
            await tab.wait("byId('domain-review').open")
            await tab.click("#domain-review-confirm")
            await tab.wait("!byId('domain-review').open && !BrowserManagement.hasPending() && "
                           "byId('default-vision-enabled').checked")
            await tab.click("#settings-tab-models")
            await tab.js(f"byId('image-service-url').value={json.dumps(image_url)};"
                         "byId('image-service-enabled').checked=true;"
                         "byId('image-service-save').requestSubmit()")
            await tab.wait("byId('domain-review').open")
            await tab.click("#domain-review-confirm")
            await tab.wait("!byId('domain-review').open && !BrowserManagement.hasPending() && "
                           "byId('image-service-enabled').checked")
            await tab.click("#settings-tab-agent")
            await tab.wait("Boolean(byId('setting-runtime_options-max_steps'))")
            await tab.js(
                "byId('setting-runtime_options-max_steps').value='7';byId('setting"
                "-runtime_options-max_steps').closest('form').requestSubmit()"
            )
            await tab.wait("byId('domain-review').open")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "byId('setting-runtime_options-max_steps').value === '7' && !Brows"
                "erManagement.hasPending() && !byId('domain-review').open"
            )
            await tab.click("#settings-tab-memory")
            await tab.js(
                "byId('memory-fact').value='Prefer concise responses';"
                "byId('memory-add').requestSubmit()"
            )
            await tab.wait("byId('domain-review').open")
            assert not host.application.memory.search_facts("concise")
            await tab.click("#domain-review-confirm")
            await tab.wait("byId('memory-items').textContent.includes('Prefer concise responses')")
            await tab.click("#memory-auto")
            await tab.wait("byId('domain-review').open")
            await tab.click("#domain-review-confirm")
            await tab.wait("!byId('memory-auto').checked && !byId('memory-auto').disabled")
            await verify_integration_forms(tab)
            await verify_connections(tab, host)
            await tab.command("Page.reload")
            await tab.wait(
                "typeof authenticated !== 'undefined' && authenticated && "
                "currentView === 'integrations' && integrationSection === 'connections'"
            )
            await tab.wait("byId('connection-items').textContent.includes('fixture')")
            await tab.wait("sessionsLoaded && sessions.length > 0")
            await tab.js("toggleSessions(true)")
            await tab.click("#session-list .session-row button:last-child")
            await tab.wait("byId('session-management').open")
            await tab.js(
                "byId('session-name').value='Browser notes';byId('session-rename').requestSubmit()"
            )
            await tab.wait("byId('domain-review').open")
            await tab.click("#domain-review-confirm")
            await tab.wait("sessions.some(item => item.title === 'Browser notes')")
            await tab.js("toggleSessions(false)")
            await tab.click("#nav-library")
            await tab.click("[data-section=outputs]")
            await tab.wait(
                "!byId('generated-tools').hidden && !byId('image-add').disabled"
            )
            await tab.click("#image-add")
            await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
            await tab.click("#generation-tab-research")
            await tab.js(
                "byId('research-question').value='Compare atomic transactions';byId('research-"
                "create').requestSubmit()"
            )
            await tab.wait("reviewDialog.open && !byId('image-generate-panel').open")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "byId('research-jobs').textContent.includes('Compare atomic transa"
                "ctions') && !BrowserManagement.hasPending()"
            )
            await tab.click("#image-add")
            await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
            await tab.js(
                "[...byId('research-jobs').querySelectorAll('button')].find(button"
                " => button.textContent === 'Stop').click()"
            )
            await tab.wait("byId('domain-review').open")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "byId('research-jobs').textContent.includes('cancelled') && !Brows"
                "erManagement.hasPending()"
            )
            await tab.click("#image-add")
            await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
            await tab.click("#generation-tab-image")
            await tab.click("#image-generate-close")
            for width, height in [(320, 568), (390, 844), (768, 1024), (1440, 900)]:
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1,
                    "mobile": width < 600,
                })
                await tab.js("byId('image-add').focus()")
                await tab.click("#image-add")
                await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
                await tab.wait("byId('image-generate-panel').open")
                assert await tab.js("document.activeElement === byId('image-prompt')")
                geometry = await tab.js("""(() => {
                    const plus = byId('image-add').getBoundingClientRect();
                    const trailing = byId('artifact-query').getBoundingClientRect();
                    const dialog = byId('image-generate-panel');
                    const jobs = byId('image-jobs');
                    return {width:plus.width,height:plus.height,gap:plus.left-trailing.right,
                      aligned:Math.abs(plus.bottom-trailing.bottom)<2,filtersVisible:byId("file-option-fields").getClientRects().length>0,
                      jobsBelowForm:dialog.contains(jobs) &&
                        jobs.getBoundingClientRect().top >=
                        byId('image-generate').getBoundingClientRect().bottom,
                      fits:dialog.scrollWidth<=dialog.clientWidth &&
                        document.documentElement.scrollWidth<=innerWidth};
                })()""")
                assert (geometry["width"] == geometry["height"] == 48
                        and geometry["filtersVisible"] and geometry["aligned"]
                        and 0 <= geometry["gap"] <= 8 and geometry["fits"]
                        and geometry["jobsBelowForm"]), (width, geometry)
                if output := os.environ.get("KLAUDE_TEST_SCREENSHOTS"):
                    directory = Path(output)
                    directory.mkdir(parents=True, exist_ok=True)
                    await tab.js("Promise.all(byId('image-generate-panel').getAnimations()"
                                 ".map(animation => animation.finished))")
                    capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (directory / f"generated-dialog-{width}.png").write_bytes(
                        base64.b64decode(capture["data"])
                    )
                await tab.js("byId('image-prompt').value='Image tab draft';"
                             "byId('generation-tab-image').focus()")
                await tab.command("Input.dispatchKeyEvent", {
                    "type": "keyDown", "key": "ArrowRight", "code": "ArrowRight",
                    "windowsVirtualKeyCode": 39,
                })
                await tab.command("Input.dispatchKeyEvent", {
                    "type": "keyUp", "key": "ArrowRight", "code": "ArrowRight",
                    "windowsVirtualKeyCode": 39,
                })
                assert await tab.js("document.activeElement === byId('generation-tab-research')"
                                   " && byId('generation-tab-research').tabIndex === 0"
                                   " && byId('generation-tab-image').tabIndex === -1"
                                   " && byId('generation-image').hidden"
                                   " && !byId('generation-research').hidden")
                await tab.js("byId('research-question').value='Research tab draft';"
                             "byId('research-format').value='comparison'")
                assert await tab.js("byId('image-generate-panel').scrollWidth <= "
                                   "byId('image-generate-panel').clientWidth && "
                                   "byId('research-jobs').getBoundingClientRect().top >= "
                                   "byId('research-create').getBoundingClientRect().bottom")
                if output:
                    capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (directory / f"generated-research-{width}.png").write_bytes(
                        base64.b64decode(capture["data"])
                    )
                await tab.click("#generation-tab-image")
                assert await tab.js("byId('image-prompt').value === 'Image tab draft'")
                await tab.click("#generation-tab-research")
                assert await tab.js("byId('research-question').value === 'Research tab draft'"
                                   " && byId('research-format').value === 'comparison'")
                await tab.click("#generation-tab-image")
                await tab.command("Input.dispatchKeyEvent", {
                    "type": "keyDown", "key": "Escape", "code": "Escape",
                    "windowsVirtualKeyCode": 27,
                })
                await tab.command("Input.dispatchKeyEvent", {
                    "type": "keyUp", "key": "Escape", "code": "Escape",
                    "windowsVirtualKeyCode": 27,
                })
                await tab.wait("!byId('image-generate-panel').open")
                assert await tab.js("document.activeElement === byId('image-add')")
                assert await tab.js("byId('file-option-fields').getClientRects().length > 0")

            # Tab changes invalidate preparation for either form while keeping drafts.
            await tab.click("#image-add")
            await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
            for kind, form in [("image", "image-generate"), ("research", "research-create")]:
                await tab.click(f"#generation-tab-{kind}")
                await tab.js("""window.tabDraftFetch=fetch.bind(window);window.tabDraftDiscards=0;
                  window.releaseTabReview=undefined;window.fetch=(input,options)=>{
                    if(String(input).endsWith('/library/discard')) tabDraftDiscards++;
                    return String(input).endsWith('/library/review') ?
                      new Promise(resolve=>{window.releaseTabReview=()=>
                        resolve(tabDraftFetch(input,options));}) : tabDraftFetch(input,options);
                  };""")
                await tab.js(f"byId('{form}').requestSubmit()")
                await tab.wait("typeof releaseTabReview === 'function'")
                await tab.click(f"#generation-tab-{'research' if kind == 'image' else 'image'}")
                await tab.js("releaseTabReview()")
                await tab.wait("tabDraftDiscards > 0 && !byId('image-generate').querySelector"
                               "('button').disabled && !byId('research-create').querySelector"
                               "('button').disabled")
                await tab.js("window.fetch=tabDraftFetch")
                assert await tab.js("!reviewDialog.open && byId('image-generate-panel').open")
            await tab.click("#image-generate-close")

            # Closing during preparation discards its late review.
            await tab.click("#image-add")
            await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
            await tab.js("""window.imageDialogFetch=fetch.bind(window);window.imageDialogDiscards=0;
              window.fetch=(input,options)=>{
                if(String(input).endsWith('/library/discard')) imageDialogDiscards++;
                return String(input).endsWith('/library/review') ?
                  new Promise(resolve=>{window.releaseImageReview=()=>
                    resolve(imageDialogFetch(input,options));}) : imageDialogFetch(input,options);
              };
              byId('image-prompt').value='Amber mountain';byId('image-generate').requestSubmit();
            """)
            await tab.wait("typeof releaseImageReview === 'function'")
            await tab.click("#image-generate-close")
            await tab.js("releaseImageReview()")
            await tab.wait("imageDialogDiscards > 0 && !byId('image-add').disabled")
            await tab.js("window.fetch=imageDialogFetch")
            assert await tab.js("!reviewDialog.open && !byId('image-generate-panel').open")
            await tab.click("#image-add")
            await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
            await tab.js("byId('image-generate').requestSubmit()")
            await tab.wait("reviewDialog.open && !byId('image-generate-panel').open")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "byId('image-jobs').textContent.includes('complete') && !BrowserMa"
                "nagement.hasPending()"
            )
            if os.environ.get("KLAUDE_TEST_GENERATED_ONLY") == "1":
                await tab.click("#image-add")
                await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
                await tab.js("byId('image-jobs').scrollIntoView({block:'nearest'})")
                assert await tab.js(
                    "byId('image-jobs').getClientRects().length > 0 && "
                    "!byId('library-view').contains(byId('research-create')) && "
                    "byId('image-generate-panel').contains(byId('research-jobs'))"
                )
                await tab.click("#image-jobs button")
                await tab.wait("byId('artifact-detail').open")
                await tab.click("#artifact-close")
                await tab.wait("!byId('artifact-detail').open && byId('image-generate-panel').open")
                await tab.js("showView('chat')")
                assert await tab.js("!byId('image-generate-panel').open")
                await tab.js("showView('library')")
                await tab.wait("!byId('image-add').disabled")
                await tab.click("#image-add")
                await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
                await tab.click("[data-section=files]")
                assert await tab.js("!byId('image-generate-panel').open && "
                                    "byId('image-add').hidden && !byId('file-add').hidden")
                await tab.click("[data-section=outputs]")
                await tab.wait("!byId('image-add').disabled")
                await tab.click("#image-add")
                await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
                await tab.js("byId('image-prompt').value='Private draft'")
                await tab.click("#generation-tab-research")
                await tab.js("byId('research-question').value='Private research draft'")
                await tab.click("#logout")
                await tab.wait("!authenticated")
                assert await tab.js("!byId('image-generate-panel').open && "
                                    "!byId('image-prompt').value && "
                                    "!byId('research-question').value"
                                    " && byId('image-add').disabled")
                assert not tab.errors, tab.errors
                print(json.dumps({
                    "generated": "Image/Research tabs, drafts, keyboard, late reviews, "
                                 "queue/stop, generation, history/output/navigation/logout passed",
                    "widths": [320, 390, 768, 1440], "console_errors": 0,
                }))
                return
            generated = host.library.listing(kind="media", source="output")["items"][0]
            await tab.js(f"openArtifact({json.dumps(generated['id'])})")
            await tab.wait("byId('artifact-detail').open && !byId('vision-suggest').disabled")
            if await tab.js("artifactDialog.dataset.details==='closed'"):
                await tab.click("#image-details")
            await tab.click("#inspector-tab-ai-review")
            await tab.js("byId('vision-analyze').requestSubmit()")
            await tab.wait("byId('domain-review').open")
            await tab.click("#domain-review-confirm")
            await tab.wait("byId('vision-answer').textContent.includes('Amber widget test image.')"
                           )
            await tab.click("#vision-suggest")
            await tab.wait("byId('domain-review').open")
            await tab.click("#domain-review-confirm")
            await tab.wait("document.querySelector('.tag-filter-chip[data-tag=amber]')"
                           "?.disabled===false "
                           "&& !BrowserManagement.hasPending()")
            assert await tab.js("byId('vision-results').querySelectorAll("
                               "'.tag-filter-chip[aria-pressed=true]').length===0")
            await tab.click(".tag-filter-chip[data-tag=amber]")
            await tab.js("byId('vision-results').querySelector('form').requestSubmit()")
            await tab.wait("byId('domain-review').open")
            await tab.click("#domain-review-confirm")
            await tab.wait("byId('artifact-tag-list').textContent.includes('amber') "
                           "&& !BrowserManagement.hasPending()")
            item = host.library.artifacts.import_bytes(
                b"# Browser learning\nAmber widgets use atomic transactions.",
                "document", "knowledge-notes.md",
            )
            await tab.js(f"openArtifact({json.dumps(item['id'])})")
            await tab.wait("byId('artifact-detail').open && !byId('artifact-learn').hidden")
            await tab.js("byId('artifact-learn-library').value='widgets';"
                         "byId('artifact-learn').requestSubmit()")
            await tab.wait("byId('domain-review').open")
            await tab.click("#domain-review-confirm")
            for _ in range(200):
                completed = next((operation for operation in host.library.operations()["items"]
                                  if operation["kind"] == "artifact-learn"), None)
                if completed and completed["state"] == "completed":
                    break
                assert not completed or completed["state"] not in {"failed", "unknown"}, completed
                await asyncio.sleep(0.1)
            assert host.library.knowledge("widgets", "atomic")["hits"]
            for width, height in [(320, 568), (390, 844), (768, 1024), (1440, 900)]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                for view in ["settings", "integrations", "library"]:
                    await tab.js(f"showView('{view}')")
                    await asyncio.sleep(0.15)
                    assert await tab.js("document.documentElement.scrollWidth <= innerWidth"), (
                        width,
                        view,
                    )
            await tab.js("showView('settings')")
            await tab.wait("byId('memory-items').textContent.includes('Prefer concise responses')")
            await tab.click("#logout")
            await tab.wait("!authenticated")
            assert await tab.js(
                "!byId('memory-items').textContent && !byId('connection-items').textContent && "
                "!byId('memory-fact').value"
            )
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "memory": "review/add/automatic setting/logout passed",
                        "connections": "add disabled/reload/history passed",
                        "conversations": "review/rename passed",
                        "widths": [320, 390, 768, 1440],
                        "console_errors": 0,
                        "settings": "execution/search/fetch/Research fields rendered; "
                                    "review/save passed",
                        "research": "queue/stop passed",
                        "images": "plus/dialog/focus/responsive/dismissal/review/generation passed",
                        "knowledge": "saved document/review/real index passed",
                        "model_defaults": "Vision/Research select and enable passed",
                        "image_service": "test/review/save passed",
                        "vision": "real pixels/analysis/tags/explicit selection/save passed",
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    with tempfile.TemporaryDirectory(prefix="klaude-management-smoke-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        embedding_server = ThreadingHTTPServer(("127.0.0.1", 0), Embeddings)
        embedding_thread = threading.Thread(target=embedding_server.serve_forever, daemon=True)
        embedding_thread.start()
        cfg.models["embed"] = "fixture-embedding"
        cfg.ollama_url = f"http://127.0.0.1:{embedding_server.server_port}"
        cfg.config_dir.mkdir(parents=True)
        (cfg.config_dir / "config.toml").write_text(
            f'[services]\nollama_url = "{cfg.ollama_url}"\n[models.override]\n'
            'coder = "fixture"\nembed = "fixture-embedding"\n'
        )
        app = _app(cfg.data_dir)
        app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        session = uuid.uuid4().hex
        app.turns.bind_workspace(session, str(root), expected_revision=0)
        app.memory.log_turn(session, "user", "A saved conversation")
        service = LibraryManagement(cfg, root)
        host = LocalWebHost(app, library=service, staging_dir=root / "staging")
        host.local_models = lambda: []
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        image_fixture = generation_lab.__wrapped__(root)
        image_url = next(image_fixture)[1]
        try:
            asyncio.run(verify(host, root, chrome, session, image_url))
        finally:
            host.stop()
            thread.join(timeout=3)
            image_fixture.close()
            embedding_server.shutdown()
            embedding_server.server_close()
            embedding_thread.join(timeout=3)


if __name__ == "__main__":
    main()

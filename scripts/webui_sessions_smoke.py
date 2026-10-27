"""Current-conversation archive, fresh chat and restore in isolated Chrome."""

from __future__ import annotations

import asyncio
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
from klaude_tools import Workspace
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402


async def verify(host, root, chrome):
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
        async with websockets.connect(target["webSocketDebuggerUrl"]) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True,
            })
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait("typeof authenticated!=='undefined' && authenticated && latest")
            await tab.send("Keep this conversation")
            await tab.wait("latest.messages.some(m=>m.role==='assistant') && "
                           "!latest.active_turn_id")
            original = host.application.session_id
            await tab.js("refreshSessions()")
            await tab.js("toggleSessions(true)")
            await tab.click("#session-list .session-row button:last-child")
            await tab.wait("byId('session-management').open")
            assert await tab.js("!byId('session-archive').disabled && "
                                "!byId('session-rename').querySelector('button')")
            await tab.js("byId('session-name').value='\\u0001Invalid'; "
                         "byId('session-rename').requestSubmit()")
            await tab.wait("byId('session-management-status').textContent"
                           ".includes('Enter a conversation name')")
            assert await tab.js("byId('session-management').open && !reviewDialog.open && "
                                "!byId('session-name').disabled")
            await tab.js("byId('session-name').value='Renamed   conversation'; "
                         "byId('session-name').focus()")
            await tab.command("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13,
                "text": "\r",
            })
            await tab.command("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": "Enter", "code": "Enter",
            })
            await tab.wait("byId('session-management-status').textContent==='Saved.' && "
                           "!BrowserManagement.hasPending()")
            assert await tab.js("byId('session-management').open && !reviewDialog.open && "
                                "byId('session-name').value==='Renamed conversation'")
            assert await tab.js("fetch(byId('session-export').href).then(async r => "
                                "r.ok && (await r.text()).includes('Keep this conversation'))")
            for width in [320, 390, 1000]:
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 844, "deviceScaleFactor": 1, "mobile": width < 600,
                })
                assert await tab.js("(()=>{const a=byId('session-export').getBoundingClientRect(),"
                                    "b=byId('session-archive').getBoundingClientRect();"
                                    "return Math.abs(a.top-b.top)<1 && a.right<=b.left && "
                                    "a.left>=0 && b.right<=innerWidth})()")
                assert await tab.js("(()=>{const nodes=[...document.querySelectorAll("
                                    "'.session-dialog-actions > .quiet')];"
                                    "const signatures=nodes.map(node=>{"
                                    "const s=getComputedStyle(node);"
                                    "return JSON.stringify([s.height,s.padding,"
                                    "s.fontSize,s.fontWeight,"
                                    "s.lineHeight,s.gap,s.borderWidth,s.backgroundColor,"
                                    "getComputedStyle(node.querySelector('svg')).width])});"
                                    "return nodes.length===3 && new Set(signatures).size===1 && "
                                    "nodes.every(n=>{const r=n.getBoundingClientRect();"
                                    "return r.left>=0 && r.right<=innerWidth}) && "
                                    "byId('session-delete').textContent==='Delete'})()")
                if width >= 390:
                    assert await tab.js("(()=>{const ys=[...document.querySelectorAll("
                                        "'.session-dialog-actions > .quiet')].map(n=>"
                                        "n.getBoundingClientRect().top);"
                                        "return Math.max(...ys)-Math.min(...ys)<1})()")
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True,
            })
            await tab.click("#session-archive")
            await tab.wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-summary').textContent.includes('new chat')")
            await tab.click("#domain-review-cancel")
            await tab.wait("!reviewDialog.open && "
                           "!byId('session-list').querySelector('.session-row button:last-child')"
                           ".disabled")
            assert host.application.session_id == original
            assert not host.application.memory.session_archived(original)

            await tab.click("#session-list .session-row button:last-child")
            await tab.click("#session-archive")
            await tab.wait("reviewDialog.open")
            await tab.js("""window.sessionFetch=fetch.bind(window);
              window.fetch=(input,options)=>{
                if(String(input).endsWith('/library/submit') && options?.method==='POST')
                  window.sessionArchiveBody=JSON.parse(options.body);
                return sessionFetch(input,options);
              };
            """)
            await tab.click("#domain-review-confirm")
            await tab.wait("!reviewDialog.open && latest.session_id!==" + json.dumps(original) +
                           " && currentView==='chat' && !BrowserManagement.hasPending()")
            selected = host.application.session_id
            assert host.application.memory.session_archived(original)
            assert len(host.application.memory.load_session(original)) == 2
            assert await tab.js("latest.messages.length===0 && !byId('welcome').hidden && "
                                "!layout.classList.contains('sessions-open')")
            assert not host.application.memory.load_session(selected)
            await tab.js("domainRequest('/api/v1/library/submit','POST',sessionArchiveBody)")
            assert host.application.session_id == selected
            await tab.js("toggleSessions(true)")
            await tab.click("#archived-sessions")
            await tab.wait("byId('session-list').textContent.includes('Renamed conversation')")
            await tab.click("#session-list .session-row button:last-child")
            assert await tab.js("byId('session-archive').textContent.includes('Restore')")
            await tab.click("#session-archive")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait("!reviewDialog.open && !BrowserManagement.hasPending()")
            assert not host.application.memory.session_archived(original)
            assert host.application.session_id == selected
            await tab.click("#archived-sessions")
            await tab.wait("byId('session-list').textContent.includes('Renamed conversation')")
            assert not tab.errors, tab.errors
            class WaitingRuntime:
                def __init__(self):
                    self.entered = threading.Event()
                    self.release = threading.Event()

                def chat(self, *_args, **_kwargs):
                    self.entered.set()
                    assert self.release.wait(15)
                    return {"role": "assistant", "content": "Background work finished"}

                def close(self):
                    pass

            waiting = [WaitingRuntime(), WaitingRuntime()]
            try:
                first = host.application
                first.agent.runtime = first.agent.ollama = waiting[0]
                await tab.send("Background one")
                await tab.wait("latest.active_turn_id && !byId('new-session').disabled")
                assert waiting[0].entered.is_set()
                await tab.click("#new-session")
                await tab.wait("latest.session_id!==" + json.dumps(first.session_id))
                second = host.application
                second.agent.runtime = second.agent.ollama = waiting[1]
                await tab.send("Background two")
                await tab.wait("latest.active_turn_id")
                assert waiting[1].entered.is_set() and first.active_turn_id()
                await tab.js("refreshSessions()")
                assert await tab.js("document.querySelectorAll('.session-running').length===2")
                assert await tab.js("document.querySelectorAll("
                                    "'.session-running > .material-loading').length===2")
                await tab.js("window.busySessionIndicator="
                             "document.querySelector('.session-running')")
                await tab.js("refreshSessions()")
                assert await tab.js("busySessionIndicator==="
                                    "document.querySelector('.session-running')")
                await tab.js("toggleSessions(true)")
                await tab.click(f'[data-session-open="{first.session_id}"]')
                await tab.wait("latest.session_id===" + json.dumps(first.session_id))
                assert host.application is first and second.active_turn_id()
                waiting[0].release.set()
                await tab.wait("!latest.active_turn_id")
                await tab.js("refreshSessions()")
                assert await tab.js("document.querySelectorAll('.session-running').length===1")
                await tab.js("toggleSessions(true)")
                await tab.click(f'[data-session-open="{second.session_id}"]')
                await tab.wait("latest.session_id===" + json.dumps(second.session_id))
                waiting[1].release.set()
                await tab.wait("!latest.active_turn_id")
                second_id = second.session_id
                await tab.js("refreshSessions()")
                await tab.js("toggleSessions(true)")
                await tab.click(
                    f'.session-row:has([data-session-open="{second_id}"]) button:last-child'
                )
                assert await tab.js("!byId('session-delete').hidden")
                await tab.click("#session-delete")
                await tab.wait("reviewDialog.open")
                assert await tab.js("byId('domain-review-summary').textContent"
                                    ".includes('cannot be undone')")
                await tab.click("#domain-review-confirm")
                await tab.wait("!reviewDialog.open && !BrowserManagement.hasPending() && "
                               "latest.session_id!==" + json.dumps(second_id))
                assert not second.memory.load_session(second_id)
                assert first.memory.load_session(first.session_id)
            finally:
                for runtime in waiting:
                    runtime.release.set()
            assert not tab.errors, tab.errors
            print(json.dumps({"current_archive": "review/cancel/archive/fresh chat/"
                                                "retry/restore passed",
                              "conversation_dialog": "Enter rename/error/download/layout passed",
                              "parallel_conversations": "two workers/switch/status passed",
                              "saved_delete": "current unarchived conversation passed",
                              "width": 390, "console_errors": 0}))
    finally:
        process.terminate()
        process.wait(timeout=10)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    ))
    with tempfile.TemporaryDirectory(prefix="klaude-current-archive-") as folder:
        root = Path(folder)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        def factory():
            app = _app(cfg.data_dir)
            app.agent.workdir, app.agent.workspace = root, Workspace(root)
            app.agent.tool_config = cfg
            app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
            return app

        host = LocalWebHost(factory(), library=LibraryManagement(cfg, root),
                            staging_dir=root / "staging", application_factory=factory)
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome), 60))
        finally:
            host.stop()
            serving.join(3)


if __name__ == "__main__":
    main()

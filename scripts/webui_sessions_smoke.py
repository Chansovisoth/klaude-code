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
                                "byId('session-management-description').textContent"
                                ".includes('new chat')")
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
            await tab.wait("byId('session-list').textContent.includes('Keep this conversation')")
            await tab.click("#session-list .session-row button:last-child")
            assert await tab.js("byId('session-archive').textContent.includes('Restore')")
            await tab.click("#session-archive")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait("!reviewDialog.open && !BrowserManagement.hasPending()")
            assert not host.application.memory.session_archived(original)
            assert host.application.session_id == selected
            await tab.click("#archived-sessions")
            await tab.wait("byId('session-list').textContent.includes('Keep this conversation')")
            assert not tab.errors, tab.errors
            print(json.dumps({"current_archive": "review/cancel/archive/fresh chat/"
                                                "retry/restore passed",
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
        app = _app(cfg.data_dir)
        app.agent.workdir, app.agent.workspace = root, Workspace(root)
        app.agent.tool_config = cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        host = LocalWebHost(app, library=LibraryManagement(cfg, root),
                            staging_dir=root / "staging")
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome), 60))
        finally:
            host.stop()
            serving.join(3)


if __name__ == "__main__":
    main()

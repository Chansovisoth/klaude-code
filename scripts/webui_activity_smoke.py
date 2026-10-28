"""Real-browser activity, approval, cancellation and reconnect regression check.

Run: .venv/bin/python scripts/webui_activity_smoke.py
Uses an isolated profile and deterministic runtime; never contacts a model.
"""

from __future__ import annotations

import asyncio
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
from klaude_application.activity import Activity
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools.toolkit import Workspace, build_tools
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab


class Runtime:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def chat(self, _model, messages, **_kwargs):
        if messages[-1]["role"] == "user":
            text = messages[-1]["content"]
            if text == "Read note.txt":
                return {"role": "assistant", "content": "", "tool_calls": [{
                    "function": {"name": "read_file", "arguments": {"path": "note.txt"}},
                }]}
            if text == "Ask me":
                return {"role": "assistant", "content": "", "tool_calls": [{
                    "function": {"name": "request_user_input", "arguments": {
                        "question": "Choose a path", "options": [{"label": "A"}],
                    }},
                }]}
            if text == "Fail":
                raise RuntimeError("Fixture provider failed")
            if text == "Wait":
                self.entered.set()
                assert self.release.wait(15)
        return {"role": "assistant", "content": "A confirmed fixture response."}

    def cancel_active(self):
        self.release.set()
        return True

    def close(self):
        pass


async def verify(host, root, chrome, runtime):
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
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=4_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId !== "undefined" && !byId("local-access").hidden')
            await tab.js('byId("login-username").value="admin";'
                        'byId("login-password").value=' + json.dumps(
                host.accounts.initial_password()
            ) + ';byId("account-login").requestSubmit()')
            await tab.wait('latest?.session_id')
            await tab.send("Read note.txt")
            await tab.wait('byId("agent-activity-label").textContent === "Needs input"')
            identity = await tab.js('latest.approvals[0].id')
            await tab.js('window.activityReload=true')
            await tab.command("Page.reload")
            await tab.wait('!window.activityReload && typeof latest !== "undefined" && '
                           'latest?.approvals.length === 1')
            assert await tab.js('byId("agent-activity-label").textContent') == "Needs input"
            assert await tab.js('latest.approvals[0].id') == identity
            await tab.click("#approvals button")
            await tab.idle()
            await tab.wait('byId("agent-activity-label").textContent === "Done"')
            await tab.js('byId("agent-activity").open=true')
            assert await tab.js('byId("agent-activity-timeline").textContent.includes("read_file")')
            assert await tab.js(
                'byId("messages").textContent.includes("confirmed fixture response")')
            await tab.js('stream.close();stream=null;snapshot()')
            assert await tab.js('byId("agent-activity-label").textContent') == "Done"
            await tab.send("Ask me")
            await tab.wait('latest?.questions.length === 1')
            assert await tab.js('byId("agent-activity-label").textContent') == "Needs input"
            await tab.js('byId("questions").querySelector("button").click()')
            await tab.idle()
            await tab.send("Wait")
            await tab.wait('latest?.active_turn_id && !pending && !byId("cancel").disabled')
            assert runtime.entered.wait(2)
            assert await tab.js('byId("agent-activity-label").textContent') == "Generating response"
            await tab.click("#cancel")
            await tab.idle()
            await tab.wait('byId("agent-activity-label").textContent === "Cancelled"')
            await tab.send("Fail")
            await tab.idle()
            await tab.wait('byId("agent-activity-label").textContent === "Error"')
            await tab.js('window.activityReload=true')
            await tab.command("Page.reload")
            await tab.wait('!window.activityReload && typeof latest !== "undefined" && '
                           'latest?.activity.label === "Error"')
            # Presentation fixtures cover labels for tools unavailable to browser
            # chat today. Execution classification is covered by Python tests.
            for width in (1440, 768, 390, 320):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 844, "deviceScaleFactor": 1, "mobile": False,
                })
                for activity in Activity:
                    value = {"turn_id": "presentation", "label": activity.value,
                             "lifecycle": "completed" if activity == Activity.DONE else "running",
                             "active_count": 2, "recoverable": activity == Activity.ERROR,
                             "timeline": [{"kind": "tool.started", "label": activity.value,
                                           "tool": "fixture"}]}
                    await tab.js(f"renderAgentActivity({json.dumps(value)})")
                    assert (await tab.js('byId("agent-activity-label").textContent')
                            == activity.value)
                    assert await tab.js('document.documentElement.scrollWidth <= innerWidth')
                    for expanded in (False, True):
                        await tab.js(f'byId("agent-activity").open={json.dumps(expanded)}')
                        assert await tab.js('''(() => {
                          const card=byId("agent-activity"), wrapper=card.parentElement;
                          const style=getComputedStyle(wrapper);
                          const available=wrapper.clientWidth-parseFloat(style.paddingLeft)-
                            parseFloat(style.paddingRight);
                          return card.getBoundingClientRect().width<=480 &&
                            card.getBoundingClientRect().width<=available+1 &&
                            card.scrollWidth<=card.clientWidth;
                        })()''')
            await tab.command("Emulation.setEmulatedMedia", {"features": [
                {"name": "prefers-reduced-motion", "value": "reduce"},
            ]})
            assert await tab.js(
                'getComputedStyle(document.querySelector(".activity-dot")).animationName'
            ) == "none"
            await tab.click("#logout")
            await tab.wait('!authenticated')
            assert await tab.js('byId("agent-activity").hidden')
            assert not tab.errors, tab.errors
            print("PASS: all 13 labels at desktop/phone widths; actual approvals, questions,")
            print("completion, failure, cancellation, reload, SSE reconnect and reduced motion.")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or shutil.which("chromium")
    if not chrome:
        candidates = list((Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        ))
        if not candidates:
            raise SystemExit("Set KLAUDE_TEST_CHROME to a headless Chrome executable")
        chrome = str(candidates[-1])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.unit.test_webhost import _app

    with tempfile.TemporaryDirectory(prefix="klaude-activity-smoke-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR = root / "config"
        config_module.DATA_DIR = root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir = root
        app.agent.workspace = Workspace(root)
        app.agent.tool_config = cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        app.agent.tools = {t.name: t for t in build_tools(app.agent.workspace)
                           if t.name == "read_file"}
        app.agent.gate.policies.update(read_file="ask", request_user_input="allow")
        app.allow_approvals = app.allow_user_input_tool = True
        (root / "note.txt").write_text("Real file contents.\n")
        runtime = Runtime()
        app.agent.runtime = app.agent.ollama = runtime
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts)
        host.local_models = lambda: []
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome, runtime), 90))
        finally:
            runtime.release.set()
            host.stop()
            thread.join(3)


if __name__ == "__main__":
    main()

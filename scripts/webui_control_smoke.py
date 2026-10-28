"""Two-tab and terminal handoff checks in Chrome with an isolated model fixture.

Run: .venv/bin/python scripts/webui_control_smoke.py
Optional: KLAUDE_TEST_CHROME=/path/to/headless-chrome
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
from contextlib import AsyncExitStack
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from klaude_webhost.hosting import ManagedControl, WebHostController


class Tab:
    def __init__(self, ws):
        self.ws = ws
        self.seq = 0
        self.errors = []

    async def command(self, method, params=None):
        self.seq += 1
        await self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params or {}}))
        while True:
            result = json.loads(await self.ws.recv())
            if result.get("method") == "Runtime.exceptionThrown":
                self.errors.append(result["params"])
            if result.get("id") == self.seq:
                assert "error" not in result, result
                return result.get("result", {})

    async def js(self, expression):
        result = await self.command("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True,
        })
        assert "exceptionDetails" not in result, result
        return result.get("result", {}).get("value")

    async def wait(self, expression):
        for _ in range(100):
            if await self.js(expression):
                return
            await asyncio.sleep(0.05)
        raise AssertionError({"waiting": expression, "state": await self.js(
            'JSON.stringify({latest,notice:notice.textContent})'
        ), "errors": self.errors})

    async def click(self, selector):
        assert await self.js(f'!document.querySelector({json.dumps(selector)}).disabled')
        await self.js(f'document.querySelector({json.dumps(selector)}).click()')

    async def send(self, text):
        await self.js(f'prompt.value={json.dumps(text)};byId("composer").requestSubmit()')

    async def idle(self):
        await self.wait('latest && !latest.active_turn_id && !latest.queue.length && !pending')
        assert await self.js('notice.textContent === ""')


class Fixture:
    def __init__(self):
        self.release = threading.Event()

    def chat(self, _model, messages, **_kwargs):
        text = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        if messages[-1]["role"] == "user":
            if text == "Read note.txt":
                return {"role": "assistant", "content": "", "tool_calls": [{
                    "function": {"name": "read_file", "arguments": {"path": "note.txt"}},
                }]}
            if text == "Ask me":
                return {"role": "assistant", "content": "", "tool_calls": [{
                    "function": {"name": "request_user_input", "arguments": {
                        "question": "Choose a path", "options": [{"label": "A"}, {"label": "B"}],
                    }},
                }]}
            if text == "Wait":
                self.release.wait(20)
        return {"role": "assistant", "content": "Ready."}

    def close(self):
        pass


async def verify_races(tab):
    # Deterministic transport races in the real page: acquisition may retry,
    # an uncertain mutation may not, and auth/session changes stop the action.
    await tab.js("""(async () => {
      const original = jsonRequest, savedLatest = latest, savedEpoch = authEpoch;
      const state = { ...latest, has_control: false, control_epoch: 10 };
      let claims = 0, effects = 0;
      const assert = (ok) => { if (!ok) throw new Error("Control race assertion failed"); };
      try {
        jsonRequest = async (path) => {
          if (path === "/api/v1/session") return state;
          if (path === "/api/v1/control/claim") {
            if (++claims === 1) throw Object.assign(new Error("Competing claim"), { status: 409 });
            return { control_epoch: 11 };
          }
          effects++;
          return { accepted: true };
        };
        assert((await controlledRequest("/fixture", {})).accepted);
        assert(claims === 2 && effects === 1);
        jsonRequest = async (path) => {
          if (path === "/api/v1/session") return { ...state, has_control: true };
          effects++;
          throw new Error("Lost acknowledgement");
        };
        try { await controlledRequest("/fixture", {}); } catch { /* Expected. */ }
        assert(effects === 2);
        for (const changed of ["session", "auth"]) {
          jsonRequest = async (path) => {
            if (path === "/api/v1/session") return state;
            if (path === "/api/v1/control/claim") {
              if (changed === "session") latest = { ...savedLatest, session_id: "other" };
              else authEpoch++;
              return { control_epoch: 12 };
            }
            effects++;
          };
          try { await controlledRequest("/fixture", {}); } catch { /* Expected. */ }
          assert(effects === 2);
          latest = savedLatest;
          authEpoch = savedEpoch;
        }
      } finally { jsonRequest = original; latest = savedLatest; authEpoch = savedEpoch; }
    })()""")


async def verify_composer_controls(tab):
    """Real active controls stay in the composer and leave the transcript readable."""
    draft = await tab.js("prompt.value")
    await tab.js('prompt.value="Guide this turn";resizePrompt()')
    for theme in ("light", "dark"):
        await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
        for width, height in ((320, 844), (390, 844), (768, 844), (1440, 900), (390, 420)):
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height, "deviceScaleFactor": 1,
                "mobile": width < 600,
            })
            await tab.js("new Promise(resolve=>requestAnimationFrame("
                         "()=>requestAnimationFrame(resolve)))")
            state = await tab.js("""(()=>{
              const cancel=byId('cancel'),steer=byId('steer'),latest=byId('scroll-to-latest');
              const send=byId('send');
              const nodes=[...messages.childNodes],scroll=chatScroller.scrollTop;
              const hidden=latest.hidden;
              try {
                const article=ChatMarkdown.create('assistant',
                  'A readable message.\\n\\n'.repeat(80)+'Last visible line.','composer-fixture');
                messages.replaceChildren(article);chatScroller.scrollTop=0;latest.hidden=false;
                const rects=[latest,steer,cancel,send].map(button=>button.getBoundingClientRect());
                const hits=[latest,steer,cancel,send].every((button,i)=>button.contains(
                  document.elementFromPoint(rects[i].left+22,rects[i].top+22)));
                const composer=byId('composer').getBoundingClientRect();
                const [jump,direction,stop,queue]=rects;
                chatScroller.scrollTop=chatScroller.scrollHeight;
                const last=article.querySelector('.message-body').getBoundingClientRect();
                return {inComposer:byId('composer').contains(cancel) &&
                    byId('composer').contains(steer) &&
                    getComputedStyle(cancel.parentElement).position==='static',
                  fits:document.documentElement.scrollWidth<=innerWidth && rects.every(r=>
                    r.width>=44 && r.height>=44 && r.left>=0 && r.right<=innerWidth &&
                    r.top>=0 && r.bottom<=composer.bottom),
                  separate:jump.bottom<=composer.top && queue.right<=direction.left &&
                    direction.right<=stop.left,
                  hits,readableEnd:last.bottom<=composer.top,
                  names:cancel.getAttribute('aria-label')==='Cancel turn' &&
                    steer.getAttribute('aria-label')==='Steer'};
              } finally {
                latest.hidden=hidden;
                messages.replaceChildren(...nodes);chatScroller.scrollTop=scroll;
              }
            })()""")
            assert all(state.values()), (theme, width, height, state)
    await tab.command("Emulation.clearDeviceMetricsOverride")
    await tab.js("prompt.value=" + json.dumps(draft) + ";resizePrompt()")
    await tab.js("applyAppearance(appearance,true);snapshot()")


async def verify(host, controller, fixture, profile, chrome):
    process = subprocess.Popen([
        chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            await asyncio.sleep(0.05)
        port = int(active.read_text().splitlines()[0])
        async with AsyncExitStack() as stack:
            async def open_tab():
                with urlopen(Request(
                    f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT"
                )) as response:
                    target = json.load(response)
                ws = await stack.enter_async_context(websockets.connect(
                    target["webSocketDebuggerUrl"], max_size=4_000_000,
                ))
                tab = Tab(ws)
                await tab.command("Runtime.enable")
                await tab.command("Page.enable")
                await tab.command("Page.navigate", {"url": host.origin})
                return tab

            first = await open_tab()
            await first.wait('typeof byId !== "undefined" && !byId("local-access").hidden')
            await first.js('byId("login-username").value="admin";'
                           'byId("login-password").value=' + json.dumps(
                host.accounts.initial_password()
            ) + ';byId("account-login").requestSubmit()')
            await first.wait('latest?.session_id')
            await first.send("Hello")
            await first.wait('latest?.messages.some(item => item.role === "assistant")')
            await first.idle()
            second = await open_tab()
            await second.wait('typeof latest !== "undefined" && latest?.session_id')
            assert await first.js("clientId") != await second.js("clientId")
            assert not await second.js("latest.has_control")
            assert await second.js('byId("cancel").hidden && byId("steer").hidden && '
                                   'getComputedStyle(document.querySelector(".turn-actions"))'
                                   '.display === "none"')
            current = host.application.control()
            await second.command("Page.bringToFront")
            await second.js("snapshot();refreshSessions()")
            await asyncio.sleep(0.3)
            assert host.application.control() == current, "Watching must not claim control"
            assert await second.js('!document.querySelector("#claim")')

            # Idle controls work directly from either tab.
            await second.click("#plan-toggle")
            await second.wait("latest.plan_mode")
            await first.js("snapshot()")
            await first.click("#plan-toggle")
            await first.wait('!latest.plan_mode && latest.has_control')

            await first.send("Read note.txt")
            await first.wait('latest.approvals.length === 1')
            await second.js("snapshot()")
            assert await second.js('latest.approvals.length === 1 && !latest.has_control')
            await second.click("#approvals button")
            await second.idle()
            assert await second.js("latest.has_control")

            await first.js("snapshot()")
            await first.send("Ask me")
            await first.wait('latest.questions.length === 1')
            await second.js("snapshot()")
            await second.js('byId("questions").querySelector("input").value="B"')
            # A separate takeover must not destroy an unanswered local draft.
            host.application.take_control(host.application.controller_id,
                                          expected_epoch=host.application.control()[1])
            await second.js("snapshot()")
            assert await second.js('byId("questions").querySelector("input").value === "B"')
            await second.js('byId("questions").querySelector("form").requestSubmit()')
            await second.idle()

            # Both clients keep Cancel/Steer available during remote work.
            await first.js("snapshot()")
            await first.send("Wait")
            await first.wait('latest.active_turn_id && !pending')
            await second.js("snapshot()")
            assert await second.js('!byId("cancel").hidden && !byId("steer").hidden')
            await verify_composer_controls(second)
            await second.click("#cancel")
            await second.wait('!pending && latest.has_control')
            assert host.application._active.cancelled.is_set()
            fixture.release.set()
            await second.idle()
            fixture.release.clear()
            await first.js("snapshot()")
            await first.send("Wait")
            await first.wait('latest.active_turn_id && !pending')
            await second.js('snapshot()')
            await second.js('prompt.value="Continue here"')
            await second.click("#steer")
            await second.wait('latest.queue.length === 1')
            fixture.release.set()
            await second.idle()

            # The hosted terminal also reacquires on explicit review/cancel.
            await second.send("Read note.txt")
            await second.wait('latest.approvals.length === 1')
            approval = await second.js('latest.approvals[0].id')
            assert controller.runtime_snapshot()["approvals"]
            assert controller.decide_hosted_approval(approval, "allow_once")
            await second.idle()
            fixture.release.clear()
            await second.send("Wait")
            await second.wait('latest.active_turn_id && !pending')
            assert not controller.cancel_hosted_turn("old-turn")
            assert host.application.control()[0] == await second.js("clientId")
            assert controller.cancel_hosted_turn(await second.js("latest.active_turn_id"))
            fixture.release.set()
            await second.idle()

            # A reviewed Library operation also acquires without visiting Chat.
            item = host.library.artifacts.import_bytes(b"Saved", "document", "saved.txt")
            await first.js("snapshot()")
            await first.click("#plan-toggle")
            await first.wait("latest.plan_mode")
            await second.js("snapshot()")
            assert not await second.js("latest.has_control")
            await second.js("prepareChange(" + json.dumps({
                "operation": "tags", "target": item["id"], "revision": item["revision"],
                "value": "reviewed",
            }) + ")")
            await second.click("#domain-review-confirm")
            await second.wait('!byId("domain-review").open')
            for _ in range(100):
                if host.library.artifacts.get(item["id"])["tags"] == ["reviewed"]:
                    break
                await asyncio.sleep(0.05)
            assert host.library.artifacts.get(item["id"])["tags"] == ["reviewed"]

            # Idle navigation also acquires automatically.
            await first.js("snapshot()")
            await first.click("#plan-toggle")
            await first.wait("!latest.plan_mode")
            await second.js("snapshot()")
            await second.click("#new-session")
            previous = await first.js("latest.session_id")
            await second.wait(f'latest.session_id !== {json.dumps(previous)}')
            await verify_races(second)
            assert not first.errors and not second.errors, (first.errors, second.errors)
            print("PASS: two tabs share reviews, questions, Cancel/Steer, Library and navigation;")
            print("watching preserves control; terminal review/cancel acquire automatically;")
            print("competing claims, lost acknowledgements and auth/session races stay bounded.")
            print("PASS: composer turn controls in 10 light/dark responsive layouts.")
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

    with tempfile.TemporaryDirectory(prefix="klaude-control-smoke-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR = root / "config"
        config_module.DATA_DIR = root / "data"
        cfg = Config(models={"coder": "fixture"})
        # Shared Agent and real permission broker, without contacting Ollama.
        from klaude_tools.toolkit import Workspace, build_tools

        app = _app(root)
        app.agent.workdir = root
        app.agent.workspace = Workspace(root)
        app.agent.tools = {tool.name: tool for tool in build_tools(app.agent.workspace)
                           if tool.name == "read_file"}
        app.agent.tool_config = cfg
        app.agent.gate.policies["read_file"] = "ask"
        app.agent.gate.policies["request_user_input"] = "allow"
        app.allow_approvals = True
        app.allow_user_input_tool = True
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        (root / "note.txt").write_text("A public fixture.\n")
        fixture = Fixture()
        app.agent.runtime = fixture
        app.agent.ollama = fixture
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts, library=LibraryManagement(cfg, root))
        host.local_models = lambda: []
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        controller = WebHostController(cfg.config_dir, cfg.data_dir)
        control = ManagedControl(controller.directory, host, root)
        try:
            asyncio.run(asyncio.wait_for(
                verify(host, controller, fixture, root / "chrome", chrome), 90,
            ))
        finally:
            fixture.release.set()
            host.stop()
            thread.join(3)
            control.close()


if __name__ == "__main__":
    main()

"""Chat layout and passive details checks in isolated authenticated Chromium.

Session reads use explicit presentation fixtures; no provider or user data.
Real turn/model behavior is covered by the composer and models smoke scripts.
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
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools.toolkit import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402

OUT = Path("/tmp/klaude-chat-layout-validation")


async def verify(host, root):
    OUT.mkdir(exist_ok=True)
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
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
    report = {"fixture_content": True, "layouts": []}
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(0.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=8_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")

            async def viewport(width, height):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": width <= 768,
                    },
                )
                await asyncio.sleep(0.12)

            async def shot(name):
                result = await tab.command("Page.captureScreenshot", {"format": "png"})
                (OUT / f"{name}.png").write_bytes(base64.b64decode(result["data"]))

            await viewport(1440, 960)
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js(
                'byId("login-username").value="admin";byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await tab.wait(
                'latest?.session_id && document.documentElement.dataset.startup==="ready"'
            )
            await tab.js("""stream?.close();stream=null;clearInterval(pollTimer);
              window.chatLayoutBase=structuredClone(latest);
              window.chatLayoutState=structuredClone(latest);
              window.chatLayoutFetch=fetch;window.chatLayoutWrites=[];
              window.fetch=(input,options)=>{
                if(options?.method && options.method!=='GET') chatLayoutWrites.push(String(input));
                if(String(input)==='/api/v1/session') return Promise.resolve(new Response(
                  JSON.stringify(chatLayoutState),{headers:{'Content-Type':'application/json'}}));
                return chatLayoutFetch(input,options);
              };document.fonts.ready""")
            assert await tab.js(
                'byId("model-control").closest(".chat-toolbar") && '
                'byId("composer").contains(byId("attach-file")) && '
                'byId("composer").contains(byId("cancel")) && '
                '!byId("composer").contains(byId("model-control"))'
            )

            async def state(kind):
                await tab.js("""chatLayoutState={...structuredClone(chatLayoutBase),
                  model:'Klaude Example Coding Model With A Long Name',
                  messages:[],partial:null,active_turn_id:null,queue:[],activity:null,
                  effort_levels:['off','low','medium','high'],effort:'medium'};
                  prompt.value='';resizePrompt();""")
                if kind != "empty":
                    await tab.js("""chatLayoutState.messages=[
                      {id:'layout-user',role:'user',content:'Help me simplify this chat layout.'},
                      {id:'layout-assistant',role:'assistant',content:
                        'Keep the conversation easy to read.'+String.fromCharCode(10,10)
                        +'Attachments, Thinking and Plan stay within reach.'}];""")
                if kind.startswith("active"):
                    await tab.js(
                        "chatLayoutState.active_turn_id='layout-turn';chatLayoutState.state='thinking'"
                    )
                if kind == "active-draft":
                    await tab.js("prompt.value='Try a more compact layout';resizePrompt()")
                await tab.js("snapshot()")

            for theme in ("light", "dark"):
                await tab.js(
                    "applyAppearance({...appearance,theme:" + json.dumps(theme) + "},true)"
                )
                for width, height in (
                    (1440, 960),
                    (1024, 768),
                    (768, 900),
                    (390, 844),
                    (320, 640),
                    (844, 390),
                    (390, 430),
                ):
                    await viewport(width, height)
                    header = await tab.js("""(()=>{
                      const height=selector=>document.querySelector(selector)
                        .getBoundingClientRect().height;
                      return {bar:height('.topbar'),modelRow:height('.chat-toolbar'),
                        title:height('#mobile-chat-title')};})()""")
                    assert header["bar"] == (56 if width <= 850 else 64), header
                    assert (header["modelRow"] == 0) == (width <= 850), header
                    assert (header["title"] > 0) == (width <= 850), header
                    for kind in ("empty", "conversation", "active", "active-draft"):
                        await state(kind)
                        await asyncio.sleep(0.08)
                        geometry = await tab.js("""(()=>{
                          const box=id=>byId(id).getBoundingClientRect();
                          const composer=box('composer'),main=box('chat-view'),prompt=box('prompt');
                          const visible=id=>{const el=byId(id),r=box(id);
                            return !el.hidden && r.width>0 && r.height>0;};
                          const actions=['attach-file','mode-toggle','plan-toggle',
                            'send','steer','cancel']
                            .filter(visible).map(id=>({id,r:box(id)}));
                          return {fits:document.documentElement.scrollWidth<=innerWidth,
                            composerFits:byId('composer').scrollWidth<=byId('composer').clientWidth,
                            bounds:composer.left>=main.left && composer.right<=main.right+.5 &&
                              composer.bottom<=main.bottom+.5 && composer.top>=0,
                            readingWidth:composer.width<=800.5,
                            fullInput:Math.abs(prompt.width-(composer.width-34))<18,
                            actionsFit:actions.every(({r})=>r.left>=composer.left &&
                              r.right<=composer.right+.5 && r.top>=composer.top &&
                              r.bottom<=composer.bottom),
                            noOverlap:actions.every((a,i)=>actions.slice(i+1).every(b=>
                              a.r.right<=b.r.left+.5 || b.r.right<=a.r.left+.5 ||
                              a.r.bottom<=b.r.top+.5 || b.r.bottom<=a.r.top+.5)),
                            stop:visible('cancel'),send:visible('send'),steer:visible('steer'),
                            actions:actions.map(({id,r})=>({id,rect:r.toJSON()}))};
                        })()""")
                        for key in (
                            "fits",
                            "composerFits",
                            "bounds",
                            "readingWidth",
                            "fullInput",
                            "actionsFit",
                            "noOverlap",
                        ):
                            assert geometry[key], {
                                "theme": theme,
                                "width": width,
                                "height": height,
                                "state": kind,
                                **geometry,
                            }
                        if width <= 850:
                            rest = await tab.js('byId("composer").getBoundingClientRect().height')
                            assert 104 <= rest <= 120, (width, height, kind, rest)
                        assert geometry["stop"] == kind.startswith("active"), geometry
                        assert geometry["send"] == (kind != "active"), geometry
                        assert geometry["steer"] == (kind == "active-draft"), geometry
                        report["layouts"].append(
                            {
                                "theme": theme,
                                "width": width,
                                "height": height,
                                "state": kind,
                                **geometry,
                            }
                        )
                        if width in (1440, 390, 320) and height != 430:
                            await shot(f"{kind}-{theme}-{width}")

                    # Native top-layer details, passive reads, resize and Escape focus return.
                    await state("conversation")
                    if width <= 850:
                        await tab.click("#mobile-chat-more")
                        await tab.wait('byId("mobile-chat-menu").matches(":popover-open")')
                        await tab.click('[data-mobile-chat-action="details"]')
                    else:
                        await tab.click("#chat-info-toggle")
                    await tab.wait(
                        'byId("chat-info-panel").matches(":popover-open") && '
                        'byId("chat-info-toggle").getAttribute("aria-expanded")==="true"'
                    )
                    await asyncio.sleep(0.08)
                    assert await tab.js("""(()=>{
                      const r=byId('chat-info-panel').getBoundingClientRect();
                      return r.left>=15 && r.right<=innerWidth-15 && r.top>=15 &&
                        r.bottom<=innerHeight-15 && byId('state').textContent===latest.state &&
                        byId('session').title===latest.session_id;})()""")
                    await tab.command(
                        "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape"}
                    )
                    await tab.wait('!byId("chat-info-panel").matches(":popover-open")')
                    focus = "mobile-chat-more" if width <= 850 else "chat-info-toggle"
                    assert await tab.js(f'document.activeElement===byId("{focus}")')

            for width in (320, 390):
                await viewport(width, 844)
                await state("conversation")
                await tab.js('prompt.focus()')
                await viewport(width, 500)
                await tab.wait('document.documentElement.dataset.chatKeyboard==="true"')
                assert await tab.js('''
                  getComputedStyle(document.querySelector('.rail')).display==='none' &&
                  byId('composer').getBoundingClientRect().bottom<=visualViewport.height+.5 &&
                  document.documentElement.scrollWidth<=innerWidth''')
                await shot(f"keyboard-dark-{width}")
                await viewport(width, 844)
                await tab.wait('document.documentElement.dataset.chatKeyboard==="false"')
                assert await tab.js('getComputedStyle(document.querySelector(".rail"))'
                                    '.display!=="none"')
                # A hardware keyboard or focus alone must not remove navigation.
                await tab.js('prompt.focus()')
                assert await tab.js('document.documentElement.dataset.chatKeyboard==="false"')
                await tab.js('prompt.value=Array(12).fill("A line")'
                             '.join(String.fromCharCode(10));resizePrompt()')
                assert await tab.js('byId("composer").getBoundingClientRect().height>120 && '
                                    'byId("prompt").getBoundingClientRect().height<=160.5')
                await tab.js('prompt.value="";resizePrompt();prompt.blur()')
            # Overlay keyboards shrink the visual viewport without changing innerHeight.
            await tab.js('''prompt.focus();window.savedChatViewport=window.visualViewport;
              Object.defineProperty(window,'visualViewport',{configurable:true,value:{
                width:innerWidth,height:500,offsetLeft:0,offsetTop:0,scale:1}});
              window.dispatchEvent(new Event('resize'))''')
            await tab.wait('document.documentElement.dataset.chatKeyboard==="true"')
            assert await tab.js('byId("composer").getBoundingClientRect().bottom<=500.5')
            await tab.js('''Object.defineProperty(window,'visualViewport',{
              configurable:true,value:savedChatViewport});
              window.dispatchEvent(new Event('resize'))''')
            await tab.wait('document.documentElement.dataset.chatKeyboard==="false"')
            await tab.js('prompt.blur()')
            await tab.click("#mobile-chat-more")
            await tab.wait('byId("mobile-chat-menu").matches(":popover-open")')
            await tab.click('[data-mobile-chat-action="search"]')
            await tab.wait('byId("command-palette").open')
            await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape"})
            await tab.wait('!byId("command-palette").open && '
                           'document.activeElement===byId("mobile-chat-more")')

            await viewport(1440, 960)
            await state("conversation")
            await tab.js('''chatLayoutState.chat_model_blocked=true;
              prompt.value='Keep this draft';resizePrompt();snapshot()''')
            assert await tab.js('''!byId('chat-availability').hidden && byId('send').disabled &&
              !byId('model-picker').disabled &&
              byId('chat-availability-action').textContent==='Check Downloads' ''')
            await tab.js('sendMessage("send")')
            assert await tab.js('prompt.value==="Keep this draft" && chatLayoutWrites.length===0')
            await tab.js('''chatLayoutState.chat_model_blocked=false;
              chatLayoutState.state='interrupted';snapshot()''')
            assert await tab.js('byId("send").disabled && '
                                'byId("chat-availability-action").textContent==="New chat"')
            await state("conversation")
            assert await tab.js('byId("chat-availability").hidden && !byId("send").disabled')
            await tab.js("setContextPanel(true)")
            await tab.click("#cp-tab-agent")
            await state("conversation")
            assert await tab.js('byId("composer").scrollWidth<=byId("composer").clientWidth')
            await shot("context-panel-dark-1440")
            await tab.js("setContextPanel(false)")
            await tab.click("#chat-info-toggle")
            await tab.wait('byId("chat-info-panel").matches(":popover-open")')
            await tab.click("#model-picker")
            await tab.wait(
                'byId("model-menu").open && !byId("chat-info-panel").matches(":popover-open")'
            )
            await tab.click("#chat-info-toggle")
            await tab.wait(
                'byId("chat-info-panel").matches(":popover-open") && !byId("model-menu").open'
            )
            await tab.js('document.dispatchEvent(new Event("klaude-chat-session-changed"))')
            await tab.wait('!byId("chat-info-panel").matches(":popover-open")')
            await tab.click("#chat-info-toggle")
            await tab.wait('byId("chat-info-panel").matches(":popover-open")')
            await tab.click("#nav-workspace")
            await tab.wait('!byId("chat-info-panel").matches(":popover-open")')
            await tab.click("#nav-chat")
            await tab.click("#chat-info-toggle")
            await tab.wait('byId("chat-info-panel").matches(":popover-open")')
            # No claim or mutation was needed for any presentation or details action.
            assert await tab.js("chatLayoutWrites.length===0"), await tab.js("chatLayoutWrites")
            await viewport(390, 844)
            await tab.click("#mobile-chat-more")
            await tab.wait('byId("mobile-chat-menu").matches(":popover-open")')
            await tab.click('[data-mobile-chat-action="account"]')
            await tab.wait('currentView==="settings" && settingsSection==="account"')
            assert await tab.js('byId("account-sign-out").getBoundingClientRect().height>=44 && '
                                'byId("logout").getBoundingClientRect().height===0')
            await tab.click("#account-sign-out")
            await tab.wait('!authenticated && !byId("chat-info-panel").matches(":popover-open")')
            assert await tab.js('!byId("mobile-model-sheet").open && '
                                '!byId("mobile-model-list").textContent && '
                                'byId("mobile-chat-subtitle").textContent==="Choose a model"')
            assert not tab.errors, tab.errors
            report.update(
                {
                    "details_keyboard_focus_viewport_and_cleanup": True,
                    "passive_details": True,
                    "mobile_single_header_compact_composer_and_keyboard": True,
                    "blocked_chat_keeps_draft_and_recovery_action": True,
                    "browser_exceptions": 0,
                }
            )
            (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(
                json.dumps({**report, "layouts": len(report["layouts"]), "screenshots": str(OUT)})
            )
    finally:
        process.terminate()
        process.wait(timeout=10)


def main():
    with tempfile.TemporaryDirectory(prefix="klaude-chat-layout-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts, staging_dir=root / "staging")
        host.local_models = lambda: []
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root), 150))
        finally:
            host.stop()
            serving.join(3)


if __name__ == "__main__":
    main()

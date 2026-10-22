"""Isolated Chrome checks for Send feedback and native composer keyboard input.

Uses the real authenticated turn service and a held fixture runtime. The host
deliberately rejects the formerly new indicator asset paths, as a legacy host
does. No user sessions or external models are accessed.
"""

from __future__ import annotations

import asyncio
import base64
import io
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
from klaude_tools.toolkit import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from PIL import Image
from webui_activity_smoke import Runtime
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402

OUT = Path("/tmp/klaude-composer-preview")


async def verify(host, root, chrome, runtime):
    OUT.mkdir(exist_ok=True)
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
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Network.enable")
            await tab.command("Network.setBlockedURLs", {"urls": [
                "*/loading-indicator.js", "*/vendor/material-loading-shapes.js",
            ]})
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False,
            })
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js('byId("login-password").value=' + json.dumps(
                host.accounts.initial_password()
            ) + ';byId("account-login").requestSubmit()')
            await tab.wait('latest?.session_id && pollTimer!==null && MaterialLoading')
            assert await tab.js('enterSends()'), "Desktop input unavailable"
            assert await tab.js('Boolean(document.querySelector("script[src*=loading-indicator]"))'
                                ' && '
                                '!document.querySelector("script[src*=material-loading-shapes]")')

            async def enter(shift=False):
                for kind in ("keyDown", "keyUp"):
                    await tab.command("Input.dispatchKeyEvent", {
                        "type": kind, "key": "Enter", "code": "Enter",
                        "windowsVirtualKeyCode": 13, "text": "\r", "modifiers": 8 if shift else 0,
                    })

            async def capture(name):
                result = await tab.command("Page.captureScreenshot", {"format": "png"})
                (OUT / name).write_bytes(base64.b64decode(result["data"]))

            await tab.js('prompt.value="First line";prompt.focus();resizePrompt()')
            await enter(shift=True)
            await tab.command("Input.insertText", {"text": "Second line"})
            assert await tab.js('prompt.value==="First line\\nSecond line" && !pending')
            # IME confirmation and repeat keys never accidentally submit.
            assert await tab.js('''(() => {
              const event=new KeyboardEvent('keydown',{
                key:'Enter',isComposing:true,bubbles:true,cancelable:true});
              return prompt.dispatchEvent(event) && !pending;
            })()''')
            assert await tab.js('''(() => {
              prompt.dispatchEvent(new KeyboardEvent('keydown',{
                key:'Enter',repeat:true,bubbles:true,cancelable:true}));return !pending;
            })()''')
            await tab.js('''window.composerFetch=fetch;window.submitCount=0;
              window.fetch=(input,options)=>String(input)==='/api/v1/turns' &&
                options?.method==='POST' ? new Promise(resolve=>{
                  submitCount++;window.releaseComposerSend=()=>resolve(composerFetch(input,options));
                }) : composerFetch(input,options);
              prompt.value='Wait';prompt.focus();
            ''')
            await enter()
            await tab.wait('pending && submitCount===1 && !byId("chat-send-status").hidden')
            assert await tab.js('byId("chat-send-status").textContent==="Sending…" && '
                                'byId("chat-send-status").querySelector(".material-loading") && '
                                'byId("send").disabled && '
                                'messages.contains(byId("chat-send-status")) && '
                                '!byId("composer").contains(byId("chat-response-status"))')
            # Check real Send, not only a synthetic indicator fixture.
            await tab.js('window.sendingShape=byId("chat-send-status").querySelector("svg");'
                         'window.sendCurve=sendingShape.querySelector("path").getAttribute("d");'
                         'window.sendRotation=sendingShape.querySelector("g").getAttribute("transform")')
            await tab.wait('sendingShape.querySelector("path").getAttribute("d")!==sendCurve && '
                           'sendingShape.querySelector("g").getAttribute("transform")!==sendRotation')
            for theme in ("light", "dark"):
                await tab.js('document.documentElement.dataset.theme=' + json.dumps(theme))
                for width in (390, 1280):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": 820, "deviceScaleFactor": 1, "mobile": False,
                    })
                    await asyncio.sleep(.35)
                    state = await tab.js('''(() => {
                      const el=byId('chat-send-status'),r=el.getBoundingClientRect();
                      return {visible:r.width>0&&r.height>0&&r.top>=0&&r.bottom<=innerHeight,
                        fits:document.documentElement.scrollWidth<=innerWidth,
                        output:messages.contains(el)&&r.bottom<=byId('composer').getBoundingClientRect().top};
                    })()''')
                    assert state["visible"] and state["fits"] and state["output"], state
                    await capture(f"sending-{theme}-{width}.png")
            await enter()
            assert await tab.js('submitCount===1')
            await tab.js('releaseComposerSend();true')
            await tab.wait('latest?.active_turn_id && !pending')
            assert runtime.entered.is_set()
            assert await tab.js('byId("chat-send-status").hidden && '
                                '!!byId("agent-activity").querySelector(".material-loading")')
            await tab.js('window.responseShape=byId("agent-activity").querySelector("svg");'
                         'window.responseCurve=responseShape.querySelector("path").getAttribute("d");'
                         'window.responseRotation=responseShape.querySelector("g").getAttribute("transform")')
            await tab.wait('responseShape.querySelector("path").getAttribute("d")!==responseCurve '
                           '&& '
                           'responseShape.querySelector("g").getAttribute("transform")!==responseRotation')
            assert await tab.js('messages.contains(responseShape) && '
                                'byId("chat-response-status").previousElementSibling'
                                '.classList.contains("user") && '
                                'messages.querySelectorAll(".material-loading").length===1')
            for width in (390, 1280):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 820, "deviceScaleFactor": 1, "mobile": False,
                })
                await asyncio.sleep(.35)
                await capture(f"response-dark-{width}.png")
                if width == 390:
                    frames = []
                    for _ in range(16):
                        frame = await tab.command("Page.captureScreenshot", {"format": "png"})
                        frames.append(Image.open(io.BytesIO(base64.b64decode(frame["data"]))))
                        await asyncio.sleep(.08)
                    frames[0].save(OUT / "response-motion-mobile.gif", save_all=True,
                                   append_images=frames[1:], duration=100, loop=0)
            await tab.js('snapshot()')
            assert await tab.js('responseShape===byId("agent-activity").querySelector("svg") && '
                                'messages.contains(responseShape)')
            # The already-running legacy host has no typed activity payload.
            # Check the compatibility path with that field absent on real reads.
            # Drain the Send handler's final snapshot before swapping response data.
            await asyncio.sleep(.2)
            await tab.js('''stream?.close();stream=null;clearInterval(pollTimer);
            window.composerReads=[];window.fetch=async(input,options)=>{
              const r=await composerFetch(input,options);
              if(String(input).startsWith('/api/v1/session')){
                const data=await r.json();delete data.activity;
                composerReads.push(data);
                return new Response(JSON.stringify(data),{status:r.status,headers:r.headers});
              }return r;
            };true''')
            await tab.js('snapshot()')
            await tab.js('snapshot()')
            await tab.wait('!latest.activity && !byId("chat-send-status").hidden')
            assert await tab.js('byId("chat-send-status").textContent==="Generating response…" && '
                                '!!byId("chat-send-status").querySelector(".material-loading")')
            runtime.release.set()
            await tab.idle()
            assert await tab.js('byId("chat-send-status").hidden')
            await tab.js('window.fetch=composerFetch')
            # A rejected request keeps the draft and releases the immediate status.
            await tab.js('''window.fetch=(input,options)=>String(input)==='/api/v1/turns' ?
              Promise.resolve(new Response(JSON.stringify({error:{code:'fixture',
                message:'Fixture send rejected'}}),{status:409,
                headers:{'Content-Type':'application/json'}})) : composerFetch(input,options);
              prompt.value='Keep this draft';prompt.focus();notice.textContent='';
            ''')
            await enter()
            await tab.wait('!pending && notice.textContent.includes("Fixture send rejected")')
            assert await tab.js('prompt.value==="Keep this draft" && '
                                'byId("chat-send-status").hidden && !byId("send").disabled')
            await tab.js('window.fetch=composerFetch;notice.textContent=""')
            # Mobile software keyboards retain multiline Enter; Send still submits.
            await tab.command("Emulation.setTouchEmulationEnabled", {"enabled": True})
            await tab.command("Emulation.setEmulatedMedia", {"features": []})
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True,
            })
            await tab.wait('!enterSends()')
            await tab.js('prompt.value="Mobile";prompt.focus()')
            await enter()
            assert await tab.js('prompt.value==="Mobile\\n" && !pending')
            await tab.click("#send")
            await tab.idle()
            assert await tab.js('latest.messages.some(m=>m.role==="user" && m.content==="Mobile")')
            # Sending state is also removed on sign-out, without consuming a draft
            # from a subsequently opened session when an old response arrives.
            await tab.js('''window.fetch=(input,options)=>String(input)==='/api/v1/turns' ?
              new Promise(resolve=>{window.releaseLateSend=()=>resolve(new Response('{}',{
                headers:{'Content-Type':'application/json'}}));}) : composerFetch(input,options);
              prompt.value='Pending logout';byId('composer').requestSubmit();true;
            ''')
            await tab.wait('!byId("chat-send-status").hidden')
            await tab.click("#logout")
            await tab.wait('!authenticated && byId("chat-send-status").hidden')
            await tab.js('releaseLateSend();true')
            await tab.wait('!pending && !chatSubmission')
            assert not tab.errors, tab.errors
            result = {"desktop_enter_sends": True, "shift_enter_newline": True,
                      "ime_and_repeat_guard": True, "mobile_enter_newline_and_send_button": True,
                      "immediate_indicator_layouts": 4, "duplicate_sends_blocked": True,
                      "response_indicator_in_conversation": True,
                      "real_send_morph_and_rotation": True,
                      "activity_animation_survives_snapshot": True,
                      "legacy_asset_and_activity_compatibility": True,
                      "failed_send_keeps_draft": True, "logout_cleanup": True,
                      "browser_exceptions": 0, "screenshots": str(OUT)}
            (OUT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    ))
    with tempfile.TemporaryDirectory(prefix="klaude-composer-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace = root, Workspace(root)
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        runtime = Runtime()
        app.agent.runtime = app.agent.ollama = runtime
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts, library=LibraryManagement(cfg, root),
                            staging_dir=root / "staging")
        host.local_models = lambda: []
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome, runtime), 100))
        finally:
            runtime.release.set()
            host.stop()
            serving.join(3)


if __name__ == "__main__":
    main()

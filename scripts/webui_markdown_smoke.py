"""Isolated Chrome/CDP regression checks for WebUI Markdown, no live model work.

Run with the workspace development environment and websockets installed. Optional:
KLAUDE_TEST_CHROME=/path/to/chrome KLAUDE_MARKDOWN_SCREENSHOTS=/tmp/screenshots.
"""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_webhost import host as host_module
from klaude_webhost.accounts import AccountStore

CHROME = (
    os.environ.get("KLAUDE_TEST_CHROME")
    or shutil.which("chromium")
    or shutil.which("google-chrome")
)
if not CHROME:
    candidates = list(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    )
    if not candidates:
        raise SystemExit("Set KLAUDE_TEST_CHROME to a headless Chrome executable")
    CHROME = str(candidates[-1])
OUT = Path(os.environ.get("KLAUDE_MARKDOWN_SCREENSHOTS", "/tmp/klaude-markdown-preview"))
OUT.mkdir(exist_ok=True)


async def verify(host, profile, fixture):
    errors = []
    requests = []
    proc = subprocess.Popen(
        [
            CHROME,
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
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            targets = [json.load(r)]
        async with websockets.connect(
            targets[0]["webSocketDebuggerUrl"], max_size=10_000_000
        ) as ws:
            seq = 0

            async def cmd(method, params=None):
                nonlocal seq
                seq += 1
                await ws.send(json.dumps({"id": seq, "method": method, "params": params or {}}))
                while True:
                    data = json.loads(await ws.recv())
                    if data.get("method") == "Network.requestWillBeSent":
                        requests.append(data["params"]["request"]["url"])
                    if data.get("method") == "Runtime.exceptionThrown":
                        errors.append(data["params"])
                    if (
                        data.get("method") == "Log.entryAdded"
                        and data["params"]["entry"]["level"] == "error"
                        and data["params"]["entry"].get("source") != "network"
                    ):
                        errors.append(data["params"])
                    if data.get("id") == seq:
                        assert "error" not in data, data
                        return data.get("result", {})

            async def js(expression):
                result = await cmd(
                    "Runtime.evaluate",
                    {"expression": expression, "returnByValue": True, "awaitPromise": True},
                )
                assert "exceptionDetails" not in result, result
                return result.get("result", {}).get("value")

            async def wait(expression):
                for _ in range(100):
                    if await js(expression):
                        return
                    await asyncio.sleep(0.1)
                print(
                    "DEBUG",
                    await js(
                        "JSON.stringify({latest, notice:notice.textContent, messages:messa"
                        "ges.textContent, cursor,eventCursor,stream:stream?.readyState,"
                        "currentView, historyState:history.state})"
                    ),
                    errors,
                )
                await screenshot("failure.png")
                raise AssertionError(f"Timed out: {expression[:180]}")

            async def click(selector):
                await js(f"document.querySelector({json.dumps(selector)}).click()")

            async def screenshot(name):
                await js("document.fonts.ready.then(()=>true)")
                await asyncio.sleep(0.25)
                result = await cmd("Page.captureScreenshot", {"format": "png"})
                (OUT / name).write_bytes(base64.b64decode(result["data"]))

            async def viewport(width, height):
                await cmd(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                await asyncio.sleep(0.15)
                assert await js("document.documentElement.scrollWidth <= innerWidth"), (
                    f"Horizontal overflow at {width}"
                )

            await cmd("Network.enable")
            await cmd("Runtime.enable")
            await cmd("Log.enable")
            await cmd("Page.enable")
            await viewport(1440, 1000)
            await cmd("Page.navigate", {"url": host.origin})
            await wait(
                'document.querySelector("#account-login") && !document.querySelect'
                'or("#local-access").hidden'
            )
            await js(
                'byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + '; byId("account-login").requestSubmit()'
            )
            await wait(
                'typeof latest !== "undefined" && latest?.session_id && document.f'
                'onts.status === "loaded"'
            )
            await wait('typeof ChatMarkdown !== "undefined"')
            await js('prompt.value="Show a formatted response";byId("composer").requestSubmit()')
            await wait('messages.querySelector("[data-id=partial] .code-block")!==null')
            assert await js(
                'messages.querySelector("[data-id=partial]").getAttribute("aria-busy")==="true"'
            )
            assert await js('messages.querySelector(".message-actions .copy-button").disabled')
            assert await js(
                '[...messages.querySelectorAll(".message-actions button")].every(b=>b.disabled)'
            )
            await js(
                'window.streamArticle=messages.querySelector("[data-id=partial]");'
                'window.firstHeading=streamArticle.querySelector("h2");window.firs'
                'tCode=streamArticle.querySelector(".code-block pre");firstCode.sc'
                "rollLeft=80;window.codeScroll=firstCode.scrollLeft"
            )
            fixture.next_chunk.set()
            await wait('messages.textContent.includes("Another")')
            assert await js(
                'firstHeading===streamArticle.querySelector("h2")&&firstCode===str'
                'eamArticle.querySelector(".code-block pre")&&firstCode.scrollLeft'
                "===codeScroll"
            )
            await js(
                'window.selectedParagraph=streamArticle.querySelector("p");const r'
                "ange=document.createRange();range.selectNodeContents(selectedPara"
                "graph);getSelection().removeAllRanges();getSelection().addRange(r"
                "ange);window.selectedText=getSelection().toString()"
            )
            fixture.finish.set()
            await wait('!latest.active_turn_id&&messages.querySelector("table")!==null')
            assert await js(
                'streamArticle.isConnected&&streamArticle.dataset.id!=="partial"&&'
                'firstHeading===streamArticle.querySelector("h2")&&firstCode.scrol'
                "lLeft===codeScroll&&getSelection().toString()===selectedText"
            )
            await js("snapshot()")
            assert await js(
                'firstHeading===streamArticle.querySelector("h2")&&getSelection().'
                "toString()===selectedText"
            )
            await js("getSelection().removeAllRanges()")
            await js("firstCode.scrollTop=80;window.codeVerticalScroll=firstCode.scrollTop")
            await js(
                'streamArticle.querySelector(".code-block").scrollIntoView({block:"start"});messages.scrollTop+=60'
            )
            geometry = await js(
                '({header:streamArticle.querySelector(".code-toolbar").getBoundingClientRect().top,'
                "container:messages.getBoundingClientRect().top,codeTop:firstCode.scrollTop,"
                "expected:codeVerticalScroll,scroll:messages.scrollTop,"
                'block:streamArticle.querySelector(".code-block").getBoundingClientRect().top})'
            )
            assert abs(geometry["header"] - geometry["container"]) < 2, geometry
            assert geometry["codeTop"] == geometry["expected"], geometry
            assert await js(
                'messages.querySelector("strong").textContent==="clear"&&messages.'
                'querySelector("em").textContent==="emphasis"'
            )
            assert await js(
                'messages.querySelector("s").textContent==="old text"&&messages.qu'
                'erySelector("blockquote")!==null'
            )
            assert await js(
                'messages.querySelectorAll(".task-checkbox").length===2&&messages.'
                'querySelectorAll(".task-checkbox:checked").length===1'
            )
            assert await js(
                'messages.querySelector("ol").start===1&&messages.querySelector("t'
                'h").scope==="col"&&messages.querySelector(".align-right")!==null'
            )
            assert await js('messages.querySelector(".code-block .token.keyword")!==null')
            assert await js(
                '!messages.querySelector(".message-body script,.message-body img,'
                ".message-body svg:not(.icon),iframe,object,embed,style"
                '")&&!window.markdownExecuted'
            )
            assert await js(
                '[...messages.querySelectorAll("a")].every(a=>["https:","http:","m'
                'ailto:"].includes(a.protocol)&&a.rel.includes("noopener")&&a.rel.'
                'includes("noreferrer"))'
            )
            assert await js(
                'byId("messages").getAttribute("role")==="log"&&streamArticle.getA'
                'ttribute("aria-busy")==="false"'
            )
            await js(
                'Object.defineProperty(navigator,"clipboard",{configurable:true,va'
                "lue:{writeText:async text=>{window.copiedText=text}}})"
            )
            await click('[aria-label="Copy response"]')
            await wait("window.copiedText===" + json.dumps(fixture.full))
            await click('[aria-label="Copy code"]')
            await wait("window.copiedText===" + json.dumps(fixture.code))
            assert await js(
                'streamArticle.querySelector(".code-toolbar .copy-button svg")!==null&&'
                'streamArticle.querySelector(".code-toolbar .copy-button").textContent===""'
            )
            await js(
                "navigator.clipboard.writeText=async()=>{throw new Error('Denied')};"
                "document.execCommand=()=>{const data=new DataTransfer();"
                "document.dispatchEvent(new ClipboardEvent('copy',"
                "{clipboardData:data,bubbles:true,cancelable:true}));"
                "window.fallbackText=data.getData('text/plain');return true};"
                "window.pageScroll=scrollY"
            )
            await click('[aria-label="Copy response"]')
            await wait("window.fallbackText===" + json.dumps(fixture.full))
            assert await js('scrollY===pageScroll&&!document.querySelector(".clipboard-source")')
            assert await js(
                'streamArticle.lastElementChild.matches(".message-actions")&&'
                'streamArticle.querySelectorAll(".message-actions button").length===5&&'
                '!streamArticle.querySelector(".message-meta button")'
            )
            await click('[aria-label="Sources"]')
            await wait('document.querySelector(".message-dialog[open]")!==null')
            assert await js(
                'document.querySelectorAll(".message-sources a").length===2&&'
                '[...document.querySelectorAll(".message-sources a")].every('
                'a=>a.hostname==="example.com")'
            )
            await cmd(
                "Input.dispatchKeyEvent",
                {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
            )
            await cmd(
                "Input.dispatchKeyEvent",
                {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
            )
            await wait('!document.querySelector(".message-dialog").open')
            await js(
                'Object.defineProperty(navigator,"share",{configurable:true,'
                "value:async data=>{window.shareData=data;"
                "window.shareHadActivation=navigator.userActivation.isActive}});"
                'Object.defineProperty(navigator,"canShare",{configurable:true,value:()=>true});'
                "history.replaceState(null,'',location.pathname+'?ignored=secret#private-token')"
            )
            await js('window.sharedMessageId=messages.querySelector(".assistant").dataset.id')
            await click('[aria-label="Share message"]')
            await wait('document.querySelector(`.message-dialog [aria-label="Copy link"]`)!==null')
            assert await js('''(() => {
              const targets = [...document.querySelectorAll('[data-share-app]')];
              return targets.map(target => target.dataset.shareApp).join('|') ===
                'whatsapp|telegram|discord|email' && targets.every(target =>
                  target.querySelector('svg[aria-hidden="true"] path') &&
                  target.getAttribute('aria-label').startsWith('Share via '));
            })()''')
            await click('[aria-label="Copy link"]')
            await wait('window.fallbackText.includes("?session=")')
            shared_link = await js("window.fallbackText")
            assert await js(
                'new URL(fallbackText).searchParams.get("session")===latest.session_id&&'
                'new URL(fallbackText).searchParams.get("message")===sharedMessageId&&'
                '!new URL(fallbackText).hash&&!fallbackText.includes("secret")&&'
                "[...new URL(fallbackText).searchParams].length===2"
            )
            assert await js('typeof shareData==="undefined"')
            point = await js('''(() => {
              const r = document.querySelector('[aria-label="Share via"]').getBoundingClientRect();
              return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
            })()''')
            for kind in ("mousePressed", "mouseReleased"):
                await cmd("Input.dispatchMouseEvent", {
                    "type": kind, **point, "button": "left", "clickCount": 1,
                })
            await wait('window.shareData?.title==="Klaude message"')
            assert await js("shareData.url===fallbackText&&!shareData.text&&shareHadActivation")
            assert await js('!document.querySelector(".message-share-targets").hidden')
            await js('Object.defineProperty(navigator,"share",{configurable:true,value:undefined})')
            await click('[aria-label="Share via"]')
            await wait('!document.querySelector(".message-share-targets").hidden')
            assert await js('''(() => {
              const links = document.querySelectorAll(".message-share-targets a");
              const whatsapp = new URL(links[0].href), telegram = new URL(links[1].href);
              const email = new URL(links[2].href);
              return [...links].map(a => a.textContent).join("|") === "WhatsApp|Telegram|Email" &&
                whatsapp.origin === "https://wa.me" &&
                whatsapp.searchParams.get("text") === shareData.url &&
                telegram.origin === "https://t.me" &&
                telegram.searchParams.get("url") === shareData.url &&
                email.protocol === "mailto:" && email.searchParams.get("body") === shareData.url &&
                fallbackText === shareData.url;
            })()''')
            await wait(
                'document.querySelector(".message-dialog [role=status]").textContent'
                '.includes("unavailable in this browser")'
            )
            await js('window.discordCopyAttempts=0;window.savedCopyCommand=document.execCommand;'
                     'document.execCommand=(...args)=>{discordCopyAttempts++;'
                     'return savedCopyCommand(...args)}')
            await click('[aria-label="Share via Discord"]')
            await wait('document.querySelector(".message-dialog [role=status]").textContent'
                       '.includes("Share menu to choose Discord")')
            assert await js('discordCopyAttempts===0&&fallbackText===shareData.url&&'
                            '!document.querySelector("[data-share-app=discord] small")&&'
                            'document.querySelector("[data-share-app=discord]").textContent==="Discord"')
            await js('window.discordShareCalls=0;Object.defineProperty(navigator,"share",'
                     '{configurable:true,value:data=>{discordShareCalls++;'
                     'window.discordShareData=data;'
                     'window.discordShareActivation=navigator.userActivation.isActive;'
                     'return new Promise(resolve=>{window.finishDiscordShare=resolve})}})')
            point = await js('''(() => {
              const r = document.querySelector('[data-share-app=discord]').getBoundingClientRect();
              return {x:r.x+r.width/2, y:r.y+r.height/2};
            })()''')
            for kind in ("mousePressed", "mouseReleased"):
                await cmd("Input.dispatchMouseEvent", {
                    "type": kind, **point, "button": "left", "clickCount": 1,
                })
            await wait('discordShareCalls===1')
            assert await js('discordShareActivation&&discordShareData.url===shareData.url&&'
                            'Object.keys(discordShareData).sort().join("|")==="title|url"&&'
                            'document.querySelector("[data-share-app=discord]").disabled&&'
                            'document.querySelector(`[aria-label="Share via"]`).disabled&&'
                            'discordCopyAttempts===0')
            await js('finishDiscordShare()')
            await wait('!document.querySelector("[data-share-app=discord]").disabled')
            assert await js('document.querySelector(".message-dialog [role=status]").textContent'
                            '===""')
            await js('Object.defineProperty(navigator,"share",{configurable:true,value:async()=>{'
                     'throw new DOMException("Cancelled","AbortError")}})')
            await click('[aria-label="Share via Discord"]')
            await wait('!document.querySelector("[data-share-app=discord]").disabled')
            assert await js('document.querySelector(".message-dialog [role=status]").textContent'
                            '===""&&discordCopyAttempts===0')
            await js('document.execCommand=savedCopyCommand')
            await js('window.shareCalls=0;Object.defineProperty(navigator,"share",'
                     '{configurable:true,value:async()=>{shareCalls++}});'
                     'Object.defineProperty(navigator,"canShare",{configurable:true,value:()=>false})')
            await click('[aria-label="Share via"]')
            await wait('!document.querySelector(".message-share-targets").hidden')
            assert await js('shareCalls===0&&fallbackText===shareData.url')
            await js('Object.defineProperty(navigator,"canShare",'
                     '{configurable:true,value:()=>true});'
                     'Object.defineProperty(navigator,"share",{configurable:true,value:async()=>{'
                     'throw new DOMException("Blocked","NotAllowedError")}})')
            await click('[aria-label="Share via"]')
            await wait('!document.querySelector(".message-share-targets").hidden')
            assert await js('fallbackText===shareData.url')
            await js('Object.defineProperty(navigator,"share",{configurable:true,value:async()=>{'
                     'throw new DOMException("Cancelled","AbortError")}})')
            await click('[aria-label="Share via"]')
            await wait('!document.querySelector(`[aria-label="Share via"]`).disabled')
            assert await js('!document.querySelector(".message-share-targets").hidden&&'
                            'document.querySelector(".message-dialog [role=status]")'
                            '.textContent===""')
            # Older supporting browsers can expose share() without canShare().
            await js('Object.defineProperty(navigator,"canShare",'
                     '{configurable:true,value:undefined});'
                     'Object.defineProperty(navigator,"share",{configurable:true,'
                     'value:async()=>{shareCalls++}})')
            await click('[aria-label="Share via"]')
            await wait('shareCalls===1')
            await js('Object.defineProperty(navigator,"share",{configurable:true,value:undefined})')
            await js(
                'document.querySelector(".message-dialog").close();history.replaceState(null,"",location.pathname)'
            )
            await click('[aria-label="More options"]')
            await wait('document.querySelector("#message-options-menu:popover-open")!==null')
            assert await js(
                'document.querySelector("#message-options-menu time").dateTime.length>0&&'
                '[...document.querySelectorAll("#message-options-menu [role=menuitem]")]'
                '.map(b=>b.textContent).join("|")==="Branch in new chat|Retry"'
            )
            await cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape"})
            await cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape"})
            await wait('!document.querySelector("#message-options-menu").matches(":popover-open")')
            # Speech payloads/lifecycle use browser API doubles, without audible output.
            await js(
                "window.spoken=[];window.cancelCount=0;"
                'Object.defineProperty(window,"SpeechSynthesisUtterance",{configurable:true,'
                "value:class {constructor(text){this.text=text}}});"
                'Object.defineProperty(window,"speechSynthesis",{configurable:true,value:{'
                "getVoices:()=>[],speak:u=>spoken.push(u),cancel:()=>cancelCount++}});true"
            )
            await click('[aria-label="Read aloud"]')
            await wait("window.spoken.length===1")
            assert await js('spoken[0].text.includes("Build report")&&spoken[0].text.length<=1200')
            await js("spoken[0].onend()")
            await wait("spoken.length===2")
            await click('[aria-label="Stop reading"]')
            assert await js(
                'cancelCount===1&&!!document.querySelector(`[aria-label="Read aloud"]`)'
            )
            await click('[aria-label="Read aloud"]')
            await js('document.dispatchEvent(new Event("klaude-auth-reset"))')
            assert await js(
                'cancelCount===2&&!document.querySelector(`[aria-label="Stop reading"]`)'
            )
            await js(
                'window.removedSpeech=addMessage("assistant","Temporary reply.","removed-speech")'
            )
            await click('[data-id="removed-speech"] [aria-label="Read aloud"]')
            await js("removedSpeech.remove()")
            await wait("cancelCount===3")
            # Reload persisted source through the real public snapshot, without another run.
            await cmd("Page.reload")
            await wait(
                'typeof latest!=="undefined"&&latest?.session_id&&messages.querySe'
                'lector("table")!==null'
            )
            assert fixture.calls == 1
            assert await js(
                'ChatMarkdown.source(messages.querySelector(".message.assistant"))==='
                + json.dumps(fixture.full)
            )
            for width, height in [(320, 640), (390, 640), (768, 650), (1440, 900)]:
                await viewport(width, height)
                assert await js(
                    '(()=>{const row=messages.querySelector(".message-actions");'
                    "const top=row.firstElementChild.getBoundingClientRect().top;"
                    "return [...row.children].every(b=>"
                    "Math.abs(b.getBoundingClientRect().top-top)<2)})()"
                ), f"Actions wrapped at {width}"
                assert await js('byId("chat-view").scrollWidth<=byId("chat-view").clientWidth')
                assert await js("messages.scrollWidth<=messages.clientWidth")
                assert await js(
                    'byId("send").getBoundingClientRect().bottom<=byId("main-content")'
                    ".getBoundingClientRect().bottom"
                )
                await js("messages.scrollTop=0")
                await screenshot("markdown-chat-" + str(width) + ".png")
                await js('messages.querySelector(".code-block").scrollIntoView({block:"start"})')
                await js("messages.scrollTop+=60")
                assert await js(
                    'Math.abs(messages.querySelector(".code-toolbar").getBoundingClientRect().top-'
                    "messages.getBoundingClientRect().top)<2"
                ), f"Code toolbar did not follow scrolling at {width}"
                await screenshot("markdown-code-" + str(width) + ".png")
                await js('messages.querySelector(".message-actions").scrollIntoView({block:"end"})')
                await screenshot("markdown-actions-" + str(width) + ".png")
                await click('[aria-label="More options"]')
                await wait('document.querySelector("#message-options-menu:popover-open")!==null')
                assert await js(
                    '(()=>{const r=document.querySelector("#message-options-menu")'
                    '.getBoundingClientRect();'
                    "return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight})()"
                )
                await screenshot("message-menu-" + str(width) + ".png")
                await js('document.querySelector("#message-options-menu").hidePopover()')
                if width == 320:
                    await click('[aria-label="Share message"]')
                    await click('[aria-label="Share via"]')
                    await wait('!document.querySelector(".message-share-targets").hidden')
                    assert await js('''[...document.querySelectorAll("[data-share-app]")]
                      .every(a => { const r = a.getBoundingClientRect();
                        return r.height >= 44 && r.left >= 0 && r.right <= innerWidth; })''')
                    await screenshot("share-link-320.png")
                    await js('document.querySelector(".message-dialog").close()')
            for theme in ["light", "dark"]:
                for palette in await js("paletteNames"):
                    await js(
                        "document.documentElement.dataset.theme="
                        + json.dumps(theme)
                        + ";document.documentElement.dataset.palette="
                        + json.dumps(palette)
                    )
                    await screenshot("markdown-" + theme + "-" + palette + ".png")
            await js(
                "clearInterval(pollTimer);stream?.close();stream=null;messages.replaceChildren()"
            )
            user = "Literal **bold** and <img src=x onerror=alert(1)>"
            await js('addMessage("user",' + json.dumps(user) + ',"literal")')
            assert await js(
                'messages.querySelector(".message-body").textContent==='
                + json.dumps(user)
                + '&&!messages.querySelector("strong,img")'
            )
            await js(
                'window.emptySources=addMessage("assistant",'
                '"A reply without references.","no-sources")'
            )
            await click('[data-id="no-sources"] [aria-label="Sources"]')
            assert await js(
                'document.querySelector(".message-dialog").textContent.includes('
                '"No references were included")'
            )
            await js('document.querySelector(".message-dialog").close();emptySources.remove()')
            # Burst updates coalesce; unchanged blocks and selected text stay stable.
            await js(
                'window.burst=addMessage("assistant",`## Stable\n\nSelected text`,"b'
                'urst",true);window.stable=burst.querySelector("h3");window.target'
                'Text=burst.querySelector("p");const range=document.createRange();'
                "range.selectNodeContents(targetText);getSelection().removeAllRang"
                "es();getSelection().addRange(range);for(let i=0;i<200;i++)ChatMar"
                'kdown.append(burst," x");true'
            )
            await asyncio.sleep(0.2)
            assert await js(
                'getSelection().toString()==="Selected text"&&targetText.textConte'
                'nt==="Selected text"&&burst.querySelector("h3")===stable'
            )
            await js("getSelection().removeAllRanges();true")
            await wait('burst.querySelector("p").textContent.length>200')
            assert await js('burst.querySelector("h3")===stable')
            long = "x" * 128001
            await js('window.longArticle=addMessage("assistant",' + json.dumps(long) + ',"long")')
            assert await js(
                'longArticle.querySelector(".message-body").textContent===' + json.dumps(long)
            )
            await js('messages.scrollTop=0;ChatMarkdown.append(burst," tail");true')
            await asyncio.sleep(0.2)
            assert await js("messages.scrollTop===0")
            # Exercise parser/highlighter absence as a readable plain-text fallback.
            script = await cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": (
                        'Object.defineProperty(window,"markdownit",{get(){return undefined'
                        '},set(){}});Object.defineProperty(window,"speechSynthesis",'
                        "{value:undefined,configurable:true})"
                    )
                },
            )
            await cmd("Page.reload")
            await wait(
                'typeof latest!=="undefined"&&latest?.session_id&&messages.querySe'
                'lector(".message.assistant .message-plain")!==null'
            )
            assert await js(
                'messages.querySelector(".message.assistant .message-body").textContent==='
                + json.dumps(fixture.full)
            )
            assert await js('messages.querySelector(`[aria-label="Read aloud"]`).disabled')
            await cmd(
                "Page.removeScriptToEvaluateOnNewDocument", {"identifier": script["identifier"]}
            )
            await cmd("Page.reload")
            await wait(
                'typeof latest!=="undefined"&&latest?.session_id&&messages.querySe'
                'lector("table")!==null'
            )
            source_id = await js("latest.session_id")
            original_history = host.application.memory.load_session(source_id)
            await click('[aria-label="More options"]')
            await click('#message-options-menu [aria-label="Branch in new chat"]')
            await wait("latest.session_id!==" + json.dumps(source_id))
            branch_id = await js("latest.session_id")
            assert fixture.calls == 1
            assert host.application.memory.load_session(source_id) == original_history
            assert host.application.memory.load_session(branch_id) == original_history
            await wait('!pending&&messages.querySelector(".message-actions")!==null')
            await click('[aria-label="More options"]')
            await wait(
                '!document.querySelector(`#message-options-menu [aria-label="Retry"]`).disabled'
            )
            await click('#message-options-menu [aria-label="Retry"]')
            await wait(
                "latest.session_id!=="
                + json.dumps(branch_id)
                + '&&!latest.active_turn_id&&messages.querySelector("table")!==null'
            )
            assert fixture.calls == 2
            assert host.application.memory.load_session(source_id) == original_history
            assert host.application.memory.load_session(branch_id) == original_history
            retried_history = host.application.memory.load_session(host.application.session_id)
            assert len([m for m in retried_history if m["role"] == "user"]) == 1
            # Fixture resume retains the shared service's exact runtime checks
            # without making an Ollama catalog request for the synthetic model.
            host.application.resume_local = host.application.resume
            # The original linked reply must still open after it falls outside
            # the browser's bounded latest-message window.
            for index in range(120):
                host.application.memory.log_turn(source_id, "user", f"Later message {index}")
            host.application.memory.log_turn(source_id, "assistant", "A later reply to share")
            await cmd("Page.navigate", {"url": shared_link})
            await wait(
                'typeof latest!=="undefined"&&latest?.session_id==='
                + json.dumps(source_id)
                + '&&currentView==="chat"&&pollTimer!==null&&'
                'history.state?.klaudeLinkedSession===latest.session_id'
            )
            await wait('messages.querySelector(".linked-message")!==null')
            assert await js(
                'messages.querySelector(".linked-message").dataset.id==='
                'new URL(location.href).searchParams.get("message")&&'
                'messages.querySelector(".message-history-gap")!==null&&'
                '!latest.messages.some(m=>m.id===messages.querySelector(".linked-message").dataset.id)'
            )
            await js('window.linkTarget=messages.querySelector(".linked-message");snapshot()')
            assert await js('''(() => {
              const target = messages.querySelector(".linked-message");
              const bounds = target.getBoundingClientRect();
              const viewport = messages.getBoundingClientRect();
              return linkTarget === target && document.activeElement === target &&
                bounds.top >= viewport.top - 1 && bounds.top < viewport.bottom;
            })()''')
            # Keep the arrival border for three seconds, then fade only that
            # border; focus and the message itself must remain intact.
            await js('window.highlightStart=performance.now();highlightLinkedMessage(linkTarget)')
            await asyncio.sleep(2)
            assert await js('!linkTarget.classList.contains("linked-message-faded")')
            await wait('linkTarget.classList.contains("linked-message-faded")')
            assert await js('performance.now()-highlightStart>=3000')
            await asyncio.sleep(.5)
            assert await js(
                'getComputedStyle(linkTarget).outlineColor==="rgba(0, 0, 0, 0)"&&'
                'document.activeElement===linkTarget'
            )
            # Reduced motion still keeps the three-second hold, then clears
            # immediately through the existing global transition override.
            await js('document.documentElement.dataset.motion="reduced";'
                     'highlightStart=performance.now();highlightLinkedMessage(linkTarget)')
            await asyncio.sleep(2)
            assert await js('!linkTarget.classList.contains("linked-message-faded")')
            await wait('linkTarget.classList.contains("linked-message-faded")')
            assert await js('performance.now()-highlightStart>=3000')
            await asyncio.sleep(.05)
            assert await js('getComputedStyle(linkTarget).outlineColor==="rgba(0, 0, 0, 0)"')
            await js('document.documentElement.dataset.motion="full"')
            await js('''(() => {
              const replies = messages.querySelectorAll(".assistant");
              replies[replies.length - 1].querySelector('[aria-label="Share message"]').click();
            })()''')
            second_link = await js('document.querySelector(".message-share-link a").href')
            assert second_link != shared_link
            assert await js(
                'new URL(document.querySelector(".message-share-link a").href).'
                'searchParams.get("session")'
                '===latest.session_id'
            )
            await js('document.querySelector(".message-dialog").close()')
            assert fixture.calls == 2
            await js('showView("settings")')
            await cmd("Page.reload")
            await wait(
                'typeof latest!=="undefined"&&latest?.session_id==='
                + json.dumps(source_id)
                + '&&currentView==="settings"&&pollTimer!==null'
            )
            await click("#logout")
            await wait("!authenticated")
            assert await js("messages.children.length===0")
            branch_message = host.application.memory.db.execute(
                "SELECT rowid FROM turns WHERE session_id=? AND role='assistant' "
                "ORDER BY rowid LIMIT 1",
                (branch_id,),
            ).fetchone()[0]
            await cmd("Page.navigate", {"url": host.origin + "/?session=" + branch_id
                                      + "&message=stored:" + str(branch_message)})
            await wait(
                'document.querySelector("#account-login")&&!document.querySelector("#local-access").hidden'
            )
            assert host.application.session_id == source_id
            await js(
                'byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await wait(
                'typeof latest!=="undefined"&&latest?.session_id==='
                + json.dumps(branch_id)
                + '&&currentView==="chat"'
            )
            await wait('messages.querySelector(".linked-message")!==null')
            assert await js('messages.querySelector(".linked-message").dataset.id') == (
                f"stored:{branch_message}"
            )
            assert fixture.calls == 2
            assert host.application.memory.load_session(branch_id) == original_history
            await cmd("Page.navigate", {"url": host.origin + "/?session=" + branch_id
                                      + "&message=stored:9223372036854775807"})
            await wait('typeof latest!=="undefined"&&latest?.session_id&&'
                       'notice.textContent.includes("no longer available")')
            assert await js('latest.session_id') == branch_id
            await cmd("Page.navigate", {"url": host.origin + "/?session=" + branch_id
                                      + "&message=partial"})
            await wait('typeof latest!=="undefined"&&latest?.session_id&&'
                       'notice.textContent.includes("link is invalid")')
            await cmd("Page.navigate", {"url": host.origin + "/?session=invalid"})
            await wait(
                'typeof latest!=="undefined"&&latest?.session_id==='
                + json.dumps(branch_id)
                + '&&notice.textContent.includes("link is invalid")'
            )
            await click("#logout")
            await wait("!authenticated")
            assert not errors, errors
            assert all(url.startswith(host.origin) for url in requests), requests
            print(
                json.dumps(
                    {
                        "checks": [
                            "real shared-worker SSE Markdown",
                            (
                                "stable blocks/code scrolling/selection through completion and sna"
                                "pshots"
                            ),
                            "formatting and task/table semantics",
                            "locally highlighted code",
                            "raw response and code clipboard",
                            "icon-only code Copy follows conversation scrolling within its block",
                            "HTTP clipboard fallback without viewport movement",
                            "five compact response actions beneath old and streamed replies",
                            "cited links and empty Sources dialog",
                            "message-specific Copy link, native Share via URL and HTTP fallback",
                            "social/email icons and Discord native sharing without copying",
                            "older linked messages, exact focus, sign-in and unavailable targets",
                            "private links reopen after sign-in and preserve the page on reload",
                            "timestamp menu, Branch and Retry preserve original history",
                            "chunked speech, stop and sign-out cleanup with API doubles",
                            "persisted history reload",
                            "320/390/768/1440 layouts and sixteen light/dark palette combinations",
                            "literal user content",
                            "coalesced streaming and selection deferral",
                            "large-text fallback",
                            "reader scroll preservation",
                            "missing-parser fallback",
                            "logout cleanup",
                            "no external resource requests",
                        ],
                        "console_errors": errors,
                        "screenshots": str(OUT),
                    },
                    indent=2,
                )
            )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


class MarkdownFixture:
    def __init__(self):
        self.next_chunk = threading.Event()
        self.finish = threading.Event()
        self.calls = 0
        self.code = (
            'def greet(name):\n    return f"Hello, {name}"\n# '
            + ("x" * 5000)
            + "\n"
            + "# Another code line\n" * 40
        )
        self.prefix = (
            (
                "# Build report\n\nA **clear** answer with *emphasis*, ~~old text~~ "
                "and `inline_code`.\n\n```python\n"
            )
            + self.code
            + "```\n\n"
        )
        self.middle = "Another **streaming"
        self.suffix = (
            "** paragraph.\n\n- First item\n- Second item\n  - Nested item\n\n1. Ord"
            "ered item\n2. Another item\n\n- [x] Done\n- [ ] Pending\n\n> A useful q"
            "uotation.\n\n| Model | Context | State |\n| :--- | ---: | :---: |\n| "
            "Local | 32,768 | Ready |\n\n[Docs](https://example.com/docs) and ht"
            "tps://example.com/help\n\n![Remote image](https://image.invalid/pix"
            "el.png)\n\n<script>window.markdownExecuted=true</script>\n\n<svg onlo"
            'ad="window.markdownExecuted=true"></svg>\n\n[Unsafe](javascript:ale'
            "rt(1))\n\n[Data](data:text/html,test)\n"
        )
        self.full = self.prefix + self.middle + self.suffix

    def run(self, _message, scope=None):
        from klaude_core import AgentEvent

        self.calls += 1
        yield AgentEvent("text_delta", {"content": self.prefix})
        assert self.next_chunk.wait(30)
        time.sleep(0.3)
        yield AgentEvent("text_delta", {"content": self.middle})
        assert self.finish.wait(30)
        time.sleep(0.3)
        yield AgentEvent("text_delta", {"content": self.suffix})
        yield AgentEvent("text", {"content": self.full, "metadata": {"streamed": True}})


def main():
    import sys

    from klaude_tools.toolkit import Workspace

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.unit.test_webhost import _app

    with tempfile.TemporaryDirectory(prefix="klaude-markdown-smoke-") as temp:
        root = Path(temp)
        config_module.DATA_DIR = root / "data"
        config_module.CONFIG_DIR = root / "config"
        cfg = Config(models={"coder": "fixture"})
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        app = _app(root)
        app.agent.workdir = root
        app.agent.workspace = Workspace(root)
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        fixture = MarkdownFixture()
        app.agent.run = fixture.run
        host = host_module.LocalWebHost(app, accounts=accounts)
        host.local_models = lambda: []
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root / "chrome", fixture), 120))
        finally:
            fixture.next_chunk.set()
            fixture.finish.set()
            host.stop()
            thread.join(3)


if __name__ == "__main__":
    main()

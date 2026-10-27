"""Isolated Chromium acceptance for transient WebUI toasts. No provider calls."""

# Embedded browser expressions are intentionally kept intact.
# ruff: noqa: E501

import asyncio
import base64
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets

# Reuse the isolated host fixture; no live account or model/provider calls.
import webui_expressive_smoke as fixture
from webui_control_smoke import Tab

OUT = Path("/tmp/klaude-toasts-validation")
OUT.mkdir(exist_ok=True)


async def verify(host, root):
    chrome = str(
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
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(0.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(
            Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        ) as response:
            target = json.load(response)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=12000000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1440, "height": 960, "deviceScaleFactor": 1, "mobile": False},
            )
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
            await tab.js(
                "stream?.close();stream=null;clearInterval(pollTimer);document.fonts.ready"
            )
            await tab.js(
                'KlaudeToast.clear();showError(new Error("Standard mode is unsupported by this model"));showError(new Error("Failed to fetch"));showError(new Error("Failed to fetch"));domainError(new Error("Library unavailable"));KlaudeToast.show("Saved",{variant:"success",position:"bottom"})'
            )
            assert await tab.js(
                'document.querySelectorAll(".toast").length===4 && !byId("notice").textContent && !byId("library-status").textContent'
            )
            results = []
            for width in [1440, 390, 320]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": 844, "deviceScaleFactor": 1, "mobile": False},
                )
                await asyncio.sleep(0.25)
                assert await tab.js(
                    "[...document.querySelectorAll('.toast-stack')].every(s=>{const b=s.getBoundingClientRect();return s.matches(':popover-open') && b.x>=0&&b.right<=innerWidth&&b.y>=0&&b.bottom<=innerHeight&&s.scrollWidth===s.clientWidth})"
                )
                if width == 390:
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (OUT / "stacked-mobile.png").write_bytes(base64.b64decode(shot["data"]))
                results.append(width)
            await tab.click(".toast-close")
            await asyncio.sleep(0.25)
            assert await tab.js('document.querySelectorAll(".toast").length===3')
            await tab.js(
                'KlaudeToast.clear();KlaudeToast.show("<img src=x onerror=alert(1)>");KlaudeToast.show("Focus keeps this available")'
            )
            assert await tab.js('!document.querySelector(".toast img")')
            await tab.js('document.querySelector(".toast-close").focus()')
            await asyncio.sleep(5.4)
            assert await tab.js(
                'document.querySelectorAll(".toast").length===1 && document.querySelector(".toast-message").textContent==="Focus keeps this available"'
            )
            await tab.command(
                "Input.dispatchKeyEvent",
                {
                    "type": "keyDown",
                    "key": "Enter",
                    "code": "Enter",
                    "windowsVirtualKeyCode": 13,
                    "text": "\r",
                    "unmodifiedText": "\r",
                },
            )
            await asyncio.sleep(0.25)
            assert await tab.js('!document.querySelector(".toast")')
            await tab.js(
                'KlaudeToast.show("Dialog feedback");byId("mobile-model-sheet").showModal()'
            )
            await asyncio.sleep(0.1)
            assert await tab.js(
                'byId("mobile-model-sheet").contains(document.querySelector(".toast-stack")) && document.querySelector(".toast").parentElement.matches(":popover-open")'
            )
            await tab.click(".toast-close")
            await asyncio.sleep(0.25)
            assert await tab.js('!document.querySelector(".toast")')
            await tab.js(
                'KlaudeToast.show("Survives dialog close");byId("mobile-model-sheet").close()'
            )
            await asyncio.sleep(0.1)
            assert await tab.js(
                'document.querySelector(".toast").parentElement.parentElement===document.body && document.querySelector(".toast").parentElement.matches(":popover-open")'
            )
            await tab.js('KlaudeToast.clear();for(let i=0;i<9;i++)KlaudeToast.show("Message "+i)')
            assert await tab.js('document.querySelectorAll(".toast").length===5')
            await tab.js('document.dispatchEvent(new Event("klaude-auth-reset"))')
            assert await tab.js(
                '!document.querySelector(".toast") && !document.querySelector(".toast-stack:popover-open")'
            )
            await tab.js(
                'showError(Object.assign(new Error("stale"),{authEpoch:authEpoch-1}));showError(new DOMException("Cancelled","AbortError"))'
            )
            assert await tab.js('!document.querySelector(".toast")')
            await tab.js(
                'document.documentElement.dataset.motion="reduced";KlaudeToast.show("Reduced motion")'
            )
            assert await tab.js(
                'parseFloat(getComputedStyle(document.querySelector(".toast")).animationDuration)<.01'
            )
            await tab.js("KlaudeToast.clear()")
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "passedWidths": results,
                        "checks": "stacking, deduplication, top/bottom, close, five-second dismissal, focus pause, text safety, modal ownership, bounded stack, auth cleanup, stale/abort suppression, reduced motion",
                        "browserErrors": tab.errors,
                        "screenshots": str(OUT),
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=10)


fixture.verify = verify
fixture.main()

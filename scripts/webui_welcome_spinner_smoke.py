"""Real pointer/momentum checks for the New chat welcome spinner in isolated Chrome."""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
from urllib.request import Request, urlopen

import websockets
import webui_settings_smoke as fixture
from webui_control_smoke import Tab

ANGLE = """(()=>{
  const el=document.querySelector('.welcome-shape');
  const matrix=new DOMMatrixReadOnly(getComputedStyle(el).transform);
  return Math.atan2(matrix.b,matrix.a)*180/Math.PI;
})()"""


def delta(after, before):
    return (after - before + 180) % 360 - 180


async def verify(host, root, chrome, password):
    profile = root / "spinner-chrome"
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
    reports = []
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
        async with websockets.connect(target["webSocketDebuggerUrl"]) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command(
                "Emulation.setEmulatedMedia",
                {
                    "features": [
                        {"name": "prefers-reduced-motion", "value": "no-preference"},
                    ]
                },
            )
            await tab.command(
                "Page.navigate", {"url": host.origin if password else host.bootstrap_url}
            )
            if password:
                await tab.wait("typeof byId!=='undefined' && !byId('local-access').hidden")
                await tab.js(
                    'byId("login-username").value="admin";byId("login-password").value='
                    + json.dumps(host.accounts.initial_password())
                    + ';byId("account-login").requestSubmit()'
                )
            await tab.wait(
                "typeof latest!=='undefined' && latest?.session_id && authenticated && "
                "document.documentElement.dataset.startup==='ready'"
            )

            async def pointer(event, x, y, pressed=False):
                await tab.command(
                    "Input.dispatchMouseEvent",
                    {
                        "type": event,
                        "x": x,
                        "y": y,
                        "button": "left" if event != "mouseMoved" else "none",
                        "buttons": 1 if pressed else 0,
                        "clickCount": 1,
                    },
                )

            for width in (1440, 390):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 900,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                await tab.js("showView('chat');applyAppearance({...appearance,reduced:false},true)")
                await asyncio.sleep(0.1)
                center = await tab.js("""(()=>{
                  const r=document.querySelector('.welcome-emblem').getBoundingClientRect();
                  return {x:r.x+r.width/2,y:r.y+r.height/2,r:r.width*.35};
                })()""")
                x, y, radius = center["x"], center["y"], center["r"]
                idle = await tab.js(ANGLE)
                await asyncio.sleep(0.2)
                assert abs(delta(await tab.js(ANGLE), idle)) > 1
                await pointer("mousePressed", x + radius, y, True)
                assert await tab.js(
                    "document.querySelector('.welcome-emblem').classList.contains('is-spinning')"
                ), "Spinner did not capture the pointer"
                before = await tab.js(ANGLE)
                for step in range(1, 5):
                    angle = math.pi * step / 8
                    await pointer(
                        "mouseMoved",
                        x + radius * math.cos(angle),
                        y + radius * math.sin(angle),
                        True,
                    )
                    await asyncio.sleep(0.03)
                dragged = await tab.js(ANGLE)
                assert abs(delta(dragged, before)) > 60, (width, before, dragged)
                await pointer("mouseReleased", x, y + radius)
                await asyncio.sleep(0.1)
                coast = await tab.js(ANGLE)
                assert abs(delta(coast, dragged)) > 8, (width, dragged, coast)
                assert await tab.js(
                    "getComputedStyle(document.querySelector('.welcome-emblem > "
                    ".brand-paw')).transform==='none'"
                )
                await asyncio.sleep(2.8)
                coasting = await tab.js(ANGLE)
                await asyncio.sleep(0.15)
                assert abs(delta(await tab.js(ANGLE), coasting)) > 8, "Flick lost momentum too soon"
                if width == 1440:
                    await asyncio.sleep(13.5)
                    assert await tab.js(
                        "document.querySelector('.welcome-shape').getAnimations()[0]"
                        ".playState==='running'"
                    ), "Spinner did not return to its idle timeline"
                    idle_again = await tab.js(ANGLE)
                    await asyncio.sleep(.15)
                    assert 1 < abs(delta(await tab.js(ANGLE), idle_again)) < 8
                await pointer("mousePressed", x + radius, y, True)
                tapped = await tab.js(ANGLE)
                await pointer("mouseReleased", x + radius, y)
                await asyncio.sleep(0.1)
                assert abs(delta(await tab.js(ANGLE), tapped)) > 8, "Tap did not spin the backing"
                if width == 390:
                    await tab.command("Emulation.setTouchEmulationEnabled", {"enabled": True})
                    await tab.command(
                        "Input.dispatchTouchEvent",
                        {"type": "touchStart", "touchPoints": [{"x": x + radius, "y": y}]},
                    )
                    assert await tab.js(
                        "document.querySelector('.welcome-emblem').classList"
                        ".contains('is-spinning')"
                    )
                    touch_before = await tab.js(ANGLE)
                    await tab.command(
                        "Input.dispatchTouchEvent",
                        {"type": "touchMove", "touchPoints": [{"x": x, "y": y + radius}]},
                    )
                    assert abs(delta(await tab.js(ANGLE), touch_before)) > 60
                    await tab.command(
                        "Input.dispatchTouchEvent", {"type": "touchCancel", "touchPoints": []}
                    )
                    assert await tab.js(
                        "!document.querySelector('.welcome-emblem').classList"
                        ".contains('is-spinning')"
                    )
                    await tab.command("Emulation.setTouchEmulationEnabled", {"enabled": False})
                await tab.js("applyAppearance({...appearance,reduced:true},true)")
                await asyncio.sleep(0.1)
                frozen = await tab.js(ANGLE)
                await pointer("mousePressed", x + radius, y, True)
                await pointer("mouseReleased", x + radius, y)
                await asyncio.sleep(0.15)
                assert abs(delta(await tab.js(ANGLE), frozen)) < 0.1
                assert await tab.js(
                    "!document.querySelector('.welcome-emblem').classList.contains('is-spinning')"
                )
                await tab.js("applyAppearance({...appearance,reduced:false},true)")
                await tab.command(
                    "Emulation.setEmulatedMedia",
                    {
                        "features": [
                            {"name": "prefers-reduced-motion", "value": "reduce"},
                        ]
                    },
                )
                await asyncio.sleep(0.1)
                system_frozen = await tab.js(ANGLE)
                await pointer("mousePressed", x + radius, y, True)
                await pointer("mouseReleased", x + radius, y)
                await asyncio.sleep(0.1)
                assert abs(delta(await tab.js(ANGLE), system_frozen)) < 0.1
                await tab.command(
                    "Emulation.setEmulatedMedia",
                    {
                        "features": [
                            {"name": "prefers-reduced-motion", "value": "no-preference"},
                        ]
                    },
                )
                await tab.js("applyAppearance({...appearance,reduced:false},true)")
                await pointer("mousePressed", x + radius, y, True)
                await pointer("mouseReleased", x + radius, y)
                await tab.js("showView('settings',{section:'theme'})")
                assert await tab.js(
                    "!document.querySelector('.welcome-emblem').classList.contains('is-spinning')"
                )
                reports.append(
                    {
                        "width": width,
                        "idle_drag_flick_tap_reduced_cleanup": "passed",
                        "touch_cancel": "passed" if width == 390 else "not applicable",
                    }
                )
            assert not tab.errors, tab.errors
            return {"auth": "password" if password else "bootstrap", "cases": reports}
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    fixture.verify = verify
    fixture.main()

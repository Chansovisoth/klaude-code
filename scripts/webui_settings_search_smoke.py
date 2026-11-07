"""Settings search navigation geometry in real Chrome with isolated profile data.

Run: .venv/bin/python scripts/webui_settings_search_smoke.py
No production settings, model services or saved preferences are changed.
"""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
import webui_settings_smoke as fixture
from webui_control_smoke import Tab

OUT = Path(__file__).resolve().parents[1] / "output/playwright/settings-search"
WIDTHS = (1440, 768, 390)
CASES = (
    ("Reduced motion", "reduced-motion"),
    ("Surface transparency", "theme-transparency"),
    ("Search provider", "setting-search_settings-provider"),
    ("Source budget", "setting-research-sources"),
    ("Utility output tokens", "default-output-tokens"),
    ("Connected models", "models-query"),
)

MEASURE = """(()=>{
  const view=byId('settings-view'),main=byId('main-content');
  const ancestors=[];
  for(let el=view;el;el=el.parentElement)ancestors.push({
    id:el.id||el.className||el.tagName,scrollTop:el.scrollTop,
    height:el.clientHeight,scrollHeight:el.scrollHeight,
    rect:el.getBoundingClientRect().toJSON()
  });
  return {ancestors,view:view.getBoundingClientRect().toJSON(),
    main:main.getBoundingClientRect().toJSON(),focus:document.activeElement.id,
    focusRect:document.activeElement.getBoundingClientRect().toJSON(),section:settingsSection};
})()"""


def check_geometry(state, context):
    assert all(item["scrollTop"] == 0 for item in state["ancestors"][1:]), (context, state)
    for edge in ("top", "bottom"):
        assert abs(state["view"][edge] - state["main"][edge]) < 1, (context, state)


async def verify(host, root, chrome, password):
    profile = root / "search-chrome"
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
    OUT.mkdir(parents=True, exist_ok=True)
    cases = []
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
                "Page.navigate", {"url": host.origin if password else host.bootstrap_url}
            )
            if password:
                await tab.wait("typeof byId!=='undefined' && !byId('local-access').hidden")
                await tab.js(
                    'byId("login-username").value="admin";byId("login-password").value='
                    + json.dumps(host.accounts.initial_password())
                    + ';byId("account-login").requestSubmit()'
                )
            await tab.wait("typeof latest!=='undefined' && latest?.session_id && authenticated")
            await tab.wait("document.documentElement.dataset.startup==='ready'")
            for width in WIDTHS:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 900,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                for query, target_id in CASES:
                    await tab.js("showView('settings',{section:'theme'})")
                    await tab.click("#settings-search-open")
                    await tab.js(
                        "byId('settings-search-query').value="
                        + json.dumps(query)
                        + ";byId('settings-search-query').dispatchEvent(new Event('input'))"
                    )
                    await tab.wait("byId('settings-search-results').children.length>0")
                    if query == "Source budget" and password:
                        await tab.command(
                            "Input.dispatchKeyEvent",
                            {
                                "type": "keyDown",
                                "key": "Enter",
                                "code": "Enter",
                                "windowsVirtualKeyCode": 13,
                            },
                        )
                        await tab.command(
                            "Input.dispatchKeyEvent",
                            {
                                "type": "keyUp",
                                "key": "Enter",
                                "code": "Enter",
                                "windowsVirtualKeyCode": 13,
                            },
                        )
                    else:
                        await tab.click("#settings-search-results button")
                    await tab.wait("!byId('settings-search-dialog').open")
                    await asyncio.sleep(0.7)
                    after = await tab.js(MEASURE)
                    check_geometry(after, (width, query, "navigation"))
                    assert after["focus"] == target_id, (width, query, after)
                    assert (
                        after["focusRect"]["bottom"] > after["view"]["top"]
                        and after["focusRect"]["top"] < after["view"]["bottom"]
                    ), (width, query, after)
                    await tab.js("byId('settings-view').scrollTo({top:0,behavior:'instant'})")
                    await asyncio.sleep(0.1)
                    scrolled_up = await tab.js(MEASURE)
                    check_geometry(scrolled_up, (width, query, "scroll back up"))
                    assert scrolled_up["ancestors"][0]["scrollTop"] == 0, scrolled_up
                    capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (
                        OUT / f"{'password' if password else 'bootstrap'}-{width}-{target_id}.png"
                    ).write_bytes(base64.b64decode(capture["data"]))
                    cases.append(
                        {
                            "width": width,
                            "query": query,
                            "target": target_id,
                            "navigation_and_scroll_back": "passed",
                        }
                    )
            assert not tab.errors, tab.errors
            return {"auth": "password" if password else "bootstrap", "cases": cases}
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    fixture.verify = verify
    fixture.main()

"""Offline UI-icon rendering and control checks using isolated real Chrome profiles.

Run: .venv/bin/python scripts/webui_ui_icons_smoke.py
No production settings, model services, downloads or installs are used.
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

OUT = Path(__file__).resolve().parents[1] / "output/playwright/fontawesome"
MEASURE = """(()=>{
  const visible=el=>el.getClientRects().length&&!el.closest('[hidden]');
  const icons=[...document.querySelectorAll('svg.ui-icon')].filter(visible);
  const bad=icons.filter(el=>{
    const path=el.querySelector('path'),style=getComputedStyle(path);
    return !path.getBBox().width || !path.getBBox().height || style.fill==='none' ||
      style.stroke!=='none' || el.getAttribute('focusable')!=='false';
  }).map(el=>({name:el.dataset.uiIcon,source:el.dataset.iconSource,
    fill:getComputedStyle(el.querySelector('path')).fill,
    stroke:getComputedStyle(el.querySelector('path')).stroke}));
  const size=parseFloat(getComputedStyle(document.documentElement)
    .getPropertyValue('--square-control-size'));
  const squares=[...document.querySelectorAll(
    '#main-content .icon-button,#workspace-sidebar .icon-button,'+
    '#session-sidebar .icon-button,.topbar .icon-button,.context-panel .icon-button,'+
    'dialog .icon-button,.square-button,.file-view-modes>button,'+
    '.cp-view-modes>button,.pagination button')].filter(visible);
  const wrongSize=squares.filter(el=>{
    const r=el.getBoundingClientRect();return Math.abs(r.width-size)>1||Math.abs(r.height-size)>1;
  }).map(el=>({id:el.id,classes:el.className,width:el.getBoundingClientRect().width,
    height:el.getBoundingClientRect().height}));
  return {count:icons.length,bad,fits:document.documentElement.scrollWidth<=innerWidth,
    squares:squares.length,wrongSize,
    missing:[...document.querySelectorAll('svg[data-ui-icon]')].filter(el=>!el.dataset.iconSource).length,
    sources:[...new Set(icons.map(el=>el.dataset.iconSource))]};
})()"""


async def verify(host, root, chrome, password):
    profile = root / "ui-icons-chrome"
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
            await tab.command("Network.enable")
            await tab.command("Network.setBlockedURLs", {"urls": ["https://*"]})
            await tab.command(
                "Page.navigate", {"url": host.origin if password else host.bootstrap_url}
            )
            if password:
                await tab.wait("typeof byId!=='undefined' && !byId('local-access').hidden")
                assert await tab.js(
                    "[...byId('local-access').querySelectorAll('[data-lock-icon] svg')]"
                    ".every(el=>el.dataset.iconSource==='fontawesome-free-solid')"
                )
                await tab.js(
                    'byId("login-username").value="admin";byId("login-password").value='
                    + json.dumps(host.accounts.initial_password())
                    + ';byId("account-login").requestSubmit()'
                )
            await tab.wait(
                "typeof latest!=='undefined' && latest?.session_id && authenticated && "
                "document.documentElement.dataset.startup==='ready'"
            )
            await tab.js("document.fonts.ready")
            # Exercise every semantic alias, every upstream glyph and all custom
            # specialties. The temporary atlas also checks inherited fill/stroke.
            atlas = await tab.js("""(()=>{
              const node=document.createElement('div');node.id='icon-atlas';
              node.style.cssText='position:fixed;inset:0;z-index:1000;display:grid;grid-template-columns:repeat(12,1fr);overflow:auto;background:var(--surface);padding:16px';
              document.body.append(node);
              const names=[...KlaudeUIIcons.names,...Object.keys(KlaudeUIIconData.custom),
                ...Object.keys(KlaudeUIIconData.glyphs)];
              for(const name of names){
                const sample=document.createElement('span');
                sample.style.cssText='display:grid;justify-items:center;'+
                  'align-content:center;gap:8px;font-size:9px';
                sample.append(libraryIcon(name),document.createTextNode(name));node.append(sample);
              }
              const all=[...node.querySelectorAll('svg')];
              const valid=all.every(el=>el.querySelector('path').getBBox().width>0 &&
                el.getAttribute('aria-hidden')==='true'&&getComputedStyle(el.querySelector('path')).stroke==='none');
              return {count:all.length,valid,unknown:KlaudeUIIcons.definition('__proto__').name};
            })()""")
            assert atlas["valid"] and atlas["unknown"] == "file", atlas
            await tab.js("byId('icon-atlas').remove()")
            for width in (1440, 768, 390, 320):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 900,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                for theme in ("light", "dark"):
                    for view, section in (
                        ("chat", None),
                        ("settings", "models"),
                        ("settings", "agent"),
                        ("library", None),
                    ):
                        await tab.js(
                            "showView("
                            + json.dumps(view)
                            + ",{section:"
                            + json.dumps(section)
                            + "})"
                        )
                        # Leaving Settings restores the saved appearance.
                        await tab.js(
                            "applyAppearance({...appearance,theme:" + json.dumps(theme) + "},true)"
                        )
                        await asyncio.sleep(0.25)
                        state = await tab.js(MEASURE)
                        assert state["count"] and not state["bad"] and not state["missing"], (
                            width,
                            theme,
                            view,
                            section,
                            state,
                        )
                        assert state["fits"], (width, theme, view, state)
                        assert not state["wrongSize"], (width, theme, view, state["wrongSize"])
                        if view == "settings" and section == "models":
                            assert await tab.js(
                                "[...document.querySelectorAll('.model-default-icon')]"
                                ".every(el=>el.dataset.iconSource==='fontawesome-free-solid')"
                            )
                            await tab.click("#default-value-chat-picker")
                            assert await tab.js("byId('role-model-picker').open")
                            await tab.click("#role-picker-close")
                        if width in (390, 1440):
                            await asyncio.sleep(0.05)
                            await tab.js("document.activeElement.blur()")
                            capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                            auth = "password" if password else "bootstrap"
                            name = f"{auth}-{width}-{theme}-{section or view}.png"
                            (OUT / name).write_bytes(base64.b64decode(capture["data"]))
                        reports.append(
                            {
                                "width": width,
                                "theme": theme,
                                "scene": section or view,
                                "icons": state["count"],
                            }
                        )
            assert await tab.js(
                "!performance.getEntriesByType('resource').some(entry=>"
                "/fontawesome|fontawesome.com|use.fontawesome/.test(entry.name))"
            )
            assert not tab.errors, tab.errors
            return {
                "auth": "password" if password else "bootstrap",
                "atlas": atlas,
                "scenes": reports,
                "external_icon_requests": 0,
                "console_errors": 0,
            }
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    fixture.verify = verify
    fixture.main()

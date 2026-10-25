"""Real Chrome Settings geometry checks using isolated profile data.

Run: .venv/bin/python scripts/webui_settings_layout_smoke.py
Keyboard overlay geometry is emulated; physical mobile keyboards are not certified.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

import websockets
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools import Workspace
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab
from webui_settings_smoke import _app

OUT = Path("/tmp/klaude-settings-layout")

MEASURE = """(()=>{
  const view=byId('settings-view'),tabs=byId('settings-sections'),dock=byId('settings-action-dock');
  const panel=view.querySelector('[role=tabpanel]:not([hidden])');
  const bar=panel.querySelector('.settings-save-bar,#theme-save-bar')||dock.firstElementChild;
  const b=bar.getBoundingClientRect(),d=dock.getBoundingClientRect(),n=tabs.getBoundingClientRect();
  const selected=tabs.querySelector('[aria-selected=true]'),s=selected.getBoundingClientRect();
  const rail=document.querySelector('.rail').getBoundingClientRect();
  const main=byId('main-content').getBoundingClientRect();
  const p=panel.getBoundingClientRect(),v=view.getBoundingClientRect();
  const colors=[tabs,selected,dock].map(el=>getComputedStyle(el).backgroundColor);
  const buttons=[...tabs.querySelectorAll('button:not([hidden])')];
  const actions=[...bar.querySelectorAll('button:not([hidden])')]
    .map(el=>el.getBoundingClientRect());
  const discard=bar.querySelector('[id$="-discard"],#theme-reset');
  const apply=bar.querySelector('[id$="-save"],#theme-apply');
  const barStyle=getComputedStyle(bar);
  const end=view.scrollHeight-view.scrollTop-view.clientHeight<2;
  return {mobile:innerWidth<=850,width:innerWidth,bar:b.toJSON(),dock:d.toJSON(),rail:rail.toJSON(),
    sharedFooter:bar.classList.contains('theme-actions')&&discard?.classList.contains('quiet')&&
      apply?.textContent==='Apply changes'&&barStyle.borderRadius==='0px'&&
      barStyle.boxShadow==='none',
    main:main.toJSON(),tabs:n.toJSON(),end,colors,
    docked:bar.parentElement===dock,barId:bar.id,
    bodyFits:document.documentElement.scrollWidth<=innerWidth,
    viewFits:view.scrollWidth<=view.clientWidth,
    oneRow:buttons.every(button=>Math.abs(button.getBoundingClientRect().top-s.top)<1),
    horizontal:getComputedStyle(tabs).overflowX==='auto',
    separate:!tabs.classList.contains('section-chips')&&!tabs.closest('.theme-studio'),
    selectedVisible:s.right>n.left&&s.left<n.right,
    padding:parseFloat(getComputedStyle(view).paddingBottom),
    reserved:parseFloat(getComputedStyle(view).paddingBottom)>=d.height,
    actionsFit:actions.every(r=>r.left>=0&&r.right<=innerWidth&&r.top>=d.top&&r.bottom<=d.bottom),
    rightAligned:actions.at(-1)?.right>=d.right-40,
    panelEnd:panel.getBoundingClientRect().bottom,
    desktopThemeCoverage:Math.abs(b.left-p.left)<1&&Math.abs(b.right-p.right)<1&&
      b.bottom>=Math.min(v.bottom,p.bottom)-1&&
      getComputedStyle(bar).backgroundColor.startsWith('rgb(')&&
      bar.contains(document.elementFromPoint(b.left+b.width/2,
        Math.min(b.bottom,v.bottom)-2)),
    hit:document.elementFromPoint(Math.min(n.right-8,Math.max(n.left+8,s.left+8)),
      n.top+n.height/2)?.closest('#settings-sections')===tabs,
    orientation:tabs.getAttribute('aria-orientation')};
})()"""


async def verify(host, root, chrome):
    profile = root / "chrome-layout"
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
    OUT.mkdir(exist_ok=True)
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
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait(
                "typeof authenticated!=='undefined' && authenticated && latest && "
                "window.SettingsActions && "
                "document.documentElement.dataset.startup==='ready'"
            )
            await tab.js("showView('settings',{section:'agent'})")
            await tab.wait("Boolean(byId('setting-runtime_options-max_steps'))")
            await tab.js("""const field=byId('setting-runtime_options-max_steps');
              field.value=Number(field.value)+1;field.dispatchEvent(new Event('input'));
              showSettingsSection('models');""")
            await tab.wait("Boolean(byId('default-output-tokens'))")
            await tab.js("""const output=byId('default-output-tokens');
              output.value=Number(output.value)+1;output.dispatchEvent(new Event('input'));
              byId('settings-sections').querySelectorAll('button').forEach(button=>{
                button.childNodes.forEach(node=>{if(node.nodeType===Node.TEXT_NODE)node.remove()});
                const label=document.createElement('span');
                label.textContent=button.dataset.settings==='models'?
                  'Model defaults and image generation':button.dataset.settings==='agent'?
                  'Agent tools and permissions':button.dataset.settings;
                button.append(label);
              });""")
            # Editing the hex value must preserve its resting appearance.
            await tab.js("showSettingsSection('theme')")
            assert await tab.js("""(()=>{
              const e=byId('theme-accent-value'),color=byId('theme-accent');
              const measure=()=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();
                return JSON.stringify([r.width,r.height,s.padding,s.borderWidth,
                  s.backgroundColor,s.font,s.color,s.boxShadow,s.outlineStyle]);};
              const before=measure();e.focus();const focused=measure();
              e.value='#abc';e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter'}));
              const committed=color.value==='#aabbcc'&&e.value==='#aabbcc'&&
                document.querySelector('input[name="color-source"]:checked').value==='custom';
              e.focus();e.value='bad hex';e.blur();
              const invalid=color.value==='#aabbcc'&&e.value==='#aabbcc';
              e.focus();e.value='#112233';
              e.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));
              const cancelled=color.value==='#aabbcc'&&e.value==='#aabbcc';
              e.focus();e.value='#123456';e.blur();
              const blurred=color.value==='#123456';
              byId('theme-reset').click();
              return before===focused&&committed&&invalid&&cancelled&&blurred;
            })()""")
            reports = []
            for theme in ("light", "dark"):
                for width, height in (
                    (320, 568),
                    (390, 844),
                    (560, 700),
                    (768, 1024),
                    (850, 768),
                    (844, 390),
                    (851, 700),
                    (1440, 900),
                ):
                    await tab.command(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": width,
                            "height": height,
                            "deviceScaleFactor": 1,
                            "mobile": width <= 560,
                        },
                    )
                    await tab.js(
                        "applyAppearance(appearance={...appearance,theme:"
                        + json.dumps(theme)
                        + ",transparency:20,reduced:true},true)"
                    )
                    for category in ("agent", "models", "theme"):
                        await tab.js("showSettingsSection(" + json.dumps(category) + ")")
                        if category == "theme":
                            await tab.js("""{const input=document.querySelector(
                              'input[name="chat-density"]:not(:checked)');
                              input.checked=true;input.dispatchEvent(new Event('change'));}""")
                        if category == "agent":
                            await tab.js(
                                "byId('agent-settings').querySelectorAll('details')"
                                ".forEach(section=>section.open=true)"
                            )
                        if category == "agent" and width in (390, 1440):
                            help_count = await tab.js(
                                "byId('agent-settings').querySelectorAll('.settings-help-button').length"
                            )
                            assert help_count >= 20
                            for index in range(help_count):
                                await tab.js(
                                    "byId('agent-settings').querySelectorAll('.settings-help-button')"
                                f"[{index}].click()"
                                )
                                assert await tab.js("""(()=>{
                                  const d=byId('agent-help-dialog'),r=d.getBoundingClientRect();
                                  return d.matches(':modal')&&
                                    d.querySelectorAll('button').length===1&&
                                    d.querySelector('button').textContent==='OK'&&
                                    document.activeElement===d.querySelector('button')&&
                                    byId('agent-help-text').textContent.length>30&&
                                    r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;
                                })()""")
                                if index % 2:
                                    await tab.command(
                                        "Input.dispatchKeyEvent",
                                        {
                                            "type": "keyDown",
                                            "key": "Escape",
                                            "code": "Escape",
                                            "windowsVirtualKeyCode": 27,
                                        },
                                    )
                                    await tab.command(
                                        "Input.dispatchKeyEvent",
                                        {
                                            "type": "keyUp",
                                            "key": "Escape",
                                            "code": "Escape",
                                            "windowsVirtualKeyCode": 27,
                                        },
                                    )
                                else:
                                    await tab.js(
                                        "byId('agent-help-dialog').querySelector('button').click()"
                                    )
                                await tab.wait(
                                    "!byId('agent-help-dialog').open&&document.activeElement==="
                                    "byId('agent-settings').querySelectorAll('.settings-help-button')"
                                    f"[{index}]"
                                )
                        positions = (0, 0.5, 1) if width > 850 and category == "theme" else (0, 1)
                        for position in positions:
                            await tab.js(
                                "byId('settings-view').scrollTop="
                                + str(position)
                                + "*(byId('settings-view').scrollHeight-"
                                "byId('settings-view').clientHeight)"
                            )
                            await asyncio.sleep(0.1)
                            result = await tab.js(MEASURE)
                            assert (
                                result["bodyFits"] and result["viewFits"] and result["separate"]
                            ), result
                            assert result["sharedFooter"], result
                            if width <= 850:
                                assert all(
                                    result[key]
                                    for key in (
                                        "docked",
                                        "oneRow",
                                        "horizontal",
                                        "reserved",
                                        "actionsFit",
                                        "rightAligned",
                                        "hit",
                                    )
                                ), result
                                assert result["orientation"] == "horizontal", result
                                assert all(
                                    color.startswith("rgb(") for color in result["colors"]
                                ), result
                                d = result["dock"]
                                assert (
                                    abs(d["left"] - (0 if width <= 560 else result["main"]["left"]))
                                    < 1
                                ), result
                                assert (
                                    abs(
                                        d["right"]
                                        - (width if width <= 560 else result["main"]["right"])
                                    )
                                    < 1
                                ), result
                                assert (
                                    abs(
                                        d["bottom"]
                                        - (result["rail"]["top"] if width <= 560 else height)
                                    )
                                    < 1
                                ), result
                                if result["end"]:
                                    assert result["panelEnd"] <= d["top"] + 1, result
                            else:
                                assert (
                                    not result["docked"] and result["orientation"] == "vertical"
                                ), result
                                if category == "theme":
                                    assert result["desktopThemeCoverage"], result
                            reports.append(
                                {
                                    "theme": theme,
                                    "category": category,
                                    "scroll_fraction": position,
                                    **result,
                                }
                            )
                        if width in (390, 1440) and category in ("agent", "theme"):
                            shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                            (OUT / f"{category}-{theme}-{width}.png").write_bytes(
                                base64.b64decode(shot["data"])
                            )
            # Arrow/Home/End navigation keeps focus visible in the opaque scroller.
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 390,
                    "height": 844,
                    "deviceScaleFactor": 1,
                    "mobile": True,
                },
            )
            await tab.js("showSettingsSection('agent',{focus:true})")
            for key in ("End", "Home", "ArrowRight"):
                await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": key})
                await tab.command("Input.dispatchKeyEvent", {"type": "keyUp", "key": key})
                assert await tab.js(
                    "document.activeElement.matches('#settings-sections [aria-selected=true]')"
                )
                assert await tab.js(
                    "getComputedStyle(document.activeElement).outlineStyle==='solid'"
                )
            await tab.js(
                "showSettingsSection('agent');byId('setting-research-context_tokens').focus()"
            )
            await asyncio.sleep(0.15)
            await tab.command(
                "Emulation.setEmulatedMedia",
                {
                    "features": [{"name": "forced-colors", "value": "active"}],
                },
            )
            assert await tab.js("""(()=>{
              const style=getComputedStyle(byId('settings-sections')
                .querySelector('[aria-selected=true]'));
              return style.outlineStyle==='solid' && parseFloat(style.outlineWidth)>=2;
            })()""")
            await tab.command("Emulation.setEmulatedMedia", {"features": []})
            await tab.js("""window.layoutViewport=window.visualViewport;
              Object.defineProperty(window,'visualViewport',{configurable:true,
                value:{height:360,offsetTop:32,scale:1}});
              layoutViewport.dispatchEvent(new Event('resize'));""")
            await tab.wait(
                "byId('settings-action-dock').getBoundingClientRect().bottom<="
                "visualViewport.height+visualViewport.offsetTop"
            )
            await asyncio.sleep(0.15)
            overlay = await tab.js("""(()=>{
              const d=byId('settings-action-dock').getBoundingClientRect(),
              f=document.activeElement.getBoundingClientRect();return {
                dock:d.toJSON(),field:f.toJSON(),viewport:visualViewport.height+visualViewport.offsetTop,
                padding:parseFloat(getComputedStyle(byId('settings-view')).paddingBottom),
                scrollTop:byId('settings-view').scrollTop,scrollHeight:byId('settings-view').scrollHeight,
                clientHeight:byId('settings-view').clientHeight};})()""")
            assert overlay["dock"]["bottom"] <= overlay["viewport"], overlay
            assert overlay["field"]["bottom"] <= overlay["dock"]["top"], overlay
            assert overlay["padding"] > overlay["dock"]["height"], overlay
            await tab.js(
                "Object.defineProperty(window,'visualViewport',"
                "{configurable:true,value:layoutViewport});"
                "layoutViewport.dispatchEvent(new Event('resize'))"
            )
            await tab.js(
                "byId('agent-save-status').textContent="
                + json.dumps(
                    "A long connection error keeps these settings as drafts for another attempt. "
                    * 5
                )
            )
            # Resizing-layout keyboards and enlarged bottom navigation are measured too.
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 390,
                    "height": 380,
                    "deviceScaleFactor": 1,
                    "mobile": True,
                },
            )
            await tab.js("document.querySelector('.rail').style.paddingBottom='38px'")
            await asyncio.sleep(0.15)
            resized = await tab.js(MEASURE)
            assert resized["actionsFit"] and resized["dock"]["bottom"] <= resized["rail"]["top"], (
                resized
            )
            # Geometry of a long status with the pending-save recovery action.
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 320,
                    "height": 380,
                    "deviceScaleFactor": 1,
                    "mobile": True,
                },
            )
            await tab.js("byId('agent-save-check').hidden=false")
            await asyncio.sleep(0.15)
            recovery = await tab.js(MEASURE)
            assert recovery["actionsFit"] and recovery["reserved"], recovery
            await tab.js("byId('agent-save-check').hidden=true")
            await tab.click("#agent-discard")
            await tab.wait("byId('settings-action-dock').hidden")
            await tab.js("showSettingsSection('models')")
            await tab.wait("!byId('settings-action-dock').hidden")
            await tab.click("#models-discard")
            await tab.wait("byId('settings-action-dock').hidden")
            await tab.js("showSettingsSection('theme')")
            await tab.click("#theme-reset")
            await tab.wait("byId('settings-action-dock').hidden")
            await tab.js("document.querySelector('input[name=chat-density]:not(:checked)').click()")
            await tab.wait("!byId('settings-action-dock').hidden")
            await tab.click("#theme-apply")
            await tab.wait("byId('settings-action-dock').hidden")
            await tab.js(
                "document.querySelector('input[name=chat-density]:not(:checked)').click();showView('chat')"
            )
            await tab.wait("byId('settings-action-dock').hidden")
            assert not tab.errors, tab.errors
            Path("/tmp/klaude-settings-layout.json").write_text(json.dumps(reports))
            return {
                "layouts": len(reports),
                "opaque_tabs_and_dock": True,
                "long_labels_and_keyboard_navigation": True,
                "viewport_keyboard_emulation": True,
                "measured_navigation_and_padding": True,
                "drafts_and_discard_apply": True,
                "desktop_restoration": True,
                "console_errors": 0,
            }
    finally:
        process.terminate()
        process.wait(timeout=10)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    with tempfile.TemporaryDirectory(prefix="klaude-settings-layout-") as folder:
        root = Path(folder)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(cfg.data_dir)
        app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        host = LocalWebHost(app, library=LibraryManagement(cfg, root))
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            with patch(
                "klaude_application.browser_media_settings.default_model_catalog", return_value=[]
            ):
                print(json.dumps(asyncio.run(asyncio.wait_for(verify(host, root, chrome), 180))))
        finally:
            host.stop()
            thread.join(3)
            app.memory.db.close()


if __name__ == "__main__":
    main()

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
  const bar=[...panel.querySelectorAll('.settings-save-bar,#theme-save-bar')]
    .find(element=>!element.hidden&&!element.closest('[hidden]'))||dock.firstElementChild;
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
    scrollInfo:{scrollHeight:view.scrollHeight,clientHeight:view.clientHeight,scrollTop:view.scrollTop,
      viewRect:v.toJSON(),afterHeight:getComputedStyle(view,'::after').height,
      afterContent:getComputedStyle(view,'::after').content,classes:view.className},
    contentEnd:Math.max(0,...[...panel.querySelectorAll('input,select,textarea,button,summary')]
      .filter(el=>{
        const closed=el.closest('details:not([open])');
        return el.getClientRects().length && !el.closest('[hidden]') &&
          (!closed || el.tagName==='SUMMARY' && el.parentElement===closed);
      }).map(el=>el.getBoundingClientRect().bottom)),
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
            # This walkthrough intentionally keeps multiple drafts while switching
            # categories; accept the existing leave-with-draft confirmation.
            await tab.js("window.confirm=()=>true; showView('settings',{section:'agent'})")
            await tab.wait("Boolean(byId('setting-runtime_options-max_steps'))")
            assert await tab.js("""(() => {
              const groups=[...byId('agent-settings-fields')
                .querySelectorAll('details[id^=agent-group-]')];
              return groups.length>=7 && groups.every(group=>group.open);
            })()""")
            await tab.js("""byId('agent-group-search_settings').open=false;
              byId('agent-group-advanced_permissions').open=false;
              {const field=byId('setting-runtime_options-max_steps');
              field.value=Number(field.value)+1;field.dispatchEvent(new Event('input'));}""")
            await tab.click('#agent-discard')
            assert await tab.js("!byId('agent-group-search_settings').open && "
                                "!byId('agent-group-advanced_permissions').open")
            assert await tab.js("""(() => {
              const groups=[...byId('agent-settings-fields').querySelectorAll(
                ':scope > .settings-disclosure')];
              const reference=getComputedStyle(
                document.querySelector('#account-settings .settings-row-group'));
              return groups.length>=6 && groups.every(group=>{
                const body=group.querySelector(':scope > .settings-group-body');
                if (!body) return false;
                const style=getComputedStyle(body), parent=getComputedStyle(group);
                return style.backgroundColor===reference.backgroundColor &&
                  style.borderColor===reference.borderColor &&
                  style.borderRadius===reference.borderRadius && parent.borderTopWidth==='0px';
              }) && byId('agent-group-tools_permissions')
                .querySelectorAll('[data-agent-tool]').length>0;
            })()""")
            await tab.js("""byId('agent-group-tools_permissions').open=true;
              window.originalToolPolicy=SettingsDrafts.value('agent','permissions.read_file');
              const next=[...byId('setting-permissions-read_file').querySelectorAll('input')]
                .find(input=>!input.disabled && input.value!==originalToolPolicy);
              next.click();""")
            assert await tab.js(
                "SettingsDrafts.value('agent','permissions.read_file')!==originalToolPolicy"
            )
            await tab.click('#agent-discard')
            assert await tab.js(
                "SettingsDrafts.value('agent','permissions.read_file')===originalToolPolicy"
            )
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
            # Theme controls use the same grouped surfaces as the other pages.
            await tab.js("showSettingsSection('theme')")
            assert await tab.js("""(() => {
              const groups=[...byId('theme-settings').querySelectorAll(
                '.theme-option-surface, .theme-variant-options')];
              const reference=getComputedStyle(
                document.querySelector('#account-settings .settings-row-group'));
              return groups.length===6 && groups.every(group=>{
                const style=getComputedStyle(group);
                return style.backgroundColor===reference.backgroundColor &&
                  style.borderColor===reference.borderColor &&
                  style.borderRadius===reference.borderRadius;
              }) && byId('theme-settings').querySelectorAll('input[name=palette]').length===16 &&
                Boolean(byId('theme-loading-preview')) && Boolean(byId('theme-progress-preview'));
            })()""")
            # Editing the hex value must preserve its resting appearance.
            hex_check = await tab.js("""(()=>{
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
              return {same:before===focused,committed,invalid,cancelled,blurred,before,focused};
            })()""")
            assert all(
                hex_check[key] for key in ("same", "committed", "invalid", "cancelled", "blurred")
            ), hex_check
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
                        if category == "theme":
                            assert await tab.js("""(() => {
                              const preview=document.querySelector('.theme-studio-previews')
                                .getBoundingClientRect();
                              const controls=document.querySelector('.theme-studio-controls')
                                .getBoundingClientRect();
                              return Math.abs(preview.width-controls.width)<1;
                            })()"""), (theme,width)
                            assert await tab.js("""(() => {
                              const group=document.querySelector('.theme-surface-controls');
                              const bounds=group.getBoundingClientRect();
                              return [...group.querySelectorAll(':scope > label')].every((row,i)=>{
                                const r=row.getBoundingClientRect(), style=getComputedStyle(row);
                                const title=row.firstElementChild.getBoundingClientRect();
                                const control=row.lastElementChild.getBoundingClientRect();
                                return Math.abs(r.left-bounds.left-1)<1.5 &&
                                  Math.abs(bounds.right-r.right-1)<1.5 &&
                                  parseFloat(style.borderTopWidth)===(i ? 1 : 0) &&
                                  parseFloat(style.paddingLeft)>=12 &&
                                  title.right<=control.left+1 && control.right<=r.right &&
                                  title.top<control.bottom && control.top<title.bottom;
                              });
                            })()"""), (theme,width)
                        if category == "agent":
                            assert await tab.js("""(() => {
                              const group=byId('agent-group-tools_permissions')
                                .querySelector('.settings-tool-body');
                              const nested=byId('agent-group-advanced_permissions');
                              const a=group.getBoundingClientRect(),
                                b=nested.getBoundingClientRect();
                              return Math.abs(b.left-a.left-1)<1.5 &&
                                Math.abs(a.right-b.right-1)<1.5 &&
                                parseFloat(getComputedStyle(nested).borderTopWidth)===1;
                            })()"""), (theme,width)
                            divider_geometry = await tab.js("""(() => {
                              const groups=[...document.querySelectorAll(
                                '#agent-settings-fields > .settings-disclosure > '+
                                '.settings-group-body')];
                              return groups.flatMap(group=>[...group.querySelectorAll(
                                ':scope > .setting-row')].map(row=>{
                                  const outer=group.getBoundingClientRect(),
                                    inner=row.getBoundingClientRect();
                                  return {id:row.dataset.setting||row.dataset.agentTool,
                                    left:Math.abs(inner.left-outer.left-1),
                                    right:Math.abs(outer.right-inner.right-1),
                                    padding:parseFloat(getComputedStyle(row).paddingLeft)};
                                }));
                            })()""")
                            assert all(item["left"] < 1.5 and item["right"] < 1.5 and
                                       item["padding"] >= 16 for item in divider_geometry), (
                                           theme, width, divider_geometry
                                       )
                            tools_geometry = await tab.js("""(() => {
                              const group=byId('agent-group-tools_permissions')
                                .querySelector('.settings-tool-body');
                              const outer=group.getBoundingClientRect();
                              return [...group.querySelectorAll('.tool-permission-list')]
                                .map(list=>{
                                const bounds=list.getBoundingClientRect();
                                const cards=[...list.children].map(row=>({
                                  rect:row.getBoundingClientRect().toJSON(),
                                  padding:parseFloat(getComputedStyle(row).paddingLeft),
                                  segments:[...row.querySelectorAll('.tool-policy-form label span')]
                                    .map(el=>el.getBoundingClientRect().width),
                                }));
                                return {left:Math.abs(bounds.left-outer.left-1),
                                  right:Math.abs(outer.right-bounds.right-1),
                                  columns:getComputedStyle(list).gridTemplateColumns
                                    .split(' ').length,
                                  width:group.clientWidth,
                                  bottomBorder:parseFloat(getComputedStyle(list).borderBottomWidth),
                                  cards};
                              });
                            })()""")
                            assert all(
                                item["left"] < 1.5 and item["right"] < 1.5 and
                                item["bottomBorder"] == 1 and item["columns"] == (
                                    2 if width > 768 and item["width"] >= 496 else 1
                                )
                                and all(card["padding"] >= 16 and
                                        all(segment >= 44 for segment in card["segments"])
                                        for card in item["cards"])
                                for item in tools_geometry
                            ), (theme, width, tools_geometry)
                            row_geometry = await tab.js("""[...byId('agent-settings-fields')
                              .querySelectorAll(
                                '.settings-group-body > .setting-row:not(.settings-toggle-row)')]
                              .filter(row=>row.getClientRects().length).map(row=>{
                                const label=row.firstElementChild.getBoundingClientRect();
                                const controls=row.querySelector('.settings-controls')
                                  .getBoundingClientRect();
                                const bounds=row.getBoundingClientRect();
                                return {id:row.dataset.setting, left:label.toJSON(),
                                  right:controls.toJSON(), row:bounds.toJSON()};
                              })""")
                            assert all(
                                (item["left"]["right"] <= item["right"]["left"] + 1
                                 or item["left"]["bottom"] <= item["right"]["top"] + 1)
                                and item["right"]["right"] <= item["row"]["right"] + 1
                                for item in row_geometry
                            ), (theme, width, row_geometry)
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
                            if (category in ("agent", "theme") and width in (390, 1440)
                                    and position == 0):
                                shot = await tab.command(
                                    "Page.captureScreenshot", {"format": "png"}
                                )
                                (OUT / f"{category}-top-{theme}-{width}.png").write_bytes(
                                    base64.b64decode(shot["data"])
                                )
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
                                assert result["docked"] and result["orientation"] == "vertical", (
                                    result
                                )
                                assert result["reserved"] and result["actionsFit"], result
                                assert abs(result["dock"]["left"] - result["main"]["left"]) < 1, (
                                    result
                                )
                                assert abs(result["dock"]["right"] - result["main"]["right"]) < 1, (
                                    result
                                )
                                assert (
                                    abs(result["dock"]["bottom"] - result["main"]["bottom"]) < 1
                                ), result
                                if result["end"]:
                                    assert result["contentEnd"] <= result["dock"]["top"] + 1, result
                            if result["end"]:
                                assert result["contentEnd"] <= result["dock"]["top"] - 24, result
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
            # The image-service subscreen owns a separate draft and dock.
            await tab.js("showSettingsSection('models'); ModelsSettingsNavigation.show('image')")
            await tab.js("""{const field=byId('image-service-url');
              field.value='http://127.0.0.1:1235';field.dispatchEvent(new Event('input'));
              const provider=byId('image-service-provider');
              provider.value='ollama';provider.dispatchEvent(new Event('change'));}""")
            await tab.wait(
                "!byId('image-service-save-bar').hidden && "
                "byId('image-service-save-bar').parentElement===byId('settings-action-dock')"
            )
            for width, height in ((320, 568), (390, 430), (768, 1024), (851, 700), (1440, 900)):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": width <= 560,
                    },
                )
                await asyncio.sleep(0.15)
                await tab.js("byId('settings-view').scrollTop=byId('settings-view').scrollHeight")
                await asyncio.sleep(0.1)
                image_layout = await tab.js(MEASURE)
                assert await tab.js("""(() => {
                  const group=byId('image-service-save'), bounds=group.getBoundingClientRect();
                  return [...group.querySelectorAll(':scope > .setting-row')]
                    .filter(row=>row.getClientRects().length).every((row,i)=>{
                      const r=row.getBoundingClientRect(), style=getComputedStyle(row);
                      return Math.abs(r.left-bounds.left-1)<1.5 &&
                        Math.abs(bounds.right-r.right-1)<1.5 &&
                        parseFloat(style.borderTopWidth)===(i ? 1 : 0) &&
                        parseFloat(style.paddingLeft)>=16;
                    });
                })()"""), width
                assert image_layout["barId"] == "image-service-save-bar", image_layout
                assert image_layout["end"] and image_layout["contentEnd"] <= (
                    image_layout["dock"]["top"] - 24
                ), image_layout
            await tab.click("#image-service-discard")
            await tab.js("ModelsSettingsNavigation.show('overview')")

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
                "showSettingsSection('agent');byId('agent-group-research').open=true;"
                "byId('setting-research-context_tokens').focus()"
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
            # Clean pages must also leave room below their last visible option.
            for width, height in ((320, 380), (390, 430), (768, 1024), (851, 700), (1440, 900)):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": width <= 560,
                    },
                )
                for category in ("agent", "models", "image", "theme", "memory"):
                    if category == "image":
                        await tab.js(
                            "showSettingsSection('models'); ModelsSettingsNavigation.show('image')"
                        )
                    else:
                        await tab.js("showSettingsSection(" + json.dumps(category) + ")")
                        if category == "models":
                            await tab.js("ModelsSettingsNavigation.show('overview')")
                    await asyncio.sleep(0.1)
                    await tab.js(
                        "byId('settings-view').scrollTop=byId('settings-view').scrollHeight"
                    )
                    await asyncio.sleep(0.1)
                    gap = await tab.js("""(() => {
                      const view=byId('settings-view'), panel=view.querySelector(
                        '[role=tabpanel]:not([hidden])');
                      const elements=[...panel.querySelectorAll(
                        'input,select,textarea,button,summary')]
                        .filter(el=>{
                          const closed=el.closest('details:not([open])');
                          return el.getClientRects().length && !el.closest('[hidden]') &&
                            (!closed || el.tagName==='SUMMARY' && el.parentElement===closed);
                        });
                      const last=Math.max(0,...elements.map(el=>el.getBoundingClientRect().bottom));
                      return {gap:view.getBoundingClientRect().bottom-last,
                        end:view.scrollHeight-view.scrollTop-view.clientHeight<2,
                        dock:byId('settings-action-dock').hidden,
                        fits:document.documentElement.scrollWidth<=innerWidth};
                    })()""")
                    assert gap["end"] and gap["dock"] and gap["fits"] and gap["gap"] >= 24, (
                        width,
                        category,
                        gap,
                    )
            await tab.js("showSettingsSection('theme')")
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
                "desktop_page_dock": True,
                "image_service_clearance": True,
                "clean_page_clearance": True,
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

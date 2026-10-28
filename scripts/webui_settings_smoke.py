"""Isolated Chrome checks for Settings tabs, history, drafts and staged saves.

Run: .venv/bin/python scripts/webui_settings_smoke.py
No external models or real-profile settings are used.
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
from unittest.mock import patch
from urllib.request import Request, urlopen

import websockets
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_core.memory import Memory
from klaude_core.settings_store import update_settings
from klaude_tools.toolkit import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402


async def verify_chat_density(tab, output):
    assert await tab.js("byId('settings-tab-theme').textContent.trim()==='Theme' && "
                       "byId('theme-settings').querySelector('h2').textContent.trim()==='Theme'")
    assert await tab.js("appearance.chatDensity==='compact' && "
                       "document.documentElement.dataset.chatDensity==='compact'")
    # Existing device preferences gain Compact unless a density was saved, without
    # losing their selected palette, color mode or reduced-motion preference.
    assert await tab.js("""(()=>{
      const old={version:1,theme:'dark',palette:'sage',reduced:true};
      const migrated=readAppearance(JSON.stringify(old));
      const invalid=readAppearance(JSON.stringify({...old,chatDensity:'invalid'}));
      const saved=readAppearance(JSON.stringify({...old,chatDensity:'comfortable'}));
      return readAppearance(null).chatDensity==='compact' &&
        migrated.chatDensity==='compact' && migrated.theme==='dark' &&
        migrated.palette==='sage' && migrated.reduced && invalid.chatDensity==='compact' &&
        saved.chatDensity==='comfortable';
    })()""")
    await tab.click('input[name="chat-density"][value="comfortable"]')
    assert await tab.js("document.documentElement.dataset.chatDensity==='comfortable' && "
                       "appearance.chatDensity==='compact' && !byId('theme-save-bar').hidden")
    await tab.click('input[name="chat-density"][value="compact"]')
    assert await tab.js("byId('theme-save-bar').hidden")
    await tab.click('input[name="chat-density"][value="comfortable"]')
    await tab.click("#theme-reset")
    assert await tab.js("document.documentElement.dataset.chatDensity==='compact' && "
                       "byId('theme-save-bar').hidden")
    # Failed device storage keeps the saved baseline and leaves preview discardable.
    await tab.js("""window.densityStorageSave=Storage.prototype.setItem;
      Storage.prototype.setItem=function(key,value) {
        if(key===preferenceKey) throw new Error('Fixture storage unavailable');
        return densityStorageSave.call(this,key,value);
      };""")
    await tab.click('input[name="chat-density"][value="comfortable"]')
    await tab.click("#theme-apply")
    assert await tab.js("appearance.chatDensity==='compact' && "
                       "byId('theme-status').textContent.includes('Could not save') && "
                       "!byId('theme-save-bar').hidden")
    await tab.js("Storage.prototype.setItem=densityStorageSave")
    await tab.click("#theme-reset")
    await tab.click('input[name="chat-density"][value="comfortable"]')
    await tab.click("#theme-apply")
    assert await tab.js("appearance.chatDensity==='comfortable' && "
                       "JSON.parse(localStorage.getItem(preferenceKey))"
                       ".chatDensity==='comfortable' && "
                       "byId('theme-save-bar').hidden")
    await tab.click("#settings-tab-agent")
    await tab.click("#settings-tab-theme")
    assert await tab.js("document.querySelector('input[name=\"chat-density\"]:checked')"
                       ".value==='comfortable'")
    # Render the actual chat components with local sample text, without inference.
    paragraph = ("Keep the conversation easy to scan while leaving enough room for the details. "
                 "Compact spacing should show more text while keeping the same readable "
                 "font size. ")
    text = ("## A readable conversation\n\n" + paragraph * 4 + "\n\n" + paragraph * 3
            + "\n\n### Details\n\n- Keep clear headings.\n- Preserve readable text.\n"
              "- Keep action buttons easy to use.\n\n```python\n"
              "def describe_view(density):\n    return {\n        'density': density,\n"
              "        'readable': True,\n"
              "        'text': 'A long line stays inside its code block',\n"
              "    }\n```\n\n| View | Spacing |\n| --- | --- |\n"
              "| Comfortable | More room |\n| Compact | More text |\n")
    # Rebuild the sample in each synchronous measurement: an automatic snapshot
    # may otherwise restore the fixture host's empty conversation between cases.
    await tab.js("showView('chat');window.renderDensityFixture=()=>{"
                 "byId('welcome').hidden=true;messages.replaceChildren(ChatMarkdown.create('user',"
                 "'Show the same conversation with less empty space.','density-user'),"
                 "ChatMarkdown.create('assistant'," + json.dumps(text) + ", 'density-reply'));"
                 "chatScroller.scrollTop=0;};renderDensityFixture()")
    cases = []
    for theme in ("light", "dark"):
        for width in (320, 390, 768, 1440):
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": 844, "deviceScaleFactor": 1, "mobile": width < 600,
            })
            measurements = {}
            for density in ("comfortable", "compact"):
                await tab.js("applyAppearance({...appearance,theme:" + json.dumps(theme)
                             + ",chatDensity:" + json.dumps(density) + ",reduced:true},true);"
                             "chatScroller.scrollTop=0;document.fonts.ready")
                await tab.js("new Promise(resolve=>requestAnimationFrame("
                             "()=>requestAnimationFrame(resolve)))")
                measurements[density] = await tab.js("""(()=>{
                  renderDensityFixture();
                  const articles=[...messages.querySelectorAll('.message')];
                  const body=articles[1].querySelector('.message-body');
                  return {height:articles[1].getBoundingClientRect().bottom-
                    articles[0].getBoundingClientRect().top,
                    font:parseFloat(getComputedStyle(body).fontSize),
                    leading:parseFloat(getComputedStyle(body).lineHeight),
                    codeFont:parseFloat(getComputedStyle(body.querySelector('pre')).fontSize),
                    fits:messages.scrollWidth<=messages.clientWidth &&
                      document.documentElement.scrollWidth<=innerWidth,
                    targets:[...messages.querySelectorAll('button')].every(button=>
                      button.getBoundingClientRect().height>=44)};
                })()""")
                if width in (390, 1440):
                    capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"{theme}-{width}-{density}-chat.png").write_bytes(
                        base64.b64decode(capture["data"])
                    )
            comfortable, compact = measurements["comfortable"], measurements["compact"]
            assert compact["height"] < comfortable["height"] * .92, measurements
            assert compact["font"] == comfortable["font"] == 15, measurements
            assert compact["codeFont"] == comfortable["codeFont"], measurements
            assert compact["leading"] < comfortable["leading"], measurements
            assert all(item["fits"] and item["targets"] for item in measurements.values()), (
                theme, width, measurements
            )
            cases.append({"theme": theme, "width": width, **measurements})
    await tab.js("delete window.renderDensityFixture;applyAppearance(appearance,true);"
                 "showView('settings',{section:'theme'})")
    await tab.command("Page.reload")
    await tab.wait("typeof authenticated!=='undefined' && authenticated && latest?.session_id && "
                   "currentView==='settings' && settingsSection==='theme' && "
                   "document.documentElement.dataset.chatDensity==='comfortable'")
    assert await tab.js("document.querySelector('input[name=\"chat-density\"]:checked')"
                       ".value==='comfortable'")
    return cases


async def verify(host, root, chrome, password):
    profile = root / "chrome"
    process = subprocess.Popen([
        chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    output = Path("/tmp/klaude-settings-tabs")
    output.mkdir(exist_ok=True)
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"]) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            # New HTML can be served by a host whose fixed route allowlist
            # predates the draft module. Also test without structuredClone.
            await tab.command("Network.enable")
            await tab.command("Network.setBlockedURLs", {"urls": ["*/settings.js"]})
            await tab.command("Page.addScriptToEvaluateOnNewDocument", {
                "source": "delete window.structuredClone;",
            })
            await tab.command("Page.navigate", {
                "url": host.origin if password else host.bootstrap_url,
            })
            if password:
                await tab.wait("typeof byId !== 'undefined' && !byId('local-access').hidden")
                await tab.js('byId("login-username").value="admin";byId("login-password").value=' + json.dumps(
                    host.accounts.initial_password()
                ) + ';byId("account-login").requestSubmit()')
            await tab.wait("typeof latest !== 'undefined' && latest?.session_id && authenticated")
            await tab.js("showView('settings')")
            await tab.wait("Boolean(byId('default-value-chat')) && "
                           "Boolean(byId('agent-settings-fields').querySelector('form'))")
            assert await tab.js("typeof structuredClone==='undefined' && "
                               "!document.querySelector('script[src=\"/settings.js\"]') && "
                               "typeof SettingsDrafts==='object'")
            await tab.js("document.fonts.ready")
            assert await tab.js("""[...document.querySelectorAll('[data-refresh-icon]')]
              .every(button=>button.textContent.trim()==='' && button.title &&
                button.getAttribute('aria-label') && button.querySelectorAll('svg').length===1)
            """)
            assert await tab.js("byId('agent-group-runtime_options').open && "
                               "byId('agent-group-time_settings').open && "
                               "!byId('agent-group-tools_permissions').open && "
                               "!byId('model-fallbacks').open")
            assert await tab.js("!byId('agent-group-permissions') && "
                               "!byId('agent-group-tool_availability') && "
                               "byId('agent-group-tools_permissions').querySelector('summary')"
                               ".textContent.trim()==='Tools & Permissions'")
            assert await tab.js("""[...document.querySelectorAll('[data-agent-tool]')]
              .length===12 && [...document.querySelectorAll('[data-agent-tool]')].every(card=>{
                const toggle=card.querySelector('.tool-availability-form input');
                const policy=card.querySelector('.tool-policy-form');
                const choices=[...policy.querySelectorAll('input[type=radio]')];
                return toggle && policy && card.querySelector('.tool-permission-label svg') &&
                  document.querySelector(`label[for="${toggle.id}"]`) &&
                  policy.tagName==='FIELDSET' && policy.querySelector('legend').textContent &&
                  choices.length===3 && choices.every(input=>
                    document.querySelector(`label[for="${input.id}"]`)) &&
                  choices.map(input=>input.value).join(',')==='allow,ask,deny' &&
                  [...policy.querySelectorAll('label span')].map(span=>span.textContent)
                    .join(',')==='Automatic,Ask first,Deny' &&
                  choices.filter(input=>input.checked).length===1 &&
                  !card.querySelector('select,.tool-toggle-state');
              }) && !byId('setting-permissions-run_shell') &&
              !byId('setting-tool_availability-write_file')
            """)
            assert await tab.js("byId('setting-time_settings-timezone').value==='auto' && "
                               "Boolean(byId(byId('setting-time_settings-timezone')"
                               ".getAttribute('aria-describedby'))) && "
                               "[...byId('setting-time_settings-timezone').options]"
                               ".some(option=>option.value==='Asia/Phnom_Penh')")
            assert await tab.js("settingsSection === " + json.dumps(
                "account" if password else "theme"
            ))
            sections = ["account", "theme", "agent", "models", "memory"]
            assert await tab.js("!byId('settings-tab-images')")
            if not password:
                sections.remove("account")
                assert await tab.js("byId('settings-tab-account').hidden")

            layouts = []
            for theme in ("light", "dark"):
                await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                for width in (320, 390, 768, 850, 851, 1024, 1440, 1920, 2560):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": 568 if width == 320 else 844,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    })
                    await asyncio.sleep(.15)
                    for section in sections:
                        await tab.click(f"#settings-tab-{section}")
                        state = await tab.js("""(() => {
                          const view=byId('settings-view'), tabs=byId('settings-sections');
                          const selected=tabs.querySelector('[aria-selected=true]');
                          const panels=[...view.querySelectorAll('[role=tabpanel]')]
                            .filter(p=>!p.hidden);
                          const r=selected.getBoundingClientRect();
                          const nav=tabs.getBoundingClientRect();
                          const panel=panels[0].getBoundingClientRect();
                          const bounds=view.getBoundingClientRect();
                          const main=byId('main-content').getBoundingClientRect();
                          const style=getComputedStyle(view);
                          const left=bounds.left+parseFloat(style.paddingLeft);
                          const right=bounds.left+view.clientWidth-parseFloat(style.paddingRight);
                          const vertical=innerWidth>=851;
                          const buttons=[...tabs.querySelectorAll('[role=tab]')]
                            .filter(tab=>!tab.hidden).map(tab=>tab.getBoundingClientRect());
                          return {fits:view.scrollWidth<=view.clientWidth &&
                            document.documentElement.scrollWidth<=innerWidth,
                            orientation:tabs.getAttribute('aria-orientation')===
                              (vertical?'vertical':'horizontal'),
                            placement:vertical ? nav.right<=panel.left-12 &&
                              buttons.every((r,i)=>Math.abs(r.left-nav.left)<1 &&
                                (!i || r.top>=buttons[i-1].bottom+5)) :
                              nav.bottom<=panel.top+1,
                            fills:Math.abs(bounds.left-main.left)<1 &&
                              Math.abs(bounds.right-main.right)<1 &&
                              Math.abs(panel.right-right)<1 &&
                              Math.abs((vertical?nav.left:panel.left)-left)<1,
                            padding:parseFloat(style.paddingLeft)>=16 &&
                              parseFloat(style.paddingLeft)<=24,
                            panels:panels.length,linked:panels[0]?.id===selected.getAttribute('aria-controls'),
                            tabbable:tabs.querySelectorAll('[tabindex="0"]').length,
                            target:r.height>=43.9 && r.left>=nav.left-1 && r.right<=nav.right+1,
                            bounds:[r.left,r.right,r.height,nav.left,nav.right]};
                        })()""")
                        assert (all(state[key] for key in (
                            "fits", "linked", "target", "orientation", "placement",
                            "fills", "padding",
                        ))
                                and state["panels"] == state["tabbable"] == 1), (
                                    theme, width, section, state
                                )
                        if section == "models":
                            assert await tab.js(
                                "byId('image-service-settings').getBoundingClientRect().top - "
                                "byId('model-default-settings').getBoundingClientRect().bottom "
                                ">=12 && "
                                "byId('image-service-settings').getBoundingClientRect().top - "
                                "byId('model-default-settings').getBoundingClientRect().bottom "
                                "<=20"
                            )
                        # Measure expanded sections too; hidden rows must not hide
                        # the original control/Review wrapping failure from this gate.
                        density = await tab.js("""(async () => {
                          const panel=byId('settings-view').querySelector(
                            '[role=tabpanel]:not([hidden])');
                          const sections=[...panel.querySelectorAll('details.settings-disclosure')];
                          const open=sections.map(section=>section.open);
                          const defaultHeight=panel.getBoundingClientRect().height;
                          sections.forEach(section=>section.open=true);
                          await new Promise(resolve=>requestAnimationFrame(
                            ()=>requestAnimationFrame(resolve)));
                          const failures=[...panel.querySelectorAll('.settings-controls')]
                            .flatMap(controls=>{
                              const input=controls.querySelector(
                                'input:not([type=checkbox]),select');
                              const button=controls.querySelector('button');
                              if(!input || !button) return [];
                              const a=input.getBoundingClientRect();
                              const b=button.getBoundingClientRect();
                              const row=controls.closest('.setting-row').getBoundingClientRect();
                              return a.width<60 || b.top>=a.bottom || a.top>=b.bottom ||
                                b.right>row.right+1 || a.left<row.left-1 ?
                                [{id:input.id,input:a.toJSON(),button:b.toJSON(),
                                  row:row.toJSON()}] : [];
                            });
                          const overflowing=panel.scrollWidth>panel.clientWidth;
                          const rowHeights=[...panel.querySelectorAll('.setting-row')]
                            .map(row=>row.getBoundingClientRect().height);
                          const expandedHeight=panel.getBoundingClientRect().height;
                          const switches=[...panel.querySelectorAll('.switch')].every(toggle=>{
                            const r=toggle.getBoundingClientRect();
                            return r.height>=44 && r.width>=44;
                          });
                          let toolSegments=true;
                          if(panel.id==='agent-settings') {
                            const contentWidth=panel.clientWidth-
                              parseFloat(getComputedStyle(panel).paddingInlineStart)*2;
                            const columns=innerWidth>768 && contentWidth>=496 ? 2 : 1;
                            toolSegments=[...panel.querySelectorAll('.tool-permission-list')]
                              .every(list=>{
                                const policies=[...list.querySelectorAll('.tool-policy-form')];
                                return getComputedStyle(list).gridTemplateColumns
                                  .split(' ').length===columns &&
                                  policies.every((policy,index)=>columns===1 || index%2===0 ||
                                    Math.abs(policy.getBoundingClientRect().top-
                                      policies[index-1].getBoundingClientRect().top)<1);
                              }) &&
                              [...panel.querySelectorAll('[data-agent-tool]')].every(card=>{
                                const style=getComputedStyle(card);
                                const name=card.querySelector('.tool-permission-label')
                                  .getBoundingClientRect();
                                const toggle=card.querySelector('.switch').getBoundingClientRect();
                                return style.borderRadius==='0px' &&
                                  style.backgroundColor==='rgba(0, 0, 0, 0)' &&
                                  name.right<=toggle.left && name.top<toggle.bottom &&
                                  name.bottom>toggle.top &&
                                  [...card.querySelectorAll('.tool-policy-form label span')]
                                    .every(segment=>{
                                      const r=segment.getBoundingClientRect();
                                      return r.width>=44 && r.height>=44 &&
                                        segment.scrollWidth<=segment.clientWidth;
                                    });
                              });
                          }
                          const cards=panel.matches('.theme-settings') ? [panel] :
                            [...panel.querySelectorAll('.theme-settings')];
                          const cardHeights=cards.map(card=>card.getBoundingClientRect().height);
                          const controlled=[...panel.querySelectorAll('.settings-controls')]
                            .every(controls=>controls.getBoundingClientRect().width<=512.5);
                          const panelWidth=panel.getBoundingClientRect().width;
                          let roleIcons=true;
                          if(panel.id==='models-settings') {
                            const paths=new Set();
                            roleIcons=['chat','utility','research','vision'].every(role=>{
                              const input=byId(`default-value-${role}`);
                              const label=panel.querySelector(`label[for="${input.id}"]`);
                              const icon=label.querySelector('svg');
                              const text=label.querySelector('span');
                              if(!icon || !text) return false;
                              const a=icon.getBoundingClientRect(), b=text.getBoundingClientRect();
                              const row=label.closest('.setting-row').getBoundingClientRect();
                              paths.add(icon.querySelector('path').getAttribute('d'));
                              return icon.getAttribute('aria-hidden')==='true' &&
                                label.textContent.trim() && a.width===18 && a.height===18 &&
                                Math.abs(b.left-a.right-8)<1 &&
                                Math.abs(a.top+a.height/2-b.top-b.height/2)<1 &&
                                a.left>=row.left && b.right<=row.right+1;
                            }) && paths.size===4;
                          }
                          let compact=true;
                          if(panel.id==='agent-settings') {
                            const grid=byId('agent-group-runtime_options')
                              .querySelector('.settings-group-body');
                            const rows=[...grid.children].map(row=>row.getBoundingClientRect());
                            compact=grid.clientWidth>=496 ? Math.abs(rows[0].top-rows[1].top)<1 :
                              rows[1].top>=rows[0].bottom;
                            compact &&= [...grid.querySelectorAll('input')].every(input=>
                              input.getBoundingClientRect().width<=113);
                          }
                          if(panel.id==='theme-settings') {
                            const swatches=[...panel.querySelectorAll('.palette-swatch')]
                              .map(swatch=>swatch.getBoundingClientRect());
                            const rows=new Set(swatches.map(r=>Math.round(r.top))).size;
                            const columns=panel.querySelector('.theme-studio-controls')
                              .clientWidth>=568 ? 8 : 4;
                            compact=rows===Math.ceil(swatches.length/columns) &&
                              swatches.every(r=>r.width===44 && r.height===44);
                          }
                          sections.forEach((section,index)=>section.open=open[index]);
                          return {failures,overflowing,switches,rowHeights,
                            defaultHeight,expandedHeight,cardHeights,panelWidth,
                            controlled,roleIcons,compact,toolSegments};
                        })()""")
                        assert (not density["failures"] and not density["overflowing"]
                                and density["toolSegments"]
                                and density["switches"] and density["controlled"]
                                and density["compact"] and density["roleIcons"]), (
                            theme, width, section, density
                        )
                        if theme == "light" and width in (390, 1440):
                            # Taller windows must not stretch cards or their controls.
                            measure_cards = """[...byId('settings-view').querySelectorAll(
                              '.theme-settings')].filter(card=>card.getClientRects().length)
                              .map(card=>card.getBoundingClientRect().height)"""
                            before = await tab.js(measure_cards)
                            await tab.command("Emulation.setDeviceMetricsOverride", {
                                "width": width, "height": 1144, "deviceScaleFactor": 1,
                                "mobile": width < 600,
                            })
                            after = await tab.js(measure_cards)
                            assert before == after, (
                                "card stretching", width, section, before, after,
                            )
                            await tab.command("Emulation.setDeviceMetricsOverride", {
                                "width": width, "height": 844, "deviceScaleFactor": 1,
                                "mobile": width < 600,
                            })
                        layouts.append({"theme": theme, "width": width,
                                        "section": section, **density})
                        if password and width in (390, 1440, 2560):
                            await tab.js("Promise.all([...byId('settings-view').getAnimations(),"
                                         "...byId('settings-sections').getAnimations({subtree:true})]"
                                         ".map(a=>a.finished.catch(()=>{})))")
                            capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                            (output / f"{theme}-{width}-{section}.png").write_bytes(
                                base64.b64decode(capture["data"])
                            )
                            if section == "agent" and width in (390, 1440):
                                await tab.js("""(() => {
                                  const view=byId('settings-view');
                                  const tools=byId('agent-group-tools_permissions');
                                  tools.open=true;
                                  const inset=innerWidth<851 ?
                                    byId('settings-sections').offsetHeight+12 : 8;
                                  view.scrollTop+=tools.getBoundingClientRect().top-
                                    view.getBoundingClientRect().top-inset;
                                })()""")
                                await asyncio.sleep(.1)
                                capture = await tab.command("Page.captureScreenshot", {
                                    "format": "png",
                                })
                                (output / f"{theme}-{width}-tools.png").write_bytes(
                                    base64.b64decode(capture["data"])
                                )
                                await tab.js("byId('agent-group-tools_permissions').open=false;"
                                             "byId('settings-view').scrollTop=0")

            # Keyboard direction follows the live orientation; resizing keeps
            # the active category, linked panel and unsaved draft.
            await tab.js("byId('default-output-tokens').value='384';"
                         "byId('default-output-tokens').dispatchEvent(new Event('input'))")
            for width in (390, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 844, "deviceScaleFactor": 1,
                    "mobile": width < 600,
                })
                await tab.wait("byId('settings-sections').getAttribute('aria-orientation')==="
                               + json.dumps("vertical" if width >= 851 else "horizontal"))
                await tab.js("byId('settings-tab-memory').focus()")
                for key, section in (
                    ("Home", sections[0]),
                    ("ArrowDown" if width >= 851 else "ArrowRight", sections[1]),
                    ("End", "memory"),
                    ("ArrowUp" if width >= 851 else "ArrowLeft", "models"),
                ):
                    await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": key})
                    assert await tab.js(f"settingsSection==={json.dumps(section)} && "
                                        f"document.activeElement===byId('settings-tab-{section}')")
                assert await tab.js("byId('default-output-tokens').value==='384'")
            await tab.click("#settings-tab-agent")
            assert await tab.js("""(async () => {
              const view=byId('settings-view');
              const groups=[...byId('agent-settings').querySelectorAll('details')];
              const open=groups.map(group=>group.open);
              groups.forEach(group=>group.open=true);
              view.scrollTop=view.scrollHeight;
              await new Promise(resolve=>requestAnimationFrame(resolve));
              const nav=byId('settings-sections').getBoundingClientRect();
              const bounds=view.getBoundingClientRect();
              const visible=view.scrollTop>0 && nav.top>=bounds.top-1 &&
                nav.bottom<=bounds.bottom+1;
              groups.forEach((group,index)=>group.open=open[index]);
              view.scrollTop=0;
              return visible;
            })()""")
            await tab.click("#settings-tab-theme")
            assert await tab.js("byId('theme-save-bar').hidden")
            await tab.click('input[name="palette"][value="sage"]')
            assert await tab.js("byId('theme-status').textContent==='Preview · not saved'")
            await tab.click("#theme-reset")
            assert await tab.js("byId('theme-status').textContent==="
                                "'Preview discarded' && byId('theme-save-bar').hidden")
            await tab.click('input[name="palette"][value="sage"]')
            assert await tab.js("!byId('theme-save-bar').hidden")
            await tab.click("#theme-apply")
            assert await tab.js("byId('theme-status').textContent==='Saved on this device' && "
                                "byId('theme-save-bar').hidden")
            await tab.click('input[name="palette"][value="peach"]')
            await tab.click("#theme-reset")
            assert await tab.js("document.documentElement.dataset.palette==='sage' && "
                               "appearance.palette==='sage'")
            density_layouts = await verify_chat_density(tab, output)
            await tab.click("#settings-tab-memory")
            await tab.js("history.back()")
            await tab.wait("settingsSection==='theme'")
            await tab.js("history.forward()")
            await tab.wait("settingsSection==='memory'")
            await tab.command("Page.reload")
            await tab.wait("typeof authenticated!=='undefined' && authenticated && "
                           "currentView==='settings' && settingsSection==='memory' && "
                           "latest?.session_id")
            await tab.js("prompt.value='Unsent chat';showView('chat')")
            assert await tab.js("!new URLSearchParams(location.search).has('settings')")
            await tab.js("showView('settings')")
            assert await tab.js("settingsSection==='memory' && prompt.value==='Unsent chat'")
            await tab.wait("!byId('memory-auto').disabled")

            # Reviews still reach their existing service and owned worker.
            await tab.js("byId('memory-fact').value='Settings tabs fixture';"
                         "byId('memory-add').requestSubmit()")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait("byId('memory-items').textContent.includes('Settings tabs fixture') && "
                           "!BrowserManagement.hasPending()")
            await tab.click("#settings-tab-agent")
            await tab.wait("Boolean(byId('setting-runtime_options-max_steps'))")
            # Timezone and execution drafts survive navigation and save together.
            await tab.js("byId('setting-time_settings-timezone').value='Asia/Phnom_Penh';"
                         "byId('setting-time_settings-timezone')"
                         ".dispatchEvent(new Event('change'));"
                         "byId('setting-runtime_options-max_steps').value='7';"
                         "byId('setting-runtime_options-max_steps')"
                         ".dispatchEvent(new Event('input'))")
            await tab.click("#settings-tab-models")
            await tab.js("byId('image-service-url').value='http://127.0.0.1:1234';"
                         "byId('image-service-url').dispatchEvent(new Event('input'))")
            await tab.click("#settings-tab-agent")
            assert await tab.js("byId('setting-time_settings-timezone')"
                               ".value==='Asia/Phnom_Penh' && "
                               "byId('setting-runtime_options-max_steps').value==='7' && "
                               "byId('agent-unsaved-count').textContent==='2 unsaved changes'")
            await tab.click("#agent-save")
            await tab.wait("byId('agent-save-bar').hidden")
            saved = await tab.js("domainRequest('/api/v1/settings/agent','GET')")
            assert next(field for field in saved["fields"]
                        if field["id"] == "time_settings.timezone")["value"] == "Asia/Phnom_Penh"
            assert next(field for field in saved["fields"]
                        if field["id"] == "runtime_options.max_steps")["value"] == 7
            # Keyboard disclosure and independent staged availability/policy.
            await tab.js("byId('agent-group-tools_permissions').querySelector('summary').focus()")
            for kind in ("keyDown", "keyUp"):
                await tab.command("Input.dispatchKeyEvent", {
                    "type": kind, "key": "Enter", "code": "Enter",
                    "windowsVirtualKeyCode": 13,
                    **({"text": "\r"} if kind == "keyDown" else {}),
                })
            assert await tab.js("byId('agent-group-tools_permissions').open")
            await tab.click("#setting-permissions-read_file-deny")
            await tab.click("#agent-save")
            await tab.wait("byId('agent-save-bar').hidden")
            await tab.click("#setting-tool_availability-read_file")
            assert await tab.js("!byId('setting-tool_availability-read_file').checked && "
                               "byId('setting-permissions-read_file').disabled && "
                               "[...byId('setting-permissions-read_file').querySelectorAll('input')]"
                               ".every(input=>input.matches(':disabled')) && "
                               "!reviewDialog.open")
            await tab.js("byId('setting-permissions-read_file-allow').click()")
            assert await tab.js("byId('setting-permissions-read_file-deny').checked && "
                               "SettingsDrafts.value('agent','permissions.read_file')==='deny'")
            await tab.click("#agent-discard")
            assert await tab.js("byId('setting-tool_availability-read_file').checked && "
                               "byId('setting-permissions-read_file-deny').checked")
            await tab.click("#setting-tool_availability-read_file")
            await tab.click("#agent-save")
            await tab.wait("byId('agent-save-bar').hidden")
            await tab.click("#setting-tool_availability-read_file")
            await tab.click("#agent-save")
            await tab.wait("byId('settings-security')?.open")
            await tab.click("#settings-security-confirm")
            await tab.wait("byId('agent-save-bar').hidden")
            assert await tab.js("byId('setting-permissions-read_file-deny').checked")
            await tab.js("byId('agent-group-advanced_permissions').open=true")
            await tab.click("#tool-workspace-settings")
            assert await tab.js("currentView==='workspace'")
            await tab.js("showView('settings',{section:'agent'})")
            await tab.wait("byId('agent-group-tools_permissions').open")
            await tab.click("#tool-mcp-settings")
            assert await tab.js("currentView==='integrations' && "
                                "integrationSection==='connections'")
            await tab.js("showView('settings',{section:'agent'})")
            await tab.wait("byId('agent-group-tools_permissions').open")
            await tab.click("#settings-tab-models")
            await tab.click("#model-fallbacks > summary")
            await tab.js("byId('default-value-fallbacks-0').value='';"
                         "byId('default-value-fallbacks-0').dispatchEvent(new Event('change'))")
            await tab.click("#settings-tab-agent")
            assert await tab.js("byId('agent-group-tools_permissions').open")
            await tab.click("#settings-tab-models")
            fallback_draft = await tab.js("({open:byId('model-fallbacks').open, "
                                          "value:byId('default-value-fallbacks-0').value})")
            assert fallback_draft == {"open": True, "value": ""}, fallback_draft
            await tab.click("#model-fallbacks > summary")
            await tab.js("byId('default-output-tokens').value='256';"
                         "byId('default-output-tokens').dispatchEvent(new Event('input'))")
            assert await tab.js("!byId('models-save-bar').hidden && !reviewDialog.open")
            await tab.click("#models-discard")
            assert await tab.js("byId('models-save-bar').hidden")

            # A preparation finishing after a tab change must discard its review.
            await tab.click("#settings-tab-memory")
            await tab.js("""window.settingsFetch=fetch.bind(window);window.settingsDiscards=0;
              window.fetch=(input,options)=>{
                if(String(input).endsWith('/library/discard')) settingsDiscards++;
                return String(input).endsWith('/library/review') ?
                  new Promise(resolve=>{window.releaseSettingsReview=()=>
                    resolve(settingsFetch(input,options));}) : settingsFetch(input,options);
              };
              byId('memory-fact').value='Discard this';byId('memory-add').requestSubmit();
            """)
            await tab.wait("typeof releaseSettingsReview==='function'")
            await tab.click("#settings-tab-theme")
            await tab.click("#settings-tab-memory")
            await tab.js("releaseSettingsReview()")
            await tab.wait("settingsDiscards>0")
            assert await tab.js("!reviewDialog.open")
            await tab.js("window.fetch=settingsFetch")

            # Old Images links and stored selections now open Models.
            for query in ("?view=settings&settings=images", "?view=settings"):
                await tab.js("saveNavigationChoice('settings-section','images');"
                             "history.replaceState(null,''," + json.dumps(query) + ")")
                await tab.command("Page.reload")
                await tab.wait("typeof authenticated!=='undefined' && authenticated && "
                               "currentView==='settings' && settingsSection==='models' && "
                               "latest?.session_id")
                assert await tab.js("!byId('models-settings').hidden && "
                                    "byId('image-service-save').getClientRects().length>0 && "
                                    "new URLSearchParams(location.search)"
                                    ".get('settings')!=='images'")

            if password:
                await tab.wait("document.documentElement.dataset.startup==='ready'")
                await tab.click("#account-shortcut")
                assert await tab.js("settingsSection==='account' && "
                                    "!byId('account-settings').hidden && "
                                    "document.activeElement===byId('account-heading')")
                await tab.js("byId('current-password').value='Private draft'")
                await tab.click("#settings-tab-theme")
                assert await tab.js("!byId('current-password').value")
                await tab.js("showView('chat')")
                await tab.click("#account-shortcut")
                assert await tab.js("settingsSection==='account'")
                await tab.js("byId('new-password').value='Another private draft'")
            else:
                await tab.js("showSettingsSection('account')")
                assert await tab.js("settingsSection==='theme' && byId('account-settings').hidden")
            await tab.click("#logout")
            await tab.wait("!authenticated")
            assert await tab.js("!byId('new-password').value")
            assert not tab.errors, tab.errors
            return {"auth": "password" if password else "bootstrap",
                    "existing_asset_bootstrap_without_structuredClone": "passed",
                    "widths": [320, 390, 768, 850, 851, 1024, 1440, 1920, 2560],
                    "vertical_desktop_horizontal_mobile": "passed",
                    "responsive_keyboard_and_sticky_navigation": "passed",
                    "full_width_natural_heights_bounded_controls": "passed",
                    "execution_grid_palette_role_icons": "passed",
                    "theme_preview_discard_apply": "passed",
                    "appearance_chat_density_preview_discard_apply_reload": "passed",
                    "chat_density_layouts": density_layouts,
                    "expanded_rows_and_review_alignment": "passed",
                    "unified_tools_staged_policy_and_availability": "passed",
                    "advanced_permission_navigation": "passed",
                    "disclosures_switches_drafts": "passed",
                    "timezone_draft_cancel_save": "passed",
                    "layouts": layouts,
                    "tabs": sections, "history_drafts_saves": "passed", "console_errors": 0}
    finally:
        process.terminate()
        process.wait(timeout=10)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    ))
    reports = []
    for password in (True, False):
        with tempfile.TemporaryDirectory(prefix="klaude-settings-tabs-") as folder:
            root = Path(folder)
            config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
            cfg = Config(models={"coder": "fixture"})
            reference = "ollama/a-long-model-name-for-image-and-document-review:latest"
            update_settings(cfg.data_dir / "chat-preferences.json", {
                ("ai_defaults", "chat"): "ollama/qwen3.5:4b",
                ("ai_defaults", "utility"): reference,
                ("ai_defaults", "vision"): reference,
                ("ai_defaults", "fallbacks"): ["ollama/fallback-model:latest"],
            })
            memory = Memory(cfg.memory_file, cfg.sessions_db)
            memory.remember("Use readable labels and keep settings controls together.")
            memory.db.close()
            app = _app(cfg.data_dir)
            app.agent.workdir, app.agent.workspace = root, Workspace(root)
            app.agent.tool_config = cfg
            app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
            accounts = AccountStore(cfg.config_dir) if password else None
            if accounts:
                accounts.initialize()
            host = LocalWebHost(app, accounts=accounts, library=LibraryManagement(cfg, root),
                                staging_dir=root / "staging")
            serving = threading.Thread(target=host.serve_forever, daemon=True)
            serving.start()
            try:
                # Catalog behavior has its own real metadata-service smoke. Keep
                # the layout fixture independent of installed/provider models.
                with patch("klaude_application.browser_media_settings.default_model_catalog",
                           return_value=[]):
                    reports.append(asyncio.run(asyncio.wait_for(
                        verify(host, root, chrome, password), 120
                    )))
            finally:
                host.stop()
                serving.join(3)
    print(json.dumps(reports))


if __name__ == "__main__":
    main()

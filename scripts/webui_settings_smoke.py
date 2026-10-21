"""Isolated Chrome checks for Settings tabs, history, drafts and reviewed saves.

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
            await tab.command("Page.navigate", {
                "url": host.origin if password else host.bootstrap_url,
            })
            if password:
                await tab.wait("typeof byId !== 'undefined' && !byId('local-access').hidden")
                await tab.js('byId("login-password").value=' + json.dumps(
                    host.accounts.initial_password()
                ) + ';byId("account-login").requestSubmit()')
            await tab.wait("typeof latest !== 'undefined' && latest?.session_id && authenticated")
            await tab.js("showView('settings')")
            await tab.wait("Boolean(byId('default-value-chat')) && "
                           "Boolean(byId('agent-settings-fields').querySelector('form'))")
            await tab.js("document.fonts.ready")
            assert await tab.js("""[...document.querySelectorAll('[data-refresh-icon]')]
              .every(button=>button.textContent.trim()==='' && button.title &&
                button.getAttribute('aria-label') && button.querySelectorAll('svg').length===1)
            """)
            assert await tab.js("byId('agent-group-runtime_options').open && "
                               "byId('agent-group-time_settings').open && "
                               "!byId('agent-group-permissions').open && "
                               "!byId('model-fallbacks').open")
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
                            compact=rows===(panel.clientWidth-parseFloat(getComputedStyle(panel)
                              .paddingInlineStart)*2>=568 ? 1 : 2) &&
                              swatches.every(r=>r.width===44 && r.height===44);
                          }
                          sections.forEach((section,index)=>section.open=open[index]);
                          return {failures,overflowing,switches,rowHeights,
                            defaultHeight,expandedHeight,cardHeights,panelWidth,
                            controlled,roleIcons,compact};
                        })()""")
                        assert (not density["failures"] and not density["overflowing"]
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

            # Keyboard direction follows the live orientation; resizing keeps
            # the active category, linked panel and unsaved draft.
            await tab.js("byId('default-output-tokens').value='384'")
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
            await tab.click('input[name="palette"][value="sage"]')
            assert await tab.js("byId('theme-status').textContent==='Preview · not saved'")
            await tab.click("#theme-reset")
            assert await tab.js("byId('theme-status').textContent==="
                                "'Default preview · Apply to save'")
            await tab.click("#theme-apply")
            assert await tab.js("byId('theme-status').textContent==='Saved on this device'")
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
            # Timezone drafts survive category changes; cancellation does not save.
            await tab.js("byId('setting-time_settings-timezone').value='UTC'")
            await tab.click("#settings-tab-models")
            await tab.click("#settings-tab-agent")
            assert await tab.js("byId('setting-time_settings-timezone').value==='UTC'")
            await tab.js("byId('setting-time_settings-timezone').value='Asia/Phnom_Penh';"
                         "byId('setting-time_settings-timezone').closest('form').requestSubmit()")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-cancel")
            await tab.wait("!reviewDialog.open && "
                           "!BrowserManagement.busy('setting:time_settings.timezone')")
            unchanged = await tab.js("domainRequest('/api/v1/settings/agent','GET')")
            assert next(field for field in unchanged["fields"]
                        if field["id"] == "time_settings.timezone")["value"] == "auto"
            await tab.js("byId('setting-time_settings-timezone').closest('form').requestSubmit()")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait("!reviewDialog.open && !BrowserManagement.hasPending() && "
                           "byId('setting-time_settings-timezone').value==='Asia/Phnom_Penh'")
            saved_time = await tab.js("domainRequest('/api/v1/settings/agent','GET')")
            assert next(field for field in saved_time["fields"]
                        if field["id"] == "time_settings.timezone")["value"] == "Asia/Phnom_Penh"
            await tab.js("byId('setting-runtime_options-max_steps').value='7'")
            await tab.click("#settings-tab-models")
            await tab.js("byId('image-service-url').value='http://127.0.0.1:1234'")
            await tab.click("#settings-tab-agent")
            assert await tab.js("byId('setting-runtime_options-max_steps').value==='7'")
            await tab.js("byId('setting-runtime_options-max_steps').closest('form')"
                         ".requestSubmit()")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait("!reviewDialog.open && !BrowserManagement.hasPending()")
            saved = await tab.js("domainRequest('/api/v1/settings/agent','GET')")
            assert next(field for field in saved["fields"]
                        if field["id"] == "runtime_options.max_steps")["value"] == 7
            # Native switches still retain their confirmed state until review.
            await tab.js("byId('agent-group-tool_availability').querySelector('summary').focus()")
            for kind in ("keyDown", "keyUp"):
                await tab.command("Input.dispatchKeyEvent", {
                    "type": kind, "key": "Enter", "code": "Enter",
                    "windowsVirtualKeyCode": 13,
                    **({"text": "\r"} if kind == "keyDown" else {}),
                })
            assert await tab.js("byId('agent-group-tool_availability').open")
            before = await tab.js("byId('setting-tool_availability-read_file').checked")
            await tab.click("#setting-tool_availability-read_file")
            await tab.wait("reviewDialog.open")
            assert await tab.js("byId('setting-tool_availability-read_file').checked") == before
            await tab.click("#domain-review-cancel")
            await tab.wait("!reviewDialog.open")
            assert await tab.js("byId('agent-group-tool_availability').open")
            await tab.click("#settings-tab-models")
            await tab.click("#model-fallbacks > summary")
            await tab.js("byId('default-value-fallbacks-0').value=''")
            await tab.click("#settings-tab-agent")
            assert await tab.js("byId('agent-group-tool_availability').open")
            await tab.click("#settings-tab-models")
            assert await tab.js("byId('model-fallbacks').open && "
                               "byId('default-value-fallbacks-0').value===''")
            await tab.click("#model-fallbacks > summary")
            await tab.js("byId('default-output-tokens').value='256';"
                         "byId('default-output-tokens').closest('form').requestSubmit()")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-cancel")
            await tab.wait("!reviewDialog.open")

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
                    "widths": [320, 390, 768, 850, 851, 1024, 1440, 1920, 2560],
                    "vertical_desktop_horizontal_mobile": "passed",
                    "responsive_keyboard_and_sticky_navigation": "passed",
                    "full_width_natural_heights_bounded_controls": "passed",
                    "execution_grid_palette_role_icons": "passed",
                    "theme_preview_reset_apply": "passed",
                    "expanded_rows_and_review_alignment": "passed",
                    "disclosures_switches_drafts": "passed",
                    "timezone_draft_cancel_save": "passed",
                    "layouts": layouts,
                    "tabs": sections, "history_drafts_reviews": "passed", "console_errors": 0}
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

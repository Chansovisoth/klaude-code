"""Real-host Chrome regression checks for category-scoped Settings drafts.

Run: .venv/bin/python scripts/webui_settings_save_smoke.py
Uses only a temporary profile; no inference or external services.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

import websockets
from klaude_application.image_settings import ImageSettingsUnconfirmed, save_image_settings
from klaude_application.library_management import LibraryManagement
from klaude_application.operation_journal import OperationJournal
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_core.settings_store import read_settings, update_settings
from klaude_tools.toolkit import Workspace
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab
from webui_settings_smoke import _app


async def verify(host, root, cfg, chrome):
    profile = root / "chrome-save"
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
        async with websockets.connect(target["webSocketDebuggerUrl"]) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait("typeof latest!=='undefined' && authenticated && latest?.session_id")
            await tab.wait("document.documentElement.dataset.startup==='ready'")
            await tab.js("showView('settings',{section:'agent'})")
            await tab.wait("Boolean(byId('setting-permissions-read_file'))")
            await tab.js("byId('agent-group-tools_permissions').open=true")
            assert await tab.js("byId('agent-save-bar').hidden && "
                               "![...byId('agent-group-tools_permissions').querySelectorAll('button')]"
                               ".some(button=>button.textContent.includes('Review'))")
            preferences = cfg.data_dir / "chat-preferences.json"

            # Native segmented radios expose the same policy values to keyboard
            # users. Editing only stages a draft; Discard restores the baseline.
            await tab.js("byId('setting-permissions-read_file-allow').focus()")
            for key, value in ((" ", "allow"), ("ArrowRight", "ask"),
                               ("ArrowRight", "deny"), ("ArrowLeft", "ask")):
                await tab.command("Input.dispatchKeyEvent", {
                    "type": "keyDown", "key": key,
                    **({"code": "Space", "windowsVirtualKeyCode": 32} if key == " " else {}),
                })
                await tab.command("Input.dispatchKeyEvent", {"type": "keyUp", "key": key})
                assert await tab.js(f"byId('setting-permissions-read_file-{value}').checked && "
                                   f"SettingsDrafts.value('agent','permissions.read_file')==='{value}'")
            assert read_settings(preferences).get("permissions", {}).get("read_file") is None
            await tab.click("#agent-discard")

            async def stage(identity, value):
                if identity.startswith("setting-permissions-"):
                    await tab.click(f"#{identity}-{value}")
                    return
                await tab.js("(()=>{const input=byId(" + json.dumps(identity) + ");"
                             + ("input.checked=" if isinstance(value, bool) else "input.value=")
                             + json.dumps(value) + ";input.dispatchEvent(new Event("
                             "input.type==='checkbox'||input.tagName==='SELECT'?'change':'input'));})()")

            async def saved(timeout=30):
                # A clean bar means a terminal receipt AND a confirming read.
                deadline = asyncio.get_running_loop().time() + timeout
                while asyncio.get_running_loop().time() < deadline:
                    if await tab.js("byId('agent-save-bar').hidden"):
                        return
                    await asyncio.sleep(.1)
                raise AssertionError(await tab.js("byId('agent-save-status').textContent"))

            await stage("setting-permissions-read_file", "deny")
            assert read_settings(preferences).get("permissions", {}).get("read_file") != "deny"
            assert await tab.js("byId('agent-unsaved-count').textContent==='1 unsaved change'")
            await tab.click("#settings-tab-models")
            await tab.click("#settings-tab-agent")
            assert await tab.js("byId('setting-permissions-read_file-deny').checked")
            await tab.click("#agent-discard")
            assert await tab.js("byId('agent-save-bar').hidden && "
                               "!byId('setting-permissions-read_file-deny').checked")

            await stage("setting-permissions-read_file", "deny")
            await tab.click("#agent-save")
            await saved()
            assert read_settings(preferences)["permissions"]["read_file"] == "deny"
            assert await tab.js("!reviewDialog.open && !byId('settings-security')?.open")

            await stage("setting-tool_availability-read_file", False)
            assert await tab.js("byId('setting-permissions-read_file').disabled")
            await tab.click("#agent-save")
            await saved()
            assert read_settings(preferences)["tool_availability"]["read_file"] is False
            await stage("setting-tool_availability-read_file", True)
            await tab.click("#agent-save")
            await tab.wait("byId('settings-security')?.open")
            assert await tab.js("byId('settings-security-details').textContent"
                                ".includes('Read files')")
            await tab.click("#settings-security-cancel")
            await tab.wait("!byId('agent-save').disabled")
            assert read_settings(preferences)["tool_availability"]["read_file"] is False
            await tab.click("#agent-save")
            await tab.wait("byId('settings-security').open")
            await tab.click("#settings-security-confirm")
            await saved()
            assert read_settings(preferences)["tool_availability"]["read_file"] is True
            assert read_settings(preferences)["permissions"]["read_file"] == "deny"

            # Automatic access requires an explicit, setting-specific decision;
            # its native dialog reuses Material tokens and fits narrow screens.
            await stage("setting-permissions-read_file", "allow")
            await tab.click("#agent-save")
            await tab.wait("byId('settings-security').open")
            assert await tab.js("byId('settings-security-details').textContent"
                               ".includes('without an approval prompt')")
            for theme in ("light", "dark"):
                for width in (320, 390, 1440):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": 480, "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    })
                    await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                    await asyncio.sleep(.05)
                    assert await tab.js("""(()=>{
                      const dialog=byId('settings-security'), r=dialog.getBoundingClientRect();
                      return dialog.classList.contains('domain-dialog') && r.left>=0 &&
                        r.right<=innerWidth && r.top>=0 && r.bottom<=innerHeight &&
                        dialog.scrollWidth<=dialog.clientWidth &&
                        getComputedStyle(dialog).backgroundColor===getComputedStyle(
                          byId('domain-review')).backgroundColor;
                    })()""")
            await tab.click("#settings-security-cancel")
            await tab.wait("!byId('agent-save').disabled")
            await tab.click("#agent-discard")
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False,
            })

            # A tool being enabled with a more restrictive staged policy must
            # never briefly inherit its older Automatic approval during a batch.
            assert await tab.js("byId('setting-permissions-current_time-allow').checked")
            await stage("setting-tool_availability-current_time", False)
            await tab.click("#agent-save")
            await saved()
            await stage("setting-tool_availability-current_time", True)
            await stage("setting-permissions-current_time", "ask")
            await tab.js("""window.orderFetch=fetch.bind(window);window.settingOrder=[];
              window.fetch=(input,options)=>{
                if(String(input).endsWith('/library/review'))
                  settingOrder.push(JSON.parse(options.body).draft.id);
                return orderFetch(input,options);
              };""")
            await tab.click("#agent-save")
            await tab.wait("byId('settings-security').open")
            assert await tab.js("byId('settings-security-details').textContent"
                               ".includes('Ask first requires an approval prompt')")
            await tab.click("#settings-security-confirm")
            await saved()
            assert await tab.js("settingOrder.join(',')==="
                               "'permissions.current_time,tool_availability.current_time'")
            await tab.js("window.fetch=orderFetch")
            assert read_settings(preferences)["permissions"]["current_time"] == "ask"

            # An outside writer must not be overwritten with an obsolete base.
            await stage("setting-permissions-read_file", "allow")
            update_settings(preferences, {("permissions", "read_file"): "ask"})
            await tab.click("#agent-settings-refresh")
            await tab.wait("byId('agent-save-bar').textContent.includes('changed elsewhere')")
            assert await tab.js("byId('agent-save').disabled && "
                               "byId('setting-permissions-read_file-allow').checked")
            await tab.click("#agent-discard")
            assert await tab.js("byId('setting-permissions-read_file-ask').checked")

            # More than 16 field changes must fit the bounded preparation cache.
            # These are all restrictive saves through real workers, one by one.
            await tab.js("""for(const input of document.querySelectorAll(
              '#agent-settings-fields [data-setting^="permissions."] input[value="deny"]')) {
                input.click();
              }
              for(const input of document.querySelectorAll(
              '#agent-settings-fields [data-setting^="tool_availability."] input')) {
                input.checked=false;input.dispatchEvent(new Event('change'));
              }""")
            assert await tab.js("SettingsDrafts.category('agent').drafts.changed().length>16")
            await tab.click("#agent-save")
            await saved(timeout=90)
            assert all(value is False for value in read_settings(preferences)["tool_availability"]
                       .values())

            # Ordinary category changes save independently. A later failure must
            # leave earlier success confirmed and keep the remaining draft.
            await stage("setting-time_settings-timezone", "UTC")
            await stage("setting-runtime_options-max_steps", "7")
            await tab.click("#settings-tab-models")
            await tab.wait("Boolean(byId('default-output-tokens'))")
            await stage("default-output-tokens", "256")
            await tab.click("#settings-tab-agent")
            assert await tab.js("byId('agent-unsaved-count').textContent==='2 unsaved changes'")
            await tab.js("""window.saveFetch=fetch.bind(window); window.prepareCalls=0;
              window.fetch=(input,options)=>{
                if(String(input).endsWith('/library/review') && ++prepareCalls===2)
                  return Promise.resolve(new Response(
                    JSON.stringify({error:{message:'Fixture rejection'}}),
                    {status:400,headers:{'Content-Type':'application/json'}}));
                return saveFetch(input,options);
              };""")
            await tab.click("#agent-save")
            await tab.wait("byId('agent-save-status').textContent.includes('1 change saved')")
            assert read_settings(preferences)["time_settings"]["timezone"] == "UTC"
            assert read_settings(preferences).get("runtime_options", {}).get("max_steps") != 7
            assert await tab.js("byId('setting-runtime_options-max_steps').value==='7' && "
                               "byId('agent-unsaved-count').textContent==='1 unsaved change' && "
                               "!reviewDialog.open && !byId('settings-security').open")
            await tab.js("window.fetch=saveFetch")
            await tab.wait("!byId('agent-save').disabled")
            await tab.click("#agent-save")
            await saved()
            assert read_settings(preferences)["runtime_options"]["max_steps"] == 7
            await tab.click("#settings-tab-models")
            assert await tab.js("byId('default-output-tokens').value==='256' && "
                               "byId('models-unsaved-count').textContent==='1 unsaved change'")
            await tab.click("#models-save")
            await tab.wait("byId('models-save-bar').hidden")
            assert read_settings(preferences)["ai_defaults"]["output_tokens"] == 256
            await stage("default-output-tokens", "384")
            await stage("image-service-url", "http://127.0.0.1:1234")
            await tab.click("#media-settings-refresh")
            await tab.wait("!byId('default-output-tokens').disabled")
            assert await tab.js("byId('default-output-tokens').value==='384' && "
                               "byId('image-service-url').value==='http://127.0.0.1:1234'")
            await tab.click("#models-discard")
            assert await tab.js("byId('default-output-tokens').value==='256' && "
                               "byId('image-service-url').value==='' && "
                               "byId('models-save-bar').hidden")
            # An actual witnessed unknown image-settings save is reconciled by
            # the existing backend recovery operation, without contacting a model.
            journal = OperationJournal(cfg.data_dir / "operations.db")
            identity = uuid.uuid4().hex
            candidate = {"enabled": False, "endpoint": "http://127.0.0.1:1234",
                         "model": "fixture"}
            with patch.object(journal, "finish", side_effect=OSError("lost acknowledgement")):
                try:
                    save_image_settings(cfg, candidate, "", journal, identity, "cli")
                except ImageSettingsUnconfirmed:
                    pass
                else:
                    raise AssertionError("Expected a witnessed unknown save")
            await stage("default-output-tokens", "384")
            await tab.click("#media-settings-refresh")
            await tab.wait("Boolean(byId('image-settings-recovery').querySelector('button'))")
            assert await tab.js("byId('models-save').disabled")
            await tab.click("#image-settings-recovery button")
            await tab.wait("!SettingsDrafts.category('models').saving && "
                           "!byId('image-settings-recovery').querySelector('button')")
            assert journal.status(identity, "cli").state == "completed"
            assert await tab.js("byId('default-output-tokens').value==='384' && "
                               "!reviewDialog.open && !byId('models-save').disabled")
            await tab.click("#models-discard")
            await tab.click("#settings-tab-agent")

            # Losing a submission response does not authorize a second save.
            await stage("setting-runtime_options-max_steps", "8")
            await tab.js("""window.submitCalls=0; window.fetch=(input,options)=>{
              if(String(input).endsWith('/library/submit')) {
                submitCalls++;
                return saveFetch(input,options).then(()=>{
                  throw new TypeError('Lost acknowledgement');});
              }
              return saveFetch(input,options);
            };""")
            await tab.click("#agent-save")
            await tab.wait("!byId('agent-save-check').hidden && !byId('agent-save-check').disabled")
            assert await tab.js("byId('agent-save').disabled && byId('agent-discard').disabled && "
                               "SettingsDrafts.category('agent').drafts.entries"
                               ".get('runtime_options.max_steps').base.value===7")
            await tab.js("window.fetch=saveFetch")
            await tab.click("#agent-save-check")
            await saved()
            assert read_settings(preferences)["runtime_options"]["max_steps"] == 8
            assert await tab.js("submitCalls===1")

            # A successful receipt with a failed confirming read also keeps its
            # original baseline and uses a read-only status check to finish.
            await stage("setting-runtime_options-max_steps", "9")
            await tab.js("""window.failSavedRead=true; window.fetch=(input,options)=>{
              if(String(input).endsWith('/settings/agent') && failSavedRead) {
                failSavedRead=false;
                return Promise.reject(new TypeError('Offline during confirmation'));
              }
              return saveFetch(input,options);
            };""")
            await tab.click("#agent-save")
            await tab.wait("byId('agent-save-status').textContent"
                           ".includes('Offline during confirmation')")
            assert await tab.js("SettingsDrafts.category('agent').drafts.entries"
                               ".get('runtime_options.max_steps').base.value===8")
            await tab.js("window.fetch=saveFetch")
            await tab.wait("!byId('agent-save-check').disabled")
            await tab.click("#agent-save-check")
            await saved()
            assert read_settings(preferences)["runtime_options"]["max_steps"] == 9

            # A hung acknowledgement is bounded. Its late response must not
            # replace the outcome confirmed through the original receipt.
            await stage("setting-runtime_options-max_steps", "15")
            await tab.js("""window.saveTimer=setTimeout;
              window.setTimeout=(fn,ms,...args)=>saveTimer(fn,ms===30000?200:ms,...args);
              window.fetch=(input,options)=>{
              if(String(input).endsWith('/library/submit')) {
                return saveFetch(input,options).then(response=>new Promise(resolve=>{
                  window.releaseTimedOutSave=()=>resolve(response);}));
              }
              return saveFetch(input,options);
            };""")
            await tab.click("#agent-save")
            await tab.wait("byId('agent-save-status').textContent.includes('Connection timed out')")
            await tab.js("window.setTimeout=saveTimer;window.fetch=saveFetch")
            await tab.wait("!byId('agent-save-check').disabled")
            await tab.click("#agent-save-check")
            await saved()
            await tab.js("releaseTimedOutSave()")
            assert read_settings(preferences)["runtime_options"]["max_steps"] == 15

            # The backend compare-and-set remains active after preparation too.
            await stage("setting-runtime_options-max_steps", "10")
            await tab.js("""window.fetch=(input,options)=>
              String(input).endsWith('/library/submit') ?
              new Promise(resolve=>{window.releaseSave=()=>resolve(saveFetch(input,options));}) :
              saveFetch(input,options);""")
            await tab.click("#agent-save")
            await tab.wait("typeof releaseSave==='function'")
            update_settings(preferences, {("runtime_options", "max_steps"): 11})
            await tab.js("releaseSave();window.fetch=saveFetch")
            await tab.wait("byId('agent-save-bar').textContent.includes('changed elsewhere')")
            assert read_settings(preferences)["runtime_options"]["max_steps"] == 11
            assert await tab.js("byId('setting-runtime_options-max_steps').value==='10'")
            await tab.js("[...byId('agent-save-bar').querySelectorAll('button')]"
                         ".find(button=>button.textContent==='Keep my change').click()")
            await tab.click("#agent-save")
            await saved()
            assert read_settings(preferences)["runtime_options"]["max_steps"] == 10

            # A request lost before admission can only retry its same snapshot/ID.
            await stage("setting-runtime_options-max_steps", "14")
            await tab.js("""window.retryIds=[];window.dropSubmit=true;
              window.fetch=(input,options)=>{
                if(String(input).endsWith('/library/submit')) {
                  retryIds.push(JSON.parse(options.body).request_id);
                  if(dropSubmit) {dropSubmit=false;return Promise.reject(new TypeError('Offline'));}
                }
                return saveFetch(input,options);
              };""")
            await tab.click("#agent-save")
            await tab.wait("!byId('agent-save-check').hidden && !byId('agent-save-check').disabled")
            await tab.click("#agent-save-check")
            await saved()
            assert read_settings(preferences)["runtime_options"]["max_steps"] == 14
            assert await tab.js("retryIds.length===2 && retryIds[0]===retryIds[1]")
            await tab.js("window.fetch=saveFetch")

            # The bar stays inside Settings, has its own layout space and fits
            # small screens at both ends of a long expanded category.
            await stage("setting-runtime_options-max_steps", "12")
            for width in (320, 390, 768, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 700, "deviceScaleFactor": 1,
                    "mobile": width < 600,
                })
                for position in (0, 1):
                    await tab.js("byId('agent-settings').querySelectorAll('details')"
                                 ".forEach(section=>section.open=true);"
                                 f"byId('settings-view').scrollTop={position}*"
                                 "byId('settings-view').scrollHeight")
                    await asyncio.sleep(.05)
                    bounds = await tab.js("""(()=>{
                      const view=byId('settings-view'), v=view.getBoundingClientRect();
                      const bar=byId('agent-save-bar'), b=bar.getBoundingClientRect();
                      const field=byId('setting-research-context_tokens').getBoundingClientRect();
                      return {fits:view.scrollWidth<=view.clientWidth &&
                        document.documentElement.scrollWidth<=innerWidth,
                        visible:b.top>=v.top-1 && b.bottom<=innerHeight &&
                          (innerWidth>850 || bar.parentElement===byId('settings-action-dock')),
                        reserved:view.scrollTop+view.clientHeight<view.scrollHeight-2 ||
                          field.bottom<=b.top,
                        target:[...bar.querySelectorAll('button:not([hidden])')].every(button=>
                          button.getBoundingClientRect().height>=44), b:b.toJSON(),v:v.toJSON()};
                    })()""")
                    assert all(bounds[key] for key in ("fits", "visible", "reserved", "target")), (
                        width, position, bounds
                    )
                    if width in (390, 1440) and position == 1:
                        capture = await tab.command("Page.captureScreenshot", {"format": "png"})
                        output = Path("/tmp/klaude-settings-save")
                        output.mkdir(exist_ok=True)
                        (output / f"dirty-{width}.png").write_bytes(
                            base64.b64decode(capture["data"])
                        )
            await tab.click("#agent-discard")

            # Logout while a submission acknowledgement is in flight must clear
            # drafts, without treating accepted backend work as cancelled.
            await stage("setting-runtime_options-max_steps", "13")
            await tab.js("""window.fetch=(input,options)=>{
              if(String(input).endsWith('/library/submit')) return saveFetch(input,options).then(
                response=>new Promise(resolve=>{
                  window.releaseAcceptedSave=()=>resolve(response);}));
              return saveFetch(input,options);
            };""")
            await tab.click("#agent-save")
            await tab.wait("typeof releaseAcceptedSave==='function'")
            await tab.click("#logout")
            await tab.wait("!authenticated")
            await tab.js("releaseAcceptedSave();window.fetch=saveFetch")
            await asyncio.sleep(.2)
            assert await tab.js("SettingsDrafts.category('agent').drafts.entries.size===0 && "
                               "SettingsDrafts.category('models').drafts.entries.size===0 && "
                               "byId('agent-save-bar').hidden && byId('models-save-bar').hidden")

            assert not tab.errors, tab.errors
            return {"tools_staging_save_discard_navigation": "passed",
                    "independent_availability_and_policy": "passed",
                    "restrictive_policy_before_tool_activation": "passed",
                    "large_category_batch_over_16_changes": "passed",
                    "security_confirmation_and_cancel": "passed", "concurrent_writer": "passed",
                    "security_dialog_responsive_themes": "passed",
                    "agent_models_partial_success_and_draft_isolation": "passed",
                    "lost_acknowledgement_and_confirming_read": "passed",
                    "exact_unknown_image_settings_recovery": "passed",
                    "backend_compare_and_set_after_preparation": "passed",
                    "responsive_sticky_bar": [320, 390, 768, 1440], "logout_race": "passed",
                    "console_errors": 0}
    finally:
        process.terminate()
        process.wait(timeout=10)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    ))
    with tempfile.TemporaryDirectory(prefix="klaude-settings-save-") as folder:
        root = Path(folder)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        update_settings(cfg.data_dir / "chat-preferences.json", {
            ("permissions", "current_time"): "allow",
        })
        app = _app(cfg.data_dir)
        app.agent.workdir, app.agent.workspace = root, Workspace(root)
        app.agent.tool_config = cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        host = LocalWebHost(app, library=LibraryManagement(cfg, root))
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            with patch("klaude_application.browser_media_settings.default_model_catalog",
                       return_value=[]):
                result = asyncio.run(asyncio.wait_for(verify(host, root, cfg, chrome), 240))
                print(json.dumps(result))
        finally:
            host.stop()
            thread.join(3)
            app.memory.db.close()


if __name__ == "__main__":
    main()

"""Native SD model picker, reviewed load and independent default save."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_core.image_generation import read
from webui_control_smoke import Tab
from webui_model_store_smoke import main as fixture_main

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_image_model_selection import model_server  # noqa: E402


async def advanced_models(tab):
    await tab.wait("[...byId('role-picker-items').querySelectorAll('button')]"
                   ".some(b=>b.textContent==='Advanced service models')")
    await tab.js("[...byId('role-picker-items').querySelectorAll('button')]"
                 ".find(b=>b.textContent==='Advanced service models').click()")


async def verify(host, root):
    with model_server() as (url, state):
        # Simulate weights downloaded after the server last scanned its folder.
        state["pending_files"] = state["files"]
        state["files"] = []
        await browse(host, root, url, state)


async def browse(host, root, url, state):
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    ))
    profile = root / "sd-picker-chrome"
    process = subprocess.Popen([
        chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    captures = Path("/tmp/klaude-sd-model-picker-evidence")
    captures.mkdir(exist_ok=True)
    before = read(host.library.cfg)
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait("document.documentElement?.dataset.access==='locked'")
            await tab.js(
                "byId('login-username').value='admin';byId('login-password').value="
                + json.dumps(host.accounts.initial_password())
                + ";byId('account-login').requestSubmit()"
            )
            await tab.wait("typeof showView==='function' && "
                           "typeof setupReloadWitness==='undefined' && "
                           "typeof latest!=='undefined' && authenticated && "
                           "document.documentElement.dataset.startup==='ready'")
            await tab.js("showView('settings',{section:'models'})")
            await tab.wait("byId('models-image-summary').textContent.length>0")
            await tab.click('[data-model-screen=image]')
            await tab.js(
                "byId('image-service-provider').value='sdcpp';"
                "byId('image-service-provider').dispatchEvent(new Event('change'));"
                "byId('image-service-url').value=" + json.dumps(url) + ";"
                "byId('image-service-url').dispatchEvent(new Event('input'))"
            )
            assert await tab.js("!byId('image-service-model-row').hidden && "
                                "byId('image-service-model-name').hidden")
            await tab.click('#image-service-model-name-picker')
            await advanced_models(tab)
            await tab.wait("byId('role-picker-items').textContent.includes('original-model')")
            assert not state['loads']
            assert ("POST", "/sdcpp/v1/models/refresh") in state['calls']
            assert await tab.js("byId('role-picker-items').textContent.includes('Second model')")
            assert await tab.js("['Current server model','Downloaded files · setup required',"
                                "'Needs setup'].every(label=>"
                                "byId('role-picker-items').textContent.includes(label))")
            for width in (320, 390, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 900, "deviceScaleFactor": 1,
                    "mobile": width < 600,
                })
                assert await tab.js("byId('role-model-picker').scrollWidth<="
                                    "byId('role-model-picker').clientWidth && "
                                    "[...byId('role-picker-items').querySelectorAll('button.store-row')]"
                                    ".every(row=>row.getBoundingClientRect().right<=innerWidth && "
                                    "row.getBoundingClientRect().height>=44)")
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (captures / f"choice-list-{width}.png").write_bytes(
                    base64.b64decode(shot["data"])
                )
            await tab.click('#role-picker-items button')
            await tab.wait("!byId('role-model-picker').open && "
                           "byId('image-service-model-name').value==='original-model'")
            assert read(host.library.cfg) == before
            await tab.click('#image-service-model-name-picker')
            await advanced_models(tab)
            await tab.wait("byId('role-picker-items').textContent.includes('Second model')")
            assert not await tab.js(
                "byId('role-picker-items').textContent.includes('Stable Diffusion')"
            )
            await tab.js(
                "[...byId('role-picker-items').querySelectorAll('button')]"
                ".find(n=>n.querySelector('strong')?.textContent==='Second model').click()"
            )
            await tab.js(
                "const setup=document.querySelector('[data-native-recipe]');"
                "setup.value='sd';setup.dispatchEvent(new Event('change'))"
            )
            assert await tab.js("document.querySelector('[data-model-slot=model]').value"
                                "==='checkpoints/second.gguf'")
            assert await tab.js("!document.querySelector('[data-native-load]').disabled")
            await tab.click('[data-setup-save]')
            await tab.wait("document.querySelector('[data-setup-readiness]')?.textContent"
                           ".includes('ready for load review')")
            assert not state['loads'] and read(host.library.cfg) == before
            # A browser reload loses settings drafts but retains the server-side setup.
            await tab.js('window.setupReloadWitness=true')
            await tab.command('Page.reload')
            await asyncio.sleep(.3)
            await tab.wait("typeof showView==='function' && "
                           "typeof setupReloadWitness==='undefined' && "
                           "typeof latest!=='undefined' && authenticated && "
                           "document.documentElement.dataset.startup==='ready'")
            await tab.js("showView('settings',{section:'models'})")
            await tab.wait("byId('models-image-summary').textContent.length>0")
            await tab.js("ModelsSettingsNavigation.show('image')")
            await tab.js("byId('image-service-url').value=" + json.dumps(url) + ";"
                         "byId('image-service-url').dispatchEvent(new Event('input'))")
            await tab.click('#image-service-model-name-picker')
            await advanced_models(tab)
            await tab.wait("!!document.querySelector('[data-saved-setup]')")
            await tab.click('[data-saved-setup]')
            await tab.wait("document.querySelector('[data-model-slot=model]')?.value"
                           "==='checkpoints/second.gguf'")
            await tab.wait("!document.querySelector('[data-native-load]').disabled")
            assert not state['loads'] and read(host.library.cfg) == before

            for width in (320, 390, 768, 1440):
                await tab.command('Emulation.setDeviceMetricsOverride', {
                    'width': width, 'height': 900, 'deviceScaleFactor': 1, 'mobile': width < 600,
                })
                await asyncio.sleep(.1)
                assert await tab.js("""(()=>{
                  const dialog=byId('role-model-picker'),r=dialog.getBoundingClientRect();
                  return document.documentElement.scrollWidth<=innerWidth && r.left>=0 &&
                    r.right<=innerWidth && dialog.scrollWidth<=dialog.clientWidth &&
                    [...dialog.querySelectorAll('select')].filter(n=>n.offsetWidth).every(n=>{
                      const b=n.getBoundingClientRect();return b.left>=r.left&&b.right<=r.right;
                    });
                })()""")
                shot = await tab.command('Page.captureScreenshot', {'format': 'png'})
                (captures / f'choose-{width}.png').write_bytes(base64.b64decode(shot['data']))
            await tab.click('[data-native-load]')
            await tab.wait('reviewDialog.open')
            assert not state['loads']
            assert await tab.js(
                "byId('domain-review-summary').textContent.includes('Second model')"
            )
            await tab.click('#domain-review-cancel')
            await tab.wait('!reviewDialog.open')
            assert not state['loads']
            await tab.click('[data-native-load]')
            await tab.wait('reviewDialog.open')
            await tab.click('#domain-review-confirm')
            await tab.wait("!byId('role-model-picker').open && "
                           "byId('image-service-model-name').value==='second.gguf'")
            assert len(state['loads']) == 1 and read(host.library.cfg) == before
            await tab.js("byId('image-service-enabled').checked=true;"
                         "byId('image-service-enabled').dispatchEvent(new Event('change'))")
            await tab.click('#image-service-save-bar #image-service-save')
            await tab.wait("byId('settings-security')?.open")
            await tab.js(
                "[...byId('settings-security').querySelectorAll('button')]"
                ".find(n=>n.textContent==='Save changes').click()"
            )
            try:
                await tab.wait("byId('image-service-save-bar').hidden && "
                               "byId('image-service-model').textContent.includes('second.gguf')")
            except AssertionError:
                print('SAVE_STATE', await tab.js(
                    "({dialogs:[...document.querySelectorAll('dialog[open]')].map(n=>"
                    "({id:n.id,text:n.textContent})),status:byId('image-service-save-bar').textContent,"
                    "settings:byId('image-settings-status').textContent})"
                ), flush=True)
                raise
            saved = read(host.library.cfg)
            assert saved['endpoint'] == url and saved['model'] == 'second.gguf'
            assert saved['enabled'] and len(state['loads']) == 1
            await tab.click('#image-service-model-name-picker')
            await advanced_models(tab)
            await tab.wait("!!document.querySelector('[data-saved-setup]')")
            await tab.click('[data-saved-setup]')
            await tab.wait("document.querySelector('[data-setup-readiness]')?.textContent"
                           "==='Loaded and configured'")
            assert len(state['loads']) == 1
            await tab.click('#role-picker-close')
            # Composer -> setup -> composer preserves private prompt/options in memory.
            await tab.js("showView('chat')")
            await tab.click('#attach-create-image')
            await tab.wait("byId('image-generate-panel').open")
            await tab.js("byId('image-prompt').value='Keep this private draft';"
                         "byId('image-seed').value='123'")
            await tab.click('#image-setup-open')
            await tab.wait("byId('role-model-picker').open && "
                           "!!document.querySelector('[data-saved-setup]')")
            assert await tab.js("!JSON.stringify(history.state).includes('private draft')")
            await tab.click('[data-saved-setup]')
            await tab.wait("location.search.includes('models-setup=')")
            await tab.click('#role-picker-close')
            for width in (320, 1440):
                await tab.command('Emulation.setDeviceMetricsOverride', {
                    'width': width, 'height': 900, 'deviceScaleFactor': 1, 'mobile': width < 600,
                })
                await tab.js("toggleSessions(false);"
                             "byId('image-setup-handoff').scrollIntoView({block:'start'})")
                await asyncio.sleep(.1)
                assert await tab.js("document.documentElement.scrollWidth<=innerWidth && "
                                    "byId('image-setup-handoff').scrollWidth<="
                                    "byId('image-setup-handoff').clientWidth")
                shot = await tab.command('Page.captureScreenshot', {'format': 'png'})
                (captures / f'setup-handoff-{width}.png').write_bytes(
                    base64.b64decode(shot['data']))
            await tab.click('#image-setup-return')
            await tab.wait("currentView==='chat' && byId('image-generate-panel').open")
            assert await tab.js("byId('image-prompt').value==='Keep this private draft' && "
                                "byId('image-seed').value==='123'")
            assert read(host.library.cfg) == saved and len(state['loads']) == 1
            await tab.click('#image-setup-open')
            await tab.wait("byId('role-model-picker').open && "
                           "!!document.querySelector('[data-saved-setup]')")
            await tab.click('[data-saved-setup]')
            await tab.wait("location.search.includes('models-setup=')")
            await tab.js('window.setupRouteReload=true')
            await tab.command('Page.reload')
            await asyncio.sleep(.3)
            await tab.wait("typeof showView==='function' && "
                           "typeof setupRouteReload==='undefined' && authenticated && "
                           "document.documentElement.dataset.startup==='ready' && "
                           "!byId('image-setup-handoff').hidden")
            await tab.click('#image-setup-choose')
            try:
                await tab.wait("document.querySelector('[data-setup-readiness]')?.textContent"
                               "==='Loaded and configured'")
            except AssertionError:
                print(await tab.js("({url:location.href,"
                                   "status:byId('image-settings-status').textContent,"
                                   "picker:byId('role-picker-status').textContent,"
                                   "open:byId('role-model-picker').open})"), flush=True)
                raise
            assert len(state['loads']) == 1 and read(host.library.cfg) == saved
            await tab.click('#role-picker-close')
            await tab.click('#image-setup-return')
            await tab.wait("currentView==='chat' && byId('image-generate-panel').open")
            assert await tab.js("byId('image-prompt').value===''")
            await tab.click('#image-generate-close')
            await tab.js("showView('settings',{section:'models'});"
                         "ModelsSettingsNavigation.show('image')")
            await tab.wait("byId('image-service-url').value===" + json.dumps(url))
            # Empty native catalog still exposes the loaded model and explains the missing files.
            state['files'] = []
            await tab.click('#image-service-model-name-picker')
            await advanced_models(tab)
            await tab.wait("byId('role-picker-status').textContent.includes('no model files')")
            assert await tab.js("byId('role-picker-items').textContent.includes('second.gguf')")
            await tab.wait("!!document.querySelector('[data-saved-setup]')")
            await tab.click('[data-saved-setup]')
            await tab.wait("document.querySelector('[data-setup-readiness]')?.textContent"
                           "==='Selected files unavailable'")
            assert await tab.js("document.querySelector('[data-native-load]').disabled")
            assert len(state['loads']) == 1
            await tab.click('#role-picker-close')
            await tab.wait("document.activeElement===byId('image-service-model-name-picker')")
            state['runtime']['state'] = 'loading'
            await tab.click('#image-service-model-name-picker')
            await advanced_models(tab)
            await tab.wait("byId('role-picker-status').textContent.includes('server is loading')")
            await tab.click('#role-picker-close')
            state['runtime']['state'] = 'ready'
            # Saved-setup support is independently gated on older hosts.
            await tab.js("latest.image_setup_drafts=false;window.setupRequests=0;"
                         "window.originalSetupRequest=domainRequest;"
                         "domainRequest=(...args)=>{if(args[0].endsWith('image-setups'))"
                         "window.setupRequests++;return window.originalSetupRequest(...args)}")
            await tab.click('#image-service-model-name-picker')
            await advanced_models(tab)
            await tab.wait("byId('role-picker-items').textContent.includes('second.gguf')")
            assert await tab.js(
                "setupRequests===0 && !document.querySelector('[data-saved-setup]')"
            )
            await tab.click('#role-picker-close')
            await tab.js("domainRequest=window.originalSetupRequest;latest.image_setup_drafts=true")
            await tab.click('#image-service-model-name-picker')
            await advanced_models(tab)
            await tab.wait("!!document.querySelector('[data-saved-setup]')")
            await tab.js("[...document.querySelectorAll('#role-model-picker button')]"
                         ".find(n=>n.textContent==='Forget saved setup').click()")
            await tab.wait("!document.querySelector('[data-saved-setup]') && "
                           "document.querySelector('.image-model-setup').textContent"
                           ".includes('Saved selection forgotten')")
            assert read(host.library.cfg) == saved and len(state['loads']) == 1
            await tab.click('#role-picker-close')
            # Fresh assets on an older host give explicit guidance without unsupported reads.
            await tab.js('latest.image_model_selection=false')
            before_calls = len(state['calls'])
            await tab.click('#image-service-model-name-picker')
            await advanced_models(tab)
            await tab.wait("byId('role-picker-status').textContent.includes('Restart')")
            assert len(state['calls']) == before_calls
            await tab.click('#role-picker-close')
            assert not tab.errors, tab.errors
            print(json.dumps({'responsive_widths': [320, 390, 768, 1440],
                              'reviewed_native_load': True, 'loads': len(state['loads']),
                              'independent_default_save': True, 'empty_catalog': True,
                              'older_host': True, 'console_errors': 0,
                              'screenshots': str(captures)}))
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == '__main__':
    fixture_main(verify, admin_lan=True)

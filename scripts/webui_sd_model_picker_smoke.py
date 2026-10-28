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


async def verify(host, root):
    with model_server() as (url, state):
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
            await tab.wait("typeof latest!=='undefined' && authenticated && "
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
            await tab.wait("byId('role-picker-items').textContent.includes('original-model')")
            assert not state['loads']
            await tab.click('#role-picker-items button')
            await tab.wait("!byId('role-model-picker').open && "
                           "byId('image-service-model-name').value==='original-model'")
            assert read(host.library.cfg) == before
            await tab.click('#image-service-model-name-picker')
            await tab.wait("byId('role-picker-items').textContent.includes('Stable Diffusion')")
            await tab.js(
                "[...byId('role-picker-items').querySelectorAll('button')]"
                ".find(n=>n.querySelector('strong')?.textContent==='Stable Diffusion').click()"
            )
            assert await tab.js("document.querySelector('[data-native-load]').disabled")
            await tab.js(
                "const file=document.querySelector('[data-model-slot=model]');"
                "file.value='checkpoints/second.gguf';file.dispatchEvent(new Event('change'))"
            )
            assert await tab.js("!document.querySelector('[data-native-load]').disabled")
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
            # Empty native catalog still exposes the loaded model and explains the missing files.
            state['files'] = []
            await tab.click('#image-service-model-name-picker')
            await tab.wait("byId('role-picker-status').textContent.includes('no model files')")
            assert await tab.js("byId('role-picker-items').textContent.includes('second.gguf')")
            await tab.click('#role-picker-close')
            await tab.wait("document.activeElement===byId('image-service-model-name-picker')")
            state['runtime']['state'] = 'loading'
            await tab.click('#image-service-model-name-picker')
            await tab.wait("byId('role-picker-status').textContent.includes('server is loading')")
            await tab.click('#role-picker-close')
            state['runtime']['state'] = 'ready'
            # Fresh assets on an older host give explicit guidance without unsupported reads.
            await tab.js('latest.image_model_selection=false')
            before_calls = len(state['calls'])
            await tab.click('#image-service-model-name-picker')
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

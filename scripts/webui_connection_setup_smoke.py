"""Guided model connection stages use isolated workers and explicit reviews."""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from webui_control_smoke import Tab
from webui_model_store_smoke import Native, main


async def verify(host, root):
    Native.models = [{"name": "fixture:latest", "size": 1000, "digest": "a" * 64}]
    chrome = str(next((Path.home() / '.cache/puppeteer/chrome-headless-shell').glob(
        '*/chrome-headless-shell-linux64/chrome-headless-shell')))
    profile = root / 'connection-setup-chrome'
    output = Path('/tmp/klaude-connection-setup-evidence')
    output.mkdir(exist_ok=True)
    process = subprocess.Popen([chrome, '--no-sandbox', '--disable-gpu',
        '--remote-debugging-port=0', f'--user-data-dir={profile}'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if (profile / 'DevToolsActivePort').exists():
                break
            await asyncio.sleep(.05)
        port = int((profile / 'DevToolsActivePort').read_text().splitlines()[0])
        with urlopen(Request(f'http://127.0.0.1:{port}/json/new?about:blank', method='PUT')) as r:
            target = json.load(r)
        async with websockets.connect(target['webSocketDebuggerUrl'], max_size=5_000_000) as ws:
            tab = Tab(ws)

            async def wait(expression):
                try:
                    await tab.wait('Boolean(' + expression + ')')
                except AssertionError:
                    print(await tab.js("({url:location.href,"
                                       "status:byId('model-connections-status')"
                                       ".textContent, guide:byId('model-connection-setup')"
                                       ".textContent})"), flush=True)
                    raise

            await tab.command('Runtime.enable')
            await tab.command('Page.enable')
            await tab.command('Page.navigate', {'url': host.bootstrap_url})
            await wait("document.documentElement?.dataset.access==='locked'")
            await tab.js("byId('login-username').value='admin';byId('login-password').value="
                         + json.dumps(host.accounts.initial_password())
                         + ";byId('account-login').requestSubmit()")
            await wait("typeof latest!=='undefined'&&latest&&authenticated&&"
                       "document.documentElement.dataset.startup==='ready'")
            original_model = await tab.js('latest.model_ref')
            await tab.js("showView('settings',{section:'models'});"
                         "ModelsSettingsNavigation.show('connections',{focus:false})")
            await wait("!byId('model-connection-add').disabled")
            await tab.click('#model-connection-add')
            await tab.js("byId('model-connection-name').value='Guided fixture';"
                         "byId('model-connection-authentication').checked=true;"
                         "byId('model-connection-url').value="
                         + json.dumps(host.library.cfg.ollama_url))
            await tab.js("byId('model-connection-form').requestSubmit()")
            await wait('reviewDialog.open')
            assert await tab.js("byId('model-connection-editor').open")
            await tab.click('#domain-review-cancel')
            await wait("!reviewDialog.open&&!byId('model-connection-submit').disabled")
            assert await tab.js("byId('model-connection-name').value==='Guided fixture'")
            await tab.js("byId('model-connection-form').requestSubmit()")
            await wait('reviewDialog.open')
            await tab.js("window.setupOriginalRequest=domainRequest;window.setupSubmissions=0;"
                         "domainRequest=async(...args)=>{if(args[0]==='/api/v1/library/submit'){"
                         "setupSubmissions++;const result=await setupOriginalRequest(...args);"
                         "domainRequest=setupOriginalRequest;"
                         "throw Error('Fixture acknowledgement lost');"
                         "}return setupOriginalRequest(...args);}")
            await tab.click('#domain-review-confirm')
            await wait("byId('domain-review-status').textContent"
                       ".includes('Fixture acknowledgement')")
            await tab.click('#domain-review-cancel')
            await wait("byId('model-connection-setup').textContent.includes('Definition saved')")
            await tab.js("byId('connection-guide-refresh')?.click()")
            await wait("byId('model-connection-editor').open && "
                       "byId('model-connection-setup').textContent.includes('Definition saved') && "
                       "!byId('connection-guide-credential').disabled")
            assert await tab.js('setupSubmissions===1')
            connection_id = await tab.js("new URLSearchParams(location.search)"
                                         ".get('connection-setup')")
            assert connection_id and await tab.js("byId('connection-guide-enable').disabled")
            assert not await tab.js("byId('model-connection-setup').textContent"
                                   ".includes('Enabled')")
            old = await tab.js('performance.timeOrigin')
            await tab.command('Page.reload')
            await wait(f"performance.timeOrigin!=={old}&&typeof latest!=='undefined'&&"
                       "authenticated&&byId('model-connection-editor').open&&"
                       "byId('connection-guide-credential')&&!byId('connection-guide-credential').disabled")
            assert connection_id == await tab.js("new URLSearchParams(location.search)"
                                                 ".get('connection-setup')")
            await tab.js("byId('model-credential-value').value='private-guided-fixture'")
            await tab.click('#connection-guide-credential')
            await wait('reviewDialog.open')
            assert await tab.js("!byId('domain-review-summary').textContent.includes("
                                "'private-guided-fixture')&&!byId('model-credential-value').value")
            await tab.click('#domain-review-cancel')
            await wait("!reviewDialog.open&&!byId('connection-guide-credential').disabled")
            assert await tab.js("!JSON.stringify(history.state).includes('private-guided-fixture')"
                                "&&!location.href.includes('private-guided-fixture')")
            await tab.js("byId('model-credential-value').value='private-guided-fixture'")
            await tab.click('#connection-guide-credential')
            await wait('reviewDialog.open')
            await tab.click('#domain-review-confirm')
            await wait("byId('model-connection-setup').textContent.includes('Test connection')&&"
                       "!byId('connection-guide-test').disabled")
            assert await tab.js("byId('model-connection-editor').open&&"
                                "!byId('model-credential-value').value")
            for width in (320, 390, 768, 1440):
                await tab.command('Emulation.setDeviceMetricsOverride', {
                    'width': width, 'height': 900, 'deviceScaleFactor': 1, 'mobile': width < 600,
                })
                await asyncio.sleep(.2)
                assert await tab.js("byId('model-connection-editor').scrollWidth<="
                                    "byId('model-connection-editor').clientWidth")
                assert await tab.js("[...byId('model-connection-editor').querySelectorAll("
                                    "'button:not([hidden])')].filter(n=>n.getClientRects().length)"
                                    ".every(n=>n.getBoundingClientRect().height>=44)")
                shot = await tab.command('Page.captureScreenshot', {'format': 'png'})
                (output / f'guided-{width}.png').write_bytes(base64.b64decode(shot['data']))
            await tab.click('#model-connection-close')
            await tab.js("[...byId('model-settings-connections').querySelectorAll('article')]"
                         ".find(n=>n.textContent.includes('Guided fixture'))"
                         ".querySelector('button')"
                         ".click()")
            await wait("byId('model-connection-editor').open&&byId('connection-guide-test')")
            assert await tab.js("byId('connection-guide-enable').disabled")
            await tab.click('#connection-guide-test')
            await wait("!byId('connection-guide-enable').disabled")
            await tab.click('#connection-guide-enable')
            await wait('reviewDialog.open')
            await tab.click('#domain-review-cancel')
            await wait("!reviewDialog.open&&!byId('connection-guide-enable').disabled")
            await tab.click('#connection-guide-enable')
            await wait('reviewDialog.open')
            await tab.click('#domain-review-confirm')
            await wait("byId('connection-guide-done')&&!byId('connection-guide-done').disabled")
            assert original_model == await tab.js('latest.model_ref')
            await tab.click('#connection-guide-done')
            await wait("!byId('model-connection-editor').open")
            assert not await tab.js("new URLSearchParams(location.search).has('connection-setup')")
            await tab.click('#logout')
            await wait('!authenticated')
            assert await tab.js("!byId('model-credential-value').value")
            assert not tab.errors, tab.errors
            print(json.dumps({'guided_stages': True, 'review_cancel_retains_definition': True,
                              'exact_id_reload': True, 'credential_privacy': True,
                              'lost_ack_without_replay': True,
                              'explicit_test_enable': True, 'resume_disabled_connection': True,
                              'widths': [320, 390, 768, 1440], 'console_errors': 0,
                              'screenshots': str(output)}))
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == '__main__':
    main(verify, admin_lan=True)

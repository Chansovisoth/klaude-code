"""Real isolated restart/shutdown, terminal scope, re-authentication and System UI."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_webhost.hosting import WebHostController
from klaude_webhost.lan import lan_ipv4_addresses
from webui_control_smoke import Tab
from webui_model_store_smoke import Native


async def verify(root, controller, first, terminal, unrelated):
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    ))
    profile = root / "chrome"
    process = subprocess.Popen([
        chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    captures = Path("/tmp/klaude-system-evidence")
    captures.mkdir(exist_ok=True)
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

            async def wait(expression):
                for attempt in range(10):
                    try:
                        await tab.wait("Boolean(" + expression + ")")
                        return
                    except AssertionError as error:
                        if "Inspected target navigated or closed" not in str(error) or attempt == 9:
                            raise
                        await asyncio.sleep(.05)

            async def login():
                await wait("document.documentElement?.dataset.access==='locked'")
                await tab.js(
                    "byId('login-username').value='admin';byId('login-password').value="
                    + json.dumps(controller.initial_admin_password())
                    + ";byId('account-login').requestSubmit()"
                )
                await wait("typeof latest!=='undefined' && authenticated && "
                           "document.documentElement.dataset.startup==='ready' && "
                           "settingsSection==='system'")
                for _ in range(30):
                    await tab.js('SystemSettings.load()')
                    await asyncio.sleep(.2)
                    if await tab.js("!byId('system-restart').disabled"):
                        return
                raise AssertionError(await tab.js("byId('system-status').textContent"))

            await tab.command('Runtime.enable')
            await tab.command('Page.enable')
            await tab.command('Page.navigate', {
                'url': first.origin + '/?view=settings&settings=system',
            })
            await login()
            assert await tab.js("byId('system-sessions').textContent.includes('1 running')")
            for width in (320, 390, 768, 1440):
                await tab.command('Emulation.setDeviceMetricsOverride', {
                    'width': width, 'height': 900, 'deviceScaleFactor': 1, 'mobile': width < 600,
                })
                for theme in ('light', 'dark'):
                    await tab.js('applyAppearance({...appearance,reduced:true,theme:'
                                 + json.dumps(theme) + '})')
                    await asyncio.sleep(.1)
                    assert await tab.js("""(()=>{
                      const panel=byId('system-settings'),r=panel.getBoundingClientRect();
                      return document.documentElement.scrollWidth<=innerWidth &&
                        panel.scrollWidth<=panel.clientWidth &&
                        ['system-restart','system-shutdown'].every(id=>{
                          const b=byId(id).getBoundingClientRect();
                          return b.height>=44&&b.left>=r.left&&b.right<=r.right;
                        });
                    })()""")
                    shot = await tab.command('Page.captureScreenshot', {'format': 'png'})
                    (captures / f'system-{width}-{theme}.png').write_bytes(
                        base64.b64decode(shot['data'])
                    )
            for action in ('restart', 'shutdown'):
                await tab.click('#system-' + action)
                await wait("byId('system-confirm').open")
                assert await tab.js("document.activeElement===byId('system-confirm-cancel')")
                await tab.click('#system-confirm-cancel')
                await wait("!byId('system-confirm').open")
                assert controller.status().runtime_instance == first.runtime_instance
            # A definite server rejection restores the page and polling, without retry.
            await tab.click('#system-restart')
            await wait("byId('system-confirm').open")
            await tab.js("""(()=>{
              window.realSystemRequest=domainRequest;
              domainRequest=(path,...args)=>{
                if(path==='/api/v1/system/apply'){
                  const error=new Error('Runtime changed; review again');error.status=409;
                  return Promise.reject(error);
                }
                return realSystemRequest(path,...args);
              };
            })()""")
            await tab.click('#system-confirm-apply')
            await wait("byId('system-transition').hidden && !byId('system-restart').disabled")
            assert controller.status().runtime_instance == first.runtime_instance
            await tab.js('domainRequest=window.realSystemRequest;delete window.realSystemRequest')
            # Settings search opens System without executing the matching action.
            await tab.js("showSettingsSection('theme')")
            await tab.click('#settings-search-open')
            await tab.js("byId('settings-search-query').value='Restart Web UI';"
                         "byId('settings-search-query').dispatchEvent(new Event('input'))")
            await wait("byId('settings-search-results').querySelector('button')")
            await tab.click('#settings-search-results button')
            await wait("settingsSection==='system' && !byId('system-confirm').open")
            await wait("!byId('system-restart').disabled")
            await tab.click('#system-restart')
            await wait("byId('system-confirm').open")
            document = await tab.js('performance.timeOrigin')
            await tab.click('#system-confirm-apply')
            for _ in range(120):
                current = controller.status()
                if current.running and current.runtime_instance != first.runtime_instance:
                    break
                await asyncio.sleep(.2)
            else:
                raise AssertionError('Restart did not publish a new runtime')
            assert current.session_id == first.session_id
            assert current.workspace == first.workspace and current.lan_origin == first.lan_origin
            assert terminal.poll() is None and unrelated.poll() is None
            await wait(f"performance.timeOrigin!=={document} && "
                       "document.documentElement?.dataset.access==='locked'")
            await login()
            assert await tab.js('latest.session_id') == first.session_id
            await tab.click('#system-shutdown')
            await wait("byId('system-confirm').open")
            assert await tab.js("byId('system-confirm-summary').textContent.includes('1 running')")
            await tab.click('#system-confirm-apply')
            receipt = controller.directory / 'lifecycle.json'
            for _ in range(100):
                saved = json.loads(receipt.read_text()) if receipt.exists() else {}
                if (saved.get('action') == 'shutdown' and saved.get('state') == 'completed'
                        and not controller.status().running and terminal.poll() is not None):
                    break
                await asyncio.sleep(.2)
            else:
                raise AssertionError('Profile shutdown did not finish')
            assert unrelated.poll() is None
            assert not controller.desired()
            assert not tab.errors, tab.errors
            print(json.dumps({'system_tab': True, 'review_cancel': True, 'search': True,
                              'restart_reauthentication': True, 'session_workspace_lan': True,
                              'profile_terminal_stopped': True, 'other_profile_preserved': True,
                              'widths': [320, 390, 768, 1440], 'console_errors': 0,
                              'screenshots': str(captures)}))
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    with tempfile.TemporaryDirectory(prefix='klaude-system-smoke-') as temporary:
        root = Path(temporary)
        native = ThreadingHTTPServer(('127.0.0.1', 0), Native)
        Native.models = [{'name': 'fixture:latest', 'model': 'fixture:latest', 'size': 123}]
        threading.Thread(target=native.serve_forever, daemon=True).start()
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            port = reserved.getsockname()[1]
        lan = next(iter(lan_ipv4_addresses()), '')
        children = []
        controller = WebHostController(root / 'config', root / 'data')
        logs = []
        try:
            def environment(config, data):
                config.mkdir(parents=True)
                data.mkdir(parents=True)
                (config / 'config.toml').write_text(
                    f'[services]\nollama_url="http://127.0.0.1:{native.server_port}"\n'
                )
                (data / 'chat-preferences.json').write_text(json.dumps({
                    'ai_defaults': {'chat': 'ollama@default-ollama/fixture:latest'},
                    'model_default_selections': {'chat': 'manual'},
                }))
                return {**os.environ, 'KLAUDE_CONFIG_DIR': str(config),
                        'KLAUDE_DATA_DIR': str(data)}

            def launch(args, env, label):
                log = (root / (label + '.log')).open('wb')
                logs.append(log)
                child = subprocess.Popen(args, env=env, cwd=root, stdin=subprocess.PIPE,
                                         stdout=log, stderr=log)
                children.append(child)
                return child

            env = environment(root / 'config', root / 'data')
            (root / 'config/webui.json').write_text(json.dumps({
                'enabled': True, 'lan_enabled': bool(lan), 'lan_ip': lan,
            }))
            host = launch([sys.executable, '-m', 'klaude_webhost.main', '--managed',
                           '--workspace', str(root), '--port', str(port),
                           *(['--lan-ip', lan] if lan else [])], env, 'host')
            for _ in range(100):
                first = controller.status()
                if first.running:
                    break
                if host.poll() is not None:
                    raise AssertionError((root / 'host.log').read_text())
                import time
                time.sleep(.1)
            else:
                raise AssertionError('Fixture Web UI did not start')
            terminal = launch([sys.executable, '-m', 'klaude_cli.main', 'chat', '--no-tui',
                               '--model', 'fixture:latest'], env, 'terminal')
            other_env = environment(root / 'other-config', root / 'other-data')
            unrelated = launch([sys.executable, '-m', 'klaude_cli.main', 'chat', '--no-tui',
                                '--model', 'fixture:latest'], other_env, 'other-terminal')
            asyncio.run(verify(root, controller, first, terminal, unrelated))
        except BaseException:
            for log in logs:
                log.flush()
            for path in root.glob('*.log'):
                print(path.name, path.read_text()[-4000:], flush=True)
            raise
        finally:
            controller.disable()
            for child in children:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=5)
            for log in logs:
                log.close()
            native.shutdown()
            native.server_close()


if __name__ == '__main__':
    main()

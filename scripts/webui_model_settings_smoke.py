"""Full model-settings walkthrough with isolated HTTP, journal and service fixtures."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from webui_control_smoke import Tab
from webui_model_store_smoke import Native
from webui_model_store_smoke import main as fixture_main


async def verify(host, root):
    Native.models = [
        {
            "name": "fixture:latest",
            "digest": "a" * 64,
            "size": 1000,
            "details": {"parameter_size": "1B"},
        }
    ]
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    profile = root / "chrome"
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
    output = Path("/tmp/klaude-model-settings-evidence")
    output.mkdir(exist_ok=True)
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(0.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            if host.accounts:
                await tab.wait("document.documentElement?.dataset.access === 'locked'")
                await tab.js(
                    "byId('login-username').value='admin'; byId('login-password').value="
                    + json.dumps(host.accounts.initial_password())
                    + "; byId('account-login').requestSubmit()"
                )
            await tab.wait(
                "typeof latest !== 'undefined' && authenticated && latest && docu"
                "ment.documentElement.dataset.startup==='ready'"
            )
            await tab.js("showView('settings', {section:'models'})")
            await tab.wait(
                "!byId('model-connection-add').disabled && byId('default-value-ut"
                "ility-picker') && !byId('default-value-utility-picker').disabled"
            )
            await tab.click("#default-value-utility-picker")
            try:
                await tab.wait(
                    "byId('role-model-picker').open && "
                    "Boolean(byId('role-picker-items').querySelector('.store-row'))"
                )
            except AssertionError:
                print(
                    await tab.js(
                        "({open:byId('role-model-picker').open, status:byId('role-picker-"
                        "status').textContent, connection:byId('role-picker-connection')."
                        "value, items:byId('role-picker-items').textContent, section:sett"
                        "ingsSection})"
                    )
                )
                raise
            await tab.js(
                "byId('role-picker-query').value='fixture'; byId('role-picker-que"
                "ry').dispatchEvent(new Event('input'))"
            )
            await tab.click("#role-picker-items .store-row")
            assert await tab.js(
                "!byId('role-model-picker').open && !byId('models-save-bar').hidd"
                "en && byId('default-value-utility').value.endsWith('/fixture:lat"
                "est')"
            )
            await tab.click("#models-save")
            await tab.wait(
                "byId('models-save-bar').hidden && !SettingsDrafts.category('models').saving"
            )
            assert host.application.agent.model == "fixture"
            await tab.click("#image-service-test")
            try:
                await tab.wait(
                    "byId('image-settings-status').textContent.includes('No image was generated')"
                )
            except AssertionError:
                print(
                    await tab.js(
                        "({status:byId('image-settings-status').textContent,"
                        "endpoint:byId('image-service-url').value})"
                    )
                )
                raise
            await tab.click("#model-connection-add")
            await tab.js(
                "byId('model-connection-name').value='Browser native'; "
                "byId('model-connection-authentication').checked=true; "
                "byId('model-connection-url').value="
                + json.dumps(host.library.cfg.ollama_url)
                + "; byId('model-connection-form').requestSubmit()"
            )
            await tab.wait("reviewDialog.open")
            assert await tab.js("document.activeElement===byId('domain-review-cancel')")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "byId('model-settings-connections').textContent.includes('Browser"
                " native') && !byId('model-connection-add').disabled"
            )

            async def action(label):
                await tab.js(
                    "[...byId('model-settings-connections').querySelectorAll('.management-row')]"
                    ".find(r=>r.querySelector('h3').textContent==='Browser native')"
                    ".querySelectorAll('button').forEach(b=>{if(b.textContent==="
                    + json.dumps(label)
                    + ") b.click();})"
                )

            await action("Credential")
            await tab.wait("byId('model-connection-editor').open")
            await tab.js(
                "byId('model-credential-value').value='private-fixture-token'; by"
                "Id('model-connection-form').requestSubmit()"
            )
            await tab.wait("reviewDialog.open")
            assert await tab.js(
                "!byId('domain-review-summary').textContent.includes('private-fix"
                "ture-token') && !byId('model-credential-value').value"
            )
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "!byId('model-connection-add').disabled && [...byId('model-settin"
                "gs-connections').querySelectorAll('.management-row')].some(r=>r."
                "textContent.includes('Browser native')&&r.textContent.includes('"
                "Credential saved'))"
            )
            await action("Enable")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "!byId('model-connection-add').disabled && [...byId('model-settin"
                "gs-connections').querySelectorAll('.management-row')].some(r=>r."
                "textContent.includes('Browser native')&&r.textContent.includes('"
                "Enabled'))"
            )
            await tab.js("showView('models')")
            await tab.wait("byId('store-endpoint').options.length===2")
            assert await tab.js("byId('store-endpoint-label').hidden")
            await tab.js("byId('store-source').value='curated';"
                         "byId('store-source').dispatchEvent(new Event('change'))")
            await tab.wait("Boolean(document.querySelector('.store-row[data-store-model=qwen3]'))")
            await tab.click(".store-row[data-store-model=qwen3]")
            await tab.wait("!byId('store-detail').hidden && Boolean(byId('store-detail-endpoint'))")
            assert await tab.js("byId('store-detail-endpoint').options.length===2")
            await tab.click("#store-detail-back")
            await tab.wait("byId('store-detail').hidden")
            await tab.click("#store-tab-installed")
            assert await tab.js("!byId('store-endpoint-label').hidden")
            await tab.js("showView('settings', {section:'models'})")
            await tab.wait("!byId('model-connection-add').disabled")
            await action("Test")
            await tab.wait(
                "byId('model-connections-status').textContent.includes('Connection reached')"
            )
            for width, height in [(320, 568), (390, 844), (768, 1024), (1440, 900)]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                )
                for theme in ["light", "dark"]:
                    await tab.js(
                        "applyAppearance({...appearance, theme:"
                        + json.dumps(theme)
                        + ", reduced:true})"
                    )
                    assert await tab.js(
                        "document.documentElement.scrollWidth<=innerWidth && byId('models"
                        "-settings').scrollWidth<=byId('models-settings').clientWidth"
                    ), (width, theme)
                    assert await tab.js(
                        "(()=>{const h=byId('model-connections-heading').getBoundingClientRect();"
                        "const a=byId('model-connection-add').getBoundingClientRect();"
                        "return h.right<=a.left || h.bottom<=a.top || a.bottom<=h.top})()"
                    ), (width, theme, "connection heading overlap")
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"model-settings-{width}-{theme}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                await tab.js("byId('model-connections-heading').scrollIntoView({block:'start'})")
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"connections-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                await action("Edit")
                await tab.wait("byId('model-connection-editor').open")
                assert await tab.js(
                    "byId('model-connection-editor').scrollWidth<=byId('model-connect"
                    "ion-editor').clientWidth"
                )
                await tab.click("#model-connection-close")
            await action("Remove")
            await tab.wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-confirm').classList.contains('danger')")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "!byId('model-settings-connections').textContent.includes('Browse"
                "r native') && !byId('model-connection-add').disabled"
            )
            assert Native.pulls == 0
            await tab.click("#logout")
            await tab.wait("!authenticated")
            assert await tab.js(
                "!byId('model-credential-value').value && !byId('model-settings-c"
                "onnections').textContent && !byId('role-picker-items').textConte"
                "nt"
            )
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "settings": (
                            "role picker/save, image test, add-disabled, credential, enable/t"
                            "est, remove and logout passed"
                        ),
                        "widths": [320, 390, 768, 1440],
                        "console_errors": 0,
                        "screenshots": str(output),
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    fixture_main(verify, admin_lan=os.environ.get("KLAUDE_TEST_ADMIN_LAN") == "1")

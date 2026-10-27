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
            await tab.js("byId('model-fallbacks').open=true")
            await tab.click("#default-value-fallbacks-0-picker")
            await tab.wait(
                "byId('role-model-picker').open && "
                "Boolean(byId('role-picker-items').querySelector('.store-row'))"
            )
            await tab.click("#role-picker-items .store-row")
            assert await tab.js(
                "!byId('models-save-bar').hidden && "
                "SettingsDrafts.value('models','fallbacks').length===1"
            )
            await tab.click("#models-discard")
            assert await tab.js("SettingsDrafts.value('models','fallbacks').length===0")
            await tab.click("[data-model-screen=image]")
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
            await tab.click("#models-settings-back")
            await tab.click("[data-model-screen=connections]")
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
            await tab.js(
                "byId('store-source').value='curated';"
                "byId('store-source').dispatchEvent(new Event('change'))"
            )
            await tab.wait("Boolean(document.querySelector('.store-row[data-store-model=qwen3]'))")
            await tab.click(".store-row[data-store-model=qwen3]")
            await tab.wait("!byId('store-detail').hidden && Boolean(byId('store-detail-endpoint'))")
            assert await tab.js("byId('store-detail-endpoint').options.length===2")
            await tab.click("#store-detail-back")
            await tab.wait("byId('store-detail').hidden")
            await tab.click("#store-tab-installed")
            assert await tab.js("!byId('store-endpoint-label').hidden")
            await tab.js("showView('settings', {section:'models'})")
            await tab.click("[data-model-screen=connections]")
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
            await tab.click("#models-settings-back")
            await tab.click("[data-model-screen=catalog]")
            await tab.wait("Boolean(byId('models-items').querySelector('.models-model'))")
            assert await tab.js("!byId('models-items').querySelector('button')")
            await tab.js("history.back()")
            await tab.wait("!byId('model-default-settings').hidden")
            await tab.click("[data-model-screen=image]")
            await tab.js(
                "byId('image-service-url').value='http://127.0.0.1:54321'; byId('image-"
                "service-url').dispatchEvent(new Event('input'))"
            )
            assert await tab.js(
                "!byId('image-service-save-bar').hidden && byId('models-save-bar').hidden"
            )
            await tab.click("#image-service-discard")
            await tab.click("#models-settings-back")
            await tab.js(
                "byId('default-value-utility').value=''; "
                "byId('default-value-utility').dispatchEvent(new Event('change')); "
                "window.savedConfirm=window.confirm; window.confirm=()=>false"
            )
            await tab.click("[data-model-screen=connections]")
            assert await tab.js("!byId('model-default-settings').hidden")
            await tab.js("history.back()")
            await asyncio.sleep(0.2)
            assert await tab.js(
                "!byId('model-default-settings').hidden && "
                "new URLSearchParams(location.search).get('models-screen')==='overview'"
            )
            await tab.js("window.confirm=window.savedConfirm")
            await tab.click("#models-discard")
            for width, height in [(320, 568), (390, 844), (768, 1024), (1440, 900)]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                )
                for screen in ["overview", "connections", "catalog", "image"]:
                    await tab.js("ModelsSettingsNavigation.show(" + json.dumps(screen) + ")")
                    await asyncio.sleep(0.15)
                    assert await tab.js(
                        "document.documentElement.scrollWidth<=innerWidth && byId('models-setti"
                        "ngs').scrollWidth<=byId('models-settings').clientWidth"
                    ), (width, screen)
                    if screen == "overview":
                        assert await tab.js(
                            "new Set([...document.querySelectorAll('.settings-role-grid > "
                            ".settings-role-container')]"
                            ".map(row=>Math.round(row.getBoundingClientRect().left))).size===1"
                        )
                        await tab.js("byId('model-fallbacks').open=true")
                        assert await tab.js("""(() => {
                          const rows=[...document.querySelectorAll(
                            '.settings-fallback-form .settings-role-row')];
                          return rows.length===6 && rows.every(row => {
                            const r=row.getBoundingClientRect(),
                              group=row.closest('form').getBoundingClientRect();
                            return Math.abs(r.left-group.left)<1 && Math.abs(r.right-group.right)<1;
                          });
                        })()""")
                        assert await tab.js("""(() => {
                          const roles=getComputedStyle(
                            document.querySelector('.settings-role-grid'));
                          const advanced=getComputedStyle(byId('model-fallbacks'));
                          return roles.borderColor===advanced.borderColor &&
                            roles.borderRadius===advanced.borderRadius &&
                            roles.backgroundColor===advanced.backgroundColor;
                        })()""")
                        rows = await tab.js("""[...document.querySelectorAll(
                              '.settings-role-row, .settings-navigation-row')]
                            .filter(el=>el.getClientRects().length).map(el=>{
                              const style=getComputedStyle(el), box=el.getBoundingClientRect();
                              return {text:el.textContent, left:parseFloat(style.paddingLeft),
                                right:parseFloat(style.paddingRight), width:box.width,
                                parent:byId('models-settings').clientWidth,
                                childrenFit:[...el.children].every(child=>{
                                  const r=child.getBoundingClientRect();
                                  return !r.width || r.left>=box.left && r.right<=box.right;
                                })};
                            })""")
                        assert all(
                            row["left"] >= 12
                            and row["right"] >= 12
                            and row["width"] <= row["parent"] + 1
                            and row["childrenFit"]
                            for row in rows
                        ), (width, rows)
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"settings-{screen}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                await tab.js(
                    "ModelsSettingsNavigation.show('overview'); showView('settings',{sectio"
                    "n:'account'})"
                )
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"account-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                await tab.click("#password-open")
                assert await tab.js(
                    "byId('password-dialog').open && document.activeElement===byId('current"
                    "-password')"
                )
                if width <= 560:
                    await tab.wait(
                        "Math.abs(byId('password-dialog').getBoundingClientRect().width-innerWidth)<1"
                    )
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"password-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                await tab.js("byId('new-password').value='temporary-fixture'")
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
                await tab.wait(
                    "!byId('password-dialog').open && !byId('new-password').value && docume"
                    "nt.activeElement===byId('password-open')"
                )
                await tab.js("showView('settings',{section:'memory'})")
                await tab.wait("!byId('memory-create').disabled")
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"memory-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                await tab.click("#memory-create")
                assert await tab.js(
                    "byId('memory-editor').open && document.activeElement===byId('memory-fact')"
                )
                await tab.click("#memory-editor-cancel")
                await tab.wait(
                    "!byId('memory-editor').open && document.activeElement===byId('memory-create')"
                )
                await tab.js("showView('settings',{section:'models'})")
            await tab.js("showView('settings',{section:'memory'})")
            await tab.click("#memory-create")
            await tab.js(
                "byId('memory-fact').value='Settings layout fixture'; byId('memory-add'"
                ").requestSubmit()"
            )
            await tab.wait("reviewDialog.open")
            assert await tab.js("!byId('memory-editor').open")
            await tab.click("#domain-review-cancel")
            await tab.wait(
                "byId('memory-editor').open && "
                "byId('memory-fact').value==='Settings layout fixture'"
            )
            await tab.js("byId('memory-add').requestSubmit()")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait("byId('memory-items').textContent.includes('Settings layout fixture')")
            await tab.click("#memory-items .icon-button")
            await tab.click("#memory-items [role=menuitem]")
            assert await tab.js(
                "byId('memory-editor').open && byId('memory-fact').value==='Settings la"
                "yout fixture'"
            )
            await tab.click("#memory-editor-cancel")
            await tab.click("#memory-items .icon-button")
            await tab.js("byId('memory-items').querySelector('.danger').click()")
            await tab.wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-confirm').classList.contains('danger')")
            await tab.click("#domain-review-cancel")
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
    fixture_main(verify, admin_lan=os.environ.get("KLAUDE_TEST_ADMIN_LAN", "1") == "1")

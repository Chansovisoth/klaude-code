"""Store/Models design walkthrough on isolated catalogs; never downloads model weights."""

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
from klaude_application.integration_store import IntegrationStore
from webui_control_smoke import Tab
from webui_model_store_smoke import main as fixture_main

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_integration_store import transport


async def verify(host, root):
    state = {}
    host.library.integration_store = IntegrationStore(host.library.cfg, transport=transport(state))
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    profile = root / "design-chrome"
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
    captures = Path("/tmp/klaude-store-ux")
    captures.mkdir(exist_ok=True)
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

            async def wait(expression):
                await tab.wait("Boolean(" + expression + ")")

            async def shot(name):
                await asyncio.sleep(0.15)
                result = await tab.command("Page.captureScreenshot", {"format": "png"})
                (captures / (name + ".png")).write_bytes(base64.b64decode(result["data"]))

            async def geometry(name):
                result = await tab.js(
                    """(()=>{
                      const view=document.querySelector('.main-view:not([hidden])');
                      return {page:document.documentElement.scrollWidth<=innerWidth,
                        view:view.scrollWidth<=view.clientWidth+1,
                        nav:innerWidth<=700?byId('store-view-heading').hidden ||
                          byId('store-mobile-location').offsetHeight>=44:
                          [...byId('store-kind-nav').children].every(n=>n.offsetHeight>=44)};
                    })()"""
                )
                assert all(result.values()), (name, result)

            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await wait("document.documentElement?.dataset.access==='locked'")
            await tab.js(
                "byId('login-username').value='admin';byId('login-password').value="
                + json.dumps(host.accounts.initial_password())
                + ";byId('account-login').requestSubmit()"
            )
            await wait(
                "typeof latest!=='undefined'&&authenticated&&"
                "document.documentElement.dataset.startup==='ready'"
            )
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
            )
            await tab.js(
                "showView('settings',{section:'models'});ModelsSettingsNavigation.show('overview')"
            )
            await wait("byId('default-value-chat')&&!byId('model-default-settings').hidden")
            await shot("models-dashboard-desktop")
            await tab.js("ModelsSettingsNavigation.show('image')")
            await wait(
                "!byId('image-service-settings').hidden&&!byId('image-service-model-name-picker').disabled"
            )
            await shot("image-settings-desktop")
            await tab.js("showView('store')")
            await wait("byId('store-content').querySelector('[data-store-model]')")
            for width in (1440, 390, 320):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 900 if width > 600 else 844,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                for kind in ("models", "mcps", "skills"):
                    await tab.click("#store-kind-" + kind)
                    await wait(
                        "byId('store-kind-" + kind + "').getAttribute('aria-current')==='page'"
                    )
                    await wait(
                        "byId('store-content').querySelector('[data-store-model]')"
                        if kind == "models"
                        else "byId('integration-store-page')"
                        ".querySelector('[data-integration-item]')"
                    )
                    await geometry(f"{kind}-{width}")
                    await shot(f"{kind}-{width}")
                    if kind != "models":
                        await tab.click("#integration-store-page [data-integration-item]")
                        await wait(
                            "byId('integration-store-page').querySelector('.catalog-detail-hero')"
                        )
                        assert await tab.js(
                            "byId('integration-store-technical')&&!byId('integration-store-technical').open"
                        )
                        await geometry(f"{kind}-detail-{width}")
                        await shot(f"{kind}-detail-{width}")
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
            )
            # Keyboard category navigation, native detail disclosure and review cancellation.
            await tab.click("#store-kind-mcps")
            await wait("byId('integration-store-query')")
            await tab.js("byId('store-kind-mcps').focus()")
            await tab.command(
                "Input.dispatchKeyEvent",
                {"type": "keyDown", "key": "ArrowDown", "code": "ArrowDown"},
            )
            await tab.command(
                "Input.dispatchKeyEvent",
                {
                    "type": "keyDown",
                    "key": "Enter",
                    "code": "Enter",
                    "text": "\r",
                    "windowsVirtualKeyCode": 13,
                    "nativeVirtualKeyCode": 13,
                },
            )
            await wait("byId('store-kind-skills').getAttribute('aria-current')==='page'")
            await tab.click("#store-kind-mcps")
            await wait("byId('integration-store-page').querySelector('[data-integration-item]')")
            await tab.click("#integration-store-page [data-integration-item]")
            await wait("byId('integration-store-install')")
            await tab.click("#integration-install-options > summary")
            await tab.js("byId('integration-store-name').value='ux-search'")
            await wait("!byId('integration-store-install').disabled")
            await tab.click("#integration-store-install")
            await wait("reviewDialog.open")
            assert await tab.js("managementReview.operation==='mcp-add'")
            await tab.click("#domain-review-cancel")
            await wait("!reviewDialog.open")
            assert await tab.js("byId('integration-store-name').value==='ux-search'")
            await wait("!byId('integration-store-install').disabled")
            await tab.click("#integration-store-install")
            await wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await wait(
                "byId('integration-store-feedback').textContent.includes('Server added disabled')"
            )
            # Managed image catalog and full review are discoverable without service setup.
            await tab.js("StoreDesign.openImages()")
            await wait("byId('store-image-bundles').querySelector('[data-bundle-install]')")
            await shot("images-390")
            await geometry("images")
            await tab.click("[data-bundle-install]")
            await wait("reviewDialog.open")
            assert await tab.js("managementReview.operation==='comfy-install'")
            await tab.click("#domain-review-cancel")
            await wait("!reviewDialog.open")
            for section in ("installed", "downloads"):
                await tab.js("StoreDesign.openImages(" + json.dumps(section) + ")")
                await wait("byId('store-image-bundles').querySelector('.collection-empty')")
                await shot("images-empty-" + section)
            await tab.js(
                "StoreDesign.openImages();byId('store-query').value='no-such-model';"
                "byId('store-query').dispatchEvent(new Event('input'))"
            )
            await wait("byId('store-image-bundles').textContent.includes('No matching')")
            # Model detail remains a full page; download cancellation retains exact selection.
            await tab.click("#store-kind-models")
            await tab.js(
                "byId('store-runtime').value='ollama';"
                "byId('store-runtime').dispatchEvent(new Event('change'))"
            )
            await wait("byId('store-content').querySelector('[data-store-model]')")
            await tab.click("#store-content [data-store-model]")
            await wait("!byId('store-detail').hidden&&byId('store-variant-list')")
            await shot("model-detail-1440")
            await wait("byId('store-variant-0')&&!byId('store-variant-0').disabled")
            await tab.click("#store-variant-0")
            await wait("!byId('store-detail-install').disabled")
            variant = await tab.js("byId('store-variant-0').value")
            await tab.click("#store-detail-install")
            await wait("reviewDialog.open")
            await tab.click("#domain-review-cancel")
            await wait("!reviewDialog.open")
            assert await tab.js(
                "byId('store-variant-0').checked&&"
                "new URLSearchParams(location.search).get('models-variant')==="
                + json.dumps(variant)
            )
            origin = await tab.js("performance.timeOrigin")
            await tab.command("Page.reload")
            await wait(
                f"performance.timeOrigin!=={origin}&&typeof authenticated!=='undefined'&&"
                "authenticated&&document.documentElement.dataset.startup==='ready'&&"
                "!byId('store-detail').hidden&&Boolean(byId('store-variant-0'))"
            )
            assert await tab.js(
                "byId('store-variant-0').checked&&byId('store-runtime').value==='ollama'"
            )

            # Settings remains grouped and uses independent drafts.
            for width in (1440, 390, 320):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 900 if width > 600 else 844,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                await tab.js(
                    "showView('settings',{section:'models'});ModelsSettingsNavigation.show('overview')"
                )
                await wait("byId('default-value-chat')&&!byId('model-default-settings').hidden")
                columns = await tab.js(
                    "getComputedStyle(byId('default-model-fields')"
                    ".querySelector('.settings-role-grid')).gridTemplateColumns.split(' ').length"
                )
                assert columns == (2 if width > 600 else 1), (width, columns)
                await shot(f"settings-models-{width}")
                await tab.js("ModelsSettingsNavigation.show('image')")
                await wait(
                    "!byId('image-service-settings').hidden&&!byId('image-service-model-name-picker').disabled"
                )
                assert await tab.js(
                    "!byId('image-service-advanced').open&&Boolean(byId('image-service-enabled').closest('.image-enable-row'))"
                )
                await shot(f"settings-image-{width}")
                assert await tab.js(
                    "byId('settings-view').scrollWidth<=byId('settings-view').clientWidth+1"
                )
            await tab.js("byId('image-service-enabled').click()")
            await wait("!byId('image-service-save-bar').hidden")
            assert await tab.js("byId('models-save-bar').hidden")
            await tab.click("#image-service-discard")
            await wait("byId('image-service-save-bar').hidden")
            await tab.click("#image-browse-store")
            await wait("currentView==='store'&&byId('store-runtime').value==='comfyui'")
            for width in (1440, 390):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 900 if width > 600 else 844,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                for theme in ("light", "dark"):
                    await tab.js(
                        "applyAppearance({...appearance,reduced:true,theme:"
                        + json.dumps(theme)
                        + "});StoreDesign.route('all')"
                    )
                    await wait(
                        "!byId('store-discovery-categories').hidden&&Boolean(byId('store-content').querySelector('[data-store-model]'))"
                    )
                    await shot(f"explore-{width}-{theme}")
                    await geometry("explore")
            await tab.js("IntegrationStoreUI.manage('mcps')")
            await wait("byId('connection-items').querySelector('.collection-open')")
            await tab.click("#connection-items .collection-open")
            await wait("byId('connection-detail').open")
            await shot("installed-mcp-390")
            assert await tab.js(
                "byId('connection-detail-permission')&&!byId('connection-detail').querySelector('details').open"
            )
            await tab.click("#connection-detail-close")
            # Full source text remains available in installed details.
            await tab.js(
                "openSkill({name:'Long skill name',description:'A concise introduction. '+"
                "('More detailed source documentation. '.repeat(20)),enabled:true,"
                "source_label:'Local ZIP',indexed_file_count:3,"
                "library:'Skills',identity:'fixture'})"
            )
            await wait("byId('skill-detail').open")
            assert await tab.js(
                "byId('skill-detail-description').textContent.length<155&&!byId('skill-detail-about').hidden"
            )
            await shot("installed-skill-320")
            await tab.click("#skill-detail-close")
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "widths": [320, 390, 1440],
                        "categories": True,
                        "details": True,
                        "mcp_review_and_add": True,
                        "image_install_review": True,
                        "settings_drafts": True,
                        "screenshots": str(captures),
                        "console_errors": 0,
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    fixture_main(verify, admin_lan=True)

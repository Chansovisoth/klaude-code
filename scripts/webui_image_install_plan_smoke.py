"""Saved pre-download plans, exact child transfers and return navigation."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
import webui_image_dependencies_smoke as dependencies
import webui_image_model_store_smoke as image_store
import webui_model_store_smoke as store
from webui_control_smoke import Tab


class PlanNative(dependencies.ComponentNative, image_store.ImageNative):
    pass


async def verify(host, root, state):
    settings_path = host.library.cfg.config_dir / "image-generation.json"
    saved_settings = settings_path.read_bytes()
    image_root = root / "image-models"
    image_root.mkdir()
    previous_root = os.environ.get("KLAUDE_IMAGE_MODEL_DIR")
    os.environ["KLAUDE_IMAGE_MODEL_DIR"] = str(image_root)
    chrome = str(next((Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
        "*/chrome-headless-shell-linux64/chrome-headless-shell")))
    profile = root / "plan-chrome"
    output = Path("/tmp/klaude-image-install-plan-evidence")
    output.mkdir(exist_ok=True)
    process = subprocess.Popen([chrome, "--no-sandbox", "--disable-gpu",
        "--remote-debugging-port=0", f"--user-data-dir={profile}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
                try:
                    await tab.wait("Boolean(" + expression + ")")
                except AssertionError:
                    print(await tab.js("({url:location.href,"
                                       "status:byId('store-status')?.textContent,"
                                       "plan:document.querySelector('.store-install-plan')"
                                       "?.textContent})"), flush=True)
                    raise

            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await wait("document.documentElement?.dataset.access==='locked'")
            await tab.js("byId('login-username').value='admin';byId('login-password').value="
                         + json.dumps(host.accounts.initial_password())
                         + ";byId('account-login').requestSubmit()")
            await wait("typeof latest!=='undefined'&&authenticated&&"
                       "document.documentElement.dataset.startup==='ready'")
            await tab.js("showView('store')")
            await wait("!byId('store-runtime').querySelector('[value=sdcpp]').disabled")
            await tab.js("byId('store-runtime').value='sdcpp';"
                         "byId('store-runtime').dispatchEvent(new Event('change'))")
            await wait("document.querySelector('[data-store-model=\"hf:fixture/Image\"]')")
            await tab.click('[data-store-model="hf:fixture/Image"]')
            await wait("byId('store-variant-0')")
            await tab.click('#store-variant-0')
            await wait("byId('store-plan-open')")
            await tab.click('#store-plan-open')
            await tab.js("byId('store-plan-profile').value='flux3-klein';"
                         "byId('store-plan-profile').dispatchEvent(new Event('change'))")
            await tab.click('#store-plan-build')
            await wait("document.querySelectorAll('[data-plan-slot]').length===3")
            plan_id = await tab.js("new URLSearchParams(location.search).get('models-plan')")
            total = len(image_store.PAYLOAD) + 2 * len(dependencies.PAYLOAD)
            assert await tab.js("document.querySelector('.store-plan-total').textContent"
                                f".includes({json.dumps(f'{total:,} bytes')})")
            assert not dependencies.ComponentNative.transfers
            assert not image_store.ImageNative.transfers
            assert not list(image_root.iterdir())
            for width in (320, 390, 768, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 900, "deviceScaleFactor": 1, "mobile": width < 600,
                })
                await tab.js("toggleSessions(false);byId('store-install-plan').scrollIntoView()")
                await asyncio.sleep(.2)
                assert await tab.js("document.documentElement.scrollWidth<=innerWidth && "
                                    "byId('store-view').scrollWidth<=byId('store-view').clientWidth")
                assert await tab.js("[...document.querySelectorAll('[data-plan-action]')].every("
                                    "n=>n.getBoundingClientRect().height>=44 && "
                                    "n.getBoundingClientRect().right<=innerWidth)")
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"plan-{width}.png").write_bytes(base64.b64decode(shot["data"]))
            old = await tab.js("performance.timeOrigin")
            await tab.command("Page.reload")
            await wait(f"performance.timeOrigin!=={old} && typeof latest!=='undefined' && "
                       "authenticated && document.documentElement.dataset.startup==='ready' && "
                       "document.querySelectorAll('[data-plan-slot]').length===3")
            assert plan_id == await tab.js(
                "new URLSearchParams(location.search).get('models-plan')")
            await wait("byId('store-plan-install-all') && "
                       "!byId('store-plan-install-all').disabled")
            await tab.click('#store-plan-install-all')
            await wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-title').textContent === "
                                "'Install planned files?' && "
                                "byId('domain-review-summary').textContent"
                                ".includes('3 pinned image file downloads')")
            await tab.click('#domain-review-cancel')
            await wait("!reviewDialog.open && !byId('store-plan-install-all').disabled")
            await wait("!byId('store-plan-llm-install').disabled")
            await tab.js("byId('store-plan-llm-install').focus()")
            await tab.click('#store-plan-llm-install')
            await wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-target').textContent"
                                ".includes('text_encoders')")
            await tab.click('#domain-review-cancel')
            await wait("!reviewDialog.open && document.activeElement.id==='store-plan-llm-install'")
            assert not dependencies.ComponentNative.transfers
            await tab.click('#store-plan-primary-install')
            await wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-target').textContent"
                                ".includes('diffusion_models')")
            await tab.click('#domain-review-confirm')
            await wait("document.querySelector('[data-plan-status=primary]').textContent"
                       ".includes('Last transfer completed')")
            await tab.click('#store-plan-install-all')
            await wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-summary').textContent"
                                ".includes('2 pinned image file downloads')")
            await tab.click('#domain-review-confirm')
            await wait("byId('store-plan-llm-pause') && byId('store-plan-vae-pause')")
            await wait("document.querySelector('[data-plan-status=llm]').textContent"
                       ".includes(' / ')")
            await tab.click('#store-plan-llm-pause')
            await wait("byId('store-plan-llm-resume')")
            assert await tab.js("Boolean(byId('store-plan-vae-pause'))")
            await tab.click('#store-plan-downloads')
            await wait("byId('store-return-plan') && byId('store-detail').hidden")
            old = await tab.js("performance.timeOrigin")
            await tab.command("Page.reload")
            await wait(f"performance.timeOrigin!=={old} && typeof latest!=='undefined' && "
                       "authenticated && document.documentElement.dataset.startup==='ready' && "
                       "byId('store-return-plan')")
            await tab.click('#store-return-plan')
            await wait("byId('store-plan-llm-resume')")
            await wait("byId('store-variant-0')?.checked")
            await tab.click('#store-plan-llm-resume')
            await wait("byId('store-plan-llm-pause')")
            dependencies.ComponentNative.gate.set()
            await wait("[...document.querySelectorAll('[data-plan-status]')].filter("
                       "n=>n.textContent.includes('Last transfer completed')).length===3")
            primary = image_root / "diffusion_models/fixture/Image/checkpoint.safetensors"
            assert primary.read_bytes() == image_store.PAYLOAD
            for _, repo, filename, category in dependencies.FLUX3.values():
                saved = image_root / category / repo / filename
                assert saved.read_bytes() == dependencies.PAYLOAD
            assert settings_path.read_bytes() == saved_settings
            assert dependencies.ComponentNative.ranges
            await tab.click('#store-plan-configure')
            await wait("byId('role-model-picker').open && "
                       "document.querySelectorAll('[data-plan-visibility=candidate]').length===3")
            assert not state["loads"]
            await tab.click('[data-plan-use]')
            await wait("document.querySelector('[data-model-slot=diffusion_model]')?.value")
            assert await tab.js("[...document.querySelectorAll('[data-model-slot]')]"
                                ".filter(n=>['diffusion_model','llm','vae'].includes(n.dataset.modelSlot))"
                                ".every(n=>n.value)")
            for width in (320, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 900, "deviceScaleFactor": 1, "mobile": width < 600,
                })
                assert await tab.js("byId('role-model-picker').scrollWidth<="
                                    "byId('role-model-picker').clientWidth")
            await tab.click('[data-setup-save]')
            await wait("document.querySelector('[data-setup-readiness]')")
            setup_id = await tab.js("new URLSearchParams(location.search).get('models-setup')")
            assert setup_id
            old = await tab.js("performance.timeOrigin")
            await tab.command("Page.reload")
            await wait(f"performance.timeOrigin!=={old} && typeof latest!=='undefined' && "
                       "authenticated && document.documentElement.dataset.startup==='ready' && "
                       "byId('image-setup-choose')")
            await tab.click('#image-setup-choose')
            await wait("document.querySelectorAll('[data-plan-visibility=candidate]').length===3")
            assert not state["loads"]
            assert setup_id == await tab.js(
                "new URLSearchParams(location.search).get('models-setup')")
            assert await tab.js("document.querySelector('[data-model-slot=llm]').value.length>0")
            state["scan_root"] = None
            state["pending_files"] = []
            await tab.click('[data-plan-check]')
            await wait("document.querySelectorAll('[data-plan-visibility=not_visible]').length===3")
            assert await tab.js("document.querySelector('[data-native-load]').disabled")
            assert not state["loads"]
            state["scan_root"] = image_root
            await tab.click('[data-plan-check]')
            await wait("document.querySelectorAll('[data-plan-visibility=candidate]').length===3")
            plan_path = host.library.cfg.data_dir / "image-install-plans.json"
            plan_bytes = plan_path.read_bytes()
            plan_path.unlink()
            await tab.click('[data-plan-check]')
            await wait("document.querySelector('[data-plan-detach]')")
            assert not await tab.js("document.querySelector('[data-native-load]')")
            await tab.click('[data-plan-detach]')
            await wait("!document.querySelector('[data-plan-handoff]') && "
                       "byId('role-picker-items').textContent.includes('checkpoint.safetensors')")
            assert not state["loads"]
            plan_path.write_bytes(plan_bytes)
            await tab.js("byId('role-model-picker').close()")
            await tab.click('#image-setup-return')
            await wait("currentView==='store' && byId('store-plan-build')")
            # Old hosts omit the new UI and do not request saved plans.
            await tab.js("latest.image_install_plans=false;"
                         "document.dispatchEvent(new CustomEvent('klaude-snapshot',"
                         "{detail:latest}))")
            await wait("!byId('store-plan-build')")
            await tab.js("latest.image_install_plans=true;"
                         "document.dispatchEvent(new CustomEvent('klaude-snapshot',"
                         "{detail:latest}))")
            await tab.click('#store-detail-back')
            await wait("byId('store-detail').hidden")
            await tab.click('#store-tab-installed')
            await wait("!byId('store-saved-setups').hidden && "
                       "byId('store-saved-setups').querySelector('[data-saved-image-item]')")
            for width in (320, 390, 768, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 900, "deviceScaleFactor": 1, "mobile": width < 600,
                })
                await tab.js("toggleSessions(false);byId('store-saved-setups').scrollIntoView()")
                await asyncio.sleep(.35)
                assert await tab.js("document.documentElement.scrollWidth<=innerWidth && "
                                    "byId('store-saved-setups').scrollWidth<="
                                    "byId('store-saved-setups').clientWidth")
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"readiness-{width}.png").write_bytes(base64.b64decode(shot["data"]))
            await tab.click('#store-saved-setups [data-readiness-focus^=check-setup]')
            await wait("byId('store-saved-setups').textContent.includes('Last check:')")
            await tab.click('#store-saved-setups [data-readiness-focus^=open-setup]')
            await wait("byId('role-model-picker').open && "
                       "document.querySelector('[data-plan-handoff]')")
            assert setup_id == await tab.js(
                "new URLSearchParams(location.search).get('models-setup')")
            assert not state["loads"]
            await tab.js("byId('role-model-picker').close()")
            await tab.click('#image-setup-return')
            await wait("currentView==='store' && !byId('store-saved-setups').hidden")
            await tab.click('#store-saved-setups [data-readiness-focus^=downloads-setup]')
            await wait("byId('store-tab-downloads').getAttribute('aria-pressed')==='true'")
            await tab.js("showView('chat')")
            await tab.click('#chat-create-image')
            await wait("byId('image-generate-panel').open")
            await tab.click('#image-options')
            await wait("byId('image-create-settings').open")
            await tab.js("byId('image-setups-details').open=true")
            await wait("!byId('composer-saved-setups').hidden && "
                       "byId('composer-saved-setups').querySelector('[data-saved-image-item]')")
            await tab.js("byId('image-prompt').value='Keep this inventory draft'")
            await tab.click('#composer-saved-setups [data-readiness-focus^=open-setup]')
            await wait("byId('role-model-picker').open")
            await tab.js("byId('role-model-picker').close()")
            await tab.click('#image-setup-return')
            await wait("byId('image-generate-panel').open")
            assert await tab.js("byId('image-prompt').value==='Keep this inventory draft'")
            assert not state["loads"]
            await tab.js("byId('image-generate-panel').close()")
            await asyncio.sleep(.2)  # Let the closing modal leave the top layer.
            await tab.js("showView('settings',{section:'models'});"
                         "ModelsSettingsNavigation.show('image',{focus:false})")
            await wait("!byId('settings-saved-setups').hidden && "
                       "byId('settings-saved-setups').querySelector('[data-saved-image-item]')")
            await tab.js("byId('image-service-advanced').open=true")
            await tab.js("{const search=byId('settings-saved-setups').querySelector('input');"
                         "search.focus();search.value='no-such-saved-setup';"
                         "search.dispatchEvent(new Event('input'))}")
            await wait("byId('settings-saved-setups').textContent.includes('No matching')")
            assert await tab.js("document.activeElement.dataset.readinessFocus==='search'"), await tab.js(
                "({active:document.activeElement?.outerHTML?.slice(0,400),"
                "search:byId('settings-saved-setups').querySelector('input')?.outerHTML,"
                "dialogs:[...document.querySelectorAll('dialog')].filter(d=>d.open).map(d=>d.id)})")
            await tab.js("{const search=byId('settings-saved-setups').querySelector('input');"
                         "search.value='';search.dispatchEvent(new Event('input'))}")
            await tab.click('#settings-saved-setups [data-readiness-focus^=open-setup]')
            await wait("byId('role-model-picker').open")
            await tab.js("byId('role-model-picker').close()")
            await tab.click('#image-setup-return')
            await wait("currentView==='settings' && !byId('settings-saved-setups').hidden")
            await tab.js("latest.image_readiness_inventory=false;document.dispatchEvent("
                         "new CustomEvent('klaude-snapshot',{detail:latest}))")
            await wait("[...document.querySelectorAll('.image-readiness-inventory')]"
                       ".every(n=>n.hidden)")
            await tab.click('#logout')
            await wait("!authenticated")
            assert await tab.js("[...document.querySelectorAll('.image-readiness-inventory')]"
                                ".every(n=>!n.textContent)")
            errors = [item for item in tab.errors if 'favicon' not in str(item)]
            assert not errors, errors
            print(json.dumps({"shared_readiness_inventory": True, "plan_setup_handoff": True,
                              "saved_plan_reload": True,
                              "download_return_reload": True,
                              "exact_child_transfers": 3, "independent_pause_resume": True,
                              "review_cancellation": True, "correct_categories": True,
                              "responsive_widths": [320, 390, 768, 1440],
                              "console_errors": 0, "screenshots": str(output)}))
    finally:
        dependencies.ComponentNative.gate.set()
        process.terminate()
        process.wait(timeout=5)
        if previous_root is None:
            os.environ.pop("KLAUDE_IMAGE_MODEL_DIR", None)
        else:
            os.environ["KLAUDE_IMAGE_MODEL_DIR"] = previous_root


async def verify_with_server(host, root):
    with dependencies.model_server() as (url, state):
        state["recipes"].append(dependencies.FLUX)
        state["scan_root"] = root / "image-models"
        path = host.library.cfg.config_dir / "image-generation.json"
        settings = json.loads(path.read_text())
        settings["endpoint"] = url
        path.write_text(json.dumps(settings))
        await verify(host, root, state)


if __name__ == '__main__':
    store.Native = PlanNative
    store.main(verify_with_server, admin_lan=True)

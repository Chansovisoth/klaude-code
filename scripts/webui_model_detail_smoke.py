"""Flathub-composed full detail page; isolated metadata and reviewed effects only."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_application import model_store
from webui_control_smoke import Tab
from webui_model_store_smoke import Native
from webui_model_store_smoke import main as fixture_main


async def verify(host, root):
    Native.models = [
        {
            "name": "namespace/" + "long-model-" * 12 + "7b:latest",
            "digest": "a" * 64,
            "size": 4096,
            "details": {"parameter_size": "7B"},
        }
    ]
    Native.gguf_files = [
        {
            "rfilename": ("long-model-" + "x" * 110 + "-Q4_K_M.gguf")
            if i == 0
            else f"model-{i:02}-Q4_K_M.gguf",
            "size": 1024 + i,
        }
        for i in range(25)
    ]
    model_store.CATALOG[0]["summary"] = (
        "A source description with literal model facts and readable paragraphs. " * 12
    )
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    profile = root / "detail-chrome"
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
    output = Path("/tmp/klaude-model-detail-evidence")
    output.mkdir(exist_ok=True)
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(0.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(
            Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        ) as response:
            target = json.load(response)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            if host.accounts:
                await tab.wait("document.documentElement?.dataset.access==='locked'")
                await tab.js(
                    "byId('login-username').value='admin';byId('login-password').value="
                    + json.dumps(host.accounts.initial_password())
                    + ";byId('account-login').requestSubmit()"
                )
            await tab.wait(
                "typeof latest!=='undefined' && authenticated && "
                "document.documentElement.dataset.startup==='ready'"
            )
            await tab.js("showView('store')")
            await tab.wait("byId('store-content').querySelectorAll('.store-feature').length===3")
            await tab.wait("!byId('store-download-open').disabled")
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True},
            )
            await tab.js(
                "byId('store-content').querySelector('.store-row[data-store-model=qwen3]')"
                ".scrollIntoView({block:'center'})"
            )
            before_scroll = await tab.js("byId('store-view').scrollTop")
            await tab.click(".store-row[data-store-model=qwen3]")
            await tab.wait(
                "!byId('store-detail').hidden && byId('store-detail-title').textContent==='Qwen 3'"
            )
            assert await tab.js(
                "byId('store-detail').tagName==='SECTION' && byId('store-panel').hidden && "
                "byId('store-sections').hidden"
            )
            assert await tab.js("!byId('store-variant-list').querySelector('input:checked')")
            await tab.click("#store-detail-install")
            assert not await tab.js("reviewDialog.open") and Native.pulls == 0
            assert await tab.js("document.activeElement.name==='store-variant'")
            await tab.js(
                "[...byId('store-variant-list').querySelectorAll('input')].find(n=>n.value==='qwen3:4b').click()"
            )
            await tab.wait(
                "byId('store-variant-list').querySelector('input:checked')?.value==='qwen3:4b'"
            )
            for width, height in [
                (320, 568),
                (360, 740),
                (390, 844),
                (430, 932),
                (768, 1024),
                (1440, 1000),
            ]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                for theme in ("light", "dark"):
                    await tab.js(
                        "applyAppearance({...appearance,theme:"
                        + json.dumps(theme)
                        + ",reduced:true});byId('store-view').scrollTop=0"
                    )
                    await asyncio.sleep(0.1)
                    assert await tab.js("""(() => {
                      const identity=byId('store-detail-identity').getBoundingClientRect();
                      const logo=byId('store-detail').querySelector('.model-detail-logo')
                        .getBoundingClientRect();
                      const title=byId('store-detail-title').getBoundingClientRect();
                      const action=byId('store-detail-install').getBoundingClientRect();
                      const stats=byId('store-detail-stats').getBoundingClientRect();
                      const about=byId('store-detail-about').getBoundingClientRect();
                      return document.documentElement.scrollWidth<=innerWidth &&
                        byId('store-view').scrollWidth<=byId('store-view').clientWidth &&
                        logo.right<=title.left+1 && identity.bottom<=stats.top+1 &&
                        parseFloat(getComputedStyle(byId('store-detail-title')).fontSize)>=
                          (innerWidth>750 ? 29 : 25) &&
                        stats.bottom<=about.top+1 && about.top-stats.bottom<100 &&
                        !byId('store-detail').querySelector('[aria-roledescription=carousel]') &&
                        (innerWidth>750 ? action.left>title.left : action.width>=identity.width-2);
                    })()"""), (width, theme)
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"detail-{width}-{theme}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width":390, "height":844, "deviceScaleFactor":1, "mobile":True,
            })
            await tab.click("#store-detail-more summary")
            await tab.wait("byId('store-detail-more').open")
            await tab.wait(
                "byId('store-detail-more').querySelector('summary')"
                ".textContent.includes('Show less')"
            )
            await tab.click("#store-detail-back")
            await tab.wait("byId('store-detail').hidden")
            await tab.wait(
                "byId('store-detail').hidden && document.activeElement.dataset.storeModel==='qwen3'"
            )
            # The different viewport clamps scroll; the original viewport must restore its position.
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True},
            )
            await tab.js(
                "byId('store-content').querySelector('.store-row[data-store-model=qwen3]')"
                ".scrollIntoView({block:'center'})"
            )
            before_scroll = await tab.js("byId('store-view').scrollTop")
            await tab.click(".store-row[data-store-model=qwen3]")
            await tab.click("#store-detail-back")
            await tab.wait("byId('store-detail').hidden")
            await asyncio.sleep(0.25)
            await tab.wait("Math.abs(byId('store-view').scrollTop-Math.min("
                           + str(before_scroll) + ",byId('store-view').scrollHeight-"
                           "byId('store-view').clientHeight))<3")
            await tab.js("history.forward()")
            await tab.wait("!byId('store-detail').hidden")
            await tab.js("history.back()")
            await tab.wait("byId('store-detail').hidden")
            await tab.click("#store-tab-installed")
            await tab.click("#store-content .store-row")
            await tab.wait("!byId('store-detail').hidden")
            assert await tab.js(
                "byId('store-detail-title').textContent.length>100 && "
                "document.documentElement.scrollWidth<=innerWidth"
            )
            assert await tab.js("byId('store-detail-stats').textContent.includes('Unknown')")
            await tab.click("#store-detail-back")
            await tab.wait("byId('store-detail').hidden")
            await tab.click("#store-tab-discover")
            await tab.wait("Boolean(byId('store-content').querySelector('.store-ranked-row'))")
            await tab.click(".store-ranked-row")
            await tab.wait("byId('store-variant-list')?.querySelectorAll('input').length===20")
            assert await tab.js("!byId('store-variant-list').querySelector('input:checked')")
            await tab.click("#store-variants-next")
            assert await tab.js("byId('store-variant-list').querySelectorAll('input').length===5")
            await tab.click("#store-variant-list input")
            selected = await tab.js(
                "byId('store-variant-list').querySelector('input:checked').value"
            )
            assert selected.endswith(".gguf") and Native.pulls == 0
            await tab.command("Page.reload")
            await tab.wait(
                "typeof authenticated!=='undefined' && authenticated && "
                "!byId('store-detail').hidden && "
                "Boolean(byId('store-variant-list')?.querySelector('input'))"
            )
            await tab.wait(
                "location.search.includes('models-variant=') && "
                "!byId('store-detail-install').disabled"
            )
            assert selected == await tab.js(
                "new URL(location.href).searchParams.get('models-variant')"
            )
            # A separate repository detail failure must remain a navigable disabled page.
            Native.detail_offline = True
            await tab.js(
                "const u=new URL(location.href);"
                "u.searchParams.set('models-detail','hf:fixture/Offline-GGUF');"
                "u.searchParams.delete('models-variant');history.pushState(history.state,'',u);"
                "dispatchEvent(new PopStateEvent('popstate'))"
            )
            await tab.wait("byId('store-detail-blocker')?.textContent.includes('unavailable')")
            assert await tab.js(
                "byId('store-detail-install').disabled && !byId('store-detail').hidden"
            )
            Native.detail_offline = False
            await tab.js(
                "[...byId('store-detail-body').querySelectorAll('button')]"
                ".find(button=>button.textContent==='Retry source details').click()"
            )
            await tab.wait("byId('store-variant-list')?.querySelectorAll('input').length===20")
            assert Native.pulls == 0
            await tab.command(
                "Emulation.setEmulatedMedia",
                {
                    "features": [
                        {"name": "forced-colors", "value": "active"},
                        {"name": "prefers-reduced-motion", "value": "reduce"},
                    ]
                },
            )
            assert await tab.js("document.documentElement.scrollWidth<=innerWidth")
            await tab.click("#logout")
            await tab.wait("!authenticated")
            assert await tab.js(
                "byId('store-detail').hidden && !byId('store-detail-body').textContent"
            )
            assert Native.pulls == 0 and not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "detail_page": (
                            "hierarchy, exact choice, carousel removed, history, scroll, "
                            "long IDs, paging, reload, offline and logout passed"
                        ),
                        "widths": [320, 360, 390, 430, 768, 1440],
                        "console_errors": 0,
                        "screenshots": str(output),
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    fixture_main(verify, admin_lan=True)

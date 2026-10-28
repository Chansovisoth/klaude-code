"""Stable Diffusion/Ollama Store browser walkthrough with tiny local fixture weights."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

import websockets
import webui_model_store_smoke as store
from webui_control_smoke import Tab

PAYLOAD = b"image-fixture" * 65536
MODEL = "hf.co/fixture/Image:checkpoint.safetensors"


class ImageNative(store.Native):
    transfers = 0
    image_slow = False
    calls = []
    paged_catalog = False

    def do_GET(self):
        ImageNative.calls.append(self.path)
        url = urlsplit(self.path)
        params = parse_qs(url.query)
        if url.path == "/api/models" and ImageNative.paged_catalog:
            tag = params.get("filter", ["gguf"])[0]
            total = 38
            offset = int(params.get("cursor", ["page-0"])[0].rsplit("-", 1)[-1])
            end = min(total, offset + int(params.get("limit", ["20"])[0]))
            rows = []
            for index in range(offset, end):
                name = (
                    "Shared"
                    if index == 1
                    else "Small-GGUF"
                    if tag == "gguf" and index == 0
                    else "Image"
                    if index == 0
                    else f"Chat-{index:02}"
                )
                rows.append(
                    {
                        "id": "fixture/" + name,
                        "downloads": (1000 if tag == "gguf" else 1200) - index,
                        "pipeline_tag": "text-generation" if tag == "gguf" else "text-to-image",
                        "lastModified": "2026-10-28T00:00:00Z",
                    }
                )
            data = json.dumps(rows).encode()
            self.send_response(200)
            if end < total:
                self.send_header(
                    "Link",
                    f'<http://{self.headers["Host"]}/api/models?cursor={tag}-{end}>; rel="next"',
                )
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if url.path == "/api/models" and parse_qs(url.query).get("filter") == ["text-to-image"]:
            self.reply(
                [
                    {
                        "id": "fixture/Image",
                        "downloads": 123,
                        "pipeline_tag": "text-to-image",
                        "lastModified": "2026-10-28T00:00:00Z",
                    }
                ]
            )
        elif url.path == "/api/models/fixture/Image":
            self.reply(
                {
                    "id": "fixture/Image",
                    "sha": "b" * 40,
                    "pipeline_tag": "text-to-image",
                    "cardData": {"license": "mit"},
                    "siblings": [
                        {
                            "rfilename": "checkpoint.safetensors",
                            "lfs": {
                                "size": len(PAYLOAD),
                                "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
                            },
                        }
                    ],
                }
            )
        elif "/resolve/" in url.path:
            ImageNative.transfers += 1
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            try:
                for offset in range(0, len(PAYLOAD), 8192):
                    self.wfile.write(PAYLOAD[offset : offset + 8192])
                    self.wfile.flush()
                    if ImageNative.image_slow:
                        time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            super().do_GET()


async def verify_all(tab, image_root, wait):
    ImageNative.paged_catalog = True
    ImageNative.models = [{"name": "installed:1b", "digest": "a" * 64, "size": 1234}]
    local = image_root / "existing.safetensors"
    local.write_bytes(b"fixture")
    await tab.js(
        "byId('store-runtime').value='all';byId('store-runtime').dispatchEvent(new Event('change'))"
    )
    await wait(
        "byId('store-content').textContent.includes('Stable Diffusion') && "
        "byId('store-content').textContent.includes('Ollama')"
    )
    assert await tab.js("location.search.includes('models-runtime=all')")
    await wait(
        "byId('store-content').querySelectorAll('[data-store-model=\"hf:fixture/Shared\"]').length===2"
    )
    assert await tab.js(
        "new Set([...byId('store-content').querySelectorAll('[data-store-model]')]"
        ".map(n=>n.dataset.storeKey)).size==="
        "byId('store-content').querySelectorAll('[data-store-model]').length"
    )
    for width in (320, 390, 768, 1440):
        await tab.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": 844, "deviceScaleFactor": 1, "mobile": width < 600},
        )
        await asyncio.sleep(0.1)
        assert await tab.js(
            "document.documentElement.scrollWidth<=innerWidth && "
            "byId('store-view').scrollWidth<=byId('store-view').clientWidth"
        )
    await tab.js(
        "byId('store-query').value='fixture';byId('store-query').dispatchEvent(new Event('input'))"
    )
    await wait("!byId('store-live-pages').hidden && !byId('store-live-next').disabled")
    first = await tab.js(
        "[...byId('store-content').querySelectorAll('[data-store-model]')]"
        ".map(n=>n.dataset.storeKey)"
    )
    await tab.click("#store-live-next")
    await wait(
        "byId('store-live-page').textContent==='Page 2' && "
        "byId('store-content').querySelectorAll('[data-store-model]').length>0"
    )
    second = await tab.js(
        "[...byId('store-content').querySelectorAll('[data-store-model]')]"
        ".map(n=>n.dataset.storeKey)"
    )
    assert not set(first) & set(second)
    assert 35 <= len(first) <= 45 and 35 <= len(second) <= 45, (first, second)
    assert len(first) + len(second) == 76, (first, second)
    assert await tab.js(
        "byId('store-live-next').disabled && "
        "!byId('store-content').textContent.includes('unavailable')"
    )
    previous_document = await tab.js("performance.timeOrigin")
    await tab.command("Page.reload")
    await wait(
        f"performance.timeOrigin!=={previous_document} && "
        "typeof byId==='function' && typeof latest!=='undefined' && authenticated && "
        "document.documentElement.dataset.startup==='ready' && "
        "byId('store-live-page').textContent==='Page 2' && "
        "byId('store-content').querySelectorAll('[data-store-model]').length>0"
    )
    assert await tab.js(
        "byId('store-runtime').value==='all' && "
        "!byId('store-content').textContent.includes('unavailable')"
    )
    await tab.click("#store-live-previous")
    await wait("byId('store-live-page').textContent==='Page 1'")
    await tab.click('[data-store-model="hf:fixture/Image"]')
    await wait(
        "byId('store-detail-title').textContent==='Image' && "
        "byId('store-variant-list').querySelectorAll('input').length===1"
    )
    assert await tab.js("location.search.includes('models-runtime=sdcpp')")
    await tab.click("#store-detail-back")
    await wait(
        "byId('store-detail').hidden && byId('store-runtime').value==='all' && "
        "byId('store-content').querySelectorAll('[data-store-model]').length>0"
    )
    await tab.click('[data-store-model="hf:fixture/Small-GGUF"]')
    await wait("byId('store-variant-list').querySelectorAll('input').length===1")
    await tab.click("#store-variant-0")
    await wait("!byId('store-variant-install').disabled")
    await tab.click("#store-variant-install")
    await wait("reviewDialog.open")
    assert await tab.js(
        "managementReview.operation==='model-pull' && "
        "!byId('domain-review-target').textContent.includes('Stable Diffusion')"
    )
    await tab.click("#domain-review-cancel")
    await wait("!reviewDialog.open")
    await tab.click("#store-tab-installed")
    await tab.js(
        "byId('store-runtime').value='all';byId('store-runtime').dispatchEvent(new Event('change'))"
    )
    await wait(
        "byId('store-content').textContent.includes('installed:1b') && "
        "byId('store-content').textContent.includes('existing.safetensors')"
    )
    assert await tab.js("byId('store-tab-installed').querySelector('.tab-count').textContent==='2'")
    moved = image_root.with_name("temporarily-unavailable-models")
    image_root.rename(moved)
    try:
        await tab.click("#store-refresh")
        await wait(
            "byId('store-status').textContent.includes('Some installed models') && "
            "byId('store-content').textContent.includes('installed:1b')"
        )
        assert await tab.js("!byId('store-tab-installed').querySelector('.tab-count')")
    finally:
        moved.rename(image_root)
    await tab.click("#store-refresh")
    await wait("byId('store-content').textContent.includes('existing.safetensors')")
    await tab.click('[data-store-model="existing.safetensors"]')
    await wait("byId('store-detail-install').textContent==='Installed'")
    assert await tab.js(
        "location.search.includes('models-runtime=sdcpp') && byId('store-detail-install').disabled"
    )
    await tab.click("#store-detail-back")
    await wait("byId('store-detail').hidden && byId('store-runtime').value==='all'")
    await tab.click("#store-tab-discover")
    await tab.js(
        "byId('store-runtime').value='ollama';byId('store-runtime')"
        ".dispatchEvent(new Event('change'))"
    )
    ImageNative.paged_catalog = False
    ImageNative.models = []
    local.unlink()
    assert ImageNative.transfers == 0 and ImageNative.pulls == 0


async def verify(host, root):
    image_root = root / "image-models"
    image_root.mkdir()
    os.environ["KLAUDE_IMAGE_MODEL_DIR"] = str(image_root)
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    profile = root / "image-store-chrome"
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
    output = Path("/tmp/klaude-image-model-store-evidence")
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

            async def wait(expression):
                await tab.wait("Boolean(" + expression + ")")

            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            if host.accounts:
                await wait("document.documentElement?.dataset.access==='locked'")
                await tab.js(
                    "byId('login-username').value='admin';byId('login-password').value="
                    + json.dumps(host.accounts.initial_password())
                    + ";byId('account-login').requestSubmit()"
                )
            await wait(
                "typeof latest!=='undefined' && authenticated && "
                "document.documentElement.dataset.startup==='ready'"
            )
            await tab.js("showView('store')")
            await asyncio.sleep(1)
            await wait(
                "byId('store-content').querySelector('[data-store-model=\"hf:fixture/Small-GGUF\"]')"
            )
            await verify_all(tab, image_root, wait)
            await tab.js(
                "byId('store-runtime').value='sdcpp';byId('store-runtime')"
                ".dispatchEvent(new Event('change'))"
            )
            await wait(
                "byId('store-content').querySelector('[data-store-model=\"hf:fixture/Image\"]')"
            )
            assert await tab.js("location.search.includes('models-runtime=sdcpp')")
            assert await tab.js("byId('store-content').textContent.includes('Stable Diffusion')")
            assert ImageNative.transfers == 0
            for width, height in ((320, 568), (390, 844), (768, 1024), (1440, 900)):
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
                        + ",reduced:true})"
                    )
                    await asyncio.sleep(0.1)
                    assert await tab.js(
                        "document.documentElement.scrollWidth<=innerWidth && "
                        "byId('store-view').scrollWidth<=byId('store-view').clientWidth"
                    )
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"discover-{width}-{theme}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
            await tab.click('[data-store-model="hf:fixture/Image"]')
            await wait("byId('store-variant-list').querySelectorAll('input').length===1")
            assert await tab.js("byId('store-detail-install').textContent==='Choose model'")
            await tab.click("#store-variant-install")
            assert ImageNative.transfers == 0 and not await tab.js("reviewDialog.open")
            await tab.click("#store-variant-0")
            await wait("!byId('store-variant-install').disabled")
            # Full detail reload restores the SD catalog and exact selected file.
            previous_document = await tab.js("performance.timeOrigin")
            await tab.command("Page.reload")
            await wait(
                f"performance.timeOrigin!=={previous_document} && "
                "typeof byId==='function' && typeof latest!=='undefined' && authenticated && "
                "document.documentElement.dataset.startup==='ready' && "
                "byId('store-variant-list')?.querySelector('input:checked')"
            )
            assert await tab.js("byId('store-detail-title').textContent==='Image'")
            for width in (320, 390, 1440):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": 844, "deviceScaleFactor": 1, "mobile": width < 600},
                )
                await asyncio.sleep(0.1)
                assert await tab.js(
                    "document.documentElement.scrollWidth<=innerWidth && "
                    "byId('store-view').scrollWidth<=byId('store-view').clientWidth"
                )
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"detail-{width}.png").write_bytes(base64.b64decode(shot["data"]))
            await tab.click("#store-variant-install")
            await wait("reviewDialog.open")
            assert await tab.js(
                "byId('domain-review-title').textContent==='Download model?' && "
                "byId('domain-review-target').textContent.includes('Local Stable Diffusion')"
            )
            assert ImageNative.transfers == 0
            ImageNative.image_slow = True
            await tab.click("#domain-review-confirm")
            await wait("byId('store-content').querySelector('[data-download-action=stop]')")
            await wait(
                "[...byId('store-content').querySelectorAll('.store-download-status')]"
                ".some(node=>node.textContent.includes(' / '))"
            )
            await tab.click("[data-download-action=stop]")
            await wait("!byId('store-content').querySelector('[data-download-action=stop]')")
            for _ in range(100):
                if not host.library.model_busy():
                    break
                await asyncio.sleep(0.05)
            assert not host.library.model_busy()
            assert not list(image_root.rglob("*.part"))
            ImageNative.image_slow = False
            await tab.click("#store-tab-discover")
            await tab.click('[data-store-model="hf:fixture/Image"]')
            await wait("byId('store-variant-list').querySelectorAll('input').length===1")
            await tab.click("#store-variant-0")
            await wait("!byId('store-variant-install').disabled")
            await tab.click("#store-variant-install")
            await wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await wait("byId('store-content').textContent.includes('Complete')")
            saved = image_root / "checkpoints/fixture/Image/checkpoint.safetensors"
            assert saved.read_bytes() == PAYLOAD
            await tab.click("#store-tab-installed")
            await wait("byId('store-content').textContent.includes('checkpoint.safetensors')")
            await tab.click('[data-store-model="hf.co/fixture/Image:checkpoint.safetensors"]')
            assert await tab.js(
                "byId('store-detail-install').textContent==='Installed' && "
                "byId('store-detail-install').disabled"
            )
            assert not await tab.js("byId('store-detail-body').textContent.includes('Use model')")
            await tab.click("#store-detail-back")
            await wait("byId('store-detail').hidden")
            # Switching back reloads the Ollama catalog rather than reusing SD entries.
            await tab.js(
                "byId('store-runtime').value='ollama';byId('store-runtime')"
                ".dispatchEvent(new Event('change'))"
            )
            await tab.click("#store-tab-discover")
            await wait(
                "byId('store-content').querySelector('[data-store-model=\"hf:fixture/Small-GGUF\"]')"
            )
            assert not await tab.js(
                "byId('store-content').textContent.includes('Stable Diffusion')"
            )
            assert store.Native.pulls == 0
            # A runtime restored on an older host shows guidance without unsupported reads.
            await asyncio.sleep(0.2)
            before_legacy = len(ImageNative.calls)
            await tab.js(
                "latest.model_store_sdcpp=true;delete latest.model_store_sdcpp_revision;"
                "const u=new URL(location.href);"
                "u.searchParams.set('models-runtime','sdcpp');"
                "u.searchParams.set('models-detail','hf:fixture/Image');"
                "history.replaceState({},'',u);"
                "ModelStoreUI.restoreFromLocation()"
            )
            assert await tab.js("byId('store-status').textContent.includes('Restart')")
            await asyncio.sleep(0.25)
            assert len(ImageNative.calls) == before_legacy
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "responsive_widths": [320, 390, 768, 1440],
                        "fixture_transfers": ImageNative.transfers,
                        "console_errors": 0,
                        "cancel_retry_install": True,
                        "detail_reload": True,
                        "all_runtime": True,
                        "screenshots": str(output),
                    }
                )
            )
    finally:
        ImageNative.image_slow = False
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    previous_root = os.environ.get("KLAUDE_IMAGE_MODEL_DIR")
    store.Native = ImageNative
    try:
        store.main(verify, admin_lan=True)
    finally:
        if previous_root is None:
            os.environ.pop("KLAUDE_IMAGE_MODEL_DIR", None)
        else:
            os.environ["KLAUDE_IMAGE_MODEL_DIR"] = previous_root

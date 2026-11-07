"""Responsive Store presentation checks on isolated, synthetic catalogs and receipts.

No model downloads, production profile reads, installation or inference.
Run with uv run python scripts/webui_store_layout_smoke.py.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

import websockets
from klaude_application.integration_store import IntegrationStore
from webui_control_smoke import Tab
from webui_model_store_smoke import Native
from webui_model_store_smoke import main as fixture_main

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_integration_store import transport  # noqa: E402

CAPTURES = Path(__file__).resolve().parents[1] / "output/playwright/store-overhaul"
CATALOG = [
    ("Qwen/Qwen3.5-4B-GGUF", "text-generation"),
    ("unsloth/Llama-3.3-70B-Instruct-GGUF", "text-generation"),
    ("mistralai/Ministral-3-8B-GGUF", "text-generation"),
    ("google/gemma-3-4b-it-GGUF", "image-text-to-text"),
    ("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B-GGUF", "text-generation"),
    ("Qwen/Qwen2.5-Coder-7B-Instruct-GGUF", "text-generation"),
]
original_get = Native.do_GET


def catalog_get(self):
    path = urlsplit(self.path).path
    if path == "/api/models":
        rows = CATALOG
        if parse_qs(urlsplit(self.path).query).get("filter") == ["text-to-image"]:
            rows = [
                ("stabilityai/stable-diffusion-v1-5", "text-to-image"),
                ("stabilityai/stable-diffusion-xl-base-1.0", "text-to-image"),
            ]
        self.reply(
            [
                {
                    "id": name,
                    "downloads": 124_500 - index * 12_250,
                    "pipeline_tag": task,
                    "lastModified": "2026-11-03T00:00:00Z",
                }
                for index, (name, task) in enumerate(rows)
            ]
        )
    elif path.startswith("/api/models/") and not path.startswith("/api/models/fixture/"):
        self.reply(
            {
                "id": path.removeprefix("/api/models/"),
                "cardData": {"license": "apache-2.0"},
                "siblings": [{"rfilename": "model-Q4_K_M.gguf", "size": 2_800_000_000}],
            }
        )
    else:
        original_get(self)


async def verify(host, root):
    image_root = root / "image-models"
    image_root.mkdir()
    os.environ["KLAUDE_IMAGE_MODEL_DIR"] = str(image_root)
    host.library.integration_store = IntegrationStore(host.library.cfg, transport=transport({}))
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    profile = root / "store-layout-chrome"
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
    CAPTURES.mkdir(parents=True, exist_ok=True)
    checks = []
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

            async def wait(expression):
                expression = "Boolean(" + expression + ")"
                for _ in range(400):
                    if await tab.js(expression):
                        return
                    await asyncio.sleep(0.05)
                await tab.wait(expression)

            async def capture(name):
                await asyncio.sleep(0.15)
                result = await tab.js("""(() => {
                  const view=byId('store-view'),main=byId('store-main');
                  const visible=n=>n.getClientRects().length>0;
                  const bounded=n=>n.scrollWidth<=n.clientWidth+1;
                  return {page:document.documentElement.scrollWidth<=innerWidth,
                    view:bounded(view),main:bounded(main),
                    cards:[...view.querySelectorAll('.store-row,.store-download-row,.model-variant-row')]
                      .filter(visible).every(bounded),
                    controls:[...view.querySelectorAll('.store-download-actions button')]
                      .filter(visible).every(n=>n.offsetWidth>=44&&n.offsetHeight>=44)};
                })()""")
                assert all(result.values()), (name, result)
                checks.append(name)
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (CAPTURES / f"{name}.png").write_bytes(base64.b64decode(shot["data"]))

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
            for theme in ("light", "dark"):
                for width in (1440, 768, 390, 320):
                    await tab.command(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": width,
                            "height": 960 if width > 600 else 844,
                            "deviceScaleFactor": 1,
                            "mobile": width < 600,
                        },
                    )
                    await tab.js(
                        "applyAppearance({...appearance,reduced:true,theme:"
                        + json.dumps(theme)
                        + "},false)"
                    )
                    await tab.js("StoreDesign.route('all')")
                    await wait("byId('store-content').querySelector('[data-store-model]')")
                    await capture(f"explore-{width}-{theme}")
                    await tab.js("StoreDesign.route('ollama')")
                    await wait("byId('store-content').querySelector('[data-store-model]')")
                    await capture(f"catalog-{width}-{theme}")
                    await tab.click("#store-content [data-store-model]")
                    await wait("!byId('store-detail').hidden&&byId('store-variant-0')")
                    await capture(f"details-{width}-{theme}")
                    await tab.click("#store-variant-0")
                    await wait(
                        "byId('store-variant-0').checked&&!byId('store-detail-install').disabled"
                    )
                    await tab.click("#store-detail-install")
                    await wait("reviewDialog.open")
                    await tab.click("#domain-review-cancel")
                    await wait("!reviewDialog.open&&byId('store-variant-0').checked")
                    await tab.js("StoreDesign.route('ollama','installed')")
                    await wait("byId('store-content').querySelector('.store-installed-size')")
                    await capture(f"installed-{width}-{theme}")
                    await tab.js("StoreDesign.route('all','downloads')")
                    await wait("byId('store-content').textContent.includes('No downloads yet')")
                    await capture(f"downloads-empty-{width}-{theme}")

            # Populated receipts are supplied by the fixture reader, never admitted work.
            host.library.model_jobs = lambda: {
                "items": [
                    {
                        "request_id": f"layout-{index}",
                        "kind": "model-image-download",
                        "model": name,
                        "state": state,
                        "paused": state == "cancelled",
                        "cancellable": state == "running",
                        "progress": progress,
                        "message": "The source connection closed. Resume to continue."
                        if state == "failed"
                        else "",
                    }
                    for index, (name, state, progress) in enumerate(
                        [
                            ("sd-v1-5.safetensors", "completed", {}),
                            (
                                "qwen-image-very-long-checkpoint-name-Q4_K_M.gguf",
                                "running",
                                {"completed": 1_350_000_000, "total": 4_270_000_000},
                            ),
                            ("flux-model.safetensors", "failed", {}),
                            ("image-model.safetensors", "unknown", {}),
                            ("paused-image-model.safetensors", "cancelled", {}),
                        ]
                    )
                ],
                "observed": [],
            }
            await wait("byId('store-content').querySelectorAll('.store-download-row').length===5")
            for theme in ("light", "dark"):
                for width in (1440, 768, 390, 320):
                    await tab.command(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": width,
                            "height": 960 if width > 600 else 844,
                            "deviceScaleFactor": 1,
                            "mobile": width < 600,
                        },
                    )
                    await tab.js(
                        "applyAppearance({...appearance,reduced:true,theme:"
                        + json.dumps(theme)
                        + "},false)"
                    )
                    await capture(f"downloads-{width}-{theme}")
                    assert await tab.js(
                        "byId('store-content').querySelector('.store-download-row').dataset.state==='running'"
                    )
                    await tab.click("[data-download-action=info]")
                    await wait("byId('store-download-info').open")
                    await tab.click("#store-download-info-close")
                    await wait("!byId('store-download-info').open")
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "layouts": len(checks),
                        "widths": [320, 390, 768, 1440],
                        "themes": ["light", "dark"],
                        "review_cancel": True,
                        "download_details": True,
                        "console_errors": 0,
                        "screenshots": str(CAPTURES),
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    Native.do_GET = catalog_get
    Native.models = [
        {"name": name, "digest": "a" * 64, "size": size, "details": {"parameter_size": params}}
        for name, size, params in [
            ("qwen3.5:4b", 2_800_000_000, "4B"),
            ("gemma3:4b", 3_300_000_000, "4B"),
            ("deepseek-r1:7b", 4_700_000_000, "7B"),
            ("qwen2.5-coder-with-a-long-local-name:7b", 4_700_000_000, "7B"),
        ]
    ]
    fixture_main(verify, admin_lan=True)

"""Explicit image dependency offers, real owned transfers and metadata rescans."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import websockets
import webui_model_store_smoke as store
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from klaude_application.image_dependencies import FLUX3  # noqa: E402

from tests.unit.test_image_dependencies import FLUX  # noqa: E402
from tests.unit.test_image_model_selection import model_server  # noqa: E402

PAYLOAD = b"dependency-fixture" * 65536
REVISION = "b" * 40
SHA = hashlib.sha256(PAYLOAD).hexdigest()


class ComponentNative(store.Native):
    transfers = []
    gate = threading.Event()
    ranges = []

    def do_GET(self):
        path = urlsplit(self.path).path
        for _, repo, filename, _ in FLUX3.values():
            if path == f"/api/models/{repo}":
                self.reply({"id": repo, "sha": REVISION, "siblings": [
                    {"rfilename": filename, "lfs": {"size": len(PAYLOAD), "sha256": SHA}},
                ]})
                return
            if path == f"/{repo}/resolve/{REVISION}/{filename}":
                ComponentNative.transfers.append(path)
                start = 0
                if self.headers.get("Range"):
                    ComponentNative.ranges.append(self.headers["Range"])
                    start = int(self.headers["Range"].split("=")[1].split("-")[0])
                self.send_response(206 if start else 200)
                if start:
                    self.send_header("Content-Range",
                                     f"bytes {start}-{len(PAYLOAD)-1}/{len(PAYLOAD)}")
                self.send_header("Content-Length", str(len(PAYLOAD) - start))
                self.end_headers()
                try:
                    payload = PAYLOAD[start:]
                    self.wfile.write(payload[:256*1024])
                    self.wfile.flush()
                    ComponentNative.gate.wait(timeout=30)
                    self.wfile.write(payload[256*1024:])
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
        super().do_GET()


async def verify(host, root):
    image_root = root / "image-models"
    primary = image_root / "diffusion_models/fixture/flux.gguf"
    primary.parent.mkdir(parents=True)
    primary.write_bytes(b"installed-primary")
    previous_root = os.environ.get("KLAUDE_IMAGE_MODEL_DIR")
    os.environ["KLAUDE_IMAGE_MODEL_DIR"] = str(image_root)
    with model_server() as (url, state):
        state["recipes"].append(FLUX)
        state["scan_root"] = image_root
        try:
            await browse(host, root, url, state, image_root)
        finally:
            ComponentNative.gate.set()
            if previous_root is None:
                os.environ.pop("KLAUDE_IMAGE_MODEL_DIR", None)
            else:
                os.environ["KLAUDE_IMAGE_MODEL_DIR"] = previous_root


async def browse(host, root, url, state, image_root):
    chrome = str(next((Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
        "*/chrome-headless-shell-linux64/chrome-headless-shell")))
    profile = root / "dependency-chrome"
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
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait("document.documentElement?.dataset.access==='locked'")
            await tab.js("byId('login-username').value='admin';byId('login-password').value="
                         + json.dumps(host.accounts.initial_password())
                         + ";byId('account-login').requestSubmit()")
            await tab.wait("typeof latest!=='undefined'&&authenticated&&"
                           "document.documentElement.dataset.startup==='ready'")
            await tab.js("showView('settings',{section:'models'})")
            await tab.wait("byId('models-image-summary').textContent.length>0")
            await tab.click('[data-model-screen=image]')
            await tab.js("byId('image-service-provider').value='sdcpp';"
                         "byId('image-service-provider').dispatchEvent(new Event('change'));"
                         "byId('image-service-url').value=" + json.dumps(url) + ";"
                         "byId('image-service-url').dispatchEvent(new Event('input'))")
            await tab.click('#image-service-model-name-picker')
            await tab.wait("byId('role-picker-items').textContent.includes('fixture/flux.gguf')")
            await tab.js("[...byId('role-picker-items').querySelectorAll('button')]"
                         ".find(n=>n.textContent.includes('fixture/flux.gguf')).click()")
            await tab.js("const setup=document.querySelector('[data-native-recipe]');"
                         "setup.value='flux3-klein';setup.dispatchEvent(new Event('change'))")
            try:
                await tab.wait("Boolean(document.querySelector('[data-install-dependency=llm]'))")
            except AssertionError:
                print("Dependency UI:", await tab.js("byId('role-model-picker').textContent"))
                print("Metadata URL:", host.library.cfg.huggingface_base_url)
                raise
            assert not ComponentNative.transfers and not state["loads"]
            for width in (320, 390, 768, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 900, "deviceScaleFactor": 1, "mobile": width < 600,
                })
                assert await tab.js("byId('role-model-picker').scrollWidth <= "
                                    "byId('role-model-picker').clientWidth")
            for slot in ("llm", "vae"):
                await tab.wait(f"document.querySelector('[data-install-dependency={slot}]')"
                               "?.textContent==='Install'")
                await tab.click(f'[data-install-dependency={slot}]')
                await tab.wait("reviewDialog.open")
                assert not state["loads"]
                # Cancelling the offer does not download anything.
                if slot == "llm":
                    await tab.click('#domain-review-cancel')
                    await tab.wait("!reviewDialog.open")
                    assert not ComponentNative.transfers
                    await tab.click(f'[data-install-dependency={slot}]')
                    await tab.wait("reviewDialog.open")
                await tab.click('#domain-review-confirm')
                await tab.wait(f"Boolean(document.querySelector("
                               f"'[data-dependency-control=pause][data-slot={slot}]'))")
                if slot == "llm":
                    assert await tab.js(
                        "!document.querySelector('[data-install-dependency=vae]').disabled"
                    )
            for _ in range(100):
                if len(ComponentNative.transfers) == 2:
                    break
                await asyncio.sleep(.05)
            assert len(ComponentNative.transfers) == 2
            assert len([item for item in host.library.model_jobs()["items"]
                        if item["state"] == "running"]) == 2
            await tab.click('[data-dependency-control=pause][data-slot=llm]')
            await tab.wait("Boolean(document.querySelector("
                           "'[data-dependency-control=resume][data-slot=llm]'))")
            assert await tab.js("Boolean(document.querySelector("
                                "'[data-dependency-control=pause][data-slot=vae]'))")
            await tab.click('[data-dependency-control=resume][data-slot=llm]')
            for _ in range(100):
                if ComponentNative.ranges:
                    break
                await asyncio.sleep(.05)
            assert ComponentNative.ranges and ComponentNative.ranges[-1] != 'bytes=0-'
            ComponentNative.gate.set()
            await tab.wait("document.querySelector('[data-model-slot=llm]').value.length>0 && "
                           "document.querySelector('[data-model-slot=vae]').value.length>0")
            assert await tab.js("!document.querySelector('[data-native-load]').disabled")
            assert not state["loads"] and len(ComponentNative.transfers) == 3
            for _, repo, filename, category in FLUX3.values():
                assert (image_root / category / repo / filename).read_bytes() == PAYLOAD
            errors = [item for item in tab.errors if 'favicon' not in str(item)]
            assert not errors, errors
            print(json.dumps({"explicit_dependency_reviews": 2, "fixture_transfers": 3,
                              "parallel_workers": 2, "independent_pause_resume": True,
                              "auto_select_installed_components": True,
                              "cancel_does_not_download": True, "correct_categories": True,
                              "picker_refresh": True, "automatic_loads": 0,
                              "responsive_widths": [320, 390, 768, 1440], "console_errors": 0}))
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    store.Native = ComponentNative
    store.main(verify, admin_lan=True)

"""Live managed ComfyUI browser check against an explicitly prepared /tmp profile.

Run after the development installer has materialized the bundle in this profile:
  .venv/bin/python scripts/webui_comfyui_smoke.py --profile /tmp/klaude-comfy-live-profile
The script changes only this test profile's defaults and generates one real image.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_application.library_management import LibraryManagement
from klaude_core import comfyui_managed as managed
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_core.image_generation import history, read, save
from klaude_core.settings_store import atomic_write_private, read_settings
from klaude_tools import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab
from webui_model_store_smoke import Native

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402


async def verify(
    host, root, *, layout_only=False, exercise_install=False, custom=None, remote_custom=False
):
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    import tempfile

    profile = Path(tempfile.mkdtemp(prefix="comfy-live-chrome-", dir=root))
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
    captures = Path("/tmp/klaude-comfyui-evidence")
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
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait("document.documentElement?.dataset.access==='locked'")
            await tab.js(
                "byId('login-username').value='admin';byId('login-password').value="
                + json.dumps(host.accounts.initial_password())
                + ";byId('account-login').requestSubmit()"
            )
            await tab.wait(
                "typeof showView==='function' && "
                "typeof setupReloadWitness==='undefined' && "
                "typeof latest!=='undefined' && authenticated && "
                "document.documentElement.dataset.startup==='ready'"
            )
            await tab.js("showView('store')")
            await tab.wait(
                "Boolean(byId('store-image-bundles').querySelector('[data-bundle-install]'))"
            )
            await tab.js("byId('store-image-bundles').querySelector('[data-bundle-install]').closest('details')?.setAttribute('open','')")
            await tab.click("#store-image-bundles [data-bundle-install]")
            await tab.wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-summary').textContent.includes('SHA-256')")
            await tab.click("#domain-review-cancel")
            await tab.wait(
                "byId('store-image-bundles').querySelector('[data-bundle-install]')?.disabled===false"
            )
            assert read(host.library.cfg).get("provider", "sdcpp") == "sdcpp"
            if exercise_install:

                async def until(expression):
                    for _ in range(180):
                        if await tab.js(expression):
                            return
                        await asyncio.sleep(0.5)
                    raise AssertionError(expression)

                await tab.click("#store-image-bundles [data-bundle-install]")
                await tab.wait("reviewDialog.open")
                await tab.click("#domain-review-confirm")
                await until(
                    "(async()=>{const d=await domainRequest("
                    "'/api/v1/settings/models/image-bundles','POST',{action:'list'});"
                    "return d.pending?.state==='running';})()"
                )
                await until(
                    "[...byId('store-image-bundles').querySelectorAll('button')].some(b=>b.textContent==='Pause')"
                )
                await tab.js(
                    "[...byId('store-image-bundles').querySelectorAll('button')].find(b=>b.textContent==='Pause').click()"
                )
                await until(
                    "[...byId('store-image-bundles').querySelectorAll('button')]"
                    ".some(b=>b.textContent==='Check installation'&&!b.disabled)"
                )
                await tab.js(
                    "[...byId('store-image-bundles').querySelectorAll('button')]"
                    ".find(b=>b.textContent==='Check installation').click()"
                )
                await tab.wait("reviewDialog.open")
                await tab.click("#domain-review-confirm")
                await until(
                    "Boolean(byId('store-image-bundles').querySelector('[data-bundle-install]:not(:disabled)'))"
                )
                await tab.click("#store-image-bundles [data-bundle-install]")
                await tab.wait("reviewDialog.open")
                await tab.click("#domain-review-confirm")
                await until(
                    "Boolean(byId('store-image-bundles').querySelector('[data-bundle-choose]:not(:disabled)'))"
                )
                assert read(host.library.cfg).get("provider", "sdcpp") == "sdcpp"
                print(json.dumps({"install_pause_check_continue": "passed"}), flush=True)
            if custom:
                await tab.js(
                    "ManagedImageBundles.install("
                    + json.dumps(custom["source"])
                    + (",false" if remote_custom else "")
                    + ")"
                )
                await tab.wait("reviewDialog.open")
                assert await tab.js(
                    "byId('domain-review-summary').textContent.includes('embedded text encoder')"
                )
                await tab.click("#domain-review-confirm")
                for _ in range(240):
                    if await tab.js(
                        "Boolean(document.querySelector('[data-managed-model=\""
                        + custom["id"]
                        + "\"] [data-bundle-choose]:not(:disabled)'))"
                    ):
                        break
                    await asyncio.sleep(0.5)
                await tab.click('[data-managed-model="' + custom["id"] + '"] [data-bundle-choose]')
            else:
                await tab.click("#store-image-bundles [data-bundle-choose]")
            await tab.wait(
                "byId('image-service-provider').value==='comfyui' && "
                "!byId('image-service-save-bar').hidden"
            )
            assert read(host.library.cfg).get("provider", "sdcpp") == "sdcpp"
            assert await tab.js(
                "!byId('image-service-advanced').open && "
                "byId('image-service-url').closest('.setting-row').hidden"
            )
            await tab.click("#image-service-model-name-picker")
            await tab.wait("byId('role-picker-items').textContent.includes('Stable Diffusion 1.5')")
            for width in (320, 390, 768, 1440):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 900,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                assert await tab.js(
                    "byId('role-model-picker').scrollWidth<=byId('role-model-picker').clientWidth"
                )
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (captures / f"picker-{width}.png").write_bytes(base64.b64decode(shot["data"]))
            await tab.click("#role-picker-items .store-row")
            await tab.click("#image-service-save-bar #image-service-save")
            for _ in range(150):
                if read(host.library.cfg).get("provider", "sdcpp") == "comfyui":
                    break
                await asyncio.sleep(0.1)
            assert read(host.library.cfg).get("provider", "sdcpp") == "comfyui"
            await tab.wait("byId('image-service-save-bar').hidden")
            await tab.command("Page.reload")
            await asyncio.sleep(0.3)
            await tab.wait(
                "typeof authenticated!=='undefined' && authenticated && "
                "document.documentElement.dataset.startup==='ready'"
            )
            await tab.js(
                "showView('settings',{section:'models'});ModelsSettingsNavigation.show('image')"
            )
            await tab.wait("byId('image-service-provider').value==='comfyui'")
            for width in (320, 390, 768, 1440):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 900,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                await asyncio.sleep(0.15)
                await tab.js("toggleSessions(false)")
                await asyncio.sleep(0.4)
                assert await tab.js("document.documentElement.scrollWidth<=innerWidth")
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (captures / f"settings-{width}.png").write_bytes(base64.b64decode(shot["data"]))
            if layout_only:
                assert not tab.errors, tab.errors
                print(json.dumps({"layout": "passed", "console_errors": 0}))
                return
            await tab.js("showView('library')")
            await tab.click("[data-section=outputs]")
            await tab.wait("!byId('image-add').disabled")
            await tab.click("#image-add")
            await tab.wait("!byId('image-generate').querySelector('button[type=submit]').disabled")
            prior = {item["job"] for item in history(host.library.cfg)["items"]}
            await tab.js(
                "byId('image-reset-options').click();byId('image-prompt').value="
                "'A red cabin beside a lake, watercolor';byId('image-seed').value='84';"
                "byId('image-generate').requestSubmit()"
            )
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            for _ in range(600):
                complete = any(
                    item["job"] not in prior and item["status"] == "complete"
                    for item in history(host.library.cfg)["items"]
                )
                if complete and await tab.js(
                    "byId('image-jobs').textContent.includes('Completed') && "
                    "!BrowserManagement.hasPending()"
                ):
                    break
                await asyncio.sleep(0.5)
            assert complete
            assert await tab.js(
                "byId('image-jobs').textContent.includes('Completed') && "
                "!BrowserManagement.hasPending()"
            )
            if custom:
                assert read(host.library.cfg)["model"] == custom["id"]
                # Select a different default before reviewing shared-file removal.
                await tab.js(
                    "showView('settings',{section:'models'});ModelsSettingsNavigation.show('image')"
                )
                await tab.wait("byId('image-service-provider').value==='comfyui'")
                await tab.click("#image-service-model-name-picker")
                await tab.wait(
                    "byId('role-picker-items').querySelectorAll('.store-row').length===2"
                )
                await tab.click("#role-picker-unset")
                await tab.click("#image-service-save-bar #image-service-save")
                for _ in range(100):
                    if read(host.library.cfg)["model"] == "":
                        break
                    await asyncio.sleep(0.1)
                await tab.wait("byId('image-service-save-bar').hidden")
                await tab.js("showView('store')")
                await tab.wait(
                    "Boolean(document.querySelector('[data-managed-model=\""
                    + custom["id"]
                    + "\"]'))"
                )
                await tab.js(
                    "[...document.querySelector('[data-managed-model=\""
                    + custom["id"]
                    + "\"]').querySelectorAll('button')]"
                    ".find(b=>b.textContent==='Remove model').click()"
                )
                await tab.wait("reviewDialog.open")
                assert await tab.js(
                    "byId('domain-review-summary').textContent"
                    ".includes('shared and will be retained')"
                )
                await tab.click("#domain-review-confirm")
                for _ in range(100):
                    if read_settings(managed.record_path(host.library.cfg, custom["id"])).get(
                        "removed_by"
                    ):
                        break
                    await asyncio.sleep(0.1)
                assert read_settings(managed.record_path(host.library.cfg, custom["id"])).get(
                    "removed_by"
                )
                assert custom["path"].exists() and managed.model_path(host.library.cfg).exists()
                print(
                    json.dumps({"custom_store_install_select_generate_remove": "passed"}),
                    flush=True,
                )
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "live_generation": "passed",
                        "review_cancel": "passed",
                        "choose_apply_reload": "passed",
                        "widths": [320, 390, 768, 1440],
                        "console_errors": 0,
                        "screenshots": str(captures),
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--layout-only", action="store_true")
    parser.add_argument("--exercise-install", action="store_true")
    parser.add_argument("--exercise-custom", action="store_true")
    parser.add_argument("--remote-custom", action="store_true")
    args = parser.parse_args()
    root = args.profile.resolve()
    if not root.is_relative_to("/tmp") or not (root / "data/comfyui/installed.json").is_file():
        parser.error("Use an explicitly prepared managed ComfyUI test profile under /tmp")
    config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
    cfg = Config()
    if args.exercise_install:
        if managed.file_hash(managed.model_path(cfg)) != managed.CONTROL.sha256:
            parser.error("The test profile needs the exact previously verified checkpoint")
    else:
        managed.installed(cfg, full=True)
    custom = None
    if args.exercise_custom:
        from klaude_application import image_model_store, model_store
        from klaude_application.operation_journal import OperationJournal

        directory = root / "store-weights"
        directory.mkdir(exist_ok=True)
        os.environ["KLAUDE_IMAGE_MODEL_DIR"] = str(directory)
        b = managed.CONTROL
        source_model = f"hf.co/{b.repository}:{b.filename}"
        path = directory / "checkpoints" / b.repository / b.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            shutil.copyfile(managed.model_path(cfg), path)
        assert managed.file_hash(path) == b.sha256
        st = directory.stat()
        fields = {
            "endpoint": "image:sdcpp",
            "model": source_model,
            "root": str(directory),
            "root_device": st.st_dev,
            "root_inode": st.st_ino,
            "repo": b.repository,
            "filename": b.filename,
            "revision": b.revision,
            "sha256": b.sha256,
            "size": b.size,
            "base_url": "https://huggingface.co",
        }
        journal = OperationJournal(cfg.data_dir / "operations.db")
        rid = uuid.uuid4().hex
        receipt = journal.admit(
            request_id=rid,
            owner_id="web-admin",
            kind="model-image-download",
            resource=image_model_store.resource(fields),
            payload=fields,
        )
        journal.record_witness(
            rid,
            "web-admin",
            receipt.fence,
            before=model_store.witness(fields, False),
            after=model_store.witness(fields, True),
        )
        journal.start(rid, "web-admin", receipt.fence)
        journal.finish(rid, "web-admin", receipt.fence, state="completed", outcome="ok")
        target = model_store.target_path(cfg, rid)
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_private(target, json.dumps(fields))
        custom = {"id": "checkpoint-" + b.sha256 + "@1", "path": path, "source": source_model}
    native = ThreadingHTTPServer(("127.0.0.1", 0), Native)
    threading.Thread(target=native.serve_forever, daemon=True).start()
    cfg.ollama_url = f"http://127.0.0.1:{native.server_port}"
    (cfg.config_dir / "config.toml").write_text(f'[services]\nollama_url="{cfg.ollama_url}"\n')
    settings = read(cfg)
    save(
        cfg,
        {"enabled": False, "endpoint": "", "model": "", "provider": "sdcpp"},
        settings["revision"],
    )
    app = _app(cfg.data_dir)
    app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
    app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
    service = LibraryManagement(cfg, root)
    accounts = AccountStore(cfg.config_dir)
    accounts.initialize()
    host = LocalWebHost(app, library=service, accounts=accounts)
    host.http.host_lan = True
    host.local_models = lambda: []
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        asyncio.run(
            verify(
                host,
                root,
                layout_only=args.layout_only,
                exercise_install=args.exercise_install,
                custom=custom,
                remote_custom=args.remote_custom,
            )
        )
    finally:
        host.stop()
        thread.join(timeout=3)
        native.shutdown()
        native.server_close()


if __name__ == "__main__":
    main()

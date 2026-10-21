"""Real Chrome device/Library attachment checks with an isolated model fixture.

Run: uv run --frozen --offline python scripts/webui_attachments_smoke.py
Optional: KLAUDE_TEST_CHROME=/path/to/headless-chrome
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_application.chat_attachments import ChatAttachmentInput, prepare_attachment
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_core.session_runtime import capture
from klaude_tools.toolkit import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Fixture, Tab


class AttachmentFixture(Fixture):
    def __init__(self):
        super().__init__()
        self.messages = []

    def chat(self, model, messages, **kwargs):
        self.messages = list(messages)
        return super().chat(model, messages, **kwargs)


async def verify(host, root, chrome, fixture):
    profile = root / "chrome"
    output = Path("/tmp/klaude-attachments-preview")
    output.mkdir(exist_ok=True)
    process = subprocess.Popen([
        chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            await asyncio.sleep(.05)
        port = int(active.read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId !== "undefined" && !byId("local-access").hidden')
            await tab.js('byId("login-password").value=' + json.dumps(
                host.accounts.initial_password()
            ) + ';byId("account-login").requestSubmit()')
            await tab.wait('latest?.attachments && !byId("attach-file").disabled')
            await tab.wait('document.querySelector(".message-attachments img")?.naturalWidth > 0')
            assert await tab.js('document.querySelector(".message-prompt").textContent === '
                                '"Tell me what you see"')
            assert await tab.js('!document.querySelector(".message-body").textContent'
                                '.includes("[Attached files:")')
            await tab.js('window.savedThumbnail=document.querySelector(".message-attachments img");'
                         'snapshot()')
            await asyncio.sleep(.2)
            assert await tab.js('savedThumbnail.isConnected')
            # Updated static assets must explain a missing/older backend, rather
            # than leaving an enabled paperclip with no click handler.
            await tab.js('latest.attachments=false;ChatAttachmentsUI.refresh()')
            assert await tab.js('byId("attach-file").disabled && '
                                'byId("chat-attachment-status").textContent'
                                '.includes("server update")')
            await tab.js('latest.attachments=true;ChatAttachmentsUI.refresh();'
                         'window.savedAttachmentsUI=ChatAttachmentsUI;'
                         'window.ChatAttachmentsUI=undefined;snapshot()')
            assert await tab.js('byId("attach-file").disabled && '
                                'byId("chat-attachment-status").textContent'
                                '.includes("could not load")')
            await tab.js('window.ChatAttachmentsUI=savedAttachmentsUI;ChatAttachmentsUI.refresh()')
            assert await tab.js('!byId("attach-file").disabled && '
                                'byId("chat-attachment-status").hidden')

            async def device(name):
                tree = await tab.command("DOM.getDocument")
                node = await tab.command("DOM.querySelector", {
                    "nodeId": tree["root"]["nodeId"], "selector": "#attach-device-input",
                })
                await tab.command("DOM.setFileInputFiles", {
                    "nodeId": node["nodeId"], "files": [str(root / name)],
                })

            await tab.click("#attach-file")
            await device("device.txt")
            await tab.wait('ChatAttachmentsUI.ids().length === 1 && !ChatAttachmentsUI.preparing()')
            await tab.click("#attach-library")
            await tab.wait('document.querySelectorAll(".attachment-library-item").length === 20')
            await tab.wait('document.querySelector(".attachment-library-item img")'
                           '?.naturalWidth > 0')
            assert await tab.js('document.querySelector(".attachment-library-item .file-icon-pdf '
                                '.file-icon-badge")?.textContent === "PDF"')
            assert await tab.js('Boolean(document.querySelector(".attachment-library-item '
                                '.file-icon-code .icon")) && Boolean(document.querySelector('
                                '".attachment-library-item .file-icon-text .icon"))')
            for width, height in [(1440, 900), (390, 640), (320, 480)]:
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
                })
                await asyncio.sleep(.15)
                source_icons = await tab.js("""(() => {
                  const device=byId('attach-device'), library=byId('attach-library');
                  const icons=[...device.querySelectorAll('svg')]
                    .filter(icon=>icon.getClientRects().length);
                  return {device:icons.length===1 && (icons[0].classList
                      .contains('attachment-device-smartphone')?'smartphone':'laptop'),
                    library:library.querySelector('svg')?.innerHTML===
                      byId('nav-library').querySelector('svg').innerHTML,
                    leading:device.firstElementChild.tagName==='svg' &&
                      library.firstElementChild.tagName==='svg',
                    sameRow:device.getBoundingClientRect().top===
                      library.getBoundingClientRect().top,
                    decorative:[...device.querySelectorAll('svg'),library.querySelector('svg')]
                      .every(icon=>icon.getAttribute('aria-hidden')==='true')};
                })()""")
                assert source_icons == {
                    "device": "smartphone" if width <= 560 else "laptop",
                    "library": True, "leading": True, "sameRow": True, "decorative": True,
                }, source_icons
                assert await tab.js("""(() => {
                  const dialog = byId('attach-dialog');
                  const bounds = dialog.getBoundingClientRect();
                  return bounds.left >= 0 && bounds.right <= innerWidth &&
                    bounds.top >= 0 && bounds.bottom <= innerHeight &&
                    dialog.scrollWidth <= dialog.clientWidth &&
                    [...document.querySelectorAll('.attachment-library-item')].every(row => {
                      const art = row.querySelector('.file-artwork').getBoundingClientRect();
                      const button = row.querySelector('button').getBoundingClientRect();
                      return art.width === 44 && art.height === 44 &&
                        Math.min(button.width, button.height) >= 44 &&
                        row.scrollWidth <= row.clientWidth;
                    });
                })()""")
                screenshot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"library-picker-{width}.png").write_bytes(
                    base64.b64decode(screenshot["data"])
                )
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False,
            })
            await tab.click("#attach-next")
            await tab.wait('document.querySelectorAll(".attachment-library-item").length === 5')
            await tab.js('byId("attach-search").value="saved.md";'
                         'byId("attach-search-form").requestSubmit()')
            await tab.wait('document.querySelectorAll(".attachment-library-item").length === 1')
            await tab.click(".attachment-library-item button")
            await tab.wait('ChatAttachmentsUI.ids().length === 2 && !ChatAttachmentsUI.preparing()')
            await device("unsupported.exe")
            await tab.wait('byId("attach-status").textContent.includes("cannot be read")')
            assert await tab.js('ChatAttachmentsUI.ids().length === 2')
            await device("report.pdf")
            await tab.wait('ChatAttachmentsUI.ids().length === 3 && !ChatAttachmentsUI.preparing()')
            assert await tab.js('byId("chat-attachments").querySelector(".attachment-type-badge")'
                                '.textContent === "PDF"')
            await device("HU7hXeGbsAAYPuz.jpg")
            await tab.wait('ChatAttachmentsUI.ids().length === 4 && !ChatAttachmentsUI.preparing()')
            await tab.click("#attach-close")
            await tab.wait('byId("chat-attachments").querySelector("img")?.naturalWidth > 0')
            await tab.click('[aria-label="Remove HU7hXeGbsAAYPuz.jpg"]')
            await tab.wait('ChatAttachmentsUI.ids().length === 3')
            # Snapshots must retain the selected file and keyboard focus.
            await tab.js('window.chipButton=byId("chat-attachments").querySelector("button");'
                         'chipButton.focus();snapshot()')
            await asyncio.sleep(.2)
            assert await tab.js('chipButton.isConnected && document.activeElement === chipButton')

            sizes = []
            for width, height in [(1440, 900), (768, 900), (390, 640), (320, 480)]:
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
                })
                await asyncio.sleep(.15)
                layout = await tab.js("""(() => {
                  const composer = byId('composer').getBoundingClientRect();
                  const attach = byId('attach-file').getBoundingClientRect();
                  const send = byId('send').getBoundingClientRect();
                  return {width: innerWidth,
                    overflow: document.documentElement.scrollWidth > innerWidth,
                    composerFits: composer.left >= 0 && composer.right <= innerWidth
                      && composer.bottom <= innerHeight,
                    attach: [attach.width, attach.height], send: [send.width, send.height]};
                })()""")
                assert not layout["overflow"] and layout["composerFits"], layout
                assert min(*layout["attach"], *layout["send"]) >= 44, layout
                await tab.click("#attach-file")
                await asyncio.sleep(.3)
                assert await tab.js("""(() => {
                  const dialog = byId('attach-dialog'); const r = dialog.getBoundingClientRect();
                  return r.left >= 0 && r.right <= innerWidth
                    && r.top >= 0 && r.bottom <= innerHeight
                    && dialog.scrollWidth <= dialog.clientWidth;
                })()""")
                image = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"attach-{width}.png").write_bytes(base64.b64decode(image["data"]))
                await tab.click("#attach-close")
                assert await tab.js('Array.from(document.querySelectorAll(".attachment-card"))'
                                    '.every(card => card.scrollWidth <= card.clientWidth)')
                image = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"cards-{width}.png").write_bytes(base64.b64decode(image["data"]))
                sizes.append(layout)

            await tab.send("Summarize these attachments")
            await tab.wait('latest?.messages.some(item => item.content.startsWith('
                           '"Summarize these attachments"))')
            await tab.idle()
            observed = json.dumps(fixture.messages)
            assert "device-private-47" in observed and "library-private-82" in observed
            assert "pdf-private-93" in observed
            public = await tab.js('JSON.stringify(latest)')
            assert "device-private-47" not in public and "library-private-82" not in public
            assert "device.txt" in public and "saved.md" in public
            assert await tab.js('ChatAttachmentsUI.ids().length === 0')
            assert await tab.js('document.querySelectorAll(".message-attachments .attachment-card")'
                                '.length === 4')
            await tab.command("Page.reload")
            await tab.wait('typeof latest !== "undefined" && latest?.attachments && !pending')
            await tab.wait('document.querySelector(".message-attachments img")?.naturalWidth > 0')
            assert await tab.js('document.querySelectorAll(".message-attachments .attachment-pdf")'
                                '.length === 1')
            assert await tab.js('Array.from(document.querySelectorAll(".message-prompt"))'
                                '.every(node => !node.textContent.includes("[Attached files:"))')
            # Preparing another file during a reply leaves Cancel available and
            # waits for an idle turn rather than losing attachments in the queue.
            await tab.send("Wait")
            await tab.wait('latest.active_turn_id && !pending && !byId("attach-file").disabled')
            await tab.click("#attach-file")
            await device("device.txt")
            await tab.wait('ChatAttachmentsUI.ids().length === 1 && !ChatAttachmentsUI.preparing()')
            await tab.click("#attach-close")
            assert await tab.js('byId("send").disabled && !byId("cancel").disabled')
            fixture.release.set()
            await tab.idle()
            assert await tab.js('!byId("send").disabled')
            await tab.click("#chat-attachments button")
            await tab.wait('ChatAttachmentsUI.ids().length === 0')
            await tab.click("#attach-file")
            await device("device.txt")
            await tab.wait('ChatAttachmentsUI.ids().length === 1 && !ChatAttachmentsUI.preparing()')
            await tab.click("#attach-close")
            await tab.click("#logout")
            await tab.wait('!authenticated && ChatAttachmentsUI.ids().length === 0')
            assert not host.attachments._items
            assert not host.transfers._records
            assert not tab.errors, tab.errors
            print(json.dumps({"device_and_library": True, "private_input": True,
                              "image_thumbnails": True, "pdf_icons": True,
                              "library_picker_artwork": True,
                              "responsive_source_icons": True,
                              "sent_cards_reload": True,
                              "active_reply": True, "logout_cleanup": True,
                              "console_errors": len(tab.errors), "viewports": sizes,
                              "screenshots": str(output)}, indent=2))
    finally:
        fixture.release.set()
        process.terminate()
        process.wait(timeout=5)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or shutil.which("chromium")
    if not chrome:
        candidates = list((Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        ))
        if not candidates:
            raise SystemExit("Set KLAUDE_TEST_CHROME to a headless Chrome executable")
        chrome = str(candidates[-1])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.unit.test_webhost import _app

    with tempfile.TemporaryDirectory(prefix="klaude-attachment-smoke-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace = root, Workspace(root)
        app.agent.tool_config = cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        fixture = AttachmentFixture()
        app.agent.runtime = app.agent.ollama = fixture
        library = LibraryManagement(cfg, root)
        for index in range(22):
            name = f"other-{index}.py" if index == 21 else f"other-{index}.md"
            library.artifacts.import_bytes(b"Other file", "document", name)
        library.artifacts.import_bytes(b"library-private-82", "document", "saved.md")
        (root / "device.txt").write_text("device-private-47")
        (root / "unsupported.exe").write_bytes(b"MZ\0bad")
        from PIL import Image, ImageDraw
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, StreamObject

        picture = Image.new("RGB", (320, 240), "#c9b5eb")
        draw = ImageDraw.Draw(picture)
        draw.ellipse((80, 25, 245, 190), fill="#f0c876")
        draw.polygon([(0, 240), (150, 115), (270, 240)], fill="#587c71")
        draw.polygon([(160, 240), (280, 140), (320, 240)], fill="#8caea3")
        picture.save(root / "HU7hXeGbsAAYPuz.jpg", format="JPEG")
        library.artifacts.import_bytes((root / "HU7hXeGbsAAYPuz.jpg").read_bytes(),
                                       "media", "library-picture.jpg")
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        font = writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }))
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        stream = StreamObject()
        stream.set_data(b"BT /F1 12 Tf 20 200 Td (pdf-private-93) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        pdf = io.BytesIO()
        writer.write(pdf)
        (root / "report.pdf").write_bytes(pdf.getvalue())
        library.artifacts.import_bytes(pdf.getvalue(), "document", "library-report.pdf")
        # A completed image turn seeds the presentation fixture. Pixel delivery
        # through the real fenced worker is covered by test_chat_attachments.py.
        image = prepare_attachment("HU7hXeGbsAAYPuz.jpg",
                                   (root / "HU7hXeGbsAAYPuz.jpg").read_bytes(), preview=True)
        attachments = ChatAttachmentInput((image,))
        admission = app.turns.admit(
            request_id="image-card", session_id=app.session_id, turn_id="image-card-turn",
            worker_id=app.client_id, text=attachments.public_text("Tell me what you see"),
            scope="standard", runtime=capture(app.agent), input_key=attachments.identity,
            attachments=attachments,
        )
        app.turns.finish(
            request_id=admission.request_id, session_id=app.session_id, turn_id=admission.turn_id,
            worker_id=app.client_id, fence=admission.fence, state="completed",
            assistant="Ready.",
        )
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts, library=library, staging_dir=root / "staging")
        host.local_models = lambda: []
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome, fixture), 90))
        finally:
            fixture.release.set()
            host.stop()
            thread.join(3)


if __name__ == "__main__":
    main()

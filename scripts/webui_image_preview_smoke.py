"""Real Chrome acceptance for the responsive Library image viewer.

Uses temporary stores and real reviewed workers; no model/provider generation.
Run: uv run --frozen --offline python scripts/webui_image_preview_smoke.py
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools.toolkit import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from PIL import Image, ImageDraw
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402


async def verify(host, root, chrome, images):
    output = Path("/tmp/klaude-image-preview")
    output.mkdir(exist_ok=True)
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
    try:
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            await asyncio.sleep(0.05)
        port = int(active.read_text().splitlines()[0])
        with urlopen(
            Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        ) as response:
            target = json.load(response)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)

            async def wait(expression):
                for _ in range(120):
                    if await tab.js(expression):
                        return
                    await asyncio.sleep(0.05)
                raise AssertionError(
                    {
                        "waiting": expression,
                        "preview": await tab.js(
                            "JSON.stringify({selected:selectedArtifact?.id,focus:document.activeElement?.id,"
                            'zoom:byId("artifact-preview").dataset.zoom,navigation:previewNavigation,'
                            'details:artifactDialog.dataset.details,menu:byId("artifact-more").ariaExpanded,'
                            'mainInert:artifactDialog.querySelector(".preview-main").inert,'
                            'panelInert:byId("artifact-information").inert,'
                            'panelVisibility:getComputedStyle(byId("artifact-information")).visibility,'
                            "focusTag:document.activeElement?.tagName,"
                            'tags:byId("artifact-tags-input").value,tagError:byId("artifact-tag-new").validationMessage,'
                            'images:imageSequence.map(image=>image.id),status:byId("preview-status").textContent})'
                        ),
                        "errors": tab.errors,
                    }
                )

            tab.wait = wait

            async def click(selector):
                point = await tab.js(
                    """(() => {
                  const button=document.querySelector("""
                    + json.dumps(selector)
                    + """);
                  if (!button || button.disabled || button.closest('[inert]')) return null;
                  button.scrollIntoView({block:'nearest',inline:'nearest'});
                  const rect=button.getBoundingClientRect();
                  const point={x:rect.x+rect.width/2,y:rect.y+rect.height/2};
                  if (!button.contains(document.elementFromPoint(point.x,point.y))) return null;
                  return rect.width&&rect.height ? point : null;
                })()"""
                )
                assert point, selector
                await tab.command(
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mousePressed",
                        "button": "left",
                        "clickCount": 1,
                        **point,
                    },
                )
                await tab.command(
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mouseReleased",
                        "button": "left",
                        "clickCount": 1,
                        **point,
                    },
                )

            tab.click = click
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 1440,
                    "height": 900,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js(
                'byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await tab.wait("latest?.session_id && pollTimer!==null")
            await tab.js(
                "window.detailReads=[];window.originalFetch=fetch;"
                'window.fetch=(input,options)=>{if(String(input).includes("/lib'
                'rary/item?"))detailReads.push(String(input));return originalFe'
                "tch(input,options)}"
            )
            await tab.click("#nav-library")
            await tab.click("[data-file-view=gallery]")
            await tab.wait("filePage?.total===32 && filePage.items.length===24")

            async def open_first():
                await tab.click(".file-item button")
                await tab.wait(
                    'selectedArtifact && byId("artifact-preview").querySelector("im'
                    'g")?.naturalWidth>0'
                )

            async def key(key, code=None):
                for kind in ("keyDown", "keyUp"):
                    await tab.command(
                        "Input.dispatchKeyEvent",
                        {
                            "type": kind,
                            "key": key,
                            "code": code or key,
                            **({"windowsVirtualKeyCode": 27} if key == "Escape" else {}),
                        },
                    )

            async def screenshot(name):
                if await tab.js(
                    'byId("artifact-preview").dataset.zoom==="1" && '
                    'byId("artifact-preview").querySelector("img")?.naturalWidth>0'
                ):
                    assert await tab.js('''(() => {
                      const stage=byId('artifact-preview').getBoundingClientRect();
                      const image=byId('artifact-preview').querySelector('img');
                      const rect=image.getBoundingClientRect();
                      return rect.left>=stage.left-1 && rect.top>=stage.top-1 &&
                        rect.right<=stage.right+1 && rect.bottom<=stage.bottom+1 &&
                        getComputedStyle(image).objectFit==='contain';
                    })()'''), name
                picture = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / name).write_bytes(base64.b64decode(picture["data"]))

            await open_first()
            assert await tab.js(
                'artifactDialog.dataset.details==="partial" && !byId("artifact-information").inert'
            )
            assert await tab.js(
                'byId("artifact-metadata").textContent.includes("Added") && !by'
                'Id("artifact-metadata").textContent.includes("Modified")'
            )
            assert await tab.js(
                'byId("artifact-source").parentElement.classList.contains("prev'
                'iew-file-details") && ![...artifactDialog.querySelectorAll("h3'
                '")].some(node=>node.textContent==="Source")'
            )
            assert await tab.js(
                'byId("artifact-tags-input").type==="hidden" && byId("artifact-'
                'tag-list").children.length===8'
            )
            await tab.click("#artifact-tags-more")
            assert await tab.js('byId("artifact-tag-list").children.length===40')
            await tab.click("#artifact-tags-more")
            await tab.click("#artifact-more")
            assert await tab.js(
                '[...byId("artifact-menu").querySelectorAll("button")].map(b=>b'
                '.textContent).join(",").startsWith("Archive,Delete")'
            )
            await key("ArrowDown")
            assert await tab.js('document.activeElement.textContent==="Delete"')
            await key("Escape")
            await tab.wait(
                'artifactDialog.open && document.activeElement===byId("artifact'
                '-more") && byId("artifact-more").getAttribute("aria-expanded")'
                '==="false"'
            )
            await tab.click("#artifact-more")
            await tab.js('byId("artifact-menu").querySelectorAll("button")[1].click()')
            assert await tab.js(
                'artifactDialog.open && byId("preview-status").textContent.incl'
                'udes("Archive this file") && !reviewDialog.open'
            )
            await tab.click("#artifact-preview")
            first = await tab.js("selectedArtifact.id")
            reads = await tab.js("detailReads.length")
            await key("ArrowRight")
            await tab.wait(
                "selectedArtifact && selectedArtifact.id!=="
                + json.dumps(first)
                + " && !previewNavigation"
            )
            await key("ArrowLeft")
            await tab.wait("selectedArtifact?.id===" + json.dumps(first) + " && !previewNavigation")
            assert await tab.js("detailReads.length") == reads + 1
            await tab.click("#image-zoom-in")
            assert await tab.js('Number(byId("artifact-preview").dataset.zoom)>1')
            await key("ArrowRight")
            assert await tab.js("selectedArtifact.id") == first
            await tab.click("#image-fit")
            assert await tab.js('byId("artifact-preview").dataset.zoom==="1"')

            layouts = []
            for theme in ("light", "dark"):
                await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                for width, height in [
                    (1440, 900),
                    (1024, 768),
                    (768, 1024),
                    (390, 844),
                    (320, 568),
                    (844, 390),
                ]:
                    await tab.command(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": width,
                            "height": height,
                            "deviceScaleFactor": 1,
                            "mobile": False,
                        },
                    )
                    if width <= 850:
                        await tab.js('byId("preview-sheet-close").click()')
                    elif await tab.js('artifactDialog.dataset.details==="closed"'):
                        await tab.click("#image-details")
                    await asyncio.sleep(0.35)
                    bounds = await tab.js(
                        "(() => {\n                      const dialog=artifactDialog.get"
                        "BoundingClientRect();\n                      const stage=byId('"
                        "artifact-preview').getBoundingClientRect();\n                  "
                        "    const controls=byId('image-toolbar').getBoundingClientRect"
                        "();\n                      return {width:innerWidth,height:inne"
                        "rHeight,details:artifactDialog.dataset.details,\n              "
                        "          fits:dialog.left>=0&&dialog.top>=0&&dialog.right<=in"
                        "nerWidth+1&&dialog.bottom<=innerHeight+1,\n                    "
                        "    stageHeight:stage.height,stageWidth:stage.width,\n         "
                        "               overflow:artifactDialog.scrollWidth>artifactDia"
                        "log.clientWidth,\n                        controlsFit:controls."
                        "left>=0&&controls.right<=innerWidth,\n                        t"
                        "ouchTargets:[...byId('image-toolbar').querySelectorAll('button"
                        ",a')].filter(b=>b.getClientRects().length)\n                   "
                        "       .every(b=>b.getBoundingClientRect().width>=44&&b.getBou"
                        "ndingClientRect().height>=44)};\n                    })()"
                    )
                    assert (
                        bounds["fits"]
                        and not bounds["overflow"]
                        and bounds["controlsFit"]
                        and bounds["touchTargets"]
                    ), bounds
                    assert (
                        bounds["stageHeight"] > height * 0.55 and bounds["stageWidth"] > width * 0.5
                    ), bounds
                    if width <= 850:
                        assert bounds["details"] == "closed", bounds
                    await screenshot(f"viewer-{theme}-{width}x{height}.png")
                    await tab.click("#image-details")
                    if width > 850:  # Desktop toggles its already-visible sidebar closed.
                        await tab.click("#image-details")
                    await asyncio.sleep(0.35)
                    assert await tab.js('!byId("artifact-information").inert')
                    assert await tab.js(
                        "(() => {const panel=byId('artifact-information').getBoundingCl"
                        "ientRect();\n                      return panel.left>=0&&panel."
                        "right<=innerWidth&&panel.bottom<=innerHeight+1;})()"
                    )
                    await screenshot(f"details-{theme}-{width}x{height}.png")
                    if width <= 850:
                        await tab.wait(
                            'artifactDialog.querySelector(".preview-main").inert && documen'
                            't.activeElement===byId("preview-sheet-close")'
                        )
                        await tab.click("#preview-sheet-handle")
                        assert await tab.js('artifactDialog.dataset.details==="full"')
                        await asyncio.sleep(0.35)
                        assert await tab.js(
                            'byId("artifact-information").getBoundingClientRect().height>artifactDialog.querySelector(".preview-layout").clientHeight*.95'
                        )
                        await screenshot(f"details-full-{theme}-{width}x{height}.png")
                        await key("Escape")
                        await tab.wait(
                            'artifactDialog.open && artifactDialog.dataset.details==="close'
                            'd" && document.activeElement===byId("image-details")'
                        )
                    layouts.append({**bounds, "theme": theme})

            # Real touch events exercise pointer capture, swipe and pinch/pan arbitration.
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 390,
                    "height": 844,
                    "deviceScaleFactor": 1,
                    "mobile": True,
                },
            )
            await tab.command("Emulation.setTouchEmulationEnabled", {"enabled": True})
            await tab.js('byId("preview-sheet-close").click();byId("image-fit").click()')
            rect = await tab.js(
                'JSON.stringify(byId("artifact-preview").getBoundingClientRect().toJSON())'
            )
            rect = json.loads(rect)
            x, y = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2

            async def touch(kind, points):
                await tab.command(
                    "Input.dispatchTouchEvent",
                    {
                        "type": kind,
                        "touchPoints": [
                            {"x": px, "y": py, "id": index + 1, "radiusX": 2, "radiusY": 2}
                            for index, (px, py) in enumerate(points)
                        ],
                    },
                )

            await touch("touchStart", [(x - 30, y), (x + 30, y)])
            await touch("touchMove", [(x - 90, y), (x + 90, y)])
            await touch("touchEnd", [])
            assert await tab.js('Number(byId("artifact-preview").dataset.zoom)>2')
            await touch("touchStart", [(x, y)])
            await touch("touchMove", [(x - 110, y)])
            await touch("touchEnd", [])
            assert await tab.js("selectedArtifact.id") == first
            await tab.click("#image-fit")
            await touch("touchStart", [(x + 90, y)])
            await touch("touchMove", [(x - 90, y)])
            await touch("touchEnd", [])
            await tab.wait(
                "selectedArtifact && selectedArtifact.id!=="
                + json.dumps(first)
                + " && !previewNavigation"
            )
            assert await tab.js('byId("artifact-preview").dataset.zoom==="1"')
            await tab.wait('byId("artifact-preview").querySelector("img")?.naturalWidth>0')
            for _ in range(2):
                await touch("touchStart", [(x, y)])
                await touch("touchEnd", [])
            assert await tab.js('Number(byId("artifact-preview").dataset.zoom)>1')
            await tab.click("#image-fit")
            await screenshot("touch-portrait-fit.png")
            await tab.click("#image-next")
            await tab.wait(
                'selectedArtifact && !previewNavigation && byId("artifact-previ'
                'ew").querySelector("img")?.naturalWidth>0'
            )
            await screenshot("touch-square-fit.png")
            await tab.click("#image-details")
            await asyncio.sleep(.35)
            handle = json.loads(
                await tab.js(
                    'JSON.stringify(byId("preview-sheet-handle").getBoundingClientRect().toJSON())'
                )
            )
            hx, hy = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
            await touch("touchStart", [(hx, hy)])
            await touch("touchMove", [(hx, hy - 80)])
            await touch("touchEnd", [])
            await tab.wait('artifactDialog.dataset.details==="full"')
            await asyncio.sleep(0.35)
            handle = json.loads(
                await tab.js(
                    'JSON.stringify(byId("preview-sheet-handle").getBoundingClientRect().toJSON())'
                )
            )
            hx, hy = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
            await touch("touchStart", [(hx, hy)])
            await touch("touchMove", [(hx, hy + 80)])
            await touch("touchEnd", [])
            await tab.wait('artifactDialog.dataset.details==="closed"')
            await tab.click("#artifact-close")
            await tab.wait("selectedArtifact===null && document.activeElement===previewOrigin")

            # Source editing and chip edits preserve the existing reviewed worker.
            await open_first()
            await tab.click("#image-details")
            await tab.click("#artifact-source button:last-child")
            assert await tab.js(
                'byId("artifact-source-form").closest(".preview-file-details")!==null'
            )
            await tab.js(
                'byId("artifact-source-input").value="https://example.test/refe'
                'rence?q=1#image";byId("artifact-source-form").requestSubmit()'
            )
            await tab.wait('reviewDialog.open && managementReview?.operation==="source_link"')
            assert host.library.artifacts.get(first)["source_url"] == ""
            await tab.click("#domain-review-confirm")
            await tab.wait("!reviewDialog.open")
            for _ in range(200):
                current = host.library.artifacts.get(first)
                if current["source_url"]:
                    break
                await asyncio.sleep(0.05)
            assert current["source_url"] == "https://example.test/reference?q=1#image"
            await tab.click("#library-refresh")
            await tab.wait('!byId("library-items").classList.contains("is-loading")')
            await open_first()
            await tab.click("#image-details")
            await tab.js(
                'Object.defineProperty(navigator,"clipboard",{value:undefined,configurable:true});window.sourceCopyText="";document.addEventListener("copy",event=>{sourceCopyText=event.clipboardData?.getData("text/plain")},{once:true})'
            )
            await tab.click("#artifact-source button")
            await tab.wait('byId("preview-status").textContent==="Source link copied."')
            assert await tab.js('sourceCopyText==="https://example.test/reference?q=1#image"')
            await tab.js("delete navigator.clipboard")
            assert await tab.js(
                'byId("artifact-source").querySelector("a").href==="https://exa'
                'mple.test/reference?q=1#image"'
            )
            await tab.click("#artifact-tags-edit")
            assert await tab.js(
                'byId("artifact-tag-editor").hidden===false && byId("artifact-t'
                'ag-list").querySelectorAll("button").length===20'
            )
            await tab.click("#artifact-tag-list button")
            await tab.wait('byId("artifact-tag-list").querySelectorAll("button").length===19')
            await tab.js(
                'byId("artifact-tag-new").value="reviewed tag";byId("artifact-t'
                'ag-add").click();byId("artifact-tags").requestSubmit()'
            )
            await tab.wait('reviewDialog.open && managementReview?.operation==="tags"')
            assert "reviewed tag" not in host.library.artifacts.get(first)["tags"]
            await tab.click("#domain-review-confirm")
            await tab.wait("!reviewDialog.open")
            for _ in range(200):
                current = host.library.artifacts.get(first)
                if "reviewed tag" in current["tags"]:
                    break
                await asyncio.sleep(0.05)
            assert "reviewed tag" in current["tags"] and len(current["tags"]) == 20
            assert current["source_url"] and current["sha256"] == images[0]["sha256"]

            await tab.click("#library-refresh")
            await tab.wait('!byId("library-items").classList.contains("is-loading")')
            await open_first()
            await tab.click("#artifact-more")
            await tab.js('byId("artifact-menu").querySelector("button").click()')
            await tab.wait('reviewDialog.open && managementReview?.operation==="archive"')
            assert not host.library.artifacts.get(first)["archived"]
            await tab.click("#domain-review-confirm")
            await tab.wait("!reviewDialog.open")
            for _ in range(200):
                current = host.library.artifacts.get(first)
                if current["archived"]:
                    break
                await asyncio.sleep(0.05)
            assert current["archived"]
            await tab.js(
                'byId("artifact-status").value="archived";byId("artifact-status'
                '").dispatchEvent(new Event("change"))'
            )
            await tab.wait("filePage?.items.length===1 && filePage.items[0].archived")
            await open_first()
            await tab.click("#artifact-more")
            await tab.js('byId("artifact-menu").querySelectorAll("button")[1].click()')
            await tab.wait('reviewDialog.open && managementReview?.operation==="delete"')
            assert await tab.js(
                'byId("domain-review-confirm").textContent==="Delete permanently" && '
                'document.activeElement===byId("domain-review-cancel")'
            )
            assert await tab.js(
                'byId("domain-review-summary").textContent.includes("cannot be undone")'
            )
            await tab.click("#domain-review-cancel")
            assert host.library.artifacts.get(first)["archived"]
            await open_first()
            await tab.click("#artifact-more")
            await tab.js('byId("artifact-menu").querySelectorAll("button")[1].click()')
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait("!reviewDialog.open")
            for _ in range(200):
                try:
                    host.library.artifacts.get(first)
                except ValueError:
                    break
                await asyncio.sleep(0.05)
            else:
                raise AssertionError("Reviewed deletion did not finish")
            await tab.command(
                "Emulation.setEmulatedMedia",
                {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]},
            )
            await tab.js(
                'byId("artifact-status").value="saved";byId("artifact-status").'
                'dispatchEvent(new Event("change"))'
            )
            await tab.wait("filePage?.total===31 && filePage.items.length===24")
            await open_first()
            assert await tab.js(
                "parseFloat(getComputedStyle(artifactDialog).animationDuration)<.01"
            )
            assert await tab.js(
                '!performance.getEntriesByType("resource").some(entry=>new URL('
                "entry.name).origin!==location.origin)"
            )
            await tab.js('byId("logout").click()')
            await tab.wait("!authenticated && !artifactDialog.open && artifactDetails.size===0")
            await tab.wait(
                'byId("artifact-metadata").children.length===0 && byId("artifac'
                't-tag-list").children.length===0 && byId("artifact-source-inpu'
                't").value===""'
            )
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "layouts": layouts,
                        "touch_pinch_pan_swipe_double_tap": True,
                        "metadata_read_cache": True,
                        "reviewed_source_tags_archive_delete": True,
                        "delete_cancel_and_archive_rule": True,
                        "reduced_motion": True,
                        "logout_cleanup": True,
                        "external_requests": 0,
                        "browser_exceptions": 0,
                        "screenshots": str(output),
                    },
                    indent=2,
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    with tempfile.TemporaryDirectory(prefix="klaude-image-preview-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace = root, Workspace(root)
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        service = LibraryManagement(cfg, root)
        images = []
        for index in range(32):
            size = [(1800, 600), (600, 1800), (900, 900)][index % 3]
            picture = Image.new("RGB", size, "#e3e9e0")
            draw = ImageDraw.Draw(picture)
            draw.rounded_rectangle(
                (size[0] // 8, size[1] // 8, size[0] * 7 // 8, size[1] * 7 // 8),
                radius=40,
                fill="#797297",
            )
            draw.ellipse(
                (size[0] // 3, size[1] // 3, size[0] * 2 // 3, size[1] * 2 // 3), fill="#f0c995"
            )
            data = io.BytesIO()
            picture.save(data, format="WEBP")
            filename = (
                f"{index:02}-"
                + ("a-long-landscape-filename-" * 4 if index == 0 else "fixture-")
                + ".webp"
            )
            item = service.artifacts.import_bytes(data.getvalue(), "media", filename)
            with service.artifacts.database(write=True) as db:
                db.execute(
                    "UPDATE artifacts SET created=? WHERE id=?", (1792425600 - index, item["id"])
                )
            images.append(item)
        first = images[0]
        service.artifacts.change(
            first["id"], first["revision"], "tags", ",".join(f"manual tag {i}" for i in range(20))
        )
        with service.artifacts.database(write=True) as db:
            db.execute(
                "INSERT INTO image_tags(artifact,generated_tags,provenance) VALUES(?,?,?)",
                (
                    first["id"],
                    json.dumps([f"AI tag {i}" for i in range(20)]),
                    json.dumps({f"AI tag {i}": {} for i in range(20)}),
                ),
            )
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts, library=service, staging_dir=root / "staging")
        host.local_models = lambda: []
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome, images), 180))
        finally:
            host.stop()
            serving.join(3)


if __name__ == "__main__":
    main()

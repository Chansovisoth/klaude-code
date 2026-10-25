"""Google Lens local selection, crop and browser handoff fixture; no private uploads."""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import subprocess
import zlib
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
import webui_inspector_smoke as inspector
from webui_control_smoke import Tab


async def verify(host, service, root, chrome, image, mode, calls, *_):
    def chunk(kind, content):
        return (
            struct.pack("!I", len(content))
            + kind
            + content
            + struct.pack("!I", zlib.crc32(kind + content) & 0xFFFFFFFF)
        )

    rows = []
    for y in range(240):
        rows.append(
            b"\0"
            + b"".join(
                b"\0\0\xff" if 100 <= x < 220 and 60 <= y < 140 else b"\xff\0\0" for x in range(400)
            )
        )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", 400, 240, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )
    image = service.artifacts.import_bytes(png, "media", "lens-fixture.png")
    profile = root / "chrome-lens"
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
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait(
                "typeof byId!=='undefined' && !byId('local-access').hidden && "
                "document.documentElement.dataset.startup==='ready'"
            )
            await tab.js(
                'byId("login-username").value="admin";'
                'byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await tab.wait(
                "authenticated && latest?.session_id && !document.querySelector('.shell').inert"
            )
            output = Path("/tmp/klaude-lens-preview")
            output.mkdir(exist_ok=True)
            await tab.js("showView('library')")
            await tab.js(f"openArtifact({json.dumps(image['id'])})")
            await tab.wait(
                "selectedArtifact && "
                "byId('artifact-preview').querySelector('img')?.naturalWidth===400"
            )
            await tab.js("""
                window.lensSubmits=[];
                HTMLFormElement.prototype.submit=function() {
                    const form=this, file=form.querySelector('[name=encoded_image]').files[0];
                    lensSubmits.push({action:form.action,target:form.target,rel:form.rel,
                        entries:[...new FormData(form).keys()],name:file.name});
                    window.lastLensFile=file;
                };
            """)

            async def drag(x1, y1, x2, y2):
                rect = await tab.js("""(() => {
                    const r=byId('lens-canvas').getBoundingClientRect();
                    const scale=Math.min(r.width/400,r.height/240);
                    return {x:r.left+(r.width-400*scale)/2,
                        y:r.top+(r.height-240*scale)/2,scale};
                })()""")
                start = {"x": rect["x"] + x1 * rect["scale"], "y": rect["y"] + y1 * rect["scale"]}
                end = {"x": rect["x"] + x2 * rect["scale"], "y": rect["y"] + y2 * rect["scale"]}
                await tab.command(
                    "Input.dispatchMouseEvent",
                    {"type": "mousePressed", **start, "button": "left", "clickCount": 1},
                )
                await tab.command(
                    "Input.dispatchMouseEvent", {"type": "mouseMoved", **end, "buttons": 1}
                )
                await tab.command(
                    "Input.dispatchMouseEvent",
                    {"type": "mouseReleased", **end, "button": "left", "clickCount": 1},
                )

            async def key(name, shift=False):
                for kind in ("keyDown", "keyUp"):
                    await tab.command(
                        "Input.dispatchKeyEvent",
                        {
                            "type": kind,
                            "key": name,
                            "code": name,
                            "modifiers": 8 if shift else 0,
                            "windowsVirtualKeyCode": {
                                "Escape": 27,
                                "Enter": 13,
                                "Home": 36,
                                "ArrowLeft": 37,
                                "ArrowRight": 39,
                                "ArrowDown": 40,
                            }[name],
                        },
                    )

            async def enter_lens_mode():
                await tab.click("#image-lens")
                await tab.wait("!byId('lens-overlay').hidden && !byId('lens-search').disabled")

            layouts = []
            for width in (320, 390, 768, 1440):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": 844, "deviceScaleFactor": 1, "mobile": False},
                )
                if await tab.js("artifactDialog.dataset.details!=='closed'"):
                    await tab.click("#preview-sidebar-toggle")
                await tab.click("#image-lens")
                await tab.wait("!byId('lens-overlay').hidden && !byId('lens-search').disabled")
                assert await tab.js("""(() => {
                    const stage=byId('lens-overlay').getBoundingClientRect();
                    const action=byId('lens-search').getBoundingClientRect();
                    return !byId('lens-dialog') &&
                        byId('image-lens').nextElementSibling===byId('artifact-download') &&
                        Math.abs((action.left+action.right-stage.left-stage.right)/2)<2 &&
                        action.bottom<=stage.bottom && action.bottom>=stage.bottom-24 &&
                        document.activeElement===byId('lens-canvas') &&
                        action.left>=0 && action.right<=innerWidth;
                })()"""), width
                await tab.click("#lens-search")
                assert await tab.js("""(() => {
                    const last=lensSubmits.at(-1),url=new URL(last.action);
                    return url.origin==='https://lens.google.com' && url.pathname==='/v3/upload' &&
                        url.searchParams.get('vpw')==='400' &&
                        url.searchParams.get('vph')==='240' && last.target==='_blank' &&
                        last.rel.includes('noopener') && last.entries.join(',')==='encoded_image';
                })()""")
                await tab.wait("byId('lens-overlay').hidden && "
                               "byId('image-lens').getAttribute('aria-pressed')==='false' && "
                               "document.activeElement===byId('image-lens') && "
                               "byId('lens-canvas').width===1")
                await enter_lens_mode()
                await drag(105, 65, 215, 135)
                await tab.wait("!byId('lens-search').disabled")
                await tab.click("#lens-search")
                await tab.wait("byId('lens-overlay').hidden && "
                               "byId('image-lens').getAttribute('aria-pressed')==='false' && "
                               "document.activeElement===byId('image-lens')")
                assert await tab.js("""(async()=>{
                    const image=await createImageBitmap(lastLensFile);
                    const c=document.createElement('canvas');c.width=110;c.height=70;
                    const ctx=c.getContext('2d');ctx.drawImage(image,0,0);
                    const pixel=ctx.getImageData(55,35,1,1).data;
                    const valid=image.width===110 && image.height===70 &&
                        pixel[2]>240 && pixel[0]<15;
                    image.close();return valid;
                })()"""), await tab.js("""(async()=>{
                    const image=await createImageBitmap(lastLensFile);
                    const result={width:image.width,height:image.height,
                        selection:byId('lens-selection').textContent};
                    image.close();return result;
                })()""")
                await enter_lens_mode()
                await drag(215, 135, 205, 125)
                await tab.wait("!byId('lens-search').disabled")
                assert await tab.js("byId('lens-selection').textContent.includes('100 by 60')")
                await drag(150, 90, 155, 95)
                assert await tab.js(
                    "byId('lens-selection').textContent.includes('left 110, top 70')"
                )
                await key("ArrowRight")
                await key("ArrowLeft", shift=True)
                assert await tab.js(
                    "byId('lens-selection').textContent.includes('left 111') && "
                    "byId('lens-selection').textContent.includes('99 by 60')"
                )
                await tab.wait("!byId('lens-search').disabled")
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"inline-crop-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                await key("Home")
                await tab.wait("!byId('lens-search').disabled")
                assert await tab.js("byId('lens-selection').textContent.includes('400 by 240')")
                await key("Enter")
                await tab.wait("byId('lens-overlay').hidden && "
                               "byId('image-lens').getAttribute('aria-pressed')==='false' && "
                               "document.activeElement===byId('image-lens')")
                await enter_lens_mode()
                await key("Escape")
                await tab.wait(
                    "byId('lens-overlay').hidden && artifactDialog.open && "
                    "document.activeElement===byId('image-lens') && byId('lens-canvas').width===1"
                )
                layouts.append(width)
            # Reopening starts full-size, and navigation clears pending crop bytes.
            await tab.click("#image-lens")
            await tab.wait("!byId('lens-search').disabled")
            await tab.click("#lens-cancel")
            await tab.click("#image-lens")
            await tab.wait("!byId('lens-search').disabled")
            await tab.click("#logout")
            await tab.wait(
                "!authenticated && byId('lens-overlay').hidden && "
                "byId('lens-canvas').width===1 && byId('lens-search').disabled"
            )
            assert not tab.errors, tab.errors
            return {
                "layouts": layouts,
                "direct_form_handoff": "intercepted; no private upload",
                "full_image_and_exact_crop": "passed",
                "drag_move_resize_keyboard": "passed",
                "inline_search_geometry_escape_logout": "passed",
                "browser_exceptions": len(tab.errors),
            }
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    inspector.verify = verify
    inspector.main()

"""Focused AI Review loading/generation presentation with an isolated browser."""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
import webui_inspector_smoke as fixture
from webui_control_smoke import Tab

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jz1kAAAAASUVORK5CYII="
)


async def verify(host, service, root, chrome, image, _mode, calls, _set_default):
    other = service.artifacts.import_bytes(PNG, "media", "review-loading-second.png")
    output = Path("/tmp/klaude-review-loading")
    output.mkdir(exist_ok=True)
    profile = root / "chrome-loading"
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
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=5_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait("typeof byId!=='undefined' && !byId('local-access').hidden")
            await tab.js(
                'byId("login-username").value="admin";byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await tab.wait(
                "authenticated&&latest?.session_id&&document.documentElement.dataset.startup==='ready'&&!document.querySelector('.shell').inert"
            )
            await tab.js("""window.originalReviewRequest=domainRequest;
              window.holdReview=true;window.reviewReads=[];window.fixturePending=null;
              domainRequest=async (...args)=>{
                const result=await originalReviewRequest(...args);
                if (!args[0].startsWith('/api/v1/library/vision?')) return result;
                if (fixturePending) result.pending=fixturePending;
                return holdReview ? new Promise((resolve,reject)=>
                  reviewReads.push({resolve,reject,result})) : result;
              };document.documentElement.dataset.motion='reduced';showView('library');""")

            async def open_image(item):
                await tab.js("openArtifact(" + json.dumps(item["id"]) + ")")
                await tab.wait("selectedArtifact?.id===" + json.dumps(item["id"]))
                await tab.wait("reviewReads.length>0")
                await tab.click("#inspector-tab-ai-review")

            async def release(pending=None):
                await tab.js(
                    "window.fixturePending=" + json.dumps(pending) + ";holdReview=false;"
                    "for(const read of reviewReads.splice(0)){"
                    "read.result.pending=fixturePending;read.resolve(read.result)}"
                )

            await open_image(image)
            for theme in ("light", "dark"):
                for width in (320, 768, 1440):
                    await tab.command(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": width,
                            "height": 800,
                            "deviceScaleFactor": 1,
                            "mobile": False,
                        },
                    )
                    await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                    await tab.js(
                        "if(artifactDialog.dataset.details==='closed')byId('image-details').click()"
                    )
                    assert await tab.js("""(() => {
                      const intro=byId('vision-empty'), icon=byId('vision-empty-icon');
                      const r=icon.firstElementChild.getBoundingClientRect();
                      return !intro.hidden &&
                        intro.querySelector('h3').textContent==='Loading AI Review…' &&
                        icon.querySelector('.loading-circle-indicator') &&
                        !icon.querySelector('.material-loading') &&
                        r.width===48 && r.height===48 && !byId('vision-status').textContent &&
                        !byId('vision-status').children.length && byId('vision-submit').disabled &&
                        byId('vision-analyze').getAttribute('aria-busy')==='true' &&
                        document.documentElement.scrollWidth<=innerWidth;
                    })()"""), await tab.js(
                        "({heading:byId('vision-empty').querySelector('h3').textContent,"
                        "hidden:byId('vision-empty-icon').closest('[hidden]')?.id,"
                        "icon:byId('vision-empty-icon').innerHTML,"
                        "bounds:byId('vision-empty-icon').firstElementChild.getBoundingClientRect().toJSON(),"
                        "status:byId('vision-status').textContent,"
                        "disabled:byId('vision-submit').disabled,busy:byId('vision-analyze').getAttribute('aria-busy')})"
                    )
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"loading-{theme}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
            await release()
            await tab.wait(
                "byId('vision-empty').querySelector('h3').textContent==="
                "'Understand this image'&&!byId('vision-submit').disabled"
            )
            await tab.js("holdReview=true")
            await open_image(other)
            await release(
                {
                    "request_id": "fixture-review",
                    "state": "running",
                    "kind": "vision-analyze",
                    "cancellable": True,
                }
            )
            await tab.wait(
                "byId('vision-empty').querySelector('h3').textContent==='Generating review'"
            )
            assert await tab.js(
                "byId('vision-empty-icon').querySelector('.material-loading')!==null&&"
                "!byId('vision-empty-icon').querySelector('.loading-circle-indicator')"
            )
            await tab.js("fixturePending=null;holdReview=true")
            await open_image(image)
            await tab.js(
                "holdReview=false;for(const read of reviewReads.splice(0))"
                "read.reject(new Error('Fixture read failed'))"
            )
            await tab.wait("byId('vision-status').dataset.state==='error'")
            assert await tab.js(
                "byId('vision-empty').querySelector('h3').textContent!=='Loading AI Review…'&&"
                "!byId('vision-empty-icon').querySelector('.loading-circle-indicator')"
            )
            await tab.js("holdReview=true")
            await open_image(other)
            await tab.click("#artifact-close")
            await tab.wait("!artifactDialog.open&&byId('artifact-vision').hidden")
            await release()
            assert await tab.js("!artifactDialog.open&&byId('artifact-vision').hidden")
            assert not any(path == "/api/chat" for path, _ in calls), calls
            assert not tab.errors, tab.errors
            return {
                "initial_review_layout": "passed",
                "normal_loader_48px": "passed",
                "generation_loader_preserved": "passed",
                "failure_and_late_read": "passed",
                "viewports": [320, 768, 1440],
                "themes": ["light", "dark"],
                "screenshots": str(output),
                "browser_exceptions": 0,
            }
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    fixture.verify = verify
    fixture.main()

"""Image Studio layout, fixture generation, cancellation and output actions."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_core import image_generation
from webui_control_smoke import Tab
from webui_model_store_smoke import main

from tests.unit.test_image_generation import generation_lab


async def verify(host, root):
    service_fixture = generation_lab.__wrapped__(root / "studio-service")
    _, service_url, _, _, service_state = next(service_fixture)
    cfg = host.library.cfg
    image_generation.save(
        cfg,
        {"endpoint": service_url, "enabled": True, "model": "local-test-model"},
        image_generation.read(cfg)["revision"],
    )
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
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
    evidence = Path("/tmp/klaude-image-studio-evidence")
    evidence.mkdir(exist_ok=True)
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
            await tab.wait(
                "typeof authenticated !== 'undefined' && authenticated && latest && "
                "document.documentElement.dataset.startup==='ready'"
            )
            await tab.js("showView('chat'); librarySection='uploads'; renderFileToolbar()")
            for width in [320, 390, 768, 900, 1440]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 720,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                for entry in ["attachment", "menu"] if width <= 390 else ["attachment"]:
                    if entry == "attachment":
                        await tab.click("#attach-file")
                        await tab.click("#attach-create-image")
                    else:
                        await tab.click("#mobile-chat-more")
                        await tab.click("#chat-create-image")
                    await tab.wait(
                        "byId('image-generate-panel').open && !byId('image-submit').disabled"
                    )
                    await tab.js("renderFileToolbar()")
                    assert await tab.js("""(() => {
                      const prompt=byId('image-prompt'), dialog=byId('image-generate-panel');
                      const box=dialog.getBoundingClientRect();
                      return currentView==='chat' && !byId('generated-tools').hidden &&
                        prompt.getClientRects().length>0 &&
                        prompt.getBoundingClientRect().width>100 && box.left>=0 &&
                        box.right<=innerWidth && dialog.scrollWidth<=dialog.clientWidth+1;
                    })()""")
                    assert await tab.js(
                        "getComputedStyle(byId('generation-image'))"
                        ".gridTemplateColumns.split(' ').length===" + "1"
                    )
                    assert await tab.js(
                        "byId('image-model-summary').textContent.includes('Model:') && "
                        "byId('image-sampling-summary').textContent==='Steps: 20' && "
                        "byId('image-options').getBoundingClientRect().height>=44"
                    )
                    await tab.click("#image-options")
                    await tab.wait("byId('image-create-settings').open")
                    await tab.wait(
                        "byId('image-create-settings').getAnimations()"
                        ".every(animation=>animation.playState==='finished')"
                    )
                    assert await tab.js(
                        "[...document.querySelectorAll("
                        "'#image-ratio-quick span, #image-orientation span')]"
                        ".every(node=>node.scrollWidth<=node.clientWidth && "
                        "node.offsetHeight>=44)"
                    )
                    assert await tab.js("""(() => {
                      const dialog=byId('image-create-settings');
                      const box=dialog.getBoundingClientRect();
                      return !byId('image-ratio') && box.left>=0 && box.right<=innerWidth &&
                        dialog.scrollWidth<=dialog.clientWidth+1 &&
                        byId('image-orientation').querySelectorAll('svg').length===2;
                    })()""")
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (evidence / f"image-ratios-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                    await tab.click("#image-create-settings-done")
                    await tab.wait("document.activeElement===byId('image-options')")
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (evidence / f"studio-{entry}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                    await tab.click("#image-generate-close")
                    await tab.wait("document.activeElement===byId('attach-file')")
            await tab.click("#attach-file")
            await tab.click("#attach-create-image")
            await tab.wait("byId('image-service-status').textContent==='Ready'")
            await tab.click("#image-options")
            await tab.wait("byId('image-create-settings').open")
            await tab.wait(
                "byId('image-create-settings').getAnimations()"
                ".every(animation=>animation.playState==='finished')"
            )
            shot = await tab.command("Page.captureScreenshot", {"format": "png"})
            (evidence / "image-settings-desktop.png").write_bytes(base64.b64decode(shot["data"]))
            await tab.js(
                "byId('image-prompt').value='Watercolor apple'; "
                "byId('image-ratio-quick').querySelector('[value=\"16:9\"]').click()"
            )
            assert await tab.js(
                "byId('image-width').value==='1024' && byId('image-height').value==='576'"
            )
            await tab.js("byId('image-orientation').querySelector('[value=landscape]').focus()")
            for event_type in ["keyDown", "keyUp"]:
                await tab.command(
                    "Input.dispatchKeyEvent",
                    {
                        "type": event_type,
                        "key": "ArrowRight",
                        "code": "ArrowRight",
                        "windowsVirtualKeyCode": 39,
                    },
                )
            assert await tab.js(
                "byId('image-width').value==='576' && byId('image-height').value==='1024' && "
                "document.activeElement.value==='portrait'"
            )
            await tab.js("byId('image-ratio-quick').querySelector('[value=\"3:2\"]').click()")
            assert await tab.js(
                "byId('image-width').value==='512' && byId('image-height').value==='768'"
            )
            await tab.js("byId('image-orientation').querySelector('[value=landscape]').click()")
            assert await tab.js(
                "byId('image-width').value==='768' && byId('image-height').value==='512'"
            )
            await tab.js(
                "byId('image-ratio-quick').querySelector('[value=\"1:1\"]').click(); "
                "byId('image-orientation').querySelector('[value=portrait]').click()"
            )
            assert await tab.js(
                "byId('image-width').value==='512' && byId('image-height').value==='512'"
            )
            await tab.js(
                "byId('image-ratio-quick').querySelector('[value=custom]').click(); "
                "byId('image-seed').value='42'"
            )
            assert await tab.js(
                "byId('image-advanced').open && document.activeElement===byId('image-width')"
            )
            await tab.js(
                "byId('image-width').value='640'; "
                "byId('image-width').dispatchEvent(new Event('input')); "
                "byId('image-orientation').querySelector('[value=portrait]').click()"
            )
            assert await tab.js(
                "byId('image-width').value==='512' && byId('image-height').value==='640' && "
                "byId('image-ratio-quick').querySelector('[value=custom]').checked && "
                "byId('image-settings-dimensions').textContent==='512 × 640 pixels'"
            )
            await tab.click("#image-create-settings-done")
            await tab.click("#generation-tab-research")
            await tab.js("byId('research-question').value='Research draft'")
            assert await tab.js(
                "byId('research-model-label').textContent.startsWith('Model:') && "
                "byId('research-context-summary').textContent.includes('tokens') && "
                "byId('research-output-summary').textContent.includes('tokens')"
            )
            await tab.click("#research-options")
            await tab.wait("byId('research-create-settings').open")
            await tab.js("byId('research-format').value='comparison'")
            await tab.click("#research-create-settings-done")
            await tab.wait("document.activeElement===byId('research-options')")
            await tab.click("#generation-tab-image")
            assert await tab.js(
                "byId('image-prompt').value==='Watercolor apple' && "
                "byId('image-seed').value==='42' && "
                "byId('research-question').value==='Research draft'"
            )
            await tab.click("#image-options")
            await tab.click("#image-reset-options")
            await tab.click("#image-create-settings-done")
            await tab.js("byId('image-steps').value='0'; byId('image-generate').requestSubmit()")
            await tab.wait(
                "byId('image-create-settings').open && document.activeElement===byId('image-steps')"
            )
            assert await tab.js("!reviewDialog.open")
            await tab.js("byId('image-steps').value='20'")
            await tab.click("#image-create-settings-done")
            await tab.js("byId('image-seed').value='42'; byId('image-generate').requestSubmit()")
            await tab.wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-summary').textContent.includes('seed 42')")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "!BrowserManagement.hasPending() && "
                "byId('image-jobs').textContent.includes('Completed')"
            )
            await tab.click("#attach-file")
            await tab.click("#attach-create-image")
            await tab.wait("byId('image-jobs').textContent.includes('Completed')")
            assert await tab.js(
                "!byId('image-latest-result') && !document.querySelector('.image-output-workspace')"
            )
            await tab.js("byId('image-history').open=true")
            await tab.js("byId('image-advanced').open=false")
            for width, height in [(320, 568), (768, 900), (1440, 900)]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                for mode in ["light", "dark"]:
                    await tab.js(
                        "applyAppearance(appearance={...appearance,theme:" + json.dumps(mode) + "})"
                    )
                    assert await tab.js(
                        "byId('image-generate-panel').scrollWidth<="
                        "byId('image-generate-panel').clientWidth"
                    )
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (evidence / f"result-{width}-{mode}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                    if width == 320:
                        await tab.js("byId('image-jobs-title').scrollIntoView({block:'start'})")
                        shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (evidence / f"result-mobile-output-{mode}.png").write_bytes(
                            base64.b64decode(shot["data"])
                        )
                        await tab.js("byId('image-generate-panel').scrollTop=0")
            await tab.js(
                "byId('image-jobs').querySelector('details').open=true; "
                "[...byId('image-jobs').querySelectorAll('button')]"
                ".find(b=>b.textContent==='Open output').click()"
            )
            await tab.wait("byId('artifact-detail').open")
            await tab.click("#artifact-close")
            downloads = root / "downloads"
            downloads.mkdir()
            await tab.command(
                "Page.setDownloadBehavior",
                {
                    "behavior": "allow",
                    "downloadPath": str(downloads),
                },
            )
            await tab.js(
                "byId('image-jobs').querySelector('details').open=true; "
                "[...byId('image-jobs').querySelectorAll('button')]"
                ".find(b=>b.textContent==='Download').click()"
            )
            for _ in range(50):
                if list(downloads.glob("*.png")):
                    break
                await asyncio.sleep(0.1)
            assert list(downloads.glob("*.png"))
            await tab.js(
                "byId('image-jobs').querySelector('details').open=true; "
                "[...byId('image-jobs').querySelectorAll('button')]"
                ".find(b=>b.textContent==='Generate again').click()"
            )
            assert await tab.js(
                "byId('image-prompt').value==='Watercolor apple' && byId('image-seed').value==='42'"
            )
            # Exercise presentation of existing server states without new mutations.
            await tab.js(
                "(async()=>{window.studioJobRead=domainRequest; "
                "window.studioRealJobs=await domainRequest('/api/v1/library/jobs'); "
                "studioRealJobs.images=studioRealJobs.images.filter(item=>item.artifact); "
                "window.studioTestJobs=studioRealJobs; domainRequest=(...args)=>"
                "args[0]==='/api/v1/library/jobs' ? Promise.resolve(studioTestJobs) : "
                "studioJobRead(...args)})()"
            )
            for state, label in [
                ("running", "Generating"),
                ("failed", "Failed"),
                ("cancelled", "Cancelled"),
            ]:
                await tab.js(
                    "(async()=>{studioTestJobs={...studioRealJobs, "
                    "images:[{job:'state-fixture', "
                    "model:'A-very-long-model-name-'.repeat(12), status:"
                    + json.dumps(state)
                    + ", artifact:'', recoverable:"
                    + ("true" if state == "running" else "false")
                    + "},...studioRealJobs.images]}; await BrowserManagement.loadJobs()})()"
                )
                await tab.wait(
                    "byId('image-result-status').textContent.includes(" + json.dumps(label) + ")"
                )
                assert await tab.js(
                    "[...byId('image-jobs').querySelectorAll('button')]"
                    ".some(b=>b.textContent==='Cancel job')==="
                    + ("true" if state == "running" else "false")
                )
                assert await tab.js(
                    "byId('image-generate-panel').scrollWidth<="
                    "byId('image-generate-panel').clientWidth && "
                    "byId('image-jobs').children.length===studioRealJobs.images.length+1"
                )
            await tab.js(
                "(async()=>{domainRequest=studioJobRead; await BrowserManagement.loadJobs()})()"
            )
            await tab.js(
                "byId('image-jobs').querySelector('details').open=false; "
                "byId('image-jobs').querySelector('summary').focus()"
            )
            await tab.wait("document.activeElement===byId('image-jobs').querySelector('summary')")
            await tab.command(
                "Input.dispatchKeyEvent",
                {
                    "type": "keyDown",
                    "key": "Enter",
                    "code": "Enter",
                    "windowsVirtualKeyCode": 13,
                    "text": "\r",
                },
            )
            await tab.command(
                "Input.dispatchKeyEvent",
                {
                    "type": "keyUp",
                    "key": "Enter",
                    "code": "Enter",
                    "windowsVirtualKeyCode": 13,
                },
            )
            await tab.wait("byId('image-jobs').querySelector('details').open")
            shot = await tab.command("Page.captureScreenshot", {"format": "png"})
            (evidence / "job-actions-keyboard.png").write_bytes(base64.b64decode(shot["data"]))
            await tab.command(
                "Input.dispatchKeyEvent",
                {
                    "type": "keyDown",
                    "key": "Escape",
                    "code": "Escape",
                    "windowsVirtualKeyCode": 27,
                },
            )
            await tab.command(
                "Input.dispatchKeyEvent",
                {
                    "type": "keyUp",
                    "key": "Escape",
                    "code": "Escape",
                    "windowsVirtualKeyCode": 27,
                },
            )
            assert await tab.js(
                "byId('image-generate-panel').open && "
                "!byId('image-jobs').querySelector('details').open && "
                "document.activeElement===byId('image-jobs').querySelector('summary')"
            )
            await tab.js("byId('image-jobs').querySelector('details').open=true")
            await tab.click("#image-prompt")
            assert await tab.js("!byId('image-jobs').querySelector('details').open")
            # Reduced motion and short viewports retain one natural dialog scroller.
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 844,
                    "height": 390,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )
            await tab.command(
                "Emulation.setEmulatedMedia",
                {
                    "features": [
                        {"name": "prefers-reduced-motion", "value": "reduce"},
                        {"name": "forced-colors", "value": "active"},
                    ]
                },
            )
            await tab.js("byId('image-advanced').open=true")
            assert await tab.js(
                "byId('image-generate-panel').scrollWidth<=byId('image-generate-panel').clientWidth"
            )
            await tab.command("Emulation.setEmulatedMedia", {"features": []})
            service_state["wait"] = True
            await tab.js("byId('image-seed').value='43'; byId('image-generate').requestSubmit()")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait("byId('image-jobs').textContent.includes('Generating')")
            await tab.click("#attach-file")
            await tab.click("#attach-create-image")
            await tab.wait(
                "[...byId('image-jobs').querySelectorAll('button')]"
                ".some(b=>b.textContent==='Cancel job')"
            )
            await tab.js(
                "byId('image-history').open=true; "
                "byId('image-jobs').querySelector('details').open=true; "
                "[...byId('image-jobs').querySelectorAll('button')]"
                ".find(b=>b.textContent==='Cancel job').click()"
            )
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "byId('image-jobs').textContent.includes('Cancelled') && "
                "!BrowserManagement.hasPending()"
            )
            await tab.click("#attach-file")
            await tab.click("#attach-create-image")
            await tab.wait("byId('image-service-status').textContent==='Ready'")
            await tab.js(
                "window.originalStudioRequest=domainRequest; domainRequest=(...args)=>"
                "args[0]==='/api/v1/library/image-capabilities' ? "
                "Promise.reject(new Error('Fixture image service unavailable')) : "
                "window.originalStudioRequest(...args)"
            )
            await tab.click("#image-generate-close")
            await tab.click("#attach-file")
            await tab.click("#attach-create-image")
            await tab.wait(
                "byId('image-capabilities-status').textContent.includes('Fixture image')"
            )
            assert await tab.js(
                "byId('image-prompt').getClientRects().length>0 && byId('image-submit').disabled"
            )
            await tab.click("#image-generate-close")
            await tab.js(
                "showView('library'); librarySection='outputs'; renderFileToolbar(); "
                "BrowserManagement.loadJobs()"
            )
            await tab.wait("!byId('image-add').disabled")
            await tab.click("#image-add")
            await tab.click("#generation-tab-research")
            await tab.js(
                "(async()=>{window.creationJobs=await domainRequest('/api/v1/library/jobs')})()"
            )
            assert await tab.js(
                "byId('research-context-summary').textContent==="
                "`Context: ${creationJobs.research_defaults.context_tokens} tokens` && "
                "byId('research-output-summary').textContent==="
                "`Output: ${creationJobs.research_defaults.output_tokens} tokens`"
            )
            for width, height in [(320, 568), (390, 720), (768, 900), (900, 900), (1440, 900)]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                )
                for mode in ["light", "dark"]:
                    await tab.js(
                        "applyAppearance(appearance={...appearance,theme:"
                        + json.dumps(mode)
                        + "}); byId('image-generate-panel').scrollTop=0; "
                        "byId('research-question').focus()"
                    )
                    assert await tab.js(
                        "byId('image-generate-panel').scrollWidth<="
                        "byId('image-generate-panel').clientWidth && "
                        "byId('research-question').getBoundingClientRect().width>100 && "
                        "byId('research-options').getBoundingClientRect().height>=44"
                    )
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (evidence / f"research-{width}-{mode}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                    await tab.click("#research-options")
                    await tab.wait("byId('research-create-settings').open")
                    assert await tab.js(
                        "byId('research-create-settings').scrollWidth<="
                        "byId('research-create-settings').clientWidth && "
                        "byId('research-format').getClientRects().length>0"
                    )
                    if width in (320, 1440):
                        shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (evidence / f"research-settings-{width}-{mode}.png").write_bytes(
                            base64.b64decode(shot["data"])
                        )
                    for phase in ["keyDown", "keyUp"]:
                        await tab.command(
                            "Input.dispatchKeyEvent",
                            {
                                "type": phase,
                                "key": "Escape",
                                "code": "Escape",
                                "windowsVirtualKeyCode": 27,
                            },
                        )
                    await tab.wait(
                        "!byId('research-create-settings').open && "
                        "document.activeElement===byId('research-options')"
                    )
            await tab.js(
                "byId('research-question').value='Compare local image workflows'; "
                "byId('research-create').requestSubmit()"
            )
            await tab.wait("reviewDialog.open")
            assert await tab.js(
                "byId('domain-review-summary').textContent.includes('Queue Research')"
            )
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "!BrowserManagement.hasPending() && "
                "byId('research-jobs').textContent.includes('Compare local image workflows')"
            )
            await tab.click("#image-add")
            await tab.wait("byId('image-generate-panel').open")
            assert await tab.js(
                "byId('research-question').value==='' && byId('research-format').value==='report'"
            )
            await tab.js(
                "byId('research-history').open=true; "
                "[...byId('research-jobs').querySelectorAll('button')]"
                ".find(button=>button.textContent==='Start').click()"
            )
            await tab.wait("reviewDialog.open")
            assert await tab.js(
                "byId('domain-review-summary').textContent.includes('Start Research')"
            )
            await tab.click("#domain-review-cancel")
            await tab.wait("!reviewDialog.open && !BrowserManagement.hasPending()")
            await tab.click("#image-add")
            await tab.click("#generation-tab-image")
            # The deliberately failed service keeps Generate disabled; settings remain usable.
            await tab.click("#image-options")
            await tab.wait("byId('image-create-settings').open")
            await tab.js("byId('image-steps').value='20'")
            await tab.click("#image-create-settings-done")
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "research_review_pattern": "summary, settings, drafts, queue review",
                        "chat_image_studio": "Chat entries, Uploads, service failure",
                        "workflow": "ratios, drafts, review, output, download, cancellation",
                        "widths": [320, 390, 768, 900, 1440],
                        "console_errors": 0,
                        "screenshots": str(evidence),
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)
        service_fixture.close()


if __name__ == "__main__":
    main(verify)

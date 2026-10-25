"""Real inline Source/Tags acceptance with existing reviewed backend workers.

Uses the isolated inspector fixture and local Vision protocol server. Concurrent
writes deliberately exercise real revision rejection; persistence is not mocked.
Run: .venv/bin/python scripts/webui_metadata_smoke.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
import webui_inspector_smoke as inspector
from webui_control_smoke import Tab


async def verify(host, service, root, chrome, image, mode, calls, _set_default):
    output = Path("/tmp/klaude-metadata-refinement")
    output.mkdir(exist_ok=True)
    profile = root / "chrome-metadata"
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
            await tab.command("Emulation.setEmulatedMedia", {
                "features": [{"name": "prefers-reduced-motion", "value": "reduce"}],
            })
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait("typeof byId!=='undefined' && !byId('local-access').hidden")
            await tab.js('byId("login-username").value="admin";'
                        'byId("login-password").value=' + json.dumps(
                host.accounts.initial_password()
            ) + ';byId("account-login").requestSubmit()')
            await tab.wait("latest?.session_id && authenticated")

            async def wait(expression):
                for _ in range(300):
                    if await tab.js(expression):
                        return
                    await asyncio.sleep(.05)
                raise AssertionError((expression, await tab.js(
                    "({source:byId('artifact-source-status').textContent,"
                    "tags:byId('artifact-tags-status').textContent,"
                    "vision:byId('vision-status').textContent,review:reviewDialog.open,"
                    "item:selectedArtifact,operations:byId('domain-operations').textContent})"
                )))

            tab.wait = wait

            async def click(selector):
                await tab.js("new Promise(requestAnimationFrame)")
                await tab.js("Promise.race([Promise.all([...document.querySelectorAll("
                    "'dialog[open]')].flatMap(d=>d.getAnimations({subtree:true}))"
                    ".filter(a=>a.effect.getTiming().iterations!==Infinity)"
                    ".map(a=>a.finished.catch(()=>{}))),"
                    "new Promise(resolve=>setTimeout(resolve,350))])")
                point = None
                for _ in range(10):
                    point = await tab.js("""(async () => {
                  const b=document.querySelector(""" + json.dumps(selector) + """);
                  if (!b || b.disabled || b.closest('[hidden],[inert]')) return null;
                  b.scrollIntoView({block:'nearest'});
                  await new Promise(requestAnimationFrame);
                  const r=b.getClientRects()[0]; if(!r) return null;
                  const x=r.x+r.width/2, y=r.y+r.height/2;
                  return b.contains(document.elementFromPoint(x,y)) ? {x,y} : null;
                })()""")
                    if point:
                        break
                    await asyncio.sleep(.05)
                if not point:
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / "failed-control.png").write_bytes(base64.b64decode(shot["data"]))
                    raise AssertionError((selector, await tab.js("""(() => {
                      const b=document.querySelector(""" + json.dumps(selector) + """);
                      const r=b.getBoundingClientRect();
                      return {disabled:b.disabled,hidden:b.closest('[hidden]')?.id,
                        inert:b.closest('[inert]')?.id,rect:r.toJSON(),
                        hit:document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.outerHTML,
                        source:byId('artifact-source-status').textContent,
                        tags:byId('artifact-tags-status').textContent};
                    })()""")))
                for kind in ("mousePressed", "mouseReleased"):
                    await tab.command("Input.dispatchMouseEvent", {
                        "type": kind, **point, "button": "left", "clickCount": 1,
                    })

            async def fill(identity, value):
                await tab.js(f"byId({json.dumps(identity)}).value={json.dumps(value)};"
                             f"byId({json.dumps(identity)}).dispatchEvent("
                             "new Event('input',{bubbles:true}))")

            async def enter():
                for kind in ("keyDown", "keyUp"):
                    await tab.command("Input.dispatchKeyEvent", {
                        "type": kind, "key": "Enter", "code": "Enter",
                        "windowsVirtualKeyCode": 13,
                    })

            async def open_image(refresh=False):
                if refresh:
                    if await tab.js("artifactDialog.open"):
                        await click("#artifact-close")
                    await click("#library-refresh")
                    await tab.wait("!byId('library-items').classList.contains('is-loading')")
                await tab.js(f"openArtifact({json.dumps(image['id'])})")
                await tab.wait("selectedArtifact?.id===" + json.dumps(image["id"]))
                if await tab.js("artifactDialog.dataset.details==='closed'"):
                    await click("#image-details")
                await click("#inspector-tab-details")

            async def confirm():
                await tab.wait("reviewDialog.open && artifactDialog.open")
                await click("#domain-review-confirm")
                await tab.wait("!reviewDialog.open")

            async def screenshot(name):
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / name).write_bytes(base64.b64decode(shot["data"]))

            await click("#nav-library")
            await open_image()
            await tab.js("window.metadataReviews=0;window.metadataFetch=fetch;"
                         "window.fetch=(input,options)=>{"
                         "if(String(input).endsWith('/library/review'))metadataReviews++;"
                         "return metadataFetch(input,options)}")
            assert await tab.js("byId('artifact-source').textContent==='No source link added.'")
            await click("#artifact-source-edit")
            assert await tab.js("byId('artifact-source-save').disabled")
            await fill("artifact-source-input", "https://cancelled.test/source")
            await click("#artifact-source-cancel")
            assert service.artifacts.get(image["id"])["source_url"] == ""
            assert await tab.js("metadataReviews===0")

            await click("#artifact-source-edit")
            for value in ("javascript:alert(1)", "https://u:p@example.test", "https:///missing",
                          "https://example.test:0/x", "https://example.test/a b"):
                await fill("artifact-source-input", value)
                await click("#artifact-source-save")
                assert await tab.js("!reviewDialog.open && metadataReviews===0 && "
                                   "byId('artifact-source-status').dataset.state==='error'")
                assert await tab.js("byId('artifact-source-input').value===" + json.dumps(value))
            source = "https://example.test/image?original=" + "a" * 1200 + "#full-value"
            await fill("artifact-source-input", "  " + source + "  ")
            await click("#artifact-source-save")
            await tab.wait("reviewDialog.open")
            assert service.artifacts.get(image["id"])["source_url"] == ""
            await confirm()
            await tab.wait("byId('artifact-source-status').textContent==='Saved.'")
            assert service.artifacts.get(image["id"])["source_url"] == source
            assert await tab.js("""(() => {
              const a=byId('artifact-source').querySelector('a');
              return a.target==='_blank' && a.rel==='noopener noreferrer' &&
                a.scrollWidth>a.clientWidth && getComputedStyle(a).textOverflow==='ellipsis';
            })()""")

            await click("#artifact-source-edit")
            await fill("artifact-source-input", "https://cancelled-edit.test")
            await click("#artifact-source-cancel")
            assert service.artifacts.get(image["id"])["source_url"] == source
            await click("#artifact-source-remove")
            await tab.wait("reviewDialog.open")
            await click("#domain-review-cancel")
            assert service.artifacts.get(image["id"])["source_url"] == source
            await click("#artifact-source-cancel")
            await click("#artifact-source-remove")
            await confirm()
            await tab.wait("byId('artifact-source-status').textContent==='Saved.'")
            assert service.artifacts.get(image["id"])["source_url"] == ""

            # A real stale revision rejects preparation without losing typed source.
            await click("#artifact-source-edit")
            await fill("artifact-source-input", source)
            stored = service.artifacts.get(image["id"])
            service.artifacts.change(image["id"], stored["revision"], "tags", "External tag")
            await click("#artifact-source-save")
            await tab.wait("byId('artifact-source-status').dataset.state==='error'")
            assert not await tab.js("byId('artifact-source-form').hidden")
            assert await tab.js("byId('artifact-source-input').value===" + json.dumps(source))
            assert service.artifacts.get(image["id"])["source_url"] == ""
            await click("#artifact-source-cancel")
            await open_image(refresh=True)
            await click("#artifact-source-edit")
            await fill("artifact-source-input", "https://example.test/saved")
            await click("#artifact-source-save")
            await confirm()
            await tab.wait("byId('artifact-source-status').textContent==='Saved.'")

            # Editing alone must not run inference or submit persistence requests.
            inference_count = len([call for call in calls if call[0] == "/api/chat"])
            before = await tab.js("metadataReviews")
            await click("#artifact-tags-edit")
            assert await tab.js("byId('artifact-tags-save').disabled")
            await fill("artifact-tag-new", "Unsaved input")
            assert await tab.js("metadataReviews") == before
            assert len([call for call in calls if call[0] == "/api/chat"]) == inference_count
            await click("#artifact-tags-cancel")
            assert service.artifacts.get(image["id"])["tags"] == ["External tag"]
            await click("#artifact-tags-edit")
            await click("#artifact-tag-list button")
            await fill("artifact-tag-new", "  Artwork  ")
            await tab.js("byId('artifact-tag-new').focus()")
            await enter()
            await fill("artifact-tag-new", "artWORK")
            await click("#artifact-tag-add")
            await fill("artifact-tag-new", "Useful    reference")
            await click("#artifact-tag-add")
            assert await tab.js("byId('artifact-tags-input').value==='Artwork, Useful reference'")
            await click("#artifact-tags-save")
            await tab.wait("reviewDialog.open")
            assert service.artifacts.get(image["id"])["tags"] == ["External tag"]
            await confirm()
            await tab.wait("byId('artifact-tags-status').textContent==='Saved.'")
            assert service.artifacts.get(image["id"])["tags"] == ["Artwork", "Useful reference"]

            # Both character and count limits are enforced before a review request.
            await click("#artifact-tags-edit")
            before = await tab.js("metadataReviews")
            await fill("artifact-tag-new", "x" * 41)
            await click("#artifact-tag-add")
            assert await tab.js("byId('artifact-tags-status').dataset.state==='error'")
            await fill("artifact-tag-new", ",".join(f"Tag {i}" for i in range(19)))
            await click("#artifact-tag-add")
            assert await tab.js("byId('artifact-tags-status').dataset.state==='error'")
            assert await tab.js("metadataReviews") == before
            await click("#artifact-tags-cancel")

            # Genuine backend suggestions are offered separately; selection only edits the draft.
            mode["value"], mode["text"] = "good", '["diagram", "Artwork"]'
            await click("#inspector-tab-ai-review")
            await tab.wait("!byId('vision-suggest').disabled")
            assert await tab.js("byId('vision-suggest').textContent==='Generate tag suggestions'")
            await click("#vision-suggest")
            await tab.wait("reviewDialog.open && !artifactDialog.open")
            await click("#domain-review-confirm")
            await tab.wait("artifactDialog.open && "
                           "!!document.querySelector('.tag-filter-chip[data-tag=diagram]') && "
                           "!byId('vision-suggest').disabled")
            await click("#inspector-tab-details")
            await click("#artifact-tags-edit")
            await tab.wait("!byId('artifact-tag-suggestions').hidden")
            assert await tab.js("byId('artifact-tag-suggestion-list').children.length===1")
            await click("#artifact-tag-suggestion-list button")
            assert "diagram" not in service.artifacts.get(image["id"])["tags"]
            await click("#artifact-tags-cancel")
            assert "diagram" not in service.artifacts.get(image["id"])["tags"]
            await click("#artifact-tags-edit")
            await click("#artifact-tag-suggestion-list button")
            await click("#artifact-tags-save")
            await confirm()
            await tab.wait("byId('artifact-tags-status').textContent==='Saved.'")
            assert "diagram" in service.artifacts.get(image["id"])["tags"]
            assert service.artifacts.get(image["id"])["ai_tags"] == []

            # Change the real file after review but before the worker's effect check.
            await click("#artifact-tags-edit")
            await fill("artifact-tag-new", "Keep this draft")
            await click("#artifact-tag-add")
            await click("#artifact-tags-save")
            await tab.wait("reviewDialog.open")
            stored = service.artifacts.get(image["id"])
            service.artifacts.change(image["id"], stored["revision"], "source_link",
                                     "https://example.test/concurrent")
            await confirm()
            await tab.wait("byId('artifact-tags-status').dataset.state==='error'")
            assert "Keep this draft" not in service.artifacts.get(image["id"])["tags"]
            assert await tab.js("!byId('artifact-tag-editor').hidden && "
                               "byId('artifact-tags-input').value.includes('Keep this draft') && "
                               "!byId('artifact-tags-save').disabled")
            await click("#artifact-tags-cancel")
            await open_image(refresh=True)

            layouts = []
            for theme in ("light", "dark"):
                await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                for width, height in ((320, 568), (390, 844), (768, 1024), (1440, 900)):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
                    })
                    if await tab.js("artifactDialog.dataset.details==='closed'"):
                        await click("#image-details")
                    await click("#artifact-source-edit")
                    await fill("artifact-source-input", source)
                    await click("#artifact-tags-edit")
                    state = await tab.js("""(() => {
                      const s=byId('artifact-information')
                        .querySelector('.preview-information-scroll');
                      return {width:innerWidth,overflow:s.scrollWidth>s.clientWidth,
                        form:!byId('artifact-source-form').hidden &&
                          !byId('artifact-tag-editor').hidden,
                        safe:document.documentElement.scrollWidth<=innerWidth,
                        chips:[...byId('artifact-tag-list').querySelectorAll('.input-chip')]
                          .every(chip=>{const face=chip.querySelector('.filter-chip-face');
                            const style=getComputedStyle(face),remove=chip.querySelector('button');
                            return face.getBoundingClientRect().height>=32 &&
                              style.borderTopLeftRadius==='8px' && style.fontSize==='14px' &&
                              (!remove || remove.getBoundingClientRect().height>=48)})};
                    })()""")
                    assert (not state["overflow"] and state["safe"] and state["form"]
                            and state["chips"]), state
                    await tab.js("byId('artifact-information').querySelector("
                                 "'.preview-information-scroll').scrollTop=0")
                    await screenshot(f"metadata-{theme}-{width}.png")
                    await click("#artifact-tags-cancel")
                    await click("#artifact-source-cancel")
                    layouts.append({"theme": theme, **state})
            assert not tab.errors, tab.errors
            return {"source_add_edit_remove_cancel_validation_stale_failure": "passed",
                    "tags_normalization_duplicates_limits_cancel_worker_failure": "passed",
                    "actual_ai_suggestions_explicit_draft_save": "passed",
                    "layouts": layouts, "browser_exceptions": 0, "screenshots": str(output)}
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    inspector.verify = verify
    inspector.main()

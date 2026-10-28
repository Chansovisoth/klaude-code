"""Source editor lifecycle regression with an isolated host and real image storage."""

from __future__ import annotations

import asyncio
import json
import subprocess
from urllib.request import Request, urlopen

import websockets
import webui_inspector_smoke as inspector
from webui_control_smoke import Tab


async def verify(host, service, root, chrome, image, mode, calls, *_):
    profile = root / "chrome-source-editor"
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
            await tab.js(
                "showView('library');window.sourceEditorNode=byId('artifact-source-input')"
            )

            async def open_image():
                await tab.js(f"openArtifact({json.dumps(image['id'])})")
                await tab.wait(
                    "selectedArtifact?.id==="
                    + json.dumps(image["id"])
                    + " && byId('artifact-preview').querySelector('img')?.naturalWidth>0"
                )
                if await tab.js("artifactDialog.dataset.details==='closed'"):
                    await tab.click("#image-details")
                await tab.js(
                    "new Promise(resolve=>requestAnimationFrame("
                    "()=>requestAnimationFrame(resolve)))"
                )
                await tab.wait("!byId('artifact-source-edit').disabled")

            async def assert_intact():
                assert await tab.js(
                    "byId('artifact-source-input')===sourceEditorNode && "
                    "sourceEditorNode.isConnected && "
                    "byId('artifact-preview').querySelector('img')?.naturalWidth>0 && "
                    "!byId('artifact-source-status').textContent && !reviewDialog.open"
                )
                assert not tab.errors, tab.errors

            for width in (1440, 390):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 844,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                await open_image()
                for tab_id, direction in (("inspector-tab-ai-review", 1),
                                          ("inspector-tab-details", -1)):
                    indicator_start = await tab.js(
                        "byId('inspector-tabs').querySelector('.mtrl-tabs__indicator')"
                        ".getBoundingClientRect().left"
                    )
                    await tab.click("#" + tab_id)
                    await asyncio.sleep(.1)
                    indicator_progress = await tab.js(
                        "byId('inspector-tabs').querySelector('.mtrl-tabs__indicator')"
                        ".getBoundingClientRect().left"
                    )
                    assert (indicator_progress - indicator_start) * direction > 1, (
                        f"tab indicator did not animate toward {tab_id}: "
                        f"{indicator_start} -> {indicator_progress}"
                    )
                    await asyncio.sleep(.75)
                    indicator_metrics = await tab.js("""(() => {
                        const tabs=byId('inspector-tabs');
                        const tab=tabs.querySelector('[aria-selected=true]');
                        const label=tab.querySelector('.mtrl-button__text');
                        const indicator=tabs.querySelector('.mtrl-tabs__indicator');
                        const width=Math.max(24,label.offsetWidth-4);
                        const expectedLeft=tab.offsetLeft+label.offsetLeft+
                            (label.offsetWidth-width)/2;
                        const transformX=Number(
                            indicator.style.transform.match(/translateX\\(([-\\d.]+)px\\)/)?.[1]);
                        return {primary:tabs.classList.contains('mtrl-tabs--primary'),
                            tabHeight:tab.getBoundingClientRect().height,
                            indicatorHeight:indicator.getBoundingClientRect().height,
                            indicatorWidth:Number.parseFloat(indicator.style.width),
                            expectedWidth:width,
                            indicatorLeft:transformX, expectedLeft,
                            fontSize:getComputedStyle(tab).fontSize};
                    })()""")
                    assert (indicator_metrics["primary"] and
                            indicator_metrics["tabHeight"] == 48 and
                            indicator_metrics["indicatorHeight"] == 3 and
                            abs(indicator_metrics["indicatorWidth"] -
                                indicator_metrics["expectedWidth"]) < 1 and
                            abs(indicator_metrics["indicatorLeft"] -
                                indicator_metrics["expectedLeft"]) < 0.1 and
                            indicator_metrics["fontSize"] == "14px"), indicator_metrics
                await tab.js("byId('inspector-tab-details').focus()")
                for event_type in ("keyDown", "keyUp"):
                    await tab.command("Input.dispatchKeyEvent", {
                        "type":event_type,"key":"End","code":"End","windowsVirtualKeyCode":35,
                    })
                assert await tab.js("document.activeElement===byId('inspector-tab-ai-review') && "
                    "byId('inspector-tab-ai-review').getAttribute('aria-selected')==='true'")
                await tab.click("#inspector-tab-details")
                assert await tab.js("""(() => {
                    const close=byId('artifact-close'), more=byId('artifact-more');
                    const a=close.getBoundingClientRect(), b=more.getBoundingClientRect();
                    return !byId('preview-sidebar-toggle') &&
                        more.nextElementSibling===close &&
                        artifactDialog.querySelector('.preview-heading').contains(more) &&
                        !byId('artifact-information').contains(more) &&
                        Math.abs(a.top-b.top)<1 && b.right<=a.left &&
                        a.width>=44 && b.width>=44 && a.right<=innerWidth;
                })()""")
                await tab.click("#artifact-more")
                await tab.wait("byId('artifact-more').getAttribute('aria-expanded')==='true'")
                for event_type in ("keyDown", "keyUp"):
                    await tab.command("Input.dispatchKeyEvent", {
                        "type": event_type, "key": "Escape", "code": "Escape",
                        "windowsVirtualKeyCode": 27,
                    })
                assert await tab.js(
                    "byId('artifact-more').getAttribute('aria-expanded')==='false' && "
                    "document.activeElement===byId('artifact-more') && artifactDialog.open"
                )
                for _ in range(3):
                    await tab.click("#artifact-source-edit")
                    await tab.wait("document.activeElement===sourceEditorNode")
                    await tab.js("sourceEditorNode.blur()")
                    await tab.wait("!byId('artifact-source-edit').hidden")
                    await assert_intact()

                await tab.click("#artifact-source-edit")
                await tab.command(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyDown",
                        "key": "Escape",
                        "code": "Escape",
                        "windowsVirtualKeyCode": 27,
                    },
                )
                await tab.wait("!byId('artifact-source-edit').hidden")
                await assert_intact()
                await tab.click("#artifact-close")
                await open_image()
                await assert_intact()

                url = f"https://example.test/source-{width}"
                await tab.click("#artifact-source-edit")
                await tab.js(
                    "sourceEditorNode.value="
                    + json.dumps(url)
                    + ";sourceEditorNode.dispatchEvent(new Event('input',{bubbles:true}));"
                    "sourceEditorNode.blur()"
                )
                await tab.wait(
                    "byId('artifact-source').querySelector('a')?.textContent===" + json.dumps(url)
                )
                assert service.artifacts.get(image["id"])["source_url"] == url
                await assert_intact()
                await tab.click("#artifact-close")
                await open_image()
                await assert_intact()
                await tab.click("#artifact-source-edit")
                note = "From Discord — @artist\nOriginal concept notes <script>literal</script>"
                await tab.js(
                    "sourceEditorNode.value="
                    + json.dumps(note)
                    + ";sourceEditorNode.dispatchEvent(new Event('input',{bubbles:true}));"
                    "sourceEditorNode.blur()"
                )
                await tab.wait("byId('artifact-source').textContent===" + json.dumps(note))
                assert service.artifacts.get(image["id"])["source_url"] == note
                assert await tab.js("!byId('artifact-source').querySelector('a,script')")
                await assert_intact()
                await tab.click("#artifact-tags-edit")
                await tab.wait("document.activeElement===byId('artifact-tag-new')")
                assert await tab.js("byId('artifact-tag-draft').contains(document.activeElement)")
                await tab.js(
                    "byId('artifact-tag-new').value='Concept art';"
                    "byId('artifact-tag-new').dispatchEvent(new Event('input',{bubbles:true}))"
                )
                await tab.command(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyDown",
                        "key": "Enter",
                        "code": "Enter",
                        "windowsVirtualKeyCode": 13,
                    },
                )
                assert await tab.js(
                    "byId('artifact-tag-items').textContent.includes('Concept art') && "
                    "byId('artifact-tag-new').isConnected && !reviewDialog.open"
                )
                await tab.js("byId('artifact-tag-new').value='Uncommitted tag'")
                await tab.command(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyDown",
                        "key": "Escape",
                        "code": "Escape",
                        "windowsVirtualKeyCode": 27,
                    },
                )
                await tab.wait("byId('artifact-tag-editor').hidden")
                assert await tab.js(
                    "artifactDialog.open && artifactDialog.dataset.details!=='closed' && "
                    "document.activeElement===byId('artifact-tags-edit') && "
                    "byId('artifact-tag-new').value==='' && "
                    "!byId('artifact-tag-items').textContent.includes('Concept art')"
                )
                await assert_intact()
                assert "Concept art" not in service.artifacts.get(image["id"])["tags"]
                assert "Uncommitted tag" not in service.artifacts.get(image["id"])["tags"]
                await tab.click("#artifact-tags-edit")
                tag = f"Saved tag {width}"
                await tab.js("byId('artifact-tag-new').value=" + json.dumps(tag))
                await tab.click("#artifact-tag-add")
                await tab.click("#artifact-tags-save")
                await tab.wait("byId('artifact-tag-editor').hidden && !reviewDialog.open")
                assert tag in service.artifacts.get(image["id"])["tags"]
                await assert_intact()
                await tab.click("#artifact-source-edit")
                await tab.js(
                    "sourceEditorNode.value='Notes from Discord';"
                    "sourceEditorNode.setSelectionRange(18,18)"
                )
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
                assert await tab.js(
                    "sourceEditorNode.value==='Notes from Discord\\n' && "
                    "!byId('artifact-source-form').hidden"
                )
                mixed = (
                    "Notes from Discord\nhttps://example.test/first\nhttps://example.test/second"
                )
                await tab.js(
                    "window.sourceOriginalFetch=fetch;window.fetch=async(...args)=>{"
                    "if(String(args[0]).endsWith('/library/review'))"
                    "await new Promise(r=>setTimeout(r,250));"
                    "return sourceOriginalFetch(...args)};"
                    "sourceEditorNode.value="
                    + json.dumps(mixed)
                    + ";sourceEditorNode.dispatchEvent(new Event('input',{bubbles:true}));"
                    "sourceEditorNode.blur();artifactDialog.close()"
                )
                for _ in range(200):
                    if service.artifacts.get(image["id"])["source_url"] == mixed:
                        break
                    await asyncio.sleep(0.05)
                assert service.artifacts.get(image["id"])["source_url"] == mixed
                await tab.js("window.fetch=sourceOriginalFetch")
                await open_image()
                await tab.wait("byId('artifact-source').textContent===" + json.dumps(mixed))
                assert await tab.js("byId('artifact-source').querySelectorAll('a').length===2")
                await assert_intact()
                await tab.click("#artifact-close")
            await open_image()
            await tab.click("#inspector-tab-ai-review")
            await tab.wait("!byId('vision-suggest').disabled")
            mode["text"] = '["suggested", "illustration"]'
            saved_tags = service.artifacts.get(image["id"])["ai_tags"]
            mode["value"] = "slow"
            await tab.click("#vision-suggest")
            await tab.wait("byId('vision-suggest-label').textContent==='Cancel tag suggestions'")
            assert await tab.js("""!byId('vision-empty').hidden&&
              byId('vision-empty').querySelector('h3').textContent==='Generating tag suggestions'&&
              Boolean(byId('vision-empty-icon').querySelector('.material-loading'))&&
              byId('vision-cancel').hidden""")
            for _ in range(300):
                if await tab.js("!!document.querySelector('.tag-filter-chip[data-tag=suggested]')"):
                    break
                await asyncio.sleep(0.05)
            else:
                raise AssertionError("Tag suggestions did not finish")
            mode["value"] = "good"
            assert await tab.js("""(()=>{
              const result=byId('vision-results'), chip=result.querySelector('.tag-filter-chip');
              const reference=document.querySelector('.preview-tag.input-chip .filter-chip-face');
              const face=chip.querySelector('.filter-chip-face');
              const a=getComputedStyle(face),b=getComputedStyle(reference);
              const matches=a.padding===b.padding&&a.lineHeight===b.lineHeight&&
                getComputedStyle(result.querySelector('.preview-tags')).gap===
                getComputedStyle(byId('artifact-tag-list')).gap&&
                Math.abs(chip.getBoundingClientRect().height-32)<1;
              chip.click();
              return matches&&getComputedStyle(face).padding===b.padding&&
                byId('vision-suggest').nextElementSibling===result&&
                result.querySelector('.vision-tag-selector').firstElementChild===
                  result.querySelector('.preview-tags');
            })()""")
            assert await tab.js("""(() => {
                const actions=document.querySelector('.vision-tag-selector .preview-edit-actions');
                return actions.firstElementChild.textContent==='Clear' &&
                    actions.lastElementChild.textContent==='Save' &&
                    getComputedStyle(actions).justifyContent==='flex-end' &&
                    !actions.firstElementChild.disabled && !actions.lastElementChild.disabled;
            })()""")
            await tab.click(".vision-tags-clear")
            assert await tab.js("!document.querySelector('.tag-filter-chip[aria-pressed=true]') && "
                "document.querySelector('.vision-tags-save').disabled && "
                "document.querySelector('.vision-tags-clear').disabled")
            mode["value"] = "slow"
            await tab.click("#vision-suggest")
            await tab.wait(
                "byId('vision-suggest-label').textContent==='Cancel tag suggestions' && "
                "!byId('vision-suggest').disabled"
            )
            await tab.click("#vision-suggest")
            await tab.wait(
                "byId('vision-suggest-label').textContent==='Generate new tag suggestions' && "
                "!byId('vision-suggest').disabled"
            )
            mode["value"] = "good"
            assert await tab.js("!byId('vision-results').hidden")
            assert await tab.js("artifactDialog.open && !reviewDialog.open")
            assert service.artifacts.get(image["id"])["ai_tags"] == saved_tags
            await assert_intact()
            await tab.wait("!byId('vision-submit').disabled")
            assert await tab.js(
                "byId('vision-selected-model').textContent.includes('vision') && "
                "byId('vision-selected-context').textContent.includes('4096') && "
                "byId('vision-selected-output').textContent.includes('512')"
            )
            await tab.click("#vision-options")
            await tab.js(
                "byId('vision-model-mode').value='session';"
                "byId('vision-model-mode').dispatchEvent(new Event('change',{bubbles:true}))"
            )
            await tab.wait(
                "[...byId('vision-session-model').options].some(o=>o.value.endsWith('/other'))"
            )
            await tab.js(
                "byId('vision-session-model').value=[...byId('vision-session-model').options]"
                ".find(o=>o.value.endsWith('/other')).value;"
                "byId('vision-session-model').dispatchEvent(new Event('change',{bubbles:true}));"
                "byId('vision-context').value='8192';byId('vision-output').value='1024';"
                "byId('vision-context').dispatchEvent(new Event('input',{bubbles:true}))"
            )
            await tab.click("#vision-settings-done")
            assert await tab.js(
                "byId('vision-selected-model').textContent.includes('other') && "
                "byId('vision-selected-context').textContent.includes('8192') && "
                "byId('vision-selected-output').textContent.includes('1024')"
            )
            mode["text"] = "Direct image review result."
            mode["value"] = "slow"
            await tab.click("#vision-submit")
            await tab.wait("byId('vision-submit').textContent==='Cancel review'")
            assert await tab.js("""!byId('vision-empty').hidden&&
              byId('vision-empty').querySelector('h3').textContent==='Generating review'&&
              Boolean(byId('vision-empty-icon').querySelector('.material-loading'))&&
              byId('vision-cancel').hidden""")
            for _ in range(300):
                if await tab.js(
                    "byId('vision-answer').textContent.includes('Direct image review result.')"
                ):
                    break
                await asyncio.sleep(0.05)
            else:
                raise AssertionError(
                    await tab.js(
                        "JSON.stringify({status:byId('vision-status').textContent,"
                        "state:byId('artifact-vision').dataset.state,"
                        "answer:byId('vision-answer').textContent})"
                    )
                )
            mode["value"] = "good"
            await assert_intact()
            sent = [body for path, body in calls if path == "/api/chat"][-1]
            assert sent["model"] == "other" and sent["options"] == {
                "num_ctx": 8192,
                "num_predict": 1024,
            }
            await tab.click("#artifact-close")
            await open_image()
            await tab.click("#inspector-tab-ai-review")
            assert await tab.js(
                "byId('vision-model-mode').value==='session' && "
                "byId('vision-selected-model').textContent.includes('other')"
            )
            await tab.wait("!byId('vision-options').disabled")
            await tab.click("#vision-options")
            await tab.click("#vision-settings-reset")
            assert await tab.js(
                "byId('vision-context').value==='4096' && "
                "byId('vision-output').value==='512' && "
                "byId('vision-model-mode').value==='default'"
            )
            assert await tab.js(
                "(()=>{const reset=byId('vision-settings-reset').getBoundingClientRect(),"
                "done=byId('vision-settings-done').getBoundingClientRect();"
                "return reset.left<done.left&&Math.abs(reset.top-done.top)<1})()"
            )
            await tab.click("#vision-settings-done")
            assert await tab.js("byId('vision-selected-model').textContent.includes('vision')")
            mode["value"] = "slow"
            await tab.click("#vision-submit")
            await tab.wait(
                "byId('vision-submit').textContent==='Cancel review' && "
                "!byId('vision-submit').disabled"
            )
            await tab.click("#vision-submit")
            await tab.wait(
                "byId('vision-submit').textContent==='Review image' && "
                "!byId('vision-submit').disabled"
            )
            mode["value"] = "good"
            await tab.wait("!byId('vision-clear').hidden")
            await tab.click("#vision-clear")
            await tab.wait("byId('vision-latest').hidden && byId('vision-clear').hidden")
            await tab.click("#artifact-close")
            await open_image()
            await tab.click("#inspector-tab-ai-review")
            await tab.wait("byId('artifact-vision').dataset.state==='empty'")
            assert await tab.js("byId('vision-clear').hidden && byId('vision-answer').hidden")
            return {
                "viewports": [1440, 390],
                "repeated_empty_blurs": 6,
                "direct_saves": 6,
                "close_during_save": "passed",
                "multiline_enter_and_multiple_sources": "passed",
                "image_reopen": "passed",
                "direct_tag_suggestions": "passed",
                "tag_generating_cancel_and_details_spacing": "passed",
                "direct_image_review": "passed",
                "clear_review_survives_reopen": "passed",
                "generating_review_and_cancel_button": "passed",
                "vision_session_model_and_budgets": "passed",
                "browser_exceptions": len(tab.errors),
            }
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    inspector.verify = verify
    inspector.main()

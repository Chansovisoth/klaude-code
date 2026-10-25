"""Real Chrome file inspector, sanitized Markdown and reviewed Vision acceptance.

Uses temporary stores and the existing local Vision protocol fixture; no live
model, external service, or personal Library data is used.
Run: .venv/bin/python scripts/webui_inspector_smoke.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_application.browser_results import BrowserResults
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_vision import vision_lab  # noqa: E402
from tests.unit.test_webhost import _app  # noqa: E402

REVIEW = (
    "# Image findings\n\nA **bold** observation with *emphasis* and `inline_code`.\n\n"
    "- Amber rectangle\n- Dark background\n\n1. First item\n2. Second item\n\n"
    "[Safe link](https://example.test/reference) and [unsafe](javascript:alert(1)).\n\n"
    '<script>window.reviewInjected=true</script>\n'
    '<img src=x onerror="window.reviewInjected=true">\n\n'
    '![remote](https://example.invalid/track.png)\n\n'
    '```python\ndef review():\n    return "amber"\n```\n\n'
    + ("## More detail\n\nReadable review content with **formatting**.\n\n" * 80)
    + "END OF FULL REVIEW"
)


async def verify(host, service, root, chrome, image, mode, calls, set_default):
    output = Path("/tmp/klaude-inspector")
    output.mkdir(exist_ok=True)
    profile = root / "chrome"
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
            await tab.command("Browser.grantPermissions", {
                "origin": host.origin,
                "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"],
            })
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait("typeof byId!=='undefined' && !byId('local-access').hidden")
            await tab.wait("document.documentElement.dataset.startup==='ready'")
            await tab.js('byId("login-username").value="admin";'
                        'byId("login-password").value=' + json.dumps(
                host.accounts.initial_password()
            ) + ';byId("account-login").requestSubmit()')
            await tab.wait("latest?.session_id && authenticated")
            await tab.wait("document.documentElement.dataset.startup==='ready' && "
                           "!document.querySelector('.shell').inert")
            await tab.js("document.documentElement.dataset.motion='reduced'")

            async def wait(expression):
                for _ in range(300):
                    if await tab.js(expression):
                        return
                    await asyncio.sleep(.05)
                raise AssertionError((expression, await tab.js(
                    "({status:byId('vision-status').textContent,selected:selectedArtifact?.id,"
                    "review:reviewDialog.open,dialog:artifactDialog.open,"
                    "operations:byId('domain-operations').textContent})"
                )))

            tab.wait = wait

            async def click(selector):
                await tab.js("new Promise(requestAnimationFrame)")
                await tab.js("Promise.race([Promise.all([...document.querySelectorAll("
                             "'dialog[open]')]"
                             ".flatMap(d=>d.getAnimations({subtree:true}))"
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
                      const r=b?.getBoundingClientRect();
                      return {rect:r?.toJSON(),disabled:b?.disabled,
                        hidden:b?.closest('[hidden]')?.id,
                        inert:b?.closest('[inert]')?.id,details:artifactDialog.dataset.details,
                        hit:r && document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)
                          ?.outerHTML};
                    })()""")))
                for kind in ("mousePressed", "mouseReleased"):
                    await tab.command("Input.dispatchMouseEvent", {
                        "type": kind, **point, "button": "left", "clickCount": 1,
                    })

            async def key(name):
                for kind in ("keyDown", "keyUp"):
                    await tab.command("Input.dispatchKeyEvent", {
                        "type": kind, "key": name, "code": name,
                        **({"windowsVirtualKeyCode": {"Escape": 27, "Enter": 13}[name]}
                           if name in {"Escape", "Enter"} else {}),
                        **({"text": "\r"} if name == "Enter" and kind == "keyDown" else {}),
                    })

            async def open_image(item):
                await tab.js(f"openArtifact({json.dumps(item['id'])})")
                await tab.wait("selectedArtifact?.id===" + json.dumps(item["id"]) +
                               " && !byId('vision-suggest').disabled")
                if await tab.js("artifactDialog.dataset.details==='closed'"):
                    await click("#image-details")

            async def analyze():
                await click("#vision-submit")
                await tab.wait("reviewDialog.open && !artifactDialog.open")
                assert await tab.js("byId('domain-review-title').textContent==='Review image?' && "
                    "!byId('domain-review-title').children.length && "
                    "byId('domain-review-confirm').textContent==='Review image' && "
                    "byId('domain-review-target').textContent===" +
                    json.dumps(image["name"]) + " && "
                    "byId('domain-review-notice').textContent.includes('charges may apply') && "
                    "!byId('domain-review-technical').open")
                await check_confirmation()
                await click("#domain-review-technical > summary")
                assert await tab.js("""(() => {
                  const text=byId('domain-review-technical-summary').textContent;
                  return text.includes('Models in order:') &&
                    text.includes('Context: 6144 tokens. Output: 768 tokens.') &&
                    text.includes('capability checks') && byId('domain-review-technical')
                    .textContent.includes('continues if you leave');
                })()""")
                await click("#domain-review-confirm")
                await tab.wait("artifactDialog.open && selectedArtifact")

            async def screenshot(name):
                await tab.js("Promise.race([Promise.all([...document.querySelectorAll("
                             "'dialog[open]')].flatMap(d=>d.getAnimations({subtree:true}))"
                             ".filter(a=>a.effect.getTiming().iterations!==Infinity)"
                             ".map(a=>a.finished.catch(()=>{}))),"
                             "new Promise(resolve=>setTimeout(resolve,350))])")
                await tab.js("new Promise(resolve=>requestAnimationFrame("
                             "()=>requestAnimationFrame(resolve)))")
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / name).write_bytes(base64.b64decode(shot["data"]))

            checked_confirmations = set()

            async def check_confirmation():
                title = await tab.js("byId('domain-review-title').textContent")
                if title in checked_confirmations:
                    return
                checked_confirmations.add(title)
                for theme in ("light", "dark"):
                    await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                    for width, height in ((320, 568), (1440, 900)):
                        await tab.command("Emulation.setDeviceMetricsOverride", {
                            "width": width, "height": height, "deviceScaleFactor": 1,
                            "mobile": False,
                        })
                        assert await tab.js("reviewDialog.scrollWidth<=reviewDialog.clientWidth && "
                            "!byId('domain-review-notice').hidden && "
                            "!byId('domain-review-confirm').disabled && "
                            "document.documentElement.scrollWidth<=innerWidth")
                        await screenshot(f"confirmation-{title[:-1]}-{theme}-{width}.png")

            await click("#nav-library")
            await open_image(image)
            assert await tab.js("!byId('inspector-details').hidden && "
                "byId('inspector-ai-review').hidden && "
                "byId('artifact-metadata').textContent.includes('MIME type') && "
                "byId('artifact-tag-list').textContent==='No tags yet.' && "
                "!byId('artifact-vision').closest('#inspector-details')")
            await click("#inspector-tab-ai-review")
            await tab.wait("!byId('vision-empty').hidden && !byId('vision-submit').disabled")
            assert await tab.js("!byId('vision-settings').open && "
                               "byId('vision-question').value==='' && byId('vision-question').placeholder==='Describe this image.'")
            for width, height in ((320, 568), (1440, 900)):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
                })
                if await tab.js("artifactDialog.dataset.details==='closed'"):
                    await click("#image-details")
                assert await tab.js(r"""(() => {
                    const panel=byId('inspector-ai-review'), tab=byId('inspector-tab-ai-review');
                    const css=getComputedStyle(tab);
                    const rgb=c=>(c.match(/[\d.]+/g)||[]).slice(0,3).map(Number);
                    const lum=c=>rgb(c).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4})
                        .reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
                    const contrast=el=>{
                        let bg=el;
                        while(bg && getComputedStyle(bg).backgroundColor==='rgba(0, 0, 0, 0)') bg=bg.parentElement;
                        const a=lum(getComputedStyle(el).color), b=lum(getComputedStyle(bg).backgroundColor);
                        return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                    };
                    if(contrast(tab)<4.5 || contrast(byId('vision-retention'))<4.5 ||
                        contrast(byId('vision-suggest'))<4.5 || contrast(byId('vision-submit'))<4.5) return false;

                    return panel.scrollWidth<=panel.clientWidth &&
                        css.backgroundColor==='rgba(0, 0, 0, 0)' &&
                        getComputedStyle(byId('inspector-tabs').querySelector('.mtrl-tabs__indicator')).height==='3px' &&
                        !!byId('vision-suggest-icon').querySelector('svg') &&
                        !!byId('vision-retention-icon').querySelector('svg');
                })()""")
                for control in ("vision-submit", "vision-options"):
                    await tab.js(f"byId('{control}').scrollIntoView({{block:'center'}})")
                    await tab.command("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 0, "y": 0})
                    await asyncio.sleep(.3)
                    normal = await tab.js(f"getComputedStyle(byId('{control}')).backgroundColor")
                    point = await tab.js(f"""(() => {{
                        const r=byId('{control}').getBoundingClientRect();
                        return {{x:r.x+r.width/2,y:r.y+r.height/2}};
                    }})()""")
                    await tab.command("Input.dispatchMouseEvent", {"type": "mouseMoved", **point})
                    await asyncio.sleep(.3)
                    assert await tab.js(f"getComputedStyle(byId('{control}')).backgroundColor") != normal
                    assert await tab.js(f"""(() => {{
                        const s=getComputedStyle(byId('{control}'));
                        return parseFloat(s.borderTopLeftRadius)>=6 && parseFloat(s.borderTopRightRadius)>=6;
                    }})()""")
                await tab.command("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 0, "y": 0})
                await tab.js("byId('vision-options').focus()")
                await key("Enter")
                assert await tab.js("byId('vision-settings').open && "
                    "getComputedStyle(document.activeElement).outlineStyle!=='none'")
                assert await tab.js("""(() => {
                    const d=byId('vision-settings'), r=d.getBoundingClientRect();
                    return r.left>=0 && r.right<=innerWidth && d.scrollWidth<=d.clientWidth &&
                        getComputedStyle(byId('vision-options').querySelector('.icon')).width==='16px';
                })()""")
                await screenshot(f"review-settings-{width}.png")
                await key("Escape")
                assert await tab.js("!byId('vision-settings').open && document.activeElement===byId('vision-options')")
                await screenshot(f"empty-ai-review-{width}.png")
                await click("#inspector-tab-details")
                await screenshot(f"details-{width}.png")
                await click("#inspector-tab-ai-review")
            await click("#vision-options")
            await tab.js("byId('vision-context').value=6144;byId('vision-output').value=768;"
                         "byId('vision-question').value='Describe visible shapes carefully.'")
            await click("#vision-settings-done")
            await click("#inspector-tab-details")
            await click("#inspector-tab-ai-review")
            assert await tab.js("!byId('vision-settings').open && "
                "byId('vision-context').value==='6144' && byId('vision-output').value==='768' && "
                "byId('vision-question').value==='Describe visible shapes carefully.'")
            await tab.js("byId('vision-context').value=1024")
            await click("#vision-submit")
            assert await tab.js("byId('vision-settings').open && !reviewDialog.open")
            await tab.js("byId('vision-context').value=6144")
            await click("#vision-settings-done")
            mode["text"] = REVIEW
            mode["value"] = "slow"
            await analyze()
            await tab.wait("byId('vision-empty').querySelector('h3').textContent==='Generating review' && "
                           "!!byId('vision-empty-icon').querySelector('.material-loading')")
            await tab.wait("byId('vision-answer').textContent.includes('END OF FULL REVIEW')")
            await tab.wait("!byId('vision-submit').disabled")
            assert await tab.js("!byId('inspector-ai-review').hidden && "
                "byId('vision-answer').compareDocumentPosition(byId('vision-analyze')) & "
                "Node.DOCUMENT_POSITION_FOLLOWING")
            assert await tab.js("""(() => {
              const a=byId('vision-answer');
              return a.querySelector('h2') && a.querySelector('strong') && a.querySelector('em') &&
                a.querySelector('ul li') && a.querySelector('ol li') && a.querySelector('code') &&
                a.querySelector('pre code') && !a.querySelector('script,img,iframe,style,object') &&
                !window.reviewInjected && ![...a.querySelectorAll('a')].some(
                  link=>link.protocol==='javascript:') && a.textContent.includes('<script>') &&
                byId('vision-review-metadata').textContent.includes('Available until') &&
                byId('vision-review-metadata').textContent.includes('Provider: ollama');
            })()""")
            chats = [body for path, body in calls if path == "/api/chat"]
            assert chats[-1]["options"]["num_ctx"] == 6144
            assert chats[-1]["options"]["num_predict"] == 768
            await click("#vision-copy")
            assert await tab.js("navigator.clipboard.readText()") == REVIEW
            # LAN/HTTP fallback must copy the complete source from inside the modal.
            await tab.js("window.copiedReview='';document.addEventListener('copy',e=>{"
                         "copiedReview=e.clipboardData.getData('text/plain')});"
                         "Object.defineProperty(navigator,'clipboard',{configurable:true,"
                         "value:undefined})")
            await click("#vision-copy")
            await tab.wait("copiedReview.length>0")
            assert await tab.js("copiedReview") == REVIEW

            layouts = []
            for theme in ("light", "dark"):
                await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                for width, height in ((320, 568), (390, 844), (768, 1024), (1440, 900)):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
                    })
                    if await tab.js("artifactDialog.dataset.details==='closed'"):
                        await click("#image-details")
                    await click("#inspector-tab-ai-review")
                    await tab.js("byId('inspector-tab-ai-review').focus()")
                    await key("Home")
                    assert await tab.js("document.activeElement===byId('inspector-tab-details')")
                    await key("ArrowRight")
                    assert await tab.js("document.activeElement===byId('inspector-tab-ai-review')")
                    await key("End")
                    state = await tab.js("""(() => {
                      const panel=byId('artifact-information'), scroll=panel.querySelector(
                        '.preview-information-scroll'), r=panel.getBoundingClientRect();
                      return {fit:r.left>=0 && r.right<=innerWidth && r.bottom<=innerHeight,
                        overflow:scroll.scrollWidth>scroll.clientWidth,
                        full:innerWidth>850 || artifactDialog.dataset.details==='full',
                        oneTab:byId('inspector-tabs').querySelectorAll('[tabindex="0"]').length===1,
                        scrolls:scroll.scrollHeight>scroll.clientHeight};
                    })()""")
                    assert state["fit"] and not state["overflow"] and state["full"]
                    assert state["oneTab"] and state["scrolls"], state
                    await tab.js("byId('artifact-information').querySelector("
                                 "'.preview-information-scroll').scrollTop=0")
                    await screenshot(f"ai-review-{theme}-{width}.png")
                    await click("#vision-expand")
                    assert await tab.js("byId('vision-full-review').open && "
                        "byId('vision-full-content').textContent.includes('END OF FULL REVIEW') && "
                        "byId('vision-full-content').scrollWidth<="
                        "byId('vision-full-content').clientWidth")
                    await screenshot(f"full-review-{theme}-{width}.png")
                    await click("#vision-full-copy")
                    assert await tab.js("copiedReview") == REVIEW
                    await key("Escape")
                    await tab.wait("!byId('vision-full-review').open && artifactDialog.open")
                    assert await tab.js("document.activeElement===byId('vision-expand')")
                    layouts.append({"theme": theme, "width": width, **state})

            # A new request keeps the previous result visible while running and on failure.
            mode["value"] = "503"
            old_result = await tab.js("byId('vision-answer').dataset.result")
            await analyze()
            await tab.wait("byId('vision-status').dataset.state==='error'")
            await tab.wait("!byId('vision-suggest').disabled")
            assert await tab.js("byId('vision-answer').dataset.result===" +
                               json.dumps(old_result))
            assert await tab.js("byId('vision-answer').textContent.includes('END OF FULL REVIEW')")
            mode["value"] = "good"
            set_default("vision_enabled", False)
            await click("#vision-submit")
            await tab.wait("byId('vision-status').dataset.state==='error' && "
                           "byId('vision-status').textContent.includes('Choose and enable')")
            assert await tab.js("byId('vision-answer').textContent.includes('END OF FULL REVIEW')")
            assert not await tab.js("reviewDialog.open")
            set_default("vision_enabled", True)
            # An existing manual tag is omitted from the offered-chip selection.
            current = service.artifacts.get(image["id"])
            service.artifacts.change(image["id"], current["revision"], "tags", "Existing")
            await click("#artifact-close")
            await open_image(image)
            await click("#inspector-tab-ai-review")
            mode["text"] = '["amber", "diagram", "existing", "Original tag"]'
            await click("#vision-suggest")
            await tab.wait("reviewDialog.open")
            assert await tab.js(
                "byId('domain-review-title').textContent==='Suggest image tags?' && "
                "!byId('domain-review-title').children.length && "
                "byId('domain-review-confirm').textContent==='Suggest tags' && "
                "byId('domain-review-notice').textContent.includes('not saved automatically') && "
                "!byId('domain-review-technical').open")
            await check_confirmation()
            await click("#domain-review-confirm")
            await tab.wait("!!document.querySelector('.tag-filter-chip[data-tag=amber]') && "
                           "!document.querySelector('.tag-filter-chip[data-tag=amber]').disabled")
            assert await tab.js(
                "!document.querySelector('#vision-results input[type=checkbox]') && "
                "!document.querySelector('.tag-filter-chip[data-tag=existing]') && "
                "document.querySelectorAll('.tag-filter-chip[aria-pressed=true]').length===0 && "
                "[...document.querySelectorAll('.tag-filter-chip .icon')].every("
                "icon=>getComputedStyle(icon).display==='none') && "
                "document.querySelector('.vision-tags-save').disabled")
            assert service.artifacts.get(image["id"])["ai_tags"] == []
            await click(".tag-filter-chip[data-tag=amber] span")
            await click(".tag-filter-chip[data-tag=diagram]")
            assert await tab.js(
                "document.querySelector('.vision-tag-count').textContent==='2 selected' && "
                "document.querySelector('.vision-tags-save').textContent==='Save' && "
                "[...document.querySelectorAll('.tag-filter-chip[aria-pressed=true] .icon')]"
                ".every(icon=>getComputedStyle(icon).display!=='none')")
            for theme in ("light", "dark"):
                await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                for width, height in ((320, 568), (390, 844), (768, 1024), (1440, 900)):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": height, "deviceScaleFactor": 1,
                        "mobile": False,
                    })
                    if await tab.js("artifactDialog.dataset.details==='closed'"):
                        await click("#image-details")
                    await tab.js("document.querySelector('.tag-chip-list').scrollIntoView()")
                    await tab.js("new Promise(requestAnimationFrame)")
                    assert await tab.js("""(() => {
                      const group=document.querySelector('.tag-chip-list');
                      const panel=byId('artifact-information')
                        .querySelector('.preview-information-scroll');
                      return group.scrollWidth<=group.clientWidth &&
                        panel.scrollWidth<=panel.clientWidth &&
                        [...group.children].every(b=>b.getBoundingClientRect().height>=48 &&
                          b.getBoundingClientRect().width<=group.clientWidth &&
                          getComputedStyle(b.querySelector('.filter-chip-face'))
                            .borderTopLeftRadius==='8px') &&
                        document.querySelector('.vision-tag-count').textContent==='2 selected';
                    })()""")
                    await screenshot(f"tag-chips-{theme}-{width}.png")
            await click(".tag-filter-chip[data-tag=diagram]")
            await click(".vision-tags-clear")
            assert await tab.js("document.querySelector('.vision-tags-save').disabled && "
                "document.querySelector('.vision-tag-count').textContent==='0 selected'")
            await click(".tag-filter-chip[data-tag=amber]")
            assert await tab.js(
                "document.activeElement.matches('.tag-filter-chip[data-tag=amber]')"
            ), await tab.js("document.activeElement.outerHTML")
            await key("Enter")
            assert await tab.js("document.querySelector('.tag-filter-chip[data-tag=amber]')"
                                ".getAttribute('aria-pressed')==='false'")
            await key("Enter")
            await click("#inspector-tab-details")
            await click("#inspector-tab-ai-review")
            assert await tab.js(
                "document.querySelector('.tag-filter-chip[data-tag=amber]').getAttribute('aria-pressed')==='true'")
            await click(".vision-tags-save")
            await tab.wait("reviewDialog.open && !artifactDialog.open")
            assert await tab.js("byId('domain-review-title').textContent==='Review change' && "
                "byId('domain-review-target').hidden && byId('domain-review-notice').hidden && "
                "byId('domain-review-technical').hidden && "
                "byId('domain-review-confirm').textContent==='Confirm'")
            assert service.artifacts.get(image["id"])["ai_tags"] == []
            await click("#domain-review-cancel")
            await tab.wait("artifactDialog.open")
            await tab.wait("document.querySelector('.vision-tags-save')?.disabled===false")
            assert await tab.js("document.querySelector('.tag-filter-chip[data-tag=amber]')"
                                ".getAttribute('aria-pressed')==='true'")
            # A genuinely expired approval is rejected by the existing execution endpoint.
            await click(".vision-tags-save")
            await tab.wait("reviewDialog.open")
            review_id = await tab.js("managementReview.review_id")
            with service._lock:
                service._reviews[review_id].expires_at = time.time() - 1
            await click("#domain-review-confirm")
            await tab.wait("reviewDialog.open && "
                           "byId('domain-review-status').textContent.includes('expired')")
            await click("#domain-review-cancel")
            await tab.wait("artifactDialog.open && "
                           "document.querySelector('.vision-tags-save')?.disabled===false")
            assert await tab.js("document.querySelector('.tag-filter-chip[data-tag=amber]')"
                                ".getAttribute('aria-pressed')==='true'")
            assert service.artifacts.get(image["id"])["ai_tags"] == []
            await click('.tag-filter-chip[data-tag="Original tag"]')
            await click(".vision-tags-save")
            await tab.wait("reviewDialog.open")
            # A real checksum failure before publication keeps the same revision
            # and selection, allowing retry once the isolated fixture is repaired.
            current = service.artifacts.get(image["id"])
            original = service.artifacts.read_content(image["id"], current["revision"])
            with service.artifacts.database(write=True) as db:
                db.execute("UPDATE artifacts SET content=? WHERE id=?",
                           (b"x" * len(original), image["id"]))
            await click("#domain-review-confirm")
            await tab.wait("artifactDialog.open && "
                           "byId('vision-status').textContent.includes('Could not save tags')")
            assert service.artifacts.get(image["id"])["ai_tags"] == []
            assert await tab.js("document.querySelector('.vision-tag-count').textContent==="
                                "'2 selected' && document.querySelector('.vision-tags-save')"
                                "?.disabled===false")
            with service.artifacts.database(write=True) as db:
                db.execute("UPDATE artifacts SET content=? WHERE id=?", (original, image["id"]))
            await click(".vision-tags-save")
            await tab.wait("reviewDialog.open")
            await click("#domain-review-confirm")
            await tab.wait("selectedArtifact?.ai_tags.includes('amber')")
            await tab.wait("byId('vision-status').textContent==='Tags saved.'")
            assert service.artifacts.get(image["id"])["ai_tags"] == ["amber", "Original tag"]
            await click("#inspector-tab-details")
            await tab.wait("!!byId('artifact-tag-list').querySelector('.input-chip.tag-generated')")
            assert await tab.js("""(() => {
              const tags=byId('artifact-tag-list');
              const manual=getComputedStyle(tags.querySelector(
                '.input-chip:not(.tag-generated) .filter-chip-face'));
              const ai=getComputedStyle(tags.querySelector('.tag-generated .filter-chip-face'));
              return ['backgroundColor','borderRadius','fontSize','fontWeight','lineHeight',
                'color','outlineColor'].every(key=>manual[key]===ai[key]);
            })()""")
            # AI chips use the same draft/remove/cancel/review workflow as manual tags.
            saved_tags = service.artifacts.get(image["id"])
            provenance = service.artifacts.tagging_info(image["id"])
            await click("#artifact-tags-edit")
            await click('[aria-label="Remove tag amber"]')
            assert service.artifacts.get(image["id"]) == saved_tags
            assert await tab.js("!byId('artifact-tags-save').disabled")
            await click("#artifact-tags-cancel")
            assert await tab.js("byId('artifact-tag-list').textContent.includes('amber')")
            await click("#artifact-tags-edit")
            await click('[aria-label="Remove tag amber"]')
            await tab.js("latest.library_ai_tag_edit=false")
            await click("#artifact-tags-save")
            assert await tab.js("!reviewDialog.open && byId('artifact-tags-status')"
                                ".textContent.includes('Restart the Web UI host')")
            assert service.artifacts.get(image["id"]) == saved_tags
            await tab.js("latest.library_ai_tag_edit=true")
            await click("#artifact-tags-save")
            await tab.wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-summary').textContent"
                                ".includes('Remove AI tags: amber')")
            await click("#domain-review-cancel")
            assert service.artifacts.get(image["id"]) == saved_tags
            await tab.wait("!byId('artifact-tags-save').disabled")
            assert await tab.js("!byId('artifact-tags-save').disabled && "
                                "!byId('artifact-tag-list').textContent.includes('amber')")
            await click("#artifact-tags-save")
            await tab.wait("reviewDialog.open")
            await click("#domain-review-confirm")
            await tab.wait("byId('artifact-tags-status').textContent==='Saved.'")
            saved = service.artifacts.get(image["id"])
            assert saved["ai_tags"] == ["Original tag"] and saved["tags"] == saved_tags["tags"]
            assert service.artifacts.tagging_info(image["id"]) == {
                "Original tag": provenance["Original tag"],
            }
            await click("#inspector-tab-ai-review")

            # Use a real new-revision review, then age it in the private fixture store.
            mode["text"] = REVIEW
            await tab.wait("!byId('vision-submit').disabled")
            await analyze()
            await tab.wait("byId('vision-answer').textContent.includes('END OF FULL REVIEW')")
            identifier = await tab.js("byId('vision-answer').dataset.result")
            with BrowserResults(service.data).database(write=True) as db:
                db.execute("UPDATE results SET created=? WHERE id=?", (
                    time.time() - 90000, identifier,
                ))
            await tab.js("loadOperations()")
            await tab.wait("!byId('vision-empty').hidden && byId('vision-answer').hidden && "
                           "byId('vision-status').dataset.state==='expired'")
            assert "END OF FULL REVIEW" not in await tab.js("byId('vision-answer').textContent")
            document = service.artifacts.import_bytes(
                b"No AI review for text.", "document", "plain.txt")
            await tab.js(f"openArtifact({json.dumps(document['id'])})")
            await tab.wait("selectedArtifact?.id===" + json.dumps(document["id"]))
            assert await tab.js("byId('inspector-tab-ai-review').disabled && "
                               "!byId('inspector-details').hidden")
            await click("#artifact-close")
            await tab.click("#logout")
            await tab.wait("!authenticated && !byId('vision-full-review').open")
            assert await tab.js("!byId('vision-answer').textContent && "
                               "!byId('vision-results').textContent")
            assert not tab.errors, tab.errors
            return {"layouts": layouts, "real_review_and_tag_workers": "passed",
                    "markdown_injection_and_full_source_copy": "passed",
                    "loading_failure_expiry": "passed", "tabs_drafts_keyboard": "passed",
                    "filter_chips_keyboard_explicit_save_failure_retry": "passed",
                    "compact_ai_confirmations": "passed",
                    "browser_exceptions": 0, "screenshots": str(output)}
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    ))
    with tempfile.TemporaryDirectory(prefix="klaude-inspector-") as folder:
        root = Path(folder)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        fixture = vision_lab.__wrapped__(root)
        lab_cfg, _, _, image, calls, mode, _, set_default = next(fixture)
        cfg = Config(models={"coder": "fixture"})
        cfg.ollama_url = lab_cfg.ollama_url
        (cfg.config_dir / "config.toml").write_text(
            f'[services]\nollama_url={json.dumps(cfg.ollama_url)}\n'
            '[models.override]\ncoder="fixture"\n'
        )
        app = _app(cfg.data_dir)
        app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        service = LibraryManagement(cfg, root)
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, library=service, accounts=accounts, staging_dir=root / "staging")
        host.local_models = lambda: []
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            print(json.dumps(asyncio.run(asyncio.wait_for(
                verify(host, service, root, chrome, image, mode, calls, set_default), 180
            )), indent=2))
        finally:
            host.stop()
            serving.join(3)
            fixture.close()


if __name__ == "__main__":
    main()

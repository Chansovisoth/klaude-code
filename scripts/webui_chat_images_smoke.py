"""Chrome chat-image integration with the real host, journal and recording SD fixture."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

import websockets
from klaude_application.chat_image_actions import ChatImageActions
from klaude_core import image_generation
from webui_control_smoke import Tab
from webui_model_store_smoke import main

from tests.unit import test_image_generation as image_fixture
from tests.unit.test_image_generation import generation_lab


class ImageTab(Tab):
    async def wait(self, expression):
        for _ in range(600):
            try:
                if await self.js(expression):
                    return
            except AssertionError as error:
                if not any(text in str(error) for text in (
                    "Inspected target navigated or closed", "Execution context was destroyed",
                )):
                    raise
            await asyncio.sleep(0.05)
        raise AssertionError(
            {
                "waiting": expression,
                "errors": self.errors,
                "notice": await self.js("notice.textContent"),
                "focus": await self.js("document.activeElement?.outerHTML.slice(0,300)"),
                "startup": await self.js("document.documentElement.dataset.startup"),
                "image_action": await self.js("latest?.messages.filter(m=>m.image_action)"
                                              ".at(-1)?.image_action"),
            }
        )


async def execution_details(tab):
    await tab.wait("latest?.activity?.turn_id && !byId('agent-activity').hidden")
    result = await tab.js("""(()=>{
      const activity=latest.activity,panel=byId('agent-activity');
      const label=activity.label || ({cancelled:'Cancelled',interrupted:'Interrupted'}
        [activity.lifecycle]) || 'Waiting';
      const rows=[...byId('agent-activity-timeline').children];
      const summary=panel.querySelector('summary'),wasOpen=panel.open;
      summary.click();const toggles=panel.open!==wasOpen;summary.click();
      panel.open=true;
      return {native:panel.tagName==='DETAILS' && toggles,
        available:!byId('chat-response-status').hidden && !panel.hidden,
        identity:panel.dataset.turn===activity.turn_id,
        label:byId('agent-activity-label').textContent===label,
        diagnostics:rows.length===(activity.timeline || []).length &&
          (activity.timeline || []).every((item,i)=>['tool','status','label']
            .every(key=>!item[key] || rows[i].textContent.includes(item[key]))),
        separate:!panel.closest('.chat-image-result') &&
          !document.querySelector('.chat-image-result .material-loading'),
        cards:[...document.querySelectorAll('.chat-image-result')].length===
          latest.messages.filter(m=>m.image_action).length};
    })()""")
    assert all(result.values()), result


async def verify_progress_lifecycle(tab, host, calls, state, evidence):
    """Hold real fixture jobs at their existing lifecycle gates; never replay a job."""
    images = host.application.images
    original_png = image_fixture.png
    initial_posts = sum(path == '/sdcpp/v1/img_gen' for _, path, _ in calls)
    state.update(wait=True, cancelled=False, failed=False)
    with patch.object(image_fixture, 'png', lambda: original_png(1024, 576)):
        with patch.object(images, 'tick', lambda: None):
            await tab.send('Generate an image of a coast at 16:9')
            await tab.wait("latest.messages.filter(m=>m.image_action).at(-1)"
                           ".image_action.state==='queued'")
            identity = await tab.js("latest.messages.filter(m=>m.image_action).at(-1)"
                                    ".image_action.id")
            message = await tab.js("latest.messages.filter(m=>m.image_action).at(-1).id")
            assert sum(path == '/sdcpp/v1/img_gen' for _, path, _ in calls) == initial_posts
            assert await tab.js("""(()=>{
              const card=[...document.querySelectorAll('.chat-image-result')].at(-1);
              const tile=card.querySelector('.chat-image-asset');
              const dots=tile.querySelector('.chat-image-placeholder');
              const box=dots.getBoundingClientRect();
              return tile.dataset.imageState==='queued' &&
                tile.querySelector('.chat-image-dimensions').textContent==='1024 × 576' &&
                Math.abs(box.width/box.height-1024/576)<.01 &&
                getComputedStyle(dots,'::after').animationName==='none' &&
                !!tile.querySelector('.chat-image-cancel') &&
                !card.querySelector('.chat-image-actions');
            })()""")
            await execution_details(tab)
        images.start()
        await tab.wait("latest.messages.filter(m=>m.image_action).at(-1)"
                       ".image_action.state==='running'")
        for _ in range(200):
            if sum(path == '/sdcpp/v1/img_gen' for _, path, _ in calls) >= initial_posts + 1:
                break
            await asyncio.sleep(.05)
        await execution_details(tab)
        await tab.js("window.progressPanel=byId('agent-activity');stream.onerror()")
        await tab.wait("stream?.readyState===1")
        assert await tab.js("byId('agent-activity')===progressPanel && progressPanel.open")
        assert sum(path == '/sdcpp/v1/img_gen' for _, path, _ in calls) == initial_posts + 1
        await tab.js("window.progressReload=true")
        await tab.command('Page.reload')
        await tab.wait("!window.progressReload && typeof latest!=='undefined' && latest && "
                       "document.documentElement.dataset.startup==='ready'")
        assert await tab.js("latest.messages.filter(m=>m.image_action).at(-1)"
                            ".image_action.id") == identity
        assert await tab.js("latest.messages.filter(m=>m.image_action).at(-1).id") == message
        await execution_details(tab)
        session = await tab.js('latest.session_id')
        # Stop assistant preserves admitted image work; resuming must reuse that job.
        await tab.click('#cancel')
        await tab.idle()
        assert await tab.js("latest.messages.filter(m=>m.image_action).at(-1)"
                            ".image_action.state") == 'running'
        await tab.js("window.progressSession=switchSession('')")
        await tab.wait('latest.session_id!==' + json.dumps(session))
        await tab.js('window.progressSession=switchSession(' + json.dumps(session) + ')')
        await tab.wait('latest.session_id===' + json.dumps(session))
        assert await tab.js("latest.messages.filter(m=>m.image_action).at(-1)"
                            ".image_action.id") == identity
        await execution_details(tab)
        assert sum(path == '/sdcpp/v1/img_gen' for _, path, _ in calls) == initial_posts + 1
        await tab.js("applyAppearance({...appearance,reduced:false},true);"
                     "chatScroller.scrollTop=chatScroller.scrollHeight")
        before = await tab.js("""(()=>{
          const tile=[...document.querySelectorAll('.chat-image-result')].at(-1)
            .querySelector('.chat-image-asset'),r=tile.getBoundingClientRect();
          return {width:r.width,height:r.height};
        })()""")
        shot = await tab.command('Page.captureScreenshot', {'format': 'png'})
        (evidence / 'progress-running-with-details.png').write_bytes(base64.b64decode(shot['data']))
        state['wait'] = False
        await tab.wait("latest.messages.filter(m=>m.image_action).at(-1)"
                       ".image_action.state==='completed'")
        await tab.wait("[...document.querySelectorAll('.chat-image-open img')]"
                       ".at(-1)?.naturalWidth>0")
        after = await tab.js("""(()=>{
          const tile=[...document.querySelectorAll('.chat-image-result')].at(-1)
            .querySelector('.chat-image-asset'),r=tile.getBoundingClientRect();
          return {width:r.width,height:r.height};
        })()""")
        assert abs(before['width']-after['width']) < 1, (before, after)
        assert abs(before['height']-after['height']) < 1, (before, after)
        await tab.idle()
        await execution_details(tab)
    assert sum(path == '/sdcpp/v1/img_gen' for _, path, _ in calls) == initial_posts + 1
    # A fresh owner reconstructs an expired, unwitnessed admission as unknown.
    # No native request is ever issued for this simulated lost acknowledgement.
    images = host.application.images
    with patch.object(images, 'tick', lambda: None):
        await tab.send('Generate an image of a forest')
        await tab.wait("latest.messages.filter(m=>m.image_action).at(-1)"
                       ".image_action.state==='queued'")
        identity = await tab.js("latest.messages.filter(m=>m.image_action).at(-1).image_action.id")
        row = images._required(identity)
        assert images._update(row, 'starting')
        with images.memory._db_lock, images.memory.db:
            images.memory.db.execute('UPDATE application_image_actions SET lease=0 WHERE id=?',
                                     (identity,))
        images.close()
    app = host.application
    replacement = ChatImageActions(host.library.cfg, app.memory, app.turns, app.agent.workdir)
    replacement.operations = host.library
    app.images = replacement
    replacement.tick()
    await tab.wait("latest.messages.filter(m=>m.image_action).at(-1)"
                   ".image_action.state==='unknown'")
    await tab.idle()
    await execution_details(tab)
    for _ in range(2):
        await tab.js("window.progressSnapshot=snapshot()")
    assert await tab.js("""(()=>{
      const card=[...document.querySelectorAll('.chat-image-result')].at(-1);
      return !card.querySelector('.chat-image-placeholder') &&
        !card.querySelector('.chat-image-retry') && !!card.querySelector('.chat-image-recover') &&
        !card.querySelector('.chat-image-open') && !card.querySelector('[aria-busy=true]');
    })()""")
    await tab.js('window.progressReload=true')
    await tab.command('Page.reload')
    await tab.wait("!window.progressReload && typeof latest!=='undefined' && latest && "
                   "latest.messages.filter(m=>m.image_action).at(-1)?.image_action.state==='unknown'")
    await execution_details(tab)
    assert await tab.js("latest.messages.filter(m=>m.image_action).at(-1)"
                        ".image_action.id") == identity
    assert sum(path == '/sdcpp/v1/img_gen' for _, path, _ in calls) == initial_posts + 1


async def verify_media_cards(tab, calls, evidence):
    """Persist real fixture outputs of each shape, then inspect the restored cards."""
    original_png = image_fixture.png
    layouts = 0
    for shape, ratio, dimensions in (
        ("square", "1:1", [(512, 512)]),
        ("landscape", "16:9", [(1024, 576)]),
        ("portrait", "9:16", [(576, 1024)]),
        ("multiple", "1:1", [(512, 512)] * 3),
    ):
        previous = await tab.js("latest.messages.filter(m=>m.image_action).length")
        initial_posts = len([c for c in calls if c[1] == "/sdcpp/v1/img_gen"])

        def output(dimensions=dimensions):
            return original_png(*dimensions[0])

        with patch.object(image_fixture, "png", output):
            await tab.send(f"Generate {len(dimensions)} images of a {shape} composition at {ratio}")
            await tab.wait(
                f"latest.messages.filter(m=>m.image_action).length>{previous} && "
                "latest.messages.filter(m=>m.image_action).at(-1).image_action.state==='completed'"
            )
            await tab.idle()
        posts = len([c for c in calls if c[1] == "/sdcpp/v1/img_gen"])
        assert posts - initial_posts == len(dimensions)
        await tab.wait("[...document.querySelectorAll('.chat-image-result')].at(-1)"
                       ".querySelectorAll('.chat-image-open img').length===" + str(len(dimensions)))
        await tab.wait("[...[...document.querySelectorAll('.chat-image-result')].at(-1)"
                       ".querySelectorAll('.chat-image-open img')]"
                       ".every(image=>image.naturalWidth>0)")
        for width, height in ((320, 568), (390, 720), (768, 900), (844, 390), (1440, 900)):
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 600,
            })
            for theme in ("light", "dark"):
                await tab.js("applyAppearance({...appearance,theme:"
                             + json.dumps(theme) + "},true)")
                await tab.js("chatScroller.scrollTop=chatScroller.scrollHeight")
                geometry = await tab.js("""(()=>{
                  const result=[...document.querySelectorAll('.chat-image-result')].at(-1);
                  const cards=[...result.querySelectorAll('.chat-image-asset')];
                  return {fits:document.documentElement.scrollWidth<=innerWidth &&
                    result.scrollWidth<=result.clientWidth+1,
                    separate:!result.querySelector('.message-actions') &&
                      !!result.closest('article').querySelector('.message-actions'),
                    cards:cards.map(card=>{
                      const image=card.querySelector('img'),r=image.getBoundingClientRect();
                      const preview=card.querySelector('.chat-image-open').getBoundingClientRect();
                      const box=card.getBoundingClientRect();
                      const toolbar=card.querySelector('.chat-image-toolbar')
                        .getBoundingClientRect();
                      const footer=card.querySelector('figcaption').getBoundingClientRect();
                      const buttons=[...card.querySelectorAll(
                        '.chat-image-tools > *,figcaption button')]
                        .filter(button=>getComputedStyle(button).display!=='none');
                      return {width:r.width,height:r.height,
                        natural:[image.naturalWidth,image.naturalHeight],
                        ratio:Math.abs(r.width/r.height-image.naturalWidth/image.naturalHeight)<.01,
                        noPadding:Math.abs(preview.width-r.width)<1 &&
                          Math.abs(preview.height-r.height)<1,
                        noOverlap:toolbar.bottom<=footer.top+1,
                        bounded:r.height<=Math.min(560,innerHeight*.7)+1 &&
                          (innerWidth>850 || box.width<=result.clientWidth*.75+1) &&
                          box.left>=0 && box.right<=innerWidth &&
                          card.scrollWidth<=card.clientWidth+1,
                        controls:buttons.every(button=>{
                          const b=button.getBoundingClientRect();return b.height>=44 &&
                            b.left>=box.left && b.right<=box.right+1 &&
                            !!button.getAttribute('aria-label');}),
                        icons:buttons.every(button=>!!button.querySelector('svg'))};
                    })};
                })()""")
                assert geometry["fits"] and geometry["separate"], (shape, width, geometry)
                assert len(geometry["cards"]) == len(dimensions), geometry
                for card, expected in zip(geometry["cards"], dimensions, strict=True):
                    keys = ("ratio", "noPadding", "noOverlap", "bounded", "controls", "icons")
                    assert all(card[key] for key in keys), (
                        shape, width, theme, card,
                    )
                    assert card["natural"] == list(expected), card
                    if shape == "square" and width == 1440:
                        assert 360 <= card["width"] <= 440, card
                    if shape == "landscape" and width == 1440:
                        assert card["width"] > 500, card
                layouts += 1
                if shape == 'multiple':
                    await tab.js("[...document.querySelectorAll('.chat-image-gallery-heading')]"
                                 ".at(-1).scrollIntoView({block:'start'})")
                if width in (390, 844, 1440):
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (evidence / f"media-{shape}-{width}-{theme}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                if shape == 'portrait' and width == 844 and theme == 'dark':
                    await tab.js("[...document.querySelectorAll('[data-image-control=more]')]"
                                 ".at(-1).click()")
                    await tab.wait("document.querySelector('.chat-image-menu')"
                                   ".matches(':popover-open')")
                    await tab.click('.chat-image-menu [aria-label="Regenerate"]')
                    assert await tab.js("prompt.value==='Generate another variation' && "
                                        "!document.querySelector('.chat-image-selection').hidden "
                                        "&& !latest.active_turn_id")
                    await tab.js("ChatImageResults.clear();prompt.value='';resizePrompt()")

        await tab.js("window.mediaAssetIds=latest.messages.filter(m=>m.image_action).at(-1)"
                     ".image_action.assets.map(a=>a.id);window.mediaReload=true")
        ids = await tab.js("mediaAssetIds")
        await tab.command("Page.reload")
        await tab.wait("!window.mediaReload && typeof latest!=='undefined' && latest && "
                       "latest.messages.filter(m=>m.image_action).at(-1)?.image_action.state==='completed'")
        await tab.wait("document.documentElement.dataset.startup==='ready' && !layout.inert")
        restored = await tab.js("latest.messages.filter(m=>m.image_action).at(-1)"
                                ".image_action.assets.map(a=>a.id)")
        assert restored == ids, (shape, restored, ids)
        assert await tab.js("[...document.querySelectorAll('.chat-image-result')].at(-1)"
                            ".querySelectorAll('.chat-image-asset').length") == len(ids)
        # Native overflow keyboard behavior and focus return from the shared viewer.
        await tab.js("[...document.querySelectorAll('[data-image-control=more]')].at(-1).focus()")
        assert await tab.js("document.activeElement.dataset.imageControl==='more'")
        await tab.command("Input.dispatchKeyEvent", {
            "type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13,
            "text": "\r",
        })
        await tab.command("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13,
        })
        await tab.wait("document.querySelector('.chat-image-menu')?.matches(':popover-open')")
        await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape"})
        await tab.wait("!document.querySelector('.chat-image-menu').matches(':popover-open')")
        assert await tab.js("document.activeElement.dataset.imageControl==='more'")
        await tab.js("[...document.querySelectorAll('[data-image-control=expand]')].at(-1).click()")
        await tab.wait("byId('artifact-detail').open")
        await tab.click("#artifact-close")
        await tab.wait("!byId('artifact-detail').open")
        await tab.wait("document.activeElement.dataset.imageControl==='expand'")
        await tab.js("[...document.querySelectorAll('[data-image-control=more]')].at(-1).click()")
        await tab.wait("document.querySelector('.chat-image-menu').matches(':popover-open')")
        await tab.click('.chat-image-menu [aria-label="Image details"]')
        await tab.wait("byId('artifact-detail').open && "
                       "byId('artifact-detail').dataset.details!=='closed'")
        await tab.click("#artifact-close")
        await tab.wait("!byId('artifact-detail').open")
        await tab.wait("document.activeElement.dataset.imageControl==='more'")
    session = await tab.js("latest.session_id")
    saved = await tab.js("latest.messages.filter(m=>m.image_action)"
                         ".map(m=>m.image_action.assets.map(a=>a.id))")
    await tab.js("window.mediaOriginalSession=latest.session_id;switchSession('')")
    await tab.wait("latest.session_id!==mediaOriginalSession && !pending")
    await tab.js("switchSession(" + json.dumps(session) + ")")
    await tab.wait("latest.session_id===" + json.dumps(session) + " && !pending")
    assert await tab.js("latest.messages.filter(m=>m.image_action)"
                        ".map(m=>m.image_action.assets.map(a=>a.id))") == saved
    assert await tab.js("[...document.querySelectorAll('.chat-image-result')].at(-1)"
                        ".querySelectorAll('.chat-image-asset').length") == 3
    return layouts


async def verify(host, root):
    fixture = generation_lab.__wrapped__(root / "chat-service")
    _, endpoint, caps, calls, state = next(fixture)
    caps["features_by_mode"]["img_gen"]["init_image"] = True
    cfg = host.library.cfg
    image_generation.save(
        cfg,
        {"endpoint": endpoint, "enabled": True, "model": "local-test-model"},
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
    evidence = Path("/tmp/klaude-chat-image-evidence")
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
            tab = ImageTab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            await tab.wait(
                "typeof authenticated!=='undefined' && authenticated && latest && "
                "document.documentElement.dataset.startup==='ready'"
            )
            await tab.js("showView('chat')")
            await tab.send("Generate an image of an apple")
            await tab.wait("document.querySelector('.chat-image-open img')?.naturalWidth>0")
            await tab.idle()
            assert await tab.js(
                "document.querySelector('.chat-image-job-status').textContent==='Generated image'"
            )
            await execution_details(tab)
            asset = await tab.js(
                "latest.messages.find(m=>m.image_action)?.image_action.assets[0].id"
            )
            for width, height in [(320, 568), (390, 720), (768, 900), (1440, 900)]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                )
                for mode in ["light", "dark"]:
                    await tab.js(
                        "applyAppearance(appearance={...appearance,theme:" + json.dumps(mode) + "})"
                    )
                    assert await tab.js(
                        "[...document.querySelectorAll('.chat-image-open img')].every(n=>"
                        "n.getBoundingClientRect().height<=Math.min(560,innerHeight*.7)+1)"
                    )
                    assert await tab.js(
                        "document.documentElement.scrollWidth<=innerWidth && "
                        "[...document.querySelectorAll('.chat-image-result')].every(n=>"
                        "n.scrollWidth<=n.clientWidth+1)"
                    )
                    assert await tab.js(
                        "[...document.querySelectorAll('.chat-image-toolbar .icon-button,"
                        ".chat-image-footer button')]"
                        ".filter(n=>getComputedStyle(n).display!=='none')"
                        ".every(n=>n.getBoundingClientRect().height>=44)"
                    )
                    await tab.js("chatScroller.scrollTop=chatScroller.scrollHeight")
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (evidence / f"chat-{width}-{mode}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
            await tab.command(
                "Emulation.setEmulatedMedia",
                {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]},
            )
            await tab.click(".chat-image-open")
            await tab.wait("byId('artifact-detail').open")
            await tab.click("#artifact-close")
            downloads = root / "downloads"
            downloads.mkdir()
            await tab.command(
                "Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads)}
            )
            await tab.click(".chat-image-download")
            for _ in range(50):
                if list(downloads.glob("*.png")):
                    break
                await asyncio.sleep(0.1)
            assert list(downloads.glob("*.png"))
            await tab.js(
                "[...document.querySelectorAll('.chat-image-footer button')]"
                ".find(b=>b.textContent==='Edit').click()"
            )
            assert await tab.js(
                "!document.querySelector('.chat-image-selection').hidden && "
                "document.activeElement===byId('prompt')"
            )
            await tab.send("Make it darker")
            await tab.wait(
                "document.querySelectorAll('.chat-image-open img').length===2 && "
                "[...document.querySelectorAll('.chat-image-open img')].every(n=>n.naturalWidth>0)"
            )
            await tab.idle()
            assert [body for _, path, body in calls if path == "/sdcpp/v1/img_gen"][-1][
                "init_image"
            ]
            await tab.js("window.chatImageReloadProbe=true")
            await tab.command("Page.reload")
            await tab.wait(
                "!window.chatImageReloadProbe && typeof latest!=='undefined' && latest && "
                "document.querySelectorAll('.chat-image-open img').length===2"
            )
            assert await tab.js(
                "latest.messages.find(m=>m.image_action)?.image_action.assets[0].id==="
                + json.dumps(asset)
            )
            state["wait"] = True
            await tab.send("Generate an image of a mountain")
            await tab.wait(
                "[...document.querySelectorAll('.chat-image-job-status')]"
                ".some(n=>n.textContent==='Creating image')"
            )
            await tab.wait("document.querySelector('.chat-image-placeholder')!==null")
            await tab.command("Emulation.setEmulatedMedia", {"features": [
                {"name": "prefers-reduced-motion", "value": "no-preference"},
            ]})
            for width, height in [(320, 568), (390, 720), (768, 900), (1440, 900)]:
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
                })
                for mode in ("light", "dark"):
                    await tab.js("applyAppearance({...appearance,reduced:false,theme:"
                                 + json.dumps(mode) + "},true)")
                    await tab.js("chatScroller.scrollTop=chatScroller.scrollHeight")
                    assert await tab.js("""(()=>{
                      const tile=document.querySelector('.chat-image-placeholder');
                      const rect=tile.getBoundingClientRect();
                      const dots=getComputedStyle(tile,'::after');
                      return rect.width>0 && rect.height>0 &&
                        rect.height<=Math.min(560,innerHeight*.7)+1 &&
                        rect.right<=innerWidth && rect.left>=0 &&
                        document.documentElement.scrollWidth<=innerWidth &&
                        dots.animationName==='chat-image-halftone' &&
                        dots.backgroundImage.includes('radial-gradient') &&
                        tile.getAttribute('aria-busy')==='true' &&
                        !tile.closest('.chat-image-asset').hasAttribute('aria-busy') &&
                        !tile.closest('.chat-image-result').querySelector('.material-loading');
                    })()""")
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (evidence / f"generating-{width}-{mode}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
            position = await tab.js("getComputedStyle(document.querySelector("
                                    "'.chat-image-placeholder'),'::after').maskPosition")
            await asyncio.sleep(.15)
            assert await tab.js("getComputedStyle(document.querySelector("
                                "'.chat-image-placeholder'),'::after').maskPosition") != position
            await tab.js("applyAppearance({...appearance,reduced:true},true)")
            await tab.wait("getComputedStyle(document.querySelector("
                           "'.chat-image-placeholder'),'::after').animationName==='none'")
            with patch.object(host.application.images, 'tick', lambda: None):
                await tab.js("document.querySelector('.chat-image-cancel').focus()")
                await tab.click('.chat-image-cancel')
                await tab.wait("latest.messages.filter(m=>m.image_action).at(-1)"
                               ".image_action.state==='cancelling'")
                await execution_details(tab)
                cancellation = await tab.js("""(()=>{
                  const card=[...document.querySelectorAll('.chat-image-result')].at(-1);
                  const dots=card.querySelector('.chat-image-placeholder');
                  return {disabled:card.querySelector('.chat-image-cancel').disabled,
                    still:getComputedStyle(dots,'::after').animationName==='none',
                    focused:document.activeElement===card.querySelector('.chat-image-asset'),
                    focus:document.activeElement?.outerHTML.slice(0,250)};
                })()""")
                assert all(cancellation[key] for key in (
                    'disabled', 'still', 'focused',
                )), cancellation
                shot = await tab.command('Page.captureScreenshot', {'format': 'png'})
                (evidence / 'progress-cancelling-with-details.png').write_bytes(
                    base64.b64decode(shot['data']))
            host.application.images.start()
            await tab.wait(
                "[...document.querySelectorAll('.chat-image-job-status')]"
                ".some(n=>n.textContent==='Image cancelled')"
            )
            await tab.idle()
            await execution_details(tab)
            assert await tab.js("!document.querySelector('.chat-image-placeholder')")
            count = len([c for c in calls if c[1] == '/sdcpp/v1/img_gen'])
            await tab.click('.chat-image-retry')
            assert await tab.js("byId('prompt').value") == 'Generate an image of a mountain'
            assert len([c for c in calls if c[1] == '/sdcpp/v1/img_gen']) == count
            await tab.js('window.progressReload=true')
            await tab.command('Page.reload')
            await tab.wait("!window.progressReload && typeof latest!=='undefined' && latest && "
                           "latest.messages.filter(m=>m.image_action).at(-1)"
                           ".image_action.state==='cancelled'")
            await execution_details(tab)
            state["wait"], state["cancelled"], state["failed"] = False, False, True
            await tab.send("Generate an image of a tree")
            await tab.wait(
                "[...document.querySelectorAll('.chat-image-job-status')]"
                ".some(n=>n.textContent==='Image generation failed')"
            )
            await tab.idle()
            await execution_details(tab)
            assert await tab.js("!document.querySelector('.chat-image-placeholder')")
            assert await tab.js("[...document.querySelectorAll('.chat-image-error')]"
                                ".at(-1).textContent.length>0")
            await tab.js('window.progressReload=true')
            await tab.command('Page.reload')
            await tab.wait("!window.progressReload && typeof latest!=='undefined' && latest && "
                           "latest.messages.filter(m=>m.image_action).at(-1)"
                           ".image_action.state==='failed'")
            await execution_details(tab)
            assert len([c for c in calls if c[1] == "/sdcpp/v1/img_gen"]) == 4
            state["failed"], state["cancelled"] = False, False
            media_layouts = await verify_media_cards(tab, calls, evidence)
            await verify_progress_lifecycle(tab, host, calls, state, evidence)
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "browser": "passed",
                        "viewports": [320, 390, 768, 1440],
                        "generation": "recording fixture",
                        "preview_download_edit_reload_cancel_failure": True,
                        "halftone_loading_layouts": 8,
                        "halftone_animation_reduced_motion_and_cleanup": True,
                        "media_card_shape_layouts": media_layouts,
                        "media_card_refresh_resume_and_keyboard": True,
                        "progress_lifecycle_execution_details_and_no_replay": True,
                        "screenshots": str(evidence),
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)
        fixture.close()


if __name__ == "__main__":
    main(verify)

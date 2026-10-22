"""Isolated real-HTTP/Chrome acceptance for Klaude Expressive.

No live model/provider calls or user profile. Screenshots and measurements in
/tmp/klaude-expressive-validation. All content in screenshots is fixture data.
"""

# Embedded browser expressions are intentionally kept intact.
# ruff: noqa: E501
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
from klaude_tools import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from PIL import Image, ImageDraw
from webui_control_smoke import Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402

OUT = Path("/tmp/klaude-expressive-validation")


async def verify(host, root):
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
    OUT.mkdir(exist_ok=True)
    report = {"fixture_content": True, "layouts": [], "accessibility": []}
    axe_path = os.environ.get("KLAUDE_AXE_SOURCE")
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(0.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=12_000_000) as ws:
            tab = Tab(ws)

            async def wait(expression):
                await tab.wait(f"Boolean({expression})")

            await tab.command("Runtime.enable")
            await tab.command(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": 'window.expressiveErrors=[];window.addEventListener("error",e=>expressiveErrors.push(e.message));'
                },
            )
            await tab.command("Page.enable")
            await tab.command("Network.enable")
            await tab.command(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False},
            )
            await tab.command("Page.navigate", {"url": host.origin})
            await wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js(
                'byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await wait('latest?.session_id && window.KlaudeExpressive && byId("command-open")')
            await wait('document.documentElement.dataset.startup==="ready"')
            await tab.js(
                "document.fonts.ready;stream?.close();stream=null;clearInterval(pollTimer)"
            )

            async def shot(name):
                await tab.js("document.fonts.ready")
                await asyncio.sleep(0.15)
                data = await tab.command("Page.captureScreenshot", {"format": "png"})
                (OUT / (name + ".png")).write_bytes(base64.b64decode(data["data"]))

            if axe_path:
                await tab.js(Path(axe_path).read_text())

            async def accessibility(label):
                if not axe_path:
                    return
                # Scan the active interaction surface after finite entrance
                # animations settle; modal backdrops intentionally dim the inert
                # document and must not be treated as readable page content.
                await tab.js("Promise.all(document.getAnimations().filter(a=>"
                             "Number.isFinite(a.effect?.getComputedTiming().endTime))"
                             ".map(a=>a.finished.catch(()=>{})))")
                issues = await tab.js(
                    "axe.run(document.querySelector('dialog[open]')||document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}}).then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})))"
                )
                report["accessibility"].append({"surface": label, "violations": issues})
                (OUT / "accessibility.json").write_text(
                    json.dumps(report["accessibility"], indent=2) + "\n"
                )
                assert not issues, {"surface": label, "violations": issues}

            # Actual Google role generation: contrast across all presets/variants.
            contrast = await tab.js("""(()=>{
              const lum=hex=>{const c=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255)
                .map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);
                return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
              let minimum=100;const failures=[];
              for(const palette of paletteNames) for(const variant of Object.keys(MaterialColors.variants))
                for(const dark of [false,true]) {
                  const colors=KlaudeColors.palette({...appearance,palette,variant},dark);
                  for(const [bg,fg] of [['primary','on-primary'],['primary-container','on-primary-container'],
                    ['secondary','on-secondary'],['secondary-container','on-secondary-container'],
                    ['tertiary','on-tertiary'],['tertiary-container','on-tertiary-container'],
                    ['surface','on-surface'],['surface-container-highest','on-surface-variant'],['error','on-error']]) {
                    const a=lum(colors[bg]),b=lum(colors[fg]);const ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                    minimum=Math.min(minimum,ratio);if(ratio<4.5) failures.push({palette,variant,dark,bg,ratio});
                  }
                }
              return {minimum,failures};})()""")
            assert not contrast["failures"], contrast
            report["contrast"] = contrast
            await tab.js('showView("settings");showSettingsSection("theme")')
            original = await tab.js(
                'getComputedStyle(document.documentElement).getPropertyValue("--primary")'
            )
            await tab.js(
                'byId("theme-accent").value="#007f87";byId("theme-accent").dispatchEvent(new Event("input"))'
            )
            assert await tab.js('document.documentElement.dataset.colorSource==="custom"')
            assert original != await tab.js(
                'getComputedStyle(document.documentElement).getPropertyValue("--primary")'
            )
            await tab.click("#theme-reset")
            assert await tab.js('appearance.colorSource==="preset"')
            await tab.js(
                'byId("theme-variant").value="expressive";byId("theme-variant").dispatchEvent(new Event("change"))'
            )
            await tab.click("#theme-apply")
            assert await tab.js(
                'JSON.parse(localStorage.getItem(preferenceKey)).variant==="expressive"'
            )
            # Quantization runs locally and persists only a seed; no image URL/data.
            await tab.command("DOM.enable")
            document = await tab.command("DOM.getDocument")
            node = await tab.command(
                "DOM.querySelector",
                {"nodeId": document["root"]["nodeId"], "selector": "#theme-image"},
            )
            await tab.command(
                "DOM.setFileInputFiles",
                {"nodeId": node["nodeId"], "files": [str(root / "theme.png")]},
            )
            await wait('byId("theme-image-status").textContent.includes("Palette ready")')
            assert await tab.js(
                'appearanceDraft().colorSource==="image" && /^#[a-f0-9]{6}$/.test(appearanceDraft().accent)'
            )
            await tab.click("#theme-apply")
            assert await tab.js(
                '!localStorage.getItem(preferenceKey).includes("theme.png") && !localStorage.getItem(preferenceKey).includes("data:")'
            )
            # Switches/radio geometry comes from the measured reference.
            assert await tab.js(
                'getComputedStyle(byId("reduced-motion").nextElementSibling).width==="39px"'
            )
            report["theme_live_discard_apply_local_image"] = True

            await tab.js('showView("library")')
            await wait('byId("library-items").querySelectorAll(".file-item").length===5')
            await tab.click('[data-file-scope="current"]')
            assert await tab.js('[...byId("library-sections").querySelectorAll(".tab-count")].every(b=>b.hidden)')
            await wait('byId("library-items").querySelectorAll(".file-item").length===1')
            await tab.click('[data-file-scope="all"]')
            await wait('byId("library-items").querySelectorAll(".file-item").length===5')
            await tab.click('[data-file-view="gallery"]')
            await wait(
                'byId("library-items").dataset.view==="gallery" && byId("library-items").querySelectorAll(".file-item").length===4'
            )
            await tab.js('byId("library-items").querySelector(".file-open").focus()')
            await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "ArrowRight"})
            assert await tab.js(
                'document.activeElement===byId("library-items").querySelectorAll(".file-open")[1]'
            )
            await tab.click("#library-items .file-open")
            await wait(
                'byId("artifact-detail").open && byId("artifact-preview").querySelector("img")?.naturalWidth>0'
            )
            await shot("image-preview-desktop")
            await tab.click("#artifact-close")
            report["library_scope_gallery_keyboard_preview"] = True
            await tab.js('showView("workspace");workspaceRead("files")')
            await wait('byId("workspace-result").querySelector(".workspace-files")')
            # A failed same-directory refresh retains the usable file rows.
            await tab.js('window.workspaceFetch=fetch;window.workspaceRows=byId("workspace-result").querySelector(".workspace-files");'
                         'fetch=(input,options)=>String(input).startsWith("/api/v1/workspace/files?")?Promise.resolve(new Response(JSON.stringify({error:{message:"Fixture offline"}}),{status:503,headers:{"Content-Type":"application/json"}})):workspaceFetch(input,options);'
                         'workspaceRead("files")')
            await wait('byId("workspace-result").querySelector(".loading-error")')
            assert await tab.js('workspaceRows===byId("workspace-result").querySelector(".workspace-files")')
            await tab.js('fetch=workspaceFetch')
            await tab.click('.workspace-file-row[aria-label="Open folder src"]')
            await wait('byId("workspace-result").textContent.includes("agent.py")')
            await tab.click('.workspace-file-row[aria-label="Read file src/agent.py"]')
            await wait('byId("workspace-result").textContent.includes("def greet")')
            assert await tab.js('Boolean(byId("workspace-result").querySelector("code .token"))')
            await tab.js('showView("chat");showView("workspace")')
            await wait('byId("workspace-result").querySelector("code .token") && !loadingStates.has(byId("workspace-result"))')
            assert await tab.js('byId("workspace-result").textContent.includes("def greet") && workspaceOperation==="file"')
            assert await tab.js(
                'fetch("/api/v1/workspace/file?path=../outside").then(r=>r.status>=400)'
            )
            report["workspace_navigation_and_jail"] = True

            await tab.click("#command-open")
            await tab.js(
                'byId("command-query").value="Open Models";byId("command-query").dispatchEvent(new Event("input"))'
            )
            await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter"})
            await wait('currentView==="models" && !byId("command-palette").open')
            await tab.click("#command-open")
            await tab.click('[data-mode="shortcuts"]')
            await tab.js(
                'byId("command-query").value="zoom";byId("command-query").dispatchEvent(new Event("input"))'
            )
            assert await tab.js(
                'byId("command-results").textContent.includes("Zoom") && byId("command-results").querySelectorAll("[role=option]").length===1'
            )
            await accessibility("shortcuts")
            await shot("shortcuts")
            await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape"})
            assert await tab.js('!byId("command-palette").open')
            report["commands_search_keyboard_focus"] = True

            # Render real components with clearly labeled sample technical content.
            sample = '## A workspace that stays yours\n\nThe agent reads files only after your permission.\n\n```python\ndef greet(name: str):\n    return f"Hello, {name}"\n```\n\n| Area | State |\n| --- | --- |\n| File reading | Ask first |\n| Edits | Reviewed |'
            fixture = (
                'byId("welcome").hidden=true;messages.replaceChildren(ChatMarkdown.create("user","Review this project and explain the next step.","expressive-user"),ChatMarkdown.create("assistant",'
                + json.dumps(sample)
                + ',"expressive-assistant"));'
            )
            for theme in ("light", "dark"):
                for width, height in ((1440, 1000), (850, 900), (390, 844), (320, 740)):
                    await tab.command(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": width,
                            "height": height,
                            "deviceScaleFactor": 1,
                            "mobile": width < 600,
                        },
                    )
                    await tab.js(
                        "applyAppearance(appearance={...appearance,theme:"
                        + json.dumps(theme)
                        + ',colorSource:"preset",palette:"lavender",variant:"tonal-spot",reduced:true},true)'
                    )
                    for page, section in (
                        ("chat", None),
                        ("settings", "theme"),
                        ("settings", "agent"),
                        ("settings", "models"),
                        ("settings", "memory"),
                        ("settings", "account"),
                        ("library", None),
                        ("workspace", None),
                        ("integrations", None),
                        ("models", None),
                        ("activity", None),
                    ):
                        await tab.js("showView(" + json.dumps(page) + ")")
                        if section:
                            await tab.js("showSettingsSection(" + json.dumps(section) + ")")
                        if section == "agent":
                            await tab.js(
                                'if(byId("agent-group-tools_permissions")) byId("agent-group-tools_permissions").open=true'
                            )
                        if page == "chat":
                            await tab.js(fixture)
                        await asyncio.sleep(0.1)
                        layout = await tab.js("""(()=>{const main=byId(currentView+'-view');return {
                          page:currentView,width:innerWidth,bodyFits:document.documentElement.scrollWidth<=innerWidth,
                          mainFits:main.scrollWidth<=main.clientWidth+1,mainWidth:main.clientWidth};})()""")
                        if width == 1440 and theme == "light":
                            await accessibility(f"{page}/{section}")
                        report["layouts"].append({**layout, "theme": theme, "section": section})
                        assert layout["bodyFits"] and layout["mainFits"], layout
                        if width in (1440, 390):
                            await shot(f"{page}-{section or 'page'}-{theme}-{width}")
                    await tab.js('showView("chat");setContextPanel(true)')
                    await shot(f"context-agent-{theme}-{width}")
                    await tab.click("#cp-tab-library")
                    await tab.click("#cp-scope-all")
                    await wait('byId("cp-file-items").querySelectorAll(".file-item").length>0')
                    await tab.js("setContextPanel(false)")
            # Isolated component motion, independent of asynchronous session refreshes.
            assert await tab.js(
                "MaterialLoading.frameAt(900).progress>0 && MaterialLoading.frameAt(900).progress<1 && MaterialLoading.frameAt(900).zoom>1"
            )
            assert await tab.js("Object.keys(MaterialLoadingGeometry.shapes).length===9")
            await tab.js(
                'applyAppearance(appearance={...appearance,theme:"dark",reduced:false},true);showView("chat");'
                'window.motionIndicator=MaterialLoading.create({size:"large",contained:true});'
                'motionIndicator.id="acceptance-loader";motionIndicator.style.cssText="position:fixed;top:70px;right:20px;z-index:20";document.body.append(motionIndicator);'
                'window.motionPath=motionIndicator.querySelector("path").getAttribute("d")'
            )
            await wait('motionPath!==motionIndicator.querySelector("path").getAttribute("d")')
            await tab.js(
                'applyAppearance(appearance={...appearance,reduced:true},true);window.stillPath=motionIndicator.querySelector("path").getAttribute("d")'
            )
            await asyncio.sleep(0.05)
            await tab.js('window.stillPath=motionIndicator.querySelector("path").getAttribute("d")')
            await asyncio.sleep(0.9)
            assert await tab.js(
                'stillPath===motionIndicator.querySelector("path").getAttribute("d")'
            )
            await tab.js("motionIndicator.remove()")
            report["morph_and_reduced_motion"] = True
            assert not tab.errors, tab.errors
            report["browser_exceptions"] = tab.errors
            (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({**report, "layouts": len(report["layouts"])}))
    finally:
        process.terminate()
        process.wait(timeout=10)


def main():
    with tempfile.TemporaryDirectory(prefix="klaude-expressive-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        (root / "src").mkdir()
        (root / "src/agent.py").write_text('def greet(name):\n    return f"Hello, {name}"\n')
        library = LibraryManagement(cfg, root)
        current = library.artifacts.import_bytes(b"# Design notes\n", "document", "design-notes.md")
        with library.artifacts.database(write=True) as db:
            db.execute("UPDATE artifacts SET session=? WHERE id=?", (app.session_id, current["id"]))
        for i, (bg, fg) in enumerate(
            (
                ("#9fd7cc", "#28594e"),
                ("#dfbbef", "#705385"),
                ("#e9b59e", "#82492e"),
                ("#b6cee8", "#476c92"),
            )
        ):
            image = Image.new("RGB", (800, 600), bg)
            draw = ImageDraw.Draw(image)
            draw.ellipse((80, 30, 650, 600), fill=fg)
            draw.rounded_rectangle((300, 100, 740, 500), radius=120, fill=bg)
            buf = io.BytesIO()
            image.save(buf, "PNG")
            library.artifacts.import_bytes(buf.getvalue(), "media", f"palette-study-{i + 1}.png")
            if i == 0:
                (root / "theme.png").write_bytes(buf.getvalue())
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts, library=library, staging_dir=root / "staging")
        host.local_models = lambda: []
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root), 180))
        finally:
            host.stop()
            serving.join(3)


if __name__ == "__main__":
    main()

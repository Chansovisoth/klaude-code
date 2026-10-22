"""Stationary-pointer regression for inventory row shape flicker.

Uses the isolated Expressive HTTP/account fixture with read-only browser inventory
responses. No user data, models, external services or mutation requests. Run with
.venv/bin/python scripts/webui_collection_shapes_smoke.py. Fixture screenshots and
measurements go to /tmp/klaude-collection-shapes-validation.
"""

# Embedded browser expressions are intentionally kept intact.
# ruff: noqa: E501
from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
import webui_expressive_smoke as fixture
from webui_control_smoke import Tab

OUT = Path("/tmp/klaude-collection-shapes-validation")
SECTIONS = (("skills", "skill-items"), ("knowledge", "knowledge-items"), ("connections", "connection-items"))
TRANSPORT = """(()=>{
  const original=fetch.bind(window);
  window.fetch=async(resource,options)=>{
    const url=new URL(typeof resource==='string'?resource:resource.url,location.href);
    let result;
    if(url.pathname==='/api/v1/integrations/skills')result={items:[0,1,2].map(i=>({name:'Fixture skill '+i,description:'Read-only browser fixture for stable inventory shapes.',enabled:i!==1,identity:'fixture-'+i})),total:3,more:false};
    if(url.pathname==='/api/v1/integrations/connections')result={management_allowed:true,servers:[0,1,2].map(i=>({name:'Fixture connection '+i,description:'Read-only browser fixture for stable inventory shapes.',enabled:i!==1,transport:'http',tool_count:3,fingerprint:'fixture-'+i})),truncated:false};
    if(url.pathname==='/api/v1/library/knowledge')result={items:[0,1,2].map(i=>({id:'Fixture knowledge '+i,sources:1,chunks:5})),total:3,more:false};
    if(url.pathname==='/api/v1/library/sources')result={items:[{id:'Fixture source',library:url.searchParams.get('library'),url:'https://example.test/fixture',kind:'url',files:1,identity:'fixture-source'}],total:1,more:false};
    if(url.pathname==='/api/v1/library/knowledge/contents') {
      const library=url.searchParams.get('library');
      result={mode:library?'chunks':'libraries',available:true,summary:{sources:3,chunks:15},total:3,more:false,
        items:[0,1,2].map(i=>library?{id:'fixture-chunk-'+i,library,source:'Fixture source',text:'Read-only indexed text fixture.',characters:31}:
          {id:'Fixture knowledge '+i,sources:1,chunks:5})};
    }
    if(url.pathname==='/api/v1/library/knowledge/sources')result={items:[{id:'Fixture source',chunks:5}],summary:{sources:1,chunks:5},total:1,more:false};
    if(result)return new Response(JSON.stringify(result),{headers:{'Content-Type':'application/json'}});
    return original(resource,options);
  };
  window.rowGeometry=element=>{
    const s=getComputedStyle(element);
    return [s.borderTopLeftRadius,s.borderTopRightRadius,s.borderBottomRightRadius,s.borderBottomLeftRadius,
      element.offsetWidth,element.offsetHeight,s.transform];
  };
})()"""


async def verify(host, root):
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell")))
    profile = root / "chrome-collection-shapes"
    process = subprocess.Popen(
        [chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0", f"--user-data-dir={profile}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    OUT.mkdir(exist_ok=True)
    report = {"fixture_content": True, "cases": [], "screenshots": []}
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as response:
            target = json.load(response)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=12_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js('byId("login-password").value=' + json.dumps(host.accounts.initial_password()) + ';byId("account-login").requestSubmit()')
            await tab.wait('latest?.session_id && document.documentElement.dataset.startup==="ready"')
            await tab.js('stream?.close();stream=null;clearInterval(pollTimer)')
            await tab.js(TRANSPORT)
            await tab.js('showView("integrations")')

            async def move(x=10, y=10):
                await tab.command("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})

            async def stable(label, milliseconds=220):
                result = await tab.js("""new Promise(resolve=>{
                  const changes=[],start=performance.now();let frames=0;
                  function read(){frames++;
                    const actual=JSON.stringify([rowGeometry(probe),rowGeometry(probe.parentElement)]);
                    if(actual!==probeGeometry)changes.push(JSON.parse(actual));
                    if(performance.now()-start<DURATION)requestAnimationFrame(read);else resolve({frames,changes,hover:probe.matches(':hover')});}
                  requestAnimationFrame(read);
                })""".replace("DURATION", str(milliseconds)))
                assert not result["changes"], (label, result)
                return result

            async def select_probe(selector):
                await move()
                await tab.js('window.probe=document.querySelector(' + json.dumps(selector) + ');probe.scrollIntoView({block:"center"});')
                await asyncio.sleep(.4)
                await tab.js('window.probeGeometry=JSON.stringify([rowGeometry(probe),rowGeometry(probe.parentElement)])')

            async def shot(name):
                await tab.js("document.fonts.ready")
                await asyncio.sleep(.25)
                data = await tab.command("Page.captureScreenshot", {"format": "png"})
                (OUT / name).write_bytes(base64.b64decode(data["data"]))
                report["screenshots"].append(name)

            for width in (320, 390, 850, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 1000, "deviceScaleFactor": 1, "mobile": False,
                })
                for theme in ("light", "dark"):
                    await tab.js('applyAppearance(appearance={...appearance,reduced:false,theme:' + json.dumps(theme) + '},true)')
                    for section, container in SECTIONS:
                        await tab.click(f'[data-integration="{section}"]')
                        await tab.wait(f'byId("{container}").querySelectorAll(".collection-row").length===3')
                        case = {"width": width, "theme": theme, "section": section, "edge_frames": 0}
                        for position in (1, 2, 3):
                            await select_probe(f"#{container}>.collection-row:nth-child({position})>.collection-open")
                            point = await tab.js('(()=>{const r=probe.getBoundingClientRect();return {x:r.left+15,y:r.top+5}})()')
                            await move(**point)
                            result = await stable((case, position, "hover"), 450 if width == 1440 else 180)
                            assert result["hover"], (case, position, "lost hover at a stationary pointer")
                            case["edge_frames"] += result["frames"]
                        # A press stays within the same hit area. Releasing outside
                        # cancels the click, so no enable/edit action can run.
                        point = await tab.js('(()=>{const r=probe.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()')
                        await move(**point)
                        await tab.command("Input.dispatchMouseEvent", {"type": "mousePressed", "button": "left", "clickCount": 1, **point})
                        await stable((case, "press"))
                        await move()
                        await tab.command("Input.dispatchMouseEvent", {"type": "mouseReleased", "button": "left", "x": 10, "y": 10, "clickCount": 1})
                        await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Tab", "windowsVirtualKeyCode": 9})
                        await tab.command("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Tab", "windowsVirtualKeyCode": 9})
                        await tab.js("probe.focus()")
                        await stable((case, "focus"))
                        assert await tab.js("probe.matches(':focus-visible') && parseFloat(getComputedStyle(probe).outlineWidth)>=2"), case
                        # Unchanged inventories retain row identity and shape.
                        await tab.js(f'window.savedRows=[...byId("{container}").children]')
                        await tab.js("loadSkills()" if section == "skills" else "loadKnowledge()" if section == "knowledge" else "BrowserManagement.loadConnections()")
                        assert await tab.js(f'savedRows.every((row,i)=>row===byId("{container}").children[i])'), case
                        await stable((case, "refresh"))
                        assert await tab.js("document.documentElement.scrollWidth<=innerWidth"), case
                        report["cases"].append(case)
                        if width in (320, 1440):
                            await shot(f"{section}-{theme}-{width}.png")

            # Filtering down to one row retains all four external corners.
            await tab.click('[data-connection-state="disabled"]')
            await tab.wait('byId("connection-items").querySelectorAll(".collection-row").length===1')
            await select_probe("#connection-items .collection-open")
            await stable("single row")
            assert await tab.js("rowGeometry(probe).slice(0,4).every(radius=>radius==='23px')")
            report["single_filtered_row"] = True

            await tab.click('[data-integration="knowledge"]')
            await tab.wait('byId("knowledge-items").querySelectorAll(".collection-row").length===3')
            await tab.click("#knowledge-items .collection-open")
            await tab.wait('byId("source-items").querySelector(".source-row")!==null')
            await tab.js('byId("knowledge-sources").open=true')
            await tab.click("#source-items .collection-open")
            await tab.wait('byId("source-items").querySelector(".collection-open").getAttribute("aria-pressed")==="true"')
            await select_probe("#source-items .collection-open")
            await stable("selected knowledge source")
            assert await tab.js('getComputedStyle(probe).backgroundColor!=="rgba(0, 0, 0, 0)"')
            point = await tab.js('(()=>{const r=probe.getBoundingClientRect();return {x:r.left+15,y:r.top+5}})()')
            await move(**point)
            await stable("knowledge source row")
            report["knowledge_selection_and_sources"] = True
            await tab.command("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
            await stable("system reduced motion")
            report["reduced_motion"] = True
            assert not tab.errors, tab.errors
            report["browser_exceptions"] = tab.errors
            (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({**report, "cases": len(report["cases"])}))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    fixture.verify = verify
    fixture.main()

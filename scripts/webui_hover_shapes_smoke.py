"""Hover-exit radius regression and shared Models row styling in real Chrome.

Isolated HTTP/account/profile, fixture provider catalogs, no model execution.
Evidence: /tmp/klaude-hover-shapes-validation. Optional KLAUDE_TEST_CHROME.
"""

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
from klaude_application.browser_models import BrowserModels
from klaude_core.model_runtime import ModelInfo
from webui_collection_shapes_smoke import TRANSPORT as INVENTORY_TRANSPORT
from webui_control_smoke import Tab

OUT = Path("/tmp/klaude-hover-shapes-validation")
TRANSPORT = """(()=>{
  const original=fetch.bind(window);
  window.fetch=async(resource,options)=>{
    const url=new URL(typeof resource==='string'?resource:resource.url,location.href);
    if(url.pathname==='/api/v1/models/connections')return Response.json({connections:[
      {id:'openai',name:'OpenAI',backend:'openai_api',source:'Fixture',enabled:true},
      {id:'openrouter',name:'OpenRouter',backend:'openrouter',source:'Fixture',enabled:true},
      {id:'ollama',name:'Local Ollama',backend:'ollama',source:'Fixture',enabled:true}]});
    if(url.pathname==='/api/v1/models/catalog')return Response.json({models:Array.from({length:25},(_,i)=>({
      id:({openai:'openai_api',openrouter:'openrouter',ollama:'ollama'}[url.searchParams.get('connection')])+'@'+url.searchParams.get('connection')+'/fixture-'+i,name:'Fixture coding model '+i,effort_levels:['off','low','high']}))});
    return original(resource,options);
  };
})()"""
SAMPLE = """new Promise(resolve=>{
  const start=performance.now(),failures=[];let frames=0,minimum=Infinity;
  function sample(){frames++;
    for(const e of shapeTargets){const s=getComputedStyle(e);
      const radii=[s.borderTopLeftRadius,s.borderTopRightRadius,s.borderBottomRightRadius,s.borderBottomLeftRadius];
      for(const radius of radii){const value=parseFloat(radius);if(Number.isFinite(value))minimum=Math.min(minimum,value);
        if(value===0&&!failures.some(f=>f.element===(e.id||e.className)))failures.push({element:e.id||e.className,radii});}
    }
    if(performance.now()-start<500)requestAnimationFrame(sample);else resolve({frames,minimum,failures});
  }requestAnimationFrame(sample);
})"""


async def verify(host, root):
    host.application.agent.browser_models = BrowserModels(host.library.cfg)
    host.application.agent.model_info = ModelInfo("openai_api", "fixture-0", "Fixture coding model 0", connection_id="openai")
    host.library._installed_skills = lambda: {"items": [
        {"name": f"Fixture skill {i}", "description": "Fixture inventory", "library": "skills", "identity": str(i), "enabled": i != 1}
        for i in range(3)], "more": False}
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob("*/chrome-headless-shell-linux64/chrome-headless-shell")))
    profile = root / "chrome-hover-shapes"
    process = subprocess.Popen([chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0", f"--user-data-dir={profile}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    OUT.mkdir(exist_ok=True)
    report = {"fixture_content": True, "providers": [], "models_layouts": [], "audit": []}
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
            for domain in ("Runtime", "Page", "DOM", "CSS"):
                await tab.command(domain + ".enable")
            await tab.command("Page.addScriptToEvaluateOnNewDocument", {"source": TRANSPORT})
            await tab.command("Page.addScriptToEvaluateOnNewDocument", {"source": INVENTORY_TRANSPORT})
            await tab.command("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined"&&!byId("local-access").hidden')
            await tab.js('byId("login-password").value=' + json.dumps(host.accounts.initial_password()) + ';byId("account-login").requestSubmit()')
            await tab.wait('latest?.session_id&&document.documentElement.dataset.startup==="ready"')
            await tab.js('stream?.close();stream=null;clearInterval(pollTimer);window.savedShapeSnapshot=latest;applyAppearance(appearance={...appearance,reduced:false},true)')
            await tab.js('showView("store")')
            await tab.wait('byId("models-items").querySelectorAll(".models-model").length===20')

            async def sample(label):
                result = await tab.js(SAMPLE)
                assert not result["failures"], (label, result)
                return result

            async def exit_pointer(selector, label):
                await tab.command("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 10, "y": 10})
                await tab.js('window.shapeTargets=[document.querySelector(' + json.dumps(selector) + ')];shapeTargets[0].scrollIntoView({block:"center"})')
                await asyncio.sleep(.4)
                idle = await tab.js('getComputedStyle(shapeTargets[0]).borderTopLeftRadius')
                point = await tab.js('(()=>{const r=shapeTargets[0].getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()')
                await tab.command("Input.dispatchMouseEvent", {"type": "mouseMoved", **point})
                await sample(label + " hover")
                await tab.command("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 10, "y": 10})
                result = await sample(label + " exit")
                assert await tab.js('getComputedStyle(shapeTargets[0]).borderTopLeftRadius') == idle, label
                return result

            for provider in ("openai", "openrouter", "ollama"):
                selector = f'#models-connections [data-row-key="{provider}"]'
                await tab.click(selector)
                await tab.wait('byId("models-catalog-title").textContent===' + json.dumps({"openai": "OpenAI", "openrouter": "OpenRouter", "ollama": "Local Ollama"}[provider]))
                await tab.wait('!byId("store-refresh").disabled && byId("models-items").querySelectorAll(".models-model").length===20')
                selected = await exit_pointer(selector, provider + " selected")
                assert await tab.js('document.querySelector(' + json.dumps(selector) + ').getAttribute("aria-pressed")==="true"')
                report["providers"].append({"provider": provider, **selected})

            await tab.click('#models-connections [data-row-key="openai"]')
            await tab.wait('byId("models-catalog-title").textContent==="OpenAI" && !byId("store-refresh").disabled && byId("models-items").querySelectorAll(".models-model").length===20')
            for width in (320, 390, 850, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {"width": width, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
                for theme in ("light", "dark"):
                    await tab.js('applyAppearance(appearance={...appearance,theme:' + json.dumps(theme) + '},true)')
                    await asyncio.sleep(.2)
                    geometry = await tab.js("""(()=>{const rows=[...byId('models-items').querySelectorAll('.models-model')];return {
                      shared:rows.length===20&&rows.every(r=>r.matches('.library-card.collection-row')&&r.querySelector('.collection-icon svg')),
                      fits:document.documentElement.scrollWidth<=innerWidth&&byId('store-view').scrollWidth<=byId('store-view').clientWidth,
                      contained:rows.every(r=>{const b=r.querySelector('button').getBoundingClientRect(),box=r.getBoundingClientRect();return b.right<=box.right&&b.left>=box.left&&b.width>=44&&b.height>=44}),
                      current:rows[0].dataset.current==='true'&&rows[0].querySelector('button').textContent==='Current',
                      metadata:rows.every(r=>r.querySelector('.models-model-ref')&&r.querySelector('.model-capabilities'))};})()""")
                    assert all(geometry.values()), (width, theme, geometry)
                    report["models_layouts"].append({"width": width, "theme": theme, **geometry})
                    if width in (320, 1440):
                        await tab.js('byId("store-view").scrollTop=0')
                        data = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (OUT / f"models-{theme}-{width}.png").write_bytes(base64.b64decode(data["data"]))

            await tab.js('latest=savedShapeSnapshot')
            # Force hover for all visible rounded buttons together, then sample
            # every exit frame. Each page uses its actual shared components.
            async def audit(label):
                await asyncio.sleep(.4)
                await tab.wait('[...document.querySelectorAll(".main-view [aria-busy=true]")].every(e=>!e.getClientRects().length)')
                count = await tab.js("""(()=>{window.shapeTargets=[...document.querySelectorAll('button')].filter(e=>!e.disabled&&e.getClientRects().length&&e.offsetWidth&&e.offsetHeight&&
                  ['borderTopLeftRadius','borderTopRightRadius','borderBottomRightRadius','borderBottomLeftRadius'].every(p=>parseFloat(getComputedStyle(e)[p])>0));
                  shapeTargets.forEach(e=>e.setAttribute('data-hover-audit',''));return shapeTargets.length;})()""")
                assert count > 0, label
                document = await tab.command("DOM.getDocument")
                nodes = await tab.command("DOM.querySelectorAll", {"nodeId": document["root"]["nodeId"], "selector": "[data-hover-audit]"})
                for node in nodes["nodeIds"]:
                    await tab.command("CSS.forcePseudoState", {"nodeId": node, "forcedPseudoClasses": ["hover"]})
                await sample(label + " hover")
                for node in nodes["nodeIds"]:
                    try:
                        await tab.command("CSS.forcePseudoState", {"nodeId": node, "forcedPseudoClasses": []})
                    except AssertionError:
                        print("Audit target changed during " + label, flush=True)
                        raise
                result = await sample(label + " exit")
                await tab.js("shapeTargets.forEach(e=>e.removeAttribute('data-hover-audit'))")
                report["audit"].append({"surface": label, "buttons": count, **result})

            for width in (390, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {"width": width, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
                for page in ("chat", "library", "workspace", "integrations", "models", "activity"):
                    await tab.js('showView(' + json.dumps(page) + ')')
                    if page == "integrations":
                        for section in ("skills", "knowledge", "connections"):
                            await tab.click(f'[data-integration="{section}"]')
                            container = {"skills": "skill-items", "knowledge": "knowledge-items", "connections": "connection-items"}[section]
                            await tab.wait(f'byId("{container}").querySelectorAll(".collection-row").length===3')
                            await audit(f"{page}/{section}/{width}")
                            if section == "knowledge":
                                await tab.click("#knowledge-items .collection-open")
                                await tab.wait('byId("knowledge-items").querySelectorAll(".knowledge-chunk").length===3&&byId("source-items").querySelector(".source-row")!==null')
                                await tab.js('byId("knowledge-sources").open=true')
                                await audit(f"{page}/knowledge/chunks-and-sources/{width}")
                                await tab.js('knowledgeLocation("")')
                                await tab.wait('byId("knowledge-items").querySelectorAll(".collection-row").length===3')
                    else:
                        if page == "models":
                            await tab.wait('!byId("store-refresh").disabled&&byId("models-items").querySelectorAll(".models-model").length===20')
                        await audit(f"{page}/{width}")
                for section in ("account", "theme", "agent", "models", "memory"):
                    await tab.js('showView("settings",{section:' + json.dumps(section) + '})')
                    if section == "agent":
                        await tab.wait('Boolean(byId("agent-group-tools_permissions"))')
                        await tab.js('byId("agent-group-tools_permissions").open=true')
                    await audit(f"settings/{section}/{width}")
                await tab.click("#command-open")
                await audit(f"command-palette/{width}")
                await tab.js('byId("command-palette").close()')

            # Selected session/tag shapes also used oversized pill targets.
            await tab.js('showView("chat");window.tagShape=document.createElement("button");tagShape.className="tag-suggestion";tagShape.textContent="Fixture tag";tagShape.style.cssText="position:fixed;left:80px;top:80px;z-index:20";document.body.append(tagShape);window.sessionShape=document.createElement("button");sessionShape.className="selected";sessionShape.textContent="Fixture session";byId("session-list").append(sessionShape);window.shapeTargets=[tagShape,sessionShape]')
            await tab.js('tagShape.setAttribute("aria-pressed","true")')
            await asyncio.sleep(.4)
            await tab.js('tagShape.setAttribute("aria-pressed","false");sessionShape.classList.remove("selected")')
            report["selection_exit"] = await sample("session/tag deselection")
            await tab.js('tagShape.remove();sessionShape.remove();applyAppearance(appearance={...appearance,reduced:true},true)')
            await audit("app reduced motion")
            assert not tab.errors, tab.errors
            report["browser_exceptions"] = tab.errors
            (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({**report, "models_layouts": len(report["models_layouts"]), "audit": len(report["audit"])}))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    fixture.verify = verify
    fixture.main()

"""Real HTTP/Chrome Skills status filters with an isolated 90-Skill inventory.

No user profile, model, mutation or external service. Run with .venv/bin/python.
Screenshots and report: /tmp/klaude-skills-filters-validation.
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

OUT = Path("/tmp/klaude-skills-filters-validation")
ITEMS = [{"name": f"skill-{i:02}", "identity": str(i), "enabled": i % 3 != 0,
          "description": "review" if i % 2 else "coding", "library": "skills"}
         for i in range(90)]


async def verify(host, root):
    host.library._installed_skills = lambda: {"items": ITEMS, "more": False}
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell")))
    profile = root / "chrome-skills-filters"
    process = subprocess.Popen([chrome, "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0", f"--user-data-dir={profile}"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    OUT.mkdir(exist_ok=True)
    report = {"fixture_inventory": 90, "layouts": []}
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
            await tab.js('stream?.close();stream=null;clearInterval(pollTimer);showView("integrations")')

            async def expect(state, query="", offset=0):
                expected = [item for item in ITEMS if (state == "all" or item["enabled"] == (state == "enabled"))
                            and (not query or query in item["description"])]
                names = [item["name"] for item in expected[offset:offset + 20]]
                await tab.wait('skillsState===' + json.dumps(state) + ' && skillsOffset===' + str(offset) +
                               ' && byId("skill-items").getAttribute("aria-busy")==="false" && '
                               'JSON.stringify(installedSkills.map(item=>item.name))===' + json.dumps(json.dumps(names, separators=(",", ":"))))
                assert await tab.js('[...byId("skills-state-filter").children].filter(b=>b.getAttribute("aria-pressed")==="true").length===1 && '
                                    'byId("skills-state-filter").querySelector("[aria-pressed=true]").dataset.skillState===' + json.dumps(state))
                assert await tab.js('byId("skill-items").querySelectorAll(".skill-card").length') == len(names)
                if expected:
                    assert await tab.js('byId("skills-numbers").dataset.last') == str((len(expected) + 19) // 20)
                return expected

            await expect("all")
            for state in ("enabled", "disabled", "all"):
                await tab.click(f'[data-skill-state="{state}"]')
                expected = await expect(state)
                for offset in range(20, len(expected), 20):
                    await tab.click("#skills-next")
                    await expect(state, offset=offset)
                assert await tab.js('byId("skills-next").disabled')
            report["whole_inventory_pagination"] = True

            await tab.click('[data-skill-state="enabled"]')
            await expect("enabled")
            await tab.js('byId("skills-query").value="review";byId("skills-query").dispatchEvent(new Event("input"))')
            await expect("enabled", "review")
            await tab.click('[data-skill-state="disabled"]')
            await expect("disabled", "review")
            await tab.js('history.back()')
            await expect("enabled", "review")
            await tab.js('history.forward()')
            await expect("disabled", "review")
            await tab.command("Page.reload")
            await tab.wait('typeof latest!=="undefined" && latest?.session_id && document.documentElement.dataset.startup==="ready"')
            await expect("disabled", "review")
            await tab.js('stream?.close();stream=null;clearInterval(pollTimer)')
            await tab.click('[data-integration="knowledge"]')
            await tab.click('[data-integration="skills"]')
            await expect("disabled", "review")
            report["search_history_reload_and_navigation"] = True

            await tab.js('byId("skills-query").value="";byId("skills-filter").requestSubmit()')
            await expect("disabled")
            await tab.click('[data-skill-state="all"]')
            await expect("all")
            await tab.js('document.querySelector("[data-skill-state=all]").focus()')
            for key, state in (("ArrowRight", "enabled"), ("ArrowRight", "disabled"), ("Home", "all"), ("End", "disabled")):
                await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": key})
                await tab.command("Input.dispatchKeyEvent", {"type": "keyUp", "key": key})
                await expect(state)
                assert await tab.js("document.activeElement.dataset.skillState") == state
            report["keyboard"] = True

            for width in (320, 390, 850, 1440):
                await tab.command("Emulation.setDeviceMetricsOverride", {"width": width, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
                for theme in ("light", "dark"):
                    await tab.js('applyAppearance(appearance={...appearance,theme:' + json.dumps(theme) + '},true)')
                    for state in ("all", "enabled", "disabled"):
                        await tab.click(f'[data-skill-state="{state}"]')
                        await expect(state)
                        geometry = await tab.js('(()=>{const buttons=[...byId("skills-state-filter").children],r=buttons.map(b=>b.getBoundingClientRect());return {fits:r.every(x=>x.right<=innerWidth),oneRow:r.every(x=>Math.abs(x.top-r[0].top)<1),targets:r.every(x=>x.height>=44&&x.width>=44),pageFits:document.documentElement.scrollWidth<=innerWidth};})()')
                        assert all(geometry.values()), (width, theme, state, geometry)
                        report["layouts"].append({"width": width, "theme": theme, "state": state})
                    if width in (320, 1440):
                        await asyncio.sleep(.4)
                        data = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (OUT / f"skills-{theme}-{width}.png").write_bytes(base64.b64decode(data["data"]))

            await tab.js('byId("skills-query").value="missing";byId("skills-filter").requestSubmit()')
            await expect("disabled", "missing")
            assert await tab.js('byId("skill-items").textContent.includes("No disabled Skills match this search")')
            report["empty_state"] = True

            # A still-running older host must not silently show unfiltered pages
            # under an Enabled/Disabled indicator.
            await tab.js('window.skillsFetch=fetch.bind(window);window.fetch=(input,options)=>String(input).includes("/integrations/skills?")&&String(input).includes("state=")?Promise.resolve(new Response(JSON.stringify({error:{message:"Unknown Skills filter"}}),{status:400})):skillsFetch(input,options);byId("skills-query").value=""')
            await tab.click('[data-skill-state="enabled"]')
            await tab.wait('byId("skills-status").textContent.includes("Restart Web UI")')
            assert await tab.js('byId("skill-items").querySelectorAll(".skill-card").length===0')
            await tab.js('window.fetch=skillsFetch')
            await tab.click('[data-skill-state="all"]')
            await expect("all")
            report["older_host_guidance"] = True
            assert await tab.js('fetch("/api/v1/integrations/skills?state=invalid").then(r=>r.status)') == 400
            await tab.click("#logout")
            await tab.wait('!authenticated && installedSkills.length===0 && skillsState==="all"')
            assert not tab.errors, tab.errors
            report["browser_exceptions"] = tab.errors
            (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({**report, "layouts": len(report["layouts"])}))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    fixture.verify = verify
    fixture.main()

"""Isolated Chrome checks for conversation navigation and responsive ownership.

Presentation rows are fixtures; session mutations use webui_sessions_smoke.py.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from webui_control_smoke import Tab
from webui_settings_smoke import _app

OUT = Path("/tmp/klaude-sidebar-validation")


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
            "--blink-settings=primaryHoverType=2,availableHoverTypes=2,primaryPointerType=4,availablePointerTypes=4",
            f"--user-data-dir={profile}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    OUT.mkdir(exist_ok=True)
    try:
        for _ in range(100):
            if (profile / "DevToolsActivePort").exists():
                break
            await asyncio.sleep(0.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=8_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")

            async def viewport(width):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": 900,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                await asyncio.sleep(0.15)

            async def click(selector):
                point = await tab.js(
                    """(()=>{const e=document.querySelector("""
                    + json.dumps(selector)
                    + """);const r=e.getBoundingClientRect();
                    if(!r.width||!r.height)throw Error('Hidden control');
                    const x=r.x+r.width/2,y=r.y+r.height/2;
                    if(e.matches('button')&&document.elementFromPoint(x,y)?.closest('button')!==e)
                      throw Error(JSON.stringify({id:e.id,visibility:getComputedStyle(e).visibility,
                        hit:document.elementFromPoint(x,y)?.outerHTML.slice(0,180)}));
                    return {x,y};})()"""
                )
                await tab.command(
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mousePressed",
                        "button": "left",
                        "buttons": 1,
                        "clickCount": 1,
                        **point,
                    },
                )
                await tab.command(
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mouseReleased",
                        "button": "left",
                        "buttons": 0,
                        "clickCount": 1,
                        **point,
                    },
                )
                await asyncio.sleep(0.08)

            async def escape():
                await tab.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape"})
                await tab.command("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape"})
                await asyncio.sleep(0.08)

            await viewport(1440)
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js(
                'byId("login-username").value="admin";byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await tab.wait(
                'latest?.session_id && document.documentElement.dataset.startup==="ready"'
            )
            await tab.wait("Boolean(window.BrowserManagement?.sessionRow)")
            await tab.wait("sessionsLoaded && !loadingStates.has(byId('session-list'))")
            await tab.js("""stream?.close();stream=null;clearInterval(pollTimer);connect=()=>{};
              sessionsLoad++;latest={...latest,profile_management:true};
              window.sidebarRows=Array.from({length:28},(_,i)=>({
                session_id:i?'sidebar-fixture-'+i:latest.session_id,
                title:i===0?'Improve Klaude’s compact UI':i===1?'Research notes':
                  i===2?'A long conversation title that should stay on one line':
                  'Conversation '+i,preview:'Local fixture',resumable:true,active:false}));
              window.sidebarFetch=fetch;window.sidebarWrites=[];
              window.fetch=(input,options)=>{
                if(options?.method&&options.method!=='GET')sidebarWrites.push(String(input));
                if(String(input).startsWith('/api/v1/sessions?')){
                  const q=new URL(String(input),location.origin).searchParams.get('query')||'';
                  return Promise.resolve(new Response(JSON.stringify({query:q,
                    sessions:sidebarRows.filter(row=>row.title.toLowerCase().includes(q.toLowerCase()))}),
                    {headers:{'Content-Type':'application/json'}}));
                }return sidebarFetch(input,options);
              };sessions=sidebarRows;sessionsLoaded=true;renderSessionList();
              applyAppearance(appearance={...appearance,palette:'slate',reduced:true},true);""")
            cases = []
            for theme in ("dark", "light"):
                await tab.js(
                    "applyAppearance({...appearance,theme:" + json.dumps(theme) + "},true)"
                )
                for width in (1440, 1000, 768, 390, 320):
                    await viewport(width)
                    await tab.js("showView('chat');toggleSessions(true)")
                    await asyncio.sleep(0.1)
                    await tab.wait("!loadingStates.has(byId('session-list'))")
                    await tab.js("clearTimeout(sessionsSearchTimer);sessionsLoad++;"
                                 "latest.profile_management=true;sessions=sidebarRows;"
                                 "sessionsQuery='';sessionsLoaded=true;renderSessionList()")
                    state = await tab.js("""(()=>{
                      const rail=document.querySelector('.rail').getBoundingClientRect();
                      const panel=byId('session-sidebar').getBoundingClientRect();
                      const title=byId('desktop-page-title');
                      return {width:innerWidth,rail:rail.toJSON(),panel:panel.toJSON(),
                        fits:document.documentElement.scrollWidth<=innerWidth,
                        headerInContent:document.querySelector('.topbar').parentElement.className==='chat-frame',
                        accountInRail:byId('account-shortcut').parentElement.id==='rail-utilities',
                        actionsInRail:byId('sessions-toggle').parentElement.id==='rail-chat-actions'&&
                          byId('new-session-shortcut').parentElement.id==='rail-chat-actions',
                        modelInHeader:byId('model-control').parentElement.classList.contains('topbar'),
                        detailsBesideContext:byId('chat-info-toggle').nextElementSibling===byId('inspector-toggle'),
                        listScrolls:byId('session-list').scrollHeight>byId('session-list').clientHeight,
                        title:title.textContent,expanded:byId('sessions-toggle').getAttribute('aria-expanded'),
                        duplicates:['sessions-toggle','new-session','session-search','account-shortcut','logout']
                          .filter(id=>document.querySelectorAll('#'+id).length!==1),
                        rows:byId('session-list').children.length,
                        listHeight:byId('session-list').clientHeight,
                        scrollHeight:byId('session-list').scrollHeight};})()""")
                    assert state["fits"] and not state["duplicates"], state
                    assert state["expanded"] == "true", state
                    assert state["headerInContent"] is (width > 850), state
                    assert state["accountInRail"] is (width > 850), state
                    assert state["actionsInRail"] is (width > 850), state
                    assert state["modelInHeader"] is (width > 850), state
                    assert state["detailsBesideContext"] is (width > 850), state
                    assert state["listScrolls"], state
                    if width > 850:
                        sizes = await tab.js("""['sessions-toggle','new-session-shortcut',
                          'nav-store','nav-integrations'].map(id=>{
                          const button=byId(id);
                          const face=button.querySelector('.nav-icon,.rail-action-face');
                          return [button,face].flatMap(node=>{
                            const r=node.getBoundingClientRect();return [r.width,r.height];});})""")
                        assert all(size == sizes[0] for size in sizes), sizes
                        await tab.js("document.activeElement.blur()")
                        await tab.command(
                            "Input.dispatchMouseEvent",
                            {
                                "type": "mouseMoved",
                                "x": width - 40,
                                "y": 400,
                            },
                        )
                        assert await tab.js(
                            "getComputedStyle(document.querySelector("
                            "'#sessions-toggle .rail-toggle-logo')).display!=='none'"
                        )
                        toggle = await tab.js("""(()=>{const r=byId('sessions-toggle')
                          .getBoundingClientRect();
                          return {x:r.x+r.width/2,y:r.y+r.height/2};})()""")
                        await tab.command(
                            "Input.dispatchMouseEvent", {"type": "mouseMoved", **toggle}
                        )
                        assert await tab.js(
                            "getComputedStyle(document.querySelector("
                            "'#sessions-toggle .rail-toggle-logo')).display==='none'"
                        )
                        await tab.command(
                            "Input.dispatchMouseEvent",
                            {
                                "type": "mouseMoved",
                                "x": width - 40,
                                "y": 400,
                            },
                        )
                        await tab.wait(
                            "getComputedStyle(document.querySelector("
                            "'#session-list .session-row > button:last-child')).opacity==='0'"
                        )
                        point = await tab.js("""(()=>{const r=document.querySelector(
                          '#session-list .session-row').getBoundingClientRect();
                          return {x:r.left+20,y:r.top+r.height/2};})()""")
                        await tab.command(
                            "Input.dispatchMouseEvent",
                            {
                                "type": "mouseMoved",
                                **point,
                            },
                        )
                        await tab.wait(
                            "getComputedStyle(document.querySelector("
                            "'#session-list .session-row > button:last-child')).opacity==='1'"
                        )
                        await tab.command(
                            "Input.dispatchMouseEvent",
                            {
                                "type": "mouseMoved",
                                "x": width - 40,
                                "y": 400,
                            },
                        )
                        await tab.wait(
                            "getComputedStyle(document.querySelector("
                            "'#session-list .session-row > button:last-child')).opacity==='0'"
                        )
                    if width > 850:
                        assert state["rail"]["width"] == 52 and state["rail"]["top"] == 0, state
                        assert state["panel"]["top"] == 0, state
                        assert state["title"] == "Improve Klaude’s compact UI", state
                    await click("#session-search-toggle")
                    assert await tab.js(
                        "document.activeElement===byId('session-search')"
                        " && !byId('session-search-field').hidden"
                    )
                    bounds = await tab.js("""(()=>{const d=byId('conversation-search');
                      const r=d.getBoundingClientRect();return {open:d.open,left:r.left,
                        right:r.right,bottom:r.bottom,top:r.top};})()""")
                    assert bounds["open"] and bounds["left"] >= 8, bounds
                    assert bounds["right"] <= width - 8 and bounds["bottom"] <= 900, bounds
                    assert await tab.js(
                        "byId('conversation-search-label').textContent==='Recent chats'"
                    )
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (OUT / f"search-{theme}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                    await tab.js(
                        "byId('session-search').value='Research';"
                        "byId('session-search').dispatchEvent(new Event('input'))"
                    )
                    await tab.wait("byId('session-search-list').children.length===1")
                    assert await tab.js(
                        "byId('desktop-page-title').textContent==='Improve Klaude’s compact UI'"
                    )
                    await escape()
                    assert await tab.js(
                        "byId('session-search-field').hidden"
                        " && !byId('session-search').value"
                        " && document.activeElement===byId('session-search-toggle')"
                    )
                    await tab.wait("byId('session-list').children.length===28")
                    await click("#session-options-toggle")
                    assert await tab.js("byId('session-options').matches(':popover-open')")
                    await escape()
                    assert await tab.js(
                        "!byId('session-options').matches(':popover-open')"
                        " && !byId('session-sidebar').inert"
                    )
                    await tab.js("document.activeElement.blur()")
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (OUT / f"expanded-{theme}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                    if width > 850:
                        await click("#sessions-toggle")
                    else:
                        await escape()
                    assert await tab.js(
                        "byId('session-sidebar').inert"
                        " && byId('sessions-toggle').getAttribute('aria-expanded')==='false'"
                    )
                    if width > 850:
                        assert await tab.js(
                            "document.activeElement===byId('sessions-toggle')"
                            " && byId('sessions-toggle').parentElement.id==='rail-chat-actions'"
                        )
                        await tab.js("document.activeElement.blur()")
                        shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (OUT / f"collapsed-{theme}-{width}.png").write_bytes(
                            base64.b64decode(shot["data"])
                        )
                    cases.append({"theme": theme, **state})
            section_cases = []
            for theme in ("dark", "light"):
                await tab.js(
                    "applyAppearance({...appearance,theme:" + json.dumps(theme) + "},true)"
                )
                for width in (1440, 1000, 768, 390, 320):
                    await viewport(width)
                    for view in ("settings", "store"):
                        await tab.js(
                            "setContextPanel(true);showView(" + json.dumps(view) + ");toggleSessions(innerWidth>850)"
                        )
                        assert await tab.js("!byId('inspector').inert && getComputedStyle(byId('inspector')).display==='flex' && getComputedStyle(byId('inspector')).visibility==='visible'")
                        await tab.js("setContextPanel(false)")
                        state = await tab.js("""(()=>{
                          const panel=byId('workspace-sidebar'),r=panel.getBoundingClientRect();
                          const settings=byId('settings-sections'),store=byId('store-sidebar');
                          return {view:currentView,width:innerWidth,hidden:panel.hidden,
                            rect:r.toJSON(),fits:document.documentElement.scrollWidth<=innerWidth,
                            settingsMoved:settings.parentElement===panel,
                            storeMoved:store.parentElement===panel,
                            toggleParent:byId('sessions-toggle').parentElement.className};})()""")
                        assert state["fits"], state
                        assert state["hidden"] is (width <= 850), state
                        assert state["settingsMoved"] is (width > 850 and view == "settings"), state
                        assert state["storeMoved"] is (width > 850 and view == "store"), state
                        if width > 850 and view == "settings":
                            search_sizes = await tab.js("""['session-search-toggle','settings-search-open'].map(id=>{
                              const r=byId(id).getBoundingClientRect();return [r.width,r.height];})""")
                            assert search_sizes == [[36,36],[36,36]], search_sizes
                        if width > 850:
                            assert state["rect"]["top"] == 0 and 216 <= state["rect"]["width"] <= 288
                            await click("#sessions-toggle")
                            assert await tab.js("!byId('workspace-sidebar').hidden && byId('session-sidebar').inert && getComputedStyle(byId('session-sidebar')).display==='none'")
                            assert await tab.js("document.activeElement===byId('sessions-toggle')")
                            await click("#sessions-toggle")
                            assert await tab.js("!byId('workspace-sidebar').hidden && !byId('session-sidebar').inert && getComputedStyle(byId('session-sidebar')).display!=='none'")
                        await tab.js("document.activeElement.blur()")
                        shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (OUT / f"{view}-{theme}-{width}.png").write_bytes(
                            base64.b64decode(shot["data"])
                        )
                        section_cases.append(state)
            # The direct Models destination has older, more specific layout rules.
            for width in (1000, 1440):
                await viewport(width)
                for expanded in (True, False):
                    for context in (True, False):
                        await tab.js("showView('settings', {section:'models'});"
                                     f"toggleSessions({str(expanded).lower()});"
                                     f"setContextPanel({str(context).lower()})")
                        await asyncio.sleep(0.25)
                        geometry = await tab.js("""(()=>{
                          const box=id=>byId(id).getBoundingClientRect();
                          const nav=box('workspace-sidebar'), main=box('main-content');
                          const inspector=byId('inspector');
                          return {nav:nav.toJSON(),main:main.toJSON(),
                            context:getComputedStyle(inspector).display, inspector:inspector.getBoundingClientRect().toJSON(),
                            sessions:getComputedStyle(byId('session-sidebar')).display,
                            toggle:getComputedStyle(byId('sessions-toggle')).visibility,
                            overflow:document.documentElement.scrollWidth>innerWidth};})()""")
                        assert 216 <= geometry['nav']['width'] <= 288 and geometry['main']['left']>=geometry['nav']['right']-1, geometry
                        assert geometry['main']['top'] < 100 and geometry['main']['width'] > 0, geometry
                        assert (geometry['sessions']!='none') is expanded and geometry['toggle']=='visible', geometry
                        assert (geometry['context']!='none') is context, geometry
                        if context and width > 1240:
                            assert geometry['inspector']['width'] <= 600 and geometry['inspector']['left'] >= geometry['main']['right']-1, geometry
                            assert geometry['main']['width'] > 400, geometry
                        assert not geometry['overflow'], geometry
            await tab.js("setContextPanel(false)")
            await tab.js("showView('chat')")
            await viewport(1440)
            await tab.js("showView('chat');toggleSessions(true)")
            assert await tab.js("byId('desktop-page-title').hidden")
            await click("#account-shortcut")
            assert await tab.js("byId('profile-menu').matches(':popover-open')")
            assert await tab.js("byId('logout').parentElement.id==='profile-menu'")
            shot = await tab.command("Page.captureScreenshot", {"format": "png"})
            (OUT / "profile-menu.png").write_bytes(base64.b64decode(shot["data"]))
            await escape()
            assert await tab.js("document.activeElement===byId('account-shortcut')")
            await click("#account-shortcut")
            await click('[data-profile-action="help"]')
            assert await tab.js("byId('command-palette').open")
            await tab.js("byId('command-palette').close()")
            await click("#account-shortcut")
            await click('[data-profile-action="profile"]')
            assert await tab.js("currentView==='settings' && settingsSection==='account'")
            await tab.js("showView('chat');toggleSessions(true)")
            await tab.js(
                "latest.profile_management=true;sessions=sidebarRows;"
                "sessionsLoaded=true;renderSessionList()"
            )
            await click("#session-list .session-row > button:last-child")
            assert await tab.js("byId('session-actions-menu').matches(':popover-open')")
            shot = await tab.command("Page.captureScreenshot", {"format": "png"})
            (OUT / "session-menu.png").write_bytes(base64.b64decode(shot["data"]))
            await click("#session-actions-menu > button:first-child")
            assert await tab.js("byId('session-management').open")
            await click("#session-management-close")
            assert await tab.js("sidebarWrites.length===0"), await tab.js("sidebarWrites")
            await tab.command("Page.navigate", {"url": host.origin + "/?view=settings&settings=models"})
            await tab.wait("document.documentElement?.dataset.startup==='ready' && typeof currentView!=='undefined' && currentView==='settings' && settingsSection==='models'")
            assert await tab.js("!byId('models-settings').hidden && !byId('workspace-sidebar').hidden && byId('main-content').getBoundingClientRect().width>0")
            assert not tab.errors, tab.errors
            (OUT / "report.json").write_text(json.dumps(cases + section_cases, indent=2))
            return {
                "layouts": len(cases),
                "section_sidebar_layouts": len(section_cases),
                "search_escape_menu_collapse_focus": True,
                "responsive_control_ownership": True,
                "console_errors": 0,
                "screenshots": str(OUT),
            }
    finally:
        process.terminate()
        process.wait(timeout=10)


def main():
    with tempfile.TemporaryDirectory(prefix="klaude-sidebar-") as folder:
        root = Path(folder)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace, app.agent.tool_config = root, Workspace(root), cfg
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts)
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            print(json.dumps(asyncio.run(asyncio.wait_for(verify(host, root), 120))))
        finally:
            host.stop()
            serving.join(3)
            app.memory.db.close()


if __name__ == "__main__":
    main()

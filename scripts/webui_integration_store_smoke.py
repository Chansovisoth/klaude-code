"""Store MCP/Skills discovery, responsive layout and reviewed add with isolated catalogs."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

import websockets
from klaude_application.integration_store import IntegrationStore
from webui_control_smoke import Tab
from webui_model_store_smoke import Native
from webui_model_store_smoke import main as fixture_main

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_integration_store import transport  # noqa: E402


class CatalogModels(Native):
    def do_GET(self):
        if self.path.startswith("/api/models?") and parse_qs(urlsplit(self.path).query).get(
            "sort"
        ) == ["lastModified"]:
            self.reply(
                [
                    {
                        "id": "fixture/Recently-Updated",
                        "downloads": 24,
                        "lastModified": "2026-10-28T00:00:00Z",
                    }
                ]
            )
        else:
            super().do_GET()


async def verify_store_navigation(tab, wait):
    canonical = (
        "currentView==='store' && !byId('store-view').hidden && "
        "new URLSearchParams(location.search).get('view')==='store'"
    )
    await wait(canonical + " && byId('store-tab-downloads').getAttribute('aria-pressed')==='true'")
    assert await tab.js(
        "byId('nav-store').getAttribute('aria-current')==='page' && "
        "byId('store-home').textContent==='Store' && "
        "new URL(byId('store-home').href).searchParams.get('view')==='store'"
    )
    await tab.click('#nav-chat')
    await wait("currentView==='chat'")
    await tab.command('Page.navigateToHistoryEntry', {
        'entryId': (await tab.command('Page.getNavigationHistory'))['entries'][-2]['id'],
    })
    await wait(canonical)
    await tab.js('history.forward()')
    await wait("currentView==='chat'")
    await tab.click('#command-open')
    await tab.js(
        "byId('command-query').value='Open Store';"
        "byId('command-query').dispatchEvent(new Event('input'))"
    )
    await tab.command('Input.dispatchKeyEvent', {'type':'keyDown','key':'Enter','code':'Enter'})
    await wait(canonical + " && !byId('command-palette').open")
    # Old saved page preferences migrate without touching Settings > Models.
    await tab.js(
        "sessionStorage.setItem('klaude.webui.navigation.v1.page','models');"
        "history.replaceState(history.state,'',location.pathname)"
    )
    origin = await tab.js('performance.timeOrigin')
    await tab.command('Page.reload')
    await wait(
        f"performance.timeOrigin!=={origin} && typeof latest!=='undefined' && authenticated && "
        "document.documentElement.dataset.startup==='ready' && currentView==='store'"
    )
    assert await tab.js(
        "sessionStorage.getItem('klaude.webui.navigation.v1.page')==='store'"
    )
    # A legacy detail/filter URL is rewritten in place, preserving all its state.
    await tab.js(
        "history.pushState({routeWitness:42},'',"
        "'?view=models&models-section=downloads&models-runtime=all#kept');"
        "dispatchEvent(new PopStateEvent('popstate'))"
    )
    await wait(canonical)
    assert await tab.js(
        "history.state.routeWitness===42 && location.hash==='#kept' && "
        "new URLSearchParams(location.search).get('models-runtime')==='all' && "
        "new URLSearchParams(location.search).get('models-section')==='downloads'"
    )
    await tab.js("showView('settings',{section:'models'})")
    await wait("currentView==='settings' && settingsSection==='models'")
    assert await tab.js("new URLSearchParams(location.search).get('settings')==='models'")
    await tab.command('Emulation.setDeviceMetricsOverride', {
        'width':390,'height':844,'deviceScaleFactor':1,'mobile':True,
    })
    await tab.click('#nav-chat')
    await tab.click('#nav-more')
    await tab.click('#navigation-more [data-app-view=store]')
    await wait(canonical + " && !navigationMore.matches(':popover-open')")
    assert await tab.js("byId('nav-more').getAttribute('aria-label')==='More navigation · Store'")
    await tab.click('#nav-chat')
    await tab.js('MobileChatUI.openModels()')
    await tab.click('#mobile-model-store')
    await wait(canonical)
    await tab.click('#nav-chat')
    await tab.js("byId('chat-availability-action').click()")
    await wait(canonical + " && byId('store-tab-downloads').getAttribute('aria-pressed')==='true'")
    await tab.click('#store-home')
    await wait(canonical + " && byId('store-tab-discover').getAttribute('aria-pressed')==='true'")


async def verify_preview_rows(tab, wait, captures):
    await tab.js("""(()=>{
      window.previewRowRequest=domainRequest;window.previewRowReads=[];
      domainRequest=async(path,...args)=>{
        if(!path.startsWith('/api/v1/store/integrations?'))return previewRowRequest(path,...args);
        const p=new URL(path,location.origin).searchParams,kind=p.get('kind');
        const page=Number(p.get('page')||1),total=kind==='mcps'?30:40;
        const offset=(page-1)*20,count=Math.max(0,Math.min(20,total-offset));
        previewRowReads.push([kind,page]);
        return {items:Array.from({length:count},(_,i)=>({id:kind+'-'+(offset+i),kind,
          name:kind+' fixture '+(offset+i),description:'A useful integration for a project.',
          publisher:'example/repository'})),more:offset+count<total};
      };
      IntegrationStoreUI.refresh();
    })()""")
    for width in (320, 390, 768, 1024, 1440, 1920, 2560, 1440, 320):
        await tab.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": 1000, "deviceScaleFactor": 1, "mobile": width < 600},
        )
        await asyncio.sleep(0.25)
        await wait("""(()=>{
          const section=byId('store-integrations'),style=getComputedStyle(section);
          const minimum=parseFloat(style.getPropertyValue('--store-grid-min'));
          const gap=parseFloat(style.getPropertyValue('--store-grid-gap'));
          const columns=Math.max(1,Math.floor(
            (section.getBoundingClientRect().width+gap)/(minimum+gap)));
          return ['mcps','skills'].every(kind=>{
            const grid=byId('store-integration-'+kind).querySelector('.store-integration-grid');
            if(!grid)return false;
            const cap=Math.min(columns*4,kind==='mcps'?30:40);
            const expected=cap>=columns?Math.floor(cap/columns)*columns:cap;
            return grid.children.length===expected;
          });
        })()""")
        metrics = await tab.js("""(()=>{
          const section=byId('store-integrations'),style=getComputedStyle(section);
          const minimum=parseFloat(style.getPropertyValue('--store-grid-min'));
          const gap=parseFloat(style.getPropertyValue('--store-grid-gap'));
          const columns=Math.max(1,Math.floor(
            (section.getBoundingClientRect().width+gap)/(minimum+gap)));
          return {columns,rows:['mcps','skills'].map(kind=>{
            const grid=byId('store-integration-'+kind).querySelector('.store-integration-grid');
            const positions=new Set([...grid.children]
              .map(n=>Math.round(n.getBoundingClientRect().top)));
            return {count:grid.children.length,rows:positions.size,
              cssColumns:getComputedStyle(grid).gridTemplateColumns.split(' ').length,
              cssGap:parseFloat(getComputedStyle(grid).gap)};
          }),fits:document.documentElement.scrollWidth<=innerWidth};
        })()""")
        assert metrics["fits"] and all(
            row["rows"] <= 4 and row["cssColumns"] == metrics["columns"] and row["cssGap"] == 8
            for row in metrics["rows"]
        ), metrics
        print("preview_rows", width, metrics, flush=True)
        if width in (390, 1440, 2560):
            await tab.js("byId('store-integration-mcps').scrollIntoView({block:'start'})")
            shot = await tab.command("Page.captureScreenshot", {"format": "png"})
            (captures / f"four-rows-{width}.png").write_bytes(base64.b64decode(shot["data"]))
    reads = await tab.js("previewRowReads")
    assert sum(kind == "skills" and page == 2 for kind, page in reads) == 1, reads
    assert sum(kind == "mcps" and page == 2 for kind, page in reads) <= 1, reads
    await tab.js(
        "domainRequest=window.previewRowRequest;delete window.previewRowRequest;"
        "IntegrationStoreUI.refresh()"
    )
    await wait(
        "byId('store-integration-mcps')"
        ".querySelectorAll('[data-integration-item]').length===2 && "
        "byId('store-integration-skills')"
        ".querySelectorAll('[data-integration-item]').length===1"
    )


async def verify_browse_pages(tab, wait, state):
    for kind in ("skills", "mcps"):
        await tab.click(f'[aria-label="See all {"Skills" if kind == "skills" else "MCPs"}"]')
        await wait("byId('integration-store-query')")
        await tab.js(
            "byId('integration-store-query').value='many';"
            "byId('integration-store-query').dispatchEvent(new Event('input'));"
            "byId('integration-store-query').form.requestSubmit()"
        )
        try:
            await wait(
                "byId('integration-store-page').querySelectorAll('[data-integration-item]').length===40"
            )
        except AssertionError:
            print("BROWSE", kind, await tab.js(
                "({url:location.search,text:byId('integration-store-page').textContent,"
                "count:byId('integration-store-page').querySelectorAll('[data-integration-item]').length})"
            ), [str(r.url) for r in state['calls']], flush=True)
            raise
        if kind == "skills":
            first = await tab.js(
                "[...byId('integration-store-page').querySelectorAll('[data-integration-item]')]"
                ".map(n=>n.dataset.integrationItem)"
            )
            await tab.js(
                "[...byId('integration-store-page').querySelectorAll('nav button')]"
                ".find(n=>n.textContent==='Next').click()"
            )
            await wait(
                "byId('integration-store-page').querySelectorAll('[data-integration-item]').length===20"
                " && byId('integration-store-page').textContent.includes('Page 2')"
            )
            second = await tab.js(
                "[...byId('integration-store-page').querySelectorAll('[data-integration-item]')]"
                ".map(n=>n.dataset.integrationItem)"
            )
            assert not set(first) & set(second)
            origin = await tab.js("performance.timeOrigin")
            await tab.command("Page.reload")
            await wait(
                f"performance.timeOrigin!=={origin} && typeof byId==='function' && "
                "typeof latest!=='undefined' && authenticated && "
                "document.documentElement.dataset.startup==='ready' && "
                "byId('integration-store-page')"
                "?.querySelectorAll('[data-integration-item]').length===20"
                " && byId('integration-store-page').textContent.includes('Page 2')"
            )
            await tab.js(
                "[...byId('integration-store-page').querySelectorAll('nav button')]"
                ".find(n=>n.textContent==='Previous').click()"
            )
            await wait(
                "byId('integration-store-page').querySelectorAll('[data-integration-item]').length===40"
            )
            reads = [int(r.url.params['page']) for r in state['calls']
                     if r.url.host == 'skillsmp.com' and r.url.params.get('q') == 'many']
            assert reads == [1, 2, 3], reads
        await tab.js("byId('integration-store-page').querySelector('.model-detail-back').click()")
        await wait("!byId('store-view').classList.contains('has-integration-store')")


async def verify_order_chips(tab, wait, captures):
    async def choose(value):
        await tab.click('#integration-store-sort-chip')
        await wait("byId('integration-store-sort-menu').matches(':popover-open')")
        await tab.click(f'#integration-store-sort-menu [data-value="{value}"]')

    for kind, popular, recent in (
        ('Skills', 'Popular older skill', 'Recent skill'),
        ('MCPs', 'Popular tools', 'Recent tools'),
    ):
        await tab.click(f'[aria-label="See all {kind}"]')
        await wait("byId('integration-store-query')")
        await tab.js(
            "byId('integration-store-query').value='ordering';"
            "byId('integration-store-query').dispatchEvent(new Event('input'));"
            "byId('integration-store-query').form.requestSubmit()"
        )
        await wait(
            "byId('integration-store-page').querySelector('.store-integration-card strong')"
            "?.textContent===" + json.dumps(popular)
        )
        assert await tab.js(
            "byId('integration-store-sort-chip').getAttribute('aria-label')==='Order: Stars'"
        )
        await choose('recent')
        await wait(
            "byId('integration-store-page').querySelector('.store-integration-card strong')"
            "?.textContent===" + json.dumps(recent)
        )
        assert await tab.js(
            "new URLSearchParams(location.search).get('store-integration-sort')==='recent'"
        )
        origin = await tab.js('performance.timeOrigin')
        await tab.command('Page.reload')
        await wait(
            f"performance.timeOrigin!=={origin} && typeof byId==='function' && "
            "typeof latest!=='undefined' && authenticated && "
            "document.documentElement.dataset.startup==='ready' && "
            "byId('integration-store-sort')?.value==='recent' && "
            "byId('integration-store-page').querySelector('.store-integration-card strong')"
            "?.textContent===" + json.dumps(recent)
        )
        for width in (320, 390, 1440):
            await tab.command('Emulation.setDeviceMetricsOverride', {
                'width': width, 'height': 900, 'deviceScaleFactor': 1, 'mobile': width < 600,
            })
            await asyncio.sleep(0.1)
            assert await tab.js("""(()=>{
              const row=document.querySelector('.integration-store-filters');
              const search=byId('integration-store-query').getBoundingClientRect();
              const refresh=document.querySelector('.integration-store-toolbar button')
                .getBoundingClientRect();
              return document.documentElement.scrollWidth<=innerWidth &&
                search.height===48 && refresh.height===48 &&
                Math.abs(search.top-refresh.top)<1 && Math.abs(refresh.left-search.right-4)<1 &&
                [...row.querySelectorAll('button')].filter(n=>n.offsetWidth).every(n=>{
                  const r=n.getBoundingClientRect();
                  return r.height>=44 && r.left>=0 && r.right<=innerWidth;
                }) && document.querySelectorAll('#integration-store-sort-menu').length===1;
            })()""")
            shot = await tab.command('Page.captureScreenshot', {'format':'png'})
            (captures / f'order-{kind}-{width}.png').write_bytes(base64.b64decode(shot['data']))
        # The shared filter menu retains keyboard opening and Escape focus return.
        await tab.js("byId('integration-store-sort-chip').focus()")
        await tab.command('Input.dispatchKeyEvent', {
            'type':'keyDown', 'key':'ArrowDown', 'code':'ArrowDown',
        })
        await wait("byId('integration-store-sort-menu').matches(':popover-open')")
        await tab.command('Input.dispatchKeyEvent', {
            'type':'keyDown','key':'Escape','code':'Escape',
        })
        await wait("document.activeElement===byId('integration-store-sort-chip')")
        await choose('stars')
        await wait(
            "byId('integration-store-page').querySelector('.store-integration-card strong')"
            "?.textContent===" + json.dumps(popular)
        )
        if kind == 'Skills':
            await tab.click('#integration-store-provider-chip')
            await tab.click('#integration-store-provider-menu [data-value="skills.sh"]')
            await wait("byId('integration-store-page').textContent.includes('repo-only')")
            await tab.click('#integration-store-sort-chip')
            assert await tab.js(
                "byId('integration-store-sort-menu').querySelector('[data-value=recent]').disabled"
            )
            await tab.command('Input.dispatchKeyEvent', {
                'type':'keyDown','key':'Escape','code':'Escape',
            })
            await tab.click('#integration-store-provider-chip')
            await tab.click('#integration-store-provider-menu [data-value="skillsmp"]')
            await wait(
                "byId('integration-store-page').querySelector('.store-integration-card strong')"
                "?.textContent===" + json.dumps(popular)
            )
        else:
            await tab.js("""(()=>{
              window.orderRequest=domainRequest;window.legacyOrderReads=[];
              domainRequest=(path,...args)=>{
                if(path.startsWith('/api/v1/store/integrations?'))legacyOrderReads.push(path);
                return orderRequest(path,...args);
              };
              latest.integration_store_sort=false;dispatchEvent(new PopStateEvent('popstate'));
            })()""")
            await wait("byId('integration-store-sort')?.disabled")
            await tab.js(
                "for(let i=0;i<3;i++)document.dispatchEvent("
                "new CustomEvent('klaude-snapshot',{detail:latest}))"
            )
            assert await tab.js(
                "legacyOrderReads.length===1 && legacyOrderReads.every(path=>"
                "!new URL(path,location.origin).searchParams.has('sort'))"
            )
            await tab.js(
                "domainRequest=window.orderRequest;delete window.orderRequest;"
                "latest.integration_store_sort=true;dispatchEvent(new PopStateEvent('popstate'))"
            )
            await wait("!byId('integration-store-sort').disabled")
        await tab.js("byId('integration-store-page').querySelector('.model-detail-back').click()")
        await wait("!byId('store-view').classList.contains('has-integration-store')")


async def verify(host, root):
    state = {}
    host.library.integration_store = IntegrationStore(host.library.cfg, transport=transport(state))
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(
        next(
            (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
                "*/chrome-headless-shell-linux64/chrome-headless-shell"
            )
        )
    )
    profile = root / "integration-chrome"
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
    captures = Path("/tmp/klaude-integration-store-evidence")
    captures.mkdir(exist_ok=True)
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

            async def wait(expression):
                for attempt in range(10):
                    try:
                        await tab.wait("Boolean(" + expression + ")")
                        return
                    except AssertionError as error:
                        if "Inspected target navigated or closed" not in str(error) or attempt == 9:
                            raise
                        await asyncio.sleep(0.05)

            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            legacy = urlsplit(host.bootstrap_url)._replace(
                query='view=models&models-section=downloads'
            ).geturl()
            await tab.command("Page.navigate", {"url": legacy})
            await wait("document.documentElement?.dataset.access==='locked'")
            await tab.js(
                "byId('login-username').value='admin';byId('login-password').value="
                + json.dumps(host.accounts.initial_password())
                + ";byId('account-login').requestSubmit()"
            )
            await wait(
                "typeof latest!=='undefined' && authenticated && "
                "document.documentElement.dataset.startup==='ready'"
            )
            await verify_store_navigation(tab, wait)
            await wait("byId('store-integrations')")
            await tab.js("byId('store-integrations').scrollIntoView({block:'start'})")
            await wait(
                "byId('store-integration-mcps')"
                ".querySelectorAll('[data-integration-item]').length===2 && "
                "byId('store-integration-skills').querySelectorAll('[data-integration-item]').length===1"
            )
            await wait(
                "[...byId('store-content').querySelectorAll('h2')]"
                ".some(n=>n.textContent==='Recently updated')"
            )
            assert await tab.js("""(()=>{
                const recent=[...byId('store-content').querySelectorAll('h2')]
                  .find(n=>n.textContent==='Recently updated');
                const integrations=byId('store-integrations');
                return recent && Boolean(recent.compareDocumentPosition(integrations) &
                  Node.DOCUMENT_POSITION_FOLLOWING);
            })()""")
            assert all("/git/" not in request.url.path for request in state["calls"])
            await verify_preview_rows(tab, wait, captures)
            for kind, count in (("mcps", "12,500"), ("skills", "777")):
                await tab.js(f"byId('store-integration-{kind}').scrollIntoView({{block:'start'}})")
                await wait(
                    f"[...byId('store-integration-{kind}').querySelectorAll('[data-integration-stars]')]"
                    ".some(n=>!n.hidden && n.getAttribute('aria-label')"
                    f".includes('{count} GitHub stars'))"
                )
            assert len([r for r in state["calls"] if r.url.host == "api.github.com"]) == 2
            for width, height in ((320, 568), (390, 844), (768, 1024), (1440, 900)):
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": width < 600,
                    },
                )
                for theme in ("light", "dark"):
                    await tab.js(
                        "applyAppearance({...appearance,reduced:true,theme:"
                        + json.dumps(theme)
                        + "});"
                        "byId('store-integrations').scrollIntoView({block:'start'})"
                    )
                    await asyncio.sleep(0.25)
                    await tab.js("byId('store-integrations').scrollIntoView({block:'start'});")
                    await asyncio.sleep(0.1)
                    geometry = await tab.js("""(()=>{
                        const grid=byId('store-integration-mcps')
                          .querySelector('.store-integration-grid');
                        const cards=[...grid.children],r=grid.getBoundingClientRect();
                        return {page:document.documentElement.scrollWidth<=innerWidth,
                          view:byId('store-view').scrollWidth<=byId('store-view').clientWidth,
                          cards:cards.every(n=>{const b=n.getBoundingClientRect();
                            return b.left>=r.left-1&&b.right<=r.right+1
                              &&[...n.children].every(c=>{
                                const cr=c.getBoundingClientRect();return cr.left>=b.left-1
                                  &&cr.right<=b.right+1;});}),
                          actions:[...byId('store-integrations')
                            .querySelectorAll('.store-section-heading button')]
                            .every(n=>n.offsetHeight>=44)};
                    })()""")
                    if not all(geometry.values()):
                        shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                        (captures / "layout-failure.png").write_bytes(
                            base64.b64decode(shot["data"])
                        )
                        print(
                            "GEOMETRY",
                            await tab.js("""(()=>{
                          const grid=byId('store-integration-mcps')
                            .querySelector('.store-integration-grid');
                          return {grid:grid.getBoundingClientRect().toJSON(),
                            cards:[...grid.children].map(n=>({r:n.getBoundingClientRect().toJSON(),
                              scroll:n.scrollWidth,client:n.clientWidth,css:getComputedStyle(n).width}))};
                        })()"""),
                            flush=True,
                        )
                    assert all(geometry.values()), (width, theme, geometry)
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (captures / f"integrations-{width}-{theme}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
            await verify_browse_pages(tab, wait, state)
            await verify_order_chips(tab, wait, captures)
            # Preview opens an actual detail, then reviewed add-disabled uses the existing owner.
            await tab.js("byId('store-integrations').scrollIntoView({block:'start'})")
            await wait("byId('store-integration-mcps').querySelector('[data-integration-item]')")
            await tab.click("#store-integration-mcps [data-integration-item]")
            await wait("byId('integration-store-install')")
            assert await tab.js("byId('integration-store-page').textContent.includes('disabled')")
            await wait(
                "[...byId('integration-store-page').querySelectorAll('[data-integration-stars]')]"
                ".some(n=>!n.hidden && n.getAttribute('aria-label')"
                ".includes('12,500 GitHub stars'))"
            )
            await tab.js("byId('integration-store-name').value='store-search'")
            await tab.click("#integration-store-install")
            await wait("reviewDialog.open")
            assert await tab.js("managementReview.operation==='mcp-add'")
            await tab.click("#domain-review-confirm")
            await wait(
                "byId('integration-store-feedback').textContent.includes('Server added disabled')"
            )
            from klaude_core.mcp_client import MCPRegistry

            assert not MCPRegistry(host.library.cfg.mcp_servers_file).load()["store-search"].enabled
            await tab.js(
                "byId('integration-store-page').querySelector('.model-detail-back').click()"
            )
            await wait("byId('integration-store-query')")
            await tab.js(
                "byId('integration-store-page').querySelector('.model-detail-back').click()"
            )
            await wait("!byId('store-view').classList.contains('has-integration-store')")
            await tab.click("#store-integration-skills [data-integration-item]")
            await wait("byId('integration-store-page').textContent.includes('Verify source')")
            await tab.js(
                "[...byId('integration-store-page').querySelectorAll('button')]"
                ".find(n=>n.textContent==='Verify source').click()"
            )
            await wait("byId('integration-store-install')")
            assert await tab.js(
                "byId('integration-store-page').textContent.includes(" + json.dumps("a" * 40) + ")"
            )
            await tab.click("#integration-store-install")
            await wait("reviewDialog.open")
            assert await tab.js(
                "managementReview.operation==='skill-store-install' && "
                "byId('domain-review-summary').textContent.includes('embedding')"
            )
            await tab.click("#domain-review-cancel")
            await wait("!reviewDialog.open")
            # Reload restores the detail and verified source without fetching a package.
            origin = await tab.js("performance.timeOrigin")
            await tab.command("Page.reload")
            await wait(
                f"performance.timeOrigin!=={origin} && "
                "typeof latest!=='undefined' && authenticated && "
                "document.documentElement.dataset.startup==='ready' && "
                "byId('integration-store-install')"
            )
            assert all("/git/blobs/" not in request.url.path for request in state["calls"])
            assert not list(host.library.cfg.skills_dir.iterdir())
            await tab.command(
                "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape"}
            )
            await wait("byId('integration-store-query')")
            # Empty/errors keep search and source selection usable.
            state["offline"] = True
            await tab.js(
                "byId('integration-store-query').value='unique-offline';"
                "byId('integration-store-query').dispatchEvent(new Event('input'))"
            )
            await wait("byId('integration-store-page').textContent.includes('Catalog unavailable')")
            assert await tab.js("byId('integration-store-query').value==='unique-offline'")
            state["offline"] = False
            await tab.js(
                "[...byId('integration-store-page').querySelectorAll('button')].find(n=>n.textContent==='Retry').click()"
            )
            await wait("byId('integration-store-page').querySelector('[data-integration-item]')")
            await tab.js(
                "byId('integration-store-provider').value='skills.sh';"
                "byId('integration-store-provider').dispatchEvent(new Event('change'))"
            )
            await wait("byId('integration-store-page').textContent.includes('repo-only')")
            await tab.click("#integration-store-page [data-integration-item]")
            await wait("byId('integration-store-source-url')")
            assert not await tab.js("byId('integration-store-install')!==null")
            await tab.js(
                "byId('integration-store-source-url').value='https://github.com/example/repo/blob/main/skills/testing/SKILL.md';"
                "[...byId('integration-store-page').querySelectorAll('button')]"
                ".find(n=>n.textContent==='Verify source').click()"
            )
            await wait("byId('integration-store-install')")
            # Keyboard Tab reaches the primary action; source verification is complete.
            await tab.js("byId('integration-store-name').focus()")
            await tab.command(
                "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Tab", "code": "Tab"}
            )
            assert await tab.js("document.activeElement.id==='integration-store-install'")
            # An older host gets useful management links without catalog requests.
            await tab.js(
                "byId('integration-store-page').querySelector('.model-detail-back').click()"
            )
            await wait("byId('integration-store-query')")
            await tab.js(
                "byId('integration-store-page').querySelector('.model-detail-back').click()"
            )
            await wait("!byId('store-view').classList.contains('has-integration-store')")
            before_legacy = len(state["calls"])
            await tab.js("latest.integration_store=false;ModelStoreUI.render()")
            assert await tab.js(
                "byId('store-integrations').textContent.includes('Restart') && "
                "Boolean(byId('store-integrations')"
                ".querySelector('[aria-label=\"Manage Skills\"]'))"
            )
            await asyncio.sleep(0.25)
            assert len(state["calls"]) == before_legacy
            # Recovery survives a lost worker acknowledgement and a page reload.
            from klaude_application.skill_store_operations import initial
            from klaude_core.skill_catalog import SkillRecord

            rid = uuid.uuid4().hex
            journal = host.library.journal
            record = SkillRecord(
                "skillsmp", "recovery", "recovery-fixture", repository="example/repo",
                source_url="https://github.com/example/repo/tree/main/skills/testing",
                skill_path="skills/testing/SKILL.md", revision="a" * 40,
            )
            receipt = journal.admit(
                request_id=rid, owner_id="web-admin", kind="skill-store-install",
                resource="skill:recovery-fixture", payload=record.payload(),
            )
            journal.save_evidence(rid, "web-admin", receipt.fence, initial(record.payload()))
            journal.start(rid, "web-admin", receipt.fence)
            journal.mark_unknown(rid, "web-admin", receipt.fence)
            await tab.js("showView('activity');loadOperations()")
            await wait("[...byId('domain-operations').querySelectorAll('button')]"
                       ".some(n=>n.textContent==='Inspect recovery')")
            await tab.js("[...byId('domain-operations').querySelectorAll('button')]"
                         ".find(n=>n.textContent==='Inspect recovery').click()")
            await wait("byId('domain-operations').textContent.includes('No installation effect')")
            await tab.js("[...byId('domain-operations').querySelectorAll('button')]"
                         ".find(n=>n.textContent==='Close failed attempt').click()")
            await wait("!byId('domain-operations').textContent.includes('Inspect recovery')")
            assert journal.status(rid, "web-admin").state == "failed"
            origin = await tab.js("performance.timeOrigin")
            await tab.command("Page.reload")
            await wait(f"performance.timeOrigin!=={origin} && typeof authenticated!=='undefined' "
                       "&& authenticated && document.documentElement.dataset.startup==='ready'")
            await tab.js("showView('activity');loadOperations()")
            await wait("byId('domain-operations').textContent.includes(" + json.dumps(rid) + ")")
            assert not await tab.js(
                "byId('domain-operations').textContent.includes('Inspect recovery')"
            )
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "widths": [320, 390, 768, 1440],
                        "themes": ["light", "dark"],
                        "catalogs": True,
                        "github_stars": True,
                        "forty_item_pages": True,
                        "order_chips": True,
                        "store_url_migration": True,
                        "reviewed_mcp_add": True,
                        "pinned_skill_review": True,
                        "detail_reload": True,
                        "error_retry": True,
                        "skill_recovery": True,
                        "console_errors": 0,
                        "screenshots": str(captures),
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    import webui_model_store_smoke as fixture

    fixture.Native = CatalogModels
    fixture_main(verify, admin_lan=True)

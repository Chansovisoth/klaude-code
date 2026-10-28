"""Full model-settings walkthrough with isolated HTTP, journal and service fixtures."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from webui_control_smoke import Tab
from webui_model_store_smoke import Native
from webui_model_store_smoke import main as fixture_main


async def verify(host, root):
    Native.models = [
        {
            "name": "fixture:latest",
            "digest": "a" * 64,
            "size": 1000,
            "details": {"parameter_size": "1B"},
        }
    ]
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
    output = Path("/tmp/klaude-model-settings-evidence")
    output.mkdir(exist_ok=True)
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
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            if os.environ.get('KLAUDE_SETTINGS_SEARCH_ONLY'):
                await tab.command('Emulation.setDeviceMetricsOverride', {
                    'width': 1440, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False,
                })
            await tab.command("Page.navigate", {"url": host.bootstrap_url})
            if host.accounts:
                await tab.wait("document.documentElement?.dataset.access === 'locked'")
                await tab.js(
                    "byId('login-username').value='admin'; byId('login-password').value="
                    + json.dumps(host.accounts.initial_password())
                    + "; byId('account-login').requestSubmit()"
                )
            await tab.wait(
                "typeof latest !== 'undefined' && authenticated && latest && docu"
                "ment.documentElement.dataset.startup==='ready'"
            )
            await tab.js("showView('settings', {section:'models'})")
            await tab.click('#settings-search-open')
            await tab.wait("byId('settings-search-dialog').open && "
                           "!byId('settings-search-status').textContent.includes('Loading')")
            assert await tab.js("byId('settings-search-status').textContent==='' && "
                                "getComputedStyle(byId('settings-search-status')).display==='none'")
            coverage = await tab.js("""(async()=>{
              const data=await domainRequest('/api/v1/settings/agent');
              const missing=[];
              for(const field of data.fields) {
                byId('settings-search-query').value=field.id.replaceAll(/[._]/g,' ');
                byId('settings-search-query').dispatchEvent(new Event('input'));
                if (![...byId('settings-search-results').querySelectorAll('button')]
                  .some(button=>button.dataset.settingId===field.id)) missing.push(field.id);
              }
              return {total:data.fields.length,missing};
            })()""")
            assert coverage["total"] > 20 and not coverage["missing"], coverage
            async def search_setting(term):
                await tab.js("byId('settings-search-query').value=" + json.dumps(term) +
                             ";byId('settings-search-query').dispatchEvent(new Event('input'))")
                await tab.wait("Boolean(byId('settings-search-results').querySelector('button'))")

            async def search_key(key, code):
                await tab.command('Input.dispatchKeyEvent', {
                    'type': 'keyDown', 'key': key, 'code': key, 'windowsVirtualKeyCode': code,
                    **({'text': '\r'} if key == 'Enter' else {}),
                })
                await tab.command('Input.dispatchKeyEvent', {
                    'type': 'keyUp', 'key': key, 'code': key, 'windowsVirtualKeyCode': code,
                })

            await search_setting('theme')
            await tab.js("byId('settings-search-query').focus()")
            for key, code, expected in (('ArrowDown', 40, 0), ('ArrowDown', 40, 1),
                                        ('ArrowUp', 38, 0), ('ArrowUp', 38, -1)):
                await search_key(key, code)
                assert await tab.js("""(()=>{
                  const input=byId('settings-search-query');
                  const options=[...byId('settings-search-results').querySelectorAll('button')];
                  const selected=options.at(""" + str(expected) + """);
                  const box=byId('settings-search-results').getBoundingClientRect();
                  const item=selected.getBoundingClientRect();
                  return document.activeElement===input &&
                    input.getAttribute('aria-activedescendant')===selected.id &&
                    input.getAttribute('aria-expanded')==='true' &&
                    options.filter(option=>option.getAttribute('aria-selected')==='true')
                      .length===1 && selected.getAttribute('aria-selected')==='true' &&
                    item.top>=box.top-1 && item.bottom<=box.bottom+1;
                })()""")
            await search_key('Tab', 9)
            assert await tab.js("document.activeElement===byId('settings-search-results')"
                                ".querySelector('button')")
            await search_key('ArrowDown', 40)
            assert await tab.js("document.activeElement===byId('settings-search-results')"
                                ".querySelectorAll('button')[1]")
            await tab.js("byId('settings-search-query').focus()")
            await search_setting('reduced motion')
            assert await tab.js("!byId('settings-search-query')"
                                ".hasAttribute('aria-activedescendant')")
            await search_key('ArrowDown', 40)
            await search_key('Enter', 13)
            await tab.wait("!byId('settings-search-dialog').open && settingsSection==='theme' && "
                           "document.activeElement===byId('reduced-motion')")
            await tab.click('#settings-search-open')
            await search_setting('research context')
            await tab.click('#settings-search-results button')
            await tab.wait("settingsSection==='agent' && byId('agent-group-research').open && "
                           "document.activeElement===byId('setting-research-context_tokens')")
            await tab.click('#settings-search-open')
            await search_setting('image generation provider')
            await tab.click('#settings-search-results button')
            await tab.wait("settingsSection==='models' && !byId('image-service-settings').hidden "
                           "&& document.activeElement===byId('image-service-provider')")
            await tab.click('#settings-search-open')
            await search_setting('reduced motion')
            await tab.click('#settings-search-results button')
            await tab.wait("settingsSection==='theme' && "
                           "document.activeElement===byId('reduced-motion')")
            await tab.click('#settings-search-open')
            await tab.js("byId('settings-search-query').value='unmatched fixture search'; "
                         "byId('settings-search-query').dispatchEvent(new Event('input'))")
            assert await tab.js("byId('settings-search-status').textContent.includes('0 results')")
            await tab.js("byId('settings-search-query').focus()")
            await search_key('ArrowDown', 40)
            await search_key('ArrowUp', 38)
            await search_key('Enter', 13)
            assert await tab.js("byId('settings-search-dialog').open && "
                                "byId('settings-search-query').getAttribute('aria-expanded')==='false'"
                                " && !byId('settings-search-query')"
                                ".hasAttribute('aria-activedescendant')")
            await search_key('Escape', 27)
            await tab.wait("document.activeElement===byId('settings-search-open')")
            await tab.click('#settings-search-open')
            await tab.wait("!byId('settings-search-status').textContent.includes('Loading')")
            assert await tab.js("byId('settings-search-query').value==='' && "
                                "!byId('settings-search-results').children.length && "
                                "!byId('settings-search-query').hasAttribute('aria-activedescendant')")
            await tab.click('#settings-search-close')
            if os.environ.get('KLAUDE_SETTINGS_SEARCH_ONLY'):
                for width in (390, 320):
                    await tab.command('Emulation.setDeviceMetricsOverride', {
                        'width': width, 'height': 760, 'deviceScaleFactor': 1, 'mobile': True,
                    })
                    await tab.click('#settings-search-open')
                    await tab.wait("!byId('settings-search-status').textContent"
                                   ".includes('Loading')")
                    await search_setting('loading bar')
                    await search_key('Tab', 9)
                    await search_key('Enter', 13)
                    await tab.wait("!byId('settings-search-dialog').open && "
                                   "document.activeElement===byId('theme-loading-bar-style')")
                    assert await tab.js('document.documentElement.scrollWidth<=innerWidth')
                assert not tab.errors, tab.errors
                print(json.dumps({'settings_search': 'passed', 'agent_fields': coverage['total'],
                                  'keyboard_navigation_activation_and_scroll': True,
                                  'empty_results_escape_and_reopen': True,
                                  'widths': [1440, 390, 320], 'console_errors': 0}))
                return
            await tab.js("showView('settings', {section:'models'}); "
                         "ModelsSettingsNavigation.show('overview')")
            await tab.wait(
                "!byId('model-connection-add').disabled && byId('default-value-ut"
                "ility-picker') && !byId('default-value-utility-picker').disabled"
            )
            await tab.click("#default-value-utility-picker")
            try:
                await tab.wait(
                    "byId('role-model-picker').open && "
                    "Boolean(byId('role-picker-items').querySelector('.store-row'))"
                )
            except AssertionError:
                print(
                    await tab.js(
                        "({open:byId('role-model-picker').open, status:byId('role-picker-"
                        "status').textContent, connection:byId('role-picker-connection')."
                        "value, items:byId('role-picker-items').textContent, section:sett"
                        "ingsSection})"
                    )
                )
                raise
            await tab.js(
                "byId('role-picker-query').value='fixture'; byId('role-picker-que"
                "ry').dispatchEvent(new Event('input'))"
            )
            await tab.click("#role-picker-items .store-row")
            assert await tab.js(
                "!byId('role-model-picker').open && !byId('models-save-bar').hidd"
                "en && byId('default-value-utility').value.endsWith('/fixture:lat"
                "est')"
            )
            await tab.click("#models-save")
            await tab.wait(
                "byId('models-save-bar').hidden && !SettingsDrafts.category('models').saving"
            )
            assert host.application.agent.model == "fixture"
            await tab.js("byId('model-fallbacks').open=true")
            await tab.click("#default-value-fallbacks-0-picker")
            await tab.wait(
                "byId('role-model-picker').open && "
                "Boolean(byId('role-picker-items').querySelector('.store-row'))"
            )
            await tab.click("#role-picker-items .store-row")
            assert await tab.js(
                "!byId('models-save-bar').hidden && "
                "SettingsDrafts.value('models','fallbacks').length===1"
            )
            await tab.click("#models-discard")
            assert await tab.js("SettingsDrafts.value('models','fallbacks').length===0")
            await tab.click("[data-model-screen=image]")
            await tab.js("byId('image-service-url').value=''; "
                         "byId('image-service-url').dispatchEvent(new Event('input')); "
                         "byId('image-service-provider').value='ollama'; "
                         "byId('image-service-provider').dispatchEvent(new Event('change'))")
            assert await tab.js("byId('image-service-url').value==='http://localhost:11434' && "
                                "SettingsDrafts.value('image-service','image_service').endpoint==="
                                "'http://localhost:11434'")
            await tab.js("byId('image-service-url').value="
                         + json.dumps(host.library.cfg.ollama_url)
                         + ";byId('image-service-url').dispatchEvent(new Event('input'))")
            await tab.js("byId('image-service-provider').value='sdcpp'; "
                         "byId('image-service-provider').dispatchEvent(new Event('change')); "
                         "byId('image-service-provider').value='ollama'; "
                         "byId('image-service-provider').dispatchEvent(new Event('change'))")
            assert await tab.js("byId('image-service-url').value===" +
                                json.dumps(host.library.cfg.ollama_url))
            await tab.command('Emulation.setDeviceMetricsOverride', {
                'width':320, 'height':568, 'deviceScaleFactor':1, 'mobile':False,
            })
            assert await tab.js("""(()=>{
              const row=byId('image-service-model-row').getBoundingClientRect();
              const input=byId('image-service-model-name').getBoundingClientRect();
              const browse=byId('image-service-model-name-picker').getBoundingClientRect();
              return input.width>=60 && browse.width>=44 && browse.height>=44 &&
                input.right<=browse.left+1 && browse.right<=row.right+1 &&
                document.documentElement.scrollWidth<=innerWidth;
            })()""")
            await tab.js("window.savedDomainRequest=domainRequest; "
                         "domainRequest=async (...args)=>{if(args[0].includes('purpose=image-generation')) "
                         "throw Object.assign(new Error('old host'),{status:503}); "
                         "return window.savedDomainRequest(...args)}")
            await tab.click('#image-service-model-name-picker')
            await tab.wait("byId('role-picker-status').textContent.includes('Restart the Web UI host') && "
                           "Boolean(byId('role-picker-items').querySelector('.store-row'))")
            assert await tab.js("byId('role-picker-items').textContent.includes('not verified')")
            await tab.js("domainRequest=window.savedDomainRequest")
            await tab.click('#role-picker-refresh')
            await tab.wait("byId('role-model-picker').open && "
                           "byId('role-picker-items').textContent.includes('Image generation not declared')")
            assert await tab.js("byId('role-picker-unset').hidden && "
                               "byId('role-picker-status').textContent.includes('not')===false && "
                               "byId('role-picker-items').textContent.includes('Image generation not declared')")
            await tab.click('#role-picker-items .store-row')
            assert await tab.js("byId('image-service-model-name').value==='fixture:latest' && "
                               "!byId('image-service-save-bar').hidden && "
                               "byId('models-save-bar').hidden")
            await tab.js("byId('image-service-model-name').value='manual/model:tag'; "
                         "byId('image-service-model-name').dispatchEvent(new Event('input'))")
            assert await tab.js("SettingsDrafts.value('image-service','image_service').model==="
                               "'manual/model:tag'")
            await tab.js("byId('image-service-url').value='http://127.0.0.1:54321'; "
                         "byId('image-service-url').dispatchEvent(new Event('input'))")
            await tab.click('#image-service-model-name-picker')
            await tab.wait("byId('role-picker-status').textContent.includes('No enabled Ollama')")
            assert await tab.js("!byId('role-picker-items').querySelector('.store-row')")
            await tab.click('#role-picker-close')
            await tab.click('#image-service-discard')
            await tab.command('Emulation.setDeviceMetricsOverride', {
                'width':1440, 'height':900, 'deviceScaleFactor':1, 'mobile':False,
            })
            await tab.click("#image-service-test")
            try:
                await tab.wait(
                    "byId('image-settings-status').textContent.includes('No image was generated')"
                )
            except AssertionError:
                print(
                    await tab.js(
                        "({status:byId('image-settings-status').textContent,"
                        "endpoint:byId('image-service-url').value})"
                    )
                )
                raise
            await tab.js("byId('image-service-model-name').value=''; "
                         "byId('image-service-model-name').dispatchEvent(new Event('input'))")
            assert await tab.js("!byId('image-service-save-bar').hidden")
            await tab.click('#image-service-save-bar #image-service-save')
            try:
                await tab.wait("byId('image-service-save-bar').hidden && "
                               "byId('image-service-model-name').value!==''")
            except AssertionError:
                print(await tab.js("({status:byId('image-service-save-status').textContent, "
                                   "saved:byId('image-service-model').textContent, "
                                   "enabled:byId('image-service-enabled').checked, "
                                   "conflict:byId('image-service-save-bar').textContent})"))
                raise
            await tab.click("#models-settings-back")
            await tab.click("[data-model-screen=connections]")
            assert await tab.js("""(() => {
              const rows=[...byId('model-settings-connections')
                .querySelectorAll('.model-connection-row')];
              return [['Ollama','ollama'],['OpenAI API','openai'],['OpenRouter','openrouter'],
                ['Gemini API','google'],['OpenAI Codex','openai']].every(([name, brand])=>{
                  const row=rows.find(node=>node.querySelector('h3')?.textContent===name);
                  const mark=row?.querySelector('.model-connection-icon .model-brand-icon');
                  return mark?.dataset.brand===brand && mark.closest('[aria-hidden=true]') &&
                    getComputedStyle(mark).width==='24px';
                });
            })()""")
            assert await tab.js("""(() => {
              const mark=document.createElement('span');
              AIIcons.setPlatformIcon(mark, 'openai_compatible', {appearance:'color',size:24});
              return mark.dataset.brand==='generic';
            })()""")
            await tab.click("#model-connection-add")
            await tab.js(
                "byId('model-connection-name').value='Browser native'; "
                "byId('model-connection-authentication').checked=true; "
                "byId('model-connection-url').value="
                + json.dumps(host.library.cfg.ollama_url)
                + "; byId('model-connection-form').requestSubmit()"
            )
            await tab.wait("reviewDialog.open")
            assert await tab.js("document.activeElement===byId('domain-review-cancel')")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "byId('model-settings-connections').textContent.includes('Browser"
                " native') && !byId('model-connection-add').disabled"
            )

            async def action(label):
                await tab.js(
                    "[...byId('model-settings-connections').querySelectorAll('.management-row')]"
                    ".find(r=>r.querySelector('h3').textContent==='Browser native')"
                    ".querySelectorAll('button').forEach(b=>{if(b.textContent==="
                    + json.dumps(label)
                    + ") b.click();})"
                )

            await action("Credential")
            await tab.wait("byId('model-connection-editor').open")
            await tab.js(
                "byId('model-credential-value').value='private-fixture-token'; by"
                "Id('model-connection-form').requestSubmit()"
            )
            await tab.wait("reviewDialog.open")
            assert await tab.js(
                "!byId('domain-review-summary').textContent.includes('private-fix"
                "ture-token') && !byId('model-credential-value').value"
            )
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "!byId('model-connection-add').disabled && [...byId('model-settin"
                "gs-connections').querySelectorAll('.management-row')].some(r=>r."
                "textContent.includes('Browser native')&&r.textContent.includes('"
                "Credential saved'))"
            )
            await action("Enable")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "!byId('model-connection-add').disabled && [...byId('model-settin"
                "gs-connections').querySelectorAll('.management-row')].some(r=>r."
                "textContent.includes('Browser native')&&r.textContent.includes('"
                "Enabled'))"
            )
            await tab.js("showView('store')")
            await tab.wait("byId('store-endpoint').options.length===2")
            assert await tab.js("byId('store-endpoint-label').hidden")
            await tab.js(
                "byId('store-source').value='curated';"
                "byId('store-source').dispatchEvent(new Event('change'))"
            )
            await tab.wait("Boolean(document.querySelector('.store-row[data-store-model=qwen3]'))")
            await tab.click(".store-row[data-store-model=qwen3]")
            await tab.wait("!byId('store-detail').hidden && Boolean(byId('store-detail-endpoint'))")
            assert await tab.js("byId('store-detail-endpoint').options.length===2")
            await tab.click("#store-detail-back")
            await tab.wait("byId('store-detail').hidden")
            await tab.click("#store-tab-installed")
            assert await tab.js("!byId('store-endpoint-label').hidden")
            await tab.js("showView('settings', {section:'models'})")
            await tab.click("[data-model-screen=connections]")
            await tab.wait("!byId('model-connection-add').disabled")
            await action("Test")
            await tab.wait(
                "byId('model-connections-status').textContent.includes('Connection reached')"
            )
            for width, height in [(320, 568), (390, 844), (768, 1024), (1440, 900)]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                )
                for theme in ["light", "dark"]:
                    await tab.js(
                        "applyAppearance({...appearance, theme:"
                        + json.dumps(theme)
                        + ", reduced:true})"
                    )
                    assert await tab.js(
                        "document.documentElement.scrollWidth<=innerWidth && byId('models"
                        "-settings').scrollWidth<=byId('models-settings').clientWidth"
                    ), (width, theme)
                    assert await tab.js(
                        "(()=>{const h=byId('model-connections-heading').getBoundingClientRect();"
                        "const a=byId('model-connection-add').getBoundingClientRect();"
                        "return h.right<=a.left || h.bottom<=a.top || a.bottom<=h.top})()"
                    ), (width, theme, "connection heading overlap")
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"model-settings-{width}-{theme}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                await tab.js("byId('model-connections-heading').scrollIntoView({block:'start'})")
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"connections-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                await action("Edit")
                await tab.wait("byId('model-connection-editor').open")
                assert await tab.js(
                    "byId('model-connection-editor').scrollWidth<=byId('model-connect"
                    "ion-editor').clientWidth"
                )
                await tab.click("#model-connection-close")
            await action("Remove")
            await tab.wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-confirm').classList.contains('danger')")
            await tab.click("#domain-review-confirm")
            await tab.wait(
                "!byId('model-settings-connections').textContent.includes('Browse"
                "r native') && !byId('model-connection-add').disabled"
            )
            await tab.click("#models-settings-back")
            await tab.js("ModelsSettingsNavigation.show('catalog')")
            await tab.wait("Boolean(byId('models-items').querySelector('.models-model'))")
            assert await tab.js("!byId('models-items').querySelector('button')")
            await tab.js("history.back()")
            await tab.wait("!byId('model-default-settings').hidden")
            await tab.click("[data-model-screen=image]")
            await tab.js(
                "byId('image-service-url').value='http://127.0.0.1:54321'; byId('image-"
                "service-url').dispatchEvent(new Event('input'))"
            )
            assert await tab.js(
                "!byId('image-service-save-bar').hidden && byId('models-save-bar').hidden"
            )
            await tab.click("#image-service-discard")
            await tab.click("#models-settings-back")
            await tab.js(
                "byId('default-value-utility').value=''; "
                "byId('default-value-utility').dispatchEvent(new Event('change')); "
                "window.savedConfirm=window.confirm; window.confirm=()=>false"
            )
            await tab.click("[data-model-screen=connections]")
            assert await tab.js("!byId('model-default-settings').hidden")
            await tab.js("history.back()")
            await asyncio.sleep(0.2)
            assert await tab.js(
                "!byId('model-default-settings').hidden && "
                "new URLSearchParams(location.search).get('models-screen')==='overview'"
            )
            await tab.js("window.confirm=window.savedConfirm")
            await tab.click("#models-discard")
            for width, height in [(320, 568), (390, 844), (768, 1024), (1440, 900)]:
                await tab.command(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                )
                await tab.click('#settings-search-open')
                assert await tab.js("""(()=>{
                  const r=byId('settings-search-dialog').getBoundingClientRect();
                  return r.left>=0 && r.right<=innerWidth && r.top>=0 && r.bottom<=innerHeight;
                })()"""), width
                await tab.command('Input.dispatchKeyEvent', {
                    'type':'keyDown', 'key':'Escape', 'code':'Escape', 'windowsVirtualKeyCode':27,
                })
                await tab.command('Input.dispatchKeyEvent', {
                    'type':'keyUp', 'key':'Escape', 'code':'Escape', 'windowsVirtualKeyCode':27,
                })
                await tab.wait("!byId('settings-search-dialog').open && "
                               "document.activeElement===byId('settings-search-open')")
                for screen in ["overview", "connections", "catalog", "image"]:
                    await tab.js("ModelsSettingsNavigation.show(" + json.dumps(screen) + ")")
                    await asyncio.sleep(0.15)
                    assert await tab.js(
                        "document.documentElement.scrollWidth<=innerWidth && byId('models-setti"
                        "ngs').scrollWidth<=byId('models-settings').clientWidth"
                    ), (width, screen)
                    breadcrumb = await tab.js("""(() => ({
                      hidden:byId('models-screen-title').hidden,
                      title:byId('models-screen-title').textContent,
                      back:byId('models-settings-back').textContent,
                      defaults:!byId('model-default-settings').hidden,
                      refresh:!byId('media-settings-refresh').hidden,
                      icon:!!byId('model-default-heading').querySelector(':scope > .icon')
                    }))()""")
                    assert breadcrumb["hidden"] == (screen == "overview"), (width, screen)
                    assert breadcrumb["icon"] and breadcrumb["refresh"] == (
                        screen == "overview"
                    ), breadcrumb
                    if screen != "overview":
                        assert breadcrumb["back"] == "Models" and breadcrumb["title"] == {
                            "connections": "Connections", "catalog": "Connected models",
                            "image": "Image generation",
                        }[screen], breadcrumb
                    else:
                        assert breadcrumb["defaults"] and breadcrumb["refresh"], breadcrumb
                    if screen == "overview":
                        assert await tab.js("""!document.querySelector(
                          '#models-overview-links [data-model-screen="catalog"]')""")
                        assert await tab.js(
                            "new Set([...document.querySelectorAll('.settings-role-grid > "
                            ".settings-role-container')]"
                            ".map(row=>Math.round(row.getBoundingClientRect().left))).size===1"
                        )
                        await tab.js("byId('model-fallbacks').open=true")
                        assert await tab.js("""(() => {
                          const group=byId('model-fallbacks').getBoundingClientRect();
                          const rows=[...document.querySelectorAll(
                            '.settings-fallback-form > .setting-row, '+
                            '#model-options-heading + .settings-form-grid > .setting-row')];
                          return rows.length===8 && rows.every(row => {
                            const r=row.getBoundingClientRect(), style=getComputedStyle(row);
                            return Math.abs(r.left-group.left-1)<1.5 &&
                              Math.abs(group.right-r.right-1)<1.5 &&
                              parseFloat(style.borderTopWidth)===1;
                          });
                        })()""")
                        assert await tab.js("""(() => {
                          const roles=getComputedStyle(
                            document.querySelector('.settings-role-grid'));
                          const advanced=getComputedStyle(byId('model-fallbacks'));
                          return roles.borderColor===advanced.borderColor &&
                            roles.borderRadius===advanced.borderRadius &&
                            roles.backgroundColor===advanced.backgroundColor;
                        })()""")
                        assert await tab.js("""(() => {
                          const input=byId('default-output-tokens');
                          const row=input.closest('.setting-row');
                          const label=row.querySelector('label').getBoundingClientRect();
                          const control=input.getBoundingClientRect();
                          const bounds=row.getBoundingClientRect();
                          return label.right<=control.left+1 && control.right<=bounds.right &&
                            label.top<control.bottom && control.top<label.bottom &&
                            control.width>=80;
                        })()"""), width
                        assert await tab.js("""(() => {
                          const row=byId('default-vision-enabled').closest('.setting-row');
                          const card=byId('model-fallbacks').getBoundingClientRect();
                          return Math.abs(card.bottom-row.getBoundingClientRect().bottom-1)<1.5;
                        })()"""), width
                        assert await tab.js("""[...document.querySelectorAll(
                          '#default-model-fields .settings-role-row')].every(row=>
                            row.getBoundingClientRect().height>=64)"""), width
                        role_typography = await tab.js("""(() => {
                          const roles=[...document.querySelectorAll(
                            '#default-model-fields .settings-role-row .model-role-label')];
                          const properties=['fontFamily','fontSize','fontWeight','lineHeight',
                            'letterSpacing','color'];
                          return roles.map(label=>{
                            const style=getComputedStyle(label);
                            return Object.fromEntries(properties.map(p=>[p,style[p]]));
                          });
                        })()""")
                        assert len(role_typography) == 10 and all(
                            style == role_typography[0] for style in role_typography
                        ), (width, role_typography)
                        rows = await tab.js("""[...document.querySelectorAll(
                              '.settings-role-row, .settings-navigation-row')]
                            .filter(el=>el.getClientRects().length).map(el=>{
                              const style=getComputedStyle(el), box=el.getBoundingClientRect();
                              return {text:el.textContent, left:parseFloat(style.paddingLeft),
                                right:parseFloat(style.paddingRight), width:box.width,
                                parent:byId('models-settings').clientWidth,
                                childrenFit:[...el.children].every(child=>{
                                  const r=child.getBoundingClientRect();
                                  return !r.width || r.left>=box.left && r.right<=box.right;
                                })};
                            })""")
                        assert all(
                            row["left"] >= 12
                            and row["right"] >= 12
                            and row["width"] <= row["parent"] + 1
                            and row["childrenFit"]
                            for row in rows
                        ), (width, rows)
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"settings-{screen}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
                await tab.js(
                    "ModelsSettingsNavigation.show('overview'); showView('settings',{sectio"
                    "n:'account'})"
                )
                await tab.js("byId('settings-view').scrollTop=byId('settings-view').scrollHeight")
                await asyncio.sleep(0.1)
                account_gap = await tab.js("""(() => {
                  const view=byId('settings-view'), panel=byId('account-settings');
                  const last=byId('account-sign-out').getBoundingClientRect();
                  return {gap:view.getBoundingClientRect().bottom-last.bottom,
                    end:view.scrollHeight-view.scrollTop-view.clientHeight<2,
                    dock:byId('settings-action-dock').hidden};
                })()""")
                assert account_gap['end'] and account_gap['dock'] and account_gap['gap']>=24, (
                    width, account_gap
                )
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"account-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                await tab.click("#password-open")
                assert await tab.js(
                    "byId('password-dialog').open && document.activeElement===byId('current"
                    "-password')"
                )
                if width <= 560:
                    await tab.wait(
                        "Math.abs(byId('password-dialog').getBoundingClientRect().width-innerWidth)<1"
                    )
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"password-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                await tab.js("byId('new-password').value='temporary-fixture'")
                await tab.command(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyDown",
                        "key": "Escape",
                        "code": "Escape",
                        "windowsVirtualKeyCode": 27,
                    },
                )
                await tab.command(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyUp",
                        "key": "Escape",
                        "code": "Escape",
                        "windowsVirtualKeyCode": 27,
                    },
                )
                await tab.wait(
                    "!byId('password-dialog').open && !byId('new-password').value && docume"
                    "nt.activeElement===byId('password-open')"
                )
                await tab.js("showView('settings',{section:'memory'})")
                await tab.wait("!byId('memory-create').disabled")
                await tab.js("byId('settings-view').scrollTop=byId('settings-view').scrollHeight")
                await asyncio.sleep(0.1)
                memory_gap = await tab.js("""(() => {
                  const view=byId('settings-view');
                  const content=byId('memory-items').getBoundingClientRect();
                  return {gap:view.getBoundingClientRect().bottom-content.bottom,
                    end:view.scrollHeight-view.scrollTop-view.clientHeight<2,
                    dock:byId('settings-action-dock').hidden};
                })()""")
                assert memory_gap['end'] and memory_gap['dock'] and memory_gap['gap']>=24, (
                    width, memory_gap
                )
                shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                (output / f"memory-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                await tab.click("#memory-create")
                assert await tab.js(
                    "byId('memory-editor').open && document.activeElement===byId('memory-fact')"
                )
                await tab.click("#memory-editor-cancel")
                await tab.wait(
                    "!byId('memory-editor').open && document.activeElement===byId('memory-create')"
                )
                await tab.js("showView('settings',{section:'models'})")
            await tab.js("showView('settings',{section:'memory'})")
            await tab.click("#memory-create")
            await tab.js(
                "byId('memory-fact').value='Settings layout fixture'; byId('memory-add'"
                ").requestSubmit()"
            )
            await tab.wait("reviewDialog.open")
            assert await tab.js("!byId('memory-editor').open")
            await tab.click("#domain-review-cancel")
            await tab.wait(
                "byId('memory-editor').open && "
                "byId('memory-fact').value==='Settings layout fixture'"
            )
            await tab.js("byId('memory-add').requestSubmit()")
            await tab.wait("reviewDialog.open")
            await tab.click("#domain-review-confirm")
            await tab.wait("byId('memory-items').textContent.includes('Settings layout fixture')")
            await tab.click('#memory-create')
            await tab.js("byId('memory-fact').value='Another saved fixture'; "
                         "byId('memory-add').requestSubmit()")
            await tab.wait('reviewDialog.open')
            await tab.click('#domain-review-confirm')
            await tab.wait("byId('memory-items').querySelectorAll('.memory-row').length===2")
            assert await tab.js("""(()=>{
              const group=document.querySelector('.memory-list-group').getBoundingClientRect();
              const rows=[...byId('memory-items').querySelectorAll('.memory-row')];
              return rows.every((row,index)=>{
                const r=row.getBoundingClientRect(), style=getComputedStyle(row);
                return Math.abs(r.left-group.left-1)<1.5 &&
                  Math.abs(group.right-r.right-1)<1.5 &&
                  parseFloat(style.borderBottomWidth)===(index===rows.length-1 ? 0 : 1);
              });
            })()""")
            await tab.click("#memory-items .icon-button")
            await tab.click("#memory-items [role=menuitem]")
            assert await tab.js(
                "byId('memory-editor').open && byId('memory-fact').value==='Settings la"
                "yout fixture'"
            )
            await tab.click("#memory-editor-cancel")
            await tab.click("#memory-items .icon-button")
            await tab.js("byId('memory-items').querySelector('.danger').click()")
            await tab.wait("reviewDialog.open")
            assert await tab.js("byId('domain-review-confirm').classList.contains('danger')")
            await tab.click("#domain-review-cancel")
            assert Native.pulls == 0
            await tab.click("#logout")
            await tab.wait("!authenticated")
            assert await tab.js(
                "!byId('model-credential-value').value && !byId('model-settings-c"
                "onnections').textContent && !byId('role-picker-items').textConte"
                "nt"
            )
            assert not tab.errors, tab.errors
            print(
                json.dumps(
                    {
                        "settings": (
                            "role picker/save, image test, add-disabled, credential, enable/t"
                            "est, remove and logout passed"
                        ),
                        "widths": [320, 390, 768, 1440],
                        "console_errors": 0,
                        "screenshots": str(output),
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    fixture_main(verify, admin_lan=os.environ.get("KLAUDE_TEST_ADMIN_LAN", "1") == "1")

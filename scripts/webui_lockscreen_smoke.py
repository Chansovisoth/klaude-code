"""Real login/expiry and screenshot checks on an isolated local account/profile.

No real credentials, models, external requests or user data. Reference captures
freeze browser time only; production uses local wall time. Run with .venv/bin/python.
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
import webui_startup_smoke as fixture
from webui_control_smoke import Tab

OUT = Path('/tmp/klaude-lockscreen-validation')


async def verify(host, root, gates, failures):
    chrome = os.environ.get('KLAUDE_TEST_CHROME') or str(next((Path.home()/'.cache/puppeteer/chrome-headless-shell').glob('*/chrome-headless-shell-linux64/chrome-headless-shell')))
    profile = root/'chrome-lockscreen'
    process = subprocess.Popen([chrome, '--no-sandbox', '--disable-gpu', '--remote-debugging-port=0', f'--user-data-dir={profile}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    OUT.mkdir(exist_ok=True)
    report = {'layouts': [], 'fixture_only': True}
    try:
        for _ in range(100):
            if (profile/'DevToolsActivePort').exists():
                break
            await asyncio.sleep(.05)
        port = int((profile/'DevToolsActivePort').read_text().splitlines()[0])
        with urlopen(Request(f'http://127.0.0.1:{port}/json/new?about:blank', method='PUT')) as response:
            target = json.load(response)
        async with websockets.connect(target['webSocketDebuggerUrl'], max_size=12_000_000) as ws:
            tab = Tab(ws)
            for domain in ('Runtime', 'Page', 'Network'):
                await tab.command(domain+'.enable')
            await tab.command('Emulation.setTimezoneOverride', {'timezoneId':'Asia/Phnom_Penh'})
            frozen = await tab.command('Page.addScriptToEvaluateOnNewDocument', {'source': '''(()=>{const OriginalDate=Date;window.Date=class extends OriginalDate{constructor(...args){super(...(args.length?args:['2026-08-28T01:57:00+07:00']))}static now(){return new OriginalDate('2026-08-28T01:57:00+07:00').getTime()}}})()'''})
            await tab.command('Emulation.setDeviceMetricsOverride', {'width':1920,'height':1080,'deviceScaleFactor':1,'mobile':False})
            await tab.command('Page.navigate', {'url':host.origin})
            await tab.wait('typeof KlaudeLockScreen!=="undefined"&&document.documentElement.dataset.startup==="ready"&&!byId("local-access").hidden')
            assert await tab.js('!authenticated&&document.querySelector(".shell").inert&&layout.hidden'), await tab.js('JSON.stringify({authenticated,inert:document.querySelector(".shell").inert,layoutHidden:layout.hidden,access:document.documentElement.dataset.access,errors:window.expressiveErrors})')
            assert await tab.js('fetch("/api/v1/session").then(r=>r.status)') == 401
            await tab.js('document.fonts.ready')
            assert await tab.js('getComputedStyle(byId("local-access")).fontFamily.includes("Readex Pro")')
            assert await tab.js('''(async()=>{const response=await fetch('/lockscreen-bg.jpg');if(response.status!==200||!response.headers.get('Content-Type').startsWith('image/jpeg'))return false;const image=new Image();image.src='/lockscreen-bg.jpg';await image.decode();return image.naturalWidth>0&&image.naturalHeight>0&&document.fonts.check('17px "Readex Pro"')&&document.fonts.check('68px "Space Grotesk"');})()'''), 'The real wallpaper and fonts must load before authentication; font-family declarations alone cannot verify assets'
            report['wallpaper_and_reference_fonts_load_before_sign_in'] = True
            quote = await tab.js('document.querySelector(".lock-quote").dataset.quoteId')
            assert await tab.js('KlaudeLockQuoteCollection.quotes.some(q=>String(q.id)===document.querySelector(".lock-quote").dataset.quoteId&&q.quote===byId("lock-quote-text").textContent&&q.attribution===byId("lock-quote-attribution").textContent&&(q.source_url||null)===document.querySelector(".lock-quote").getAttribute("cite"))')
            assert await tab.js('byId("lock-quote-attribution").classList.contains("visually-hidden")&&getComputedStyle(byId("lock-quote-attribution")).clipPath==="inset(50%)"'), 'Attribution is retained without the visible English Proverb label'
            await tab.js('KlaudeLockScreen.show();KlaudeLockScreen.show();dispatchEvent(new Event("focus"))')
            assert await tab.js('document.querySelector(".lock-quote").dataset.quoteId') == quote

            # Measure the actual rendered quote, not only its CSS declaration.
            original_quote = await tab.js('byId("lock-quote-text").textContent')
            quote_layout = []
            for width in (320, 390, 768, 1440):
                await tab.command('Emulation.setDeviceMetricsOverride', {'width':width,'height':844,'deviceScaleFactor':1,'mobile':False})
                for sample in (
                    'The portal opens after one more test.',
                    'Make a little room for a new idea.',
                    'Every great work begins with a small step toward something beautifully unknown.',
                ):
                    measurement = await tab.js('''(()=>{
                      const quote=document.querySelector('.lock-quote'), text=byId('lock-quote-text');
                      text.textContent=SAMPLE;
                      KlaudeLockScreen.fitQuote();
                      const icon=quote.querySelector('svg'), bounds=quote.getBoundingClientRect();
                      const range=document.createRange(); range.selectNodeContents(text);
                      const lines=[...range.getClientRects()];
                      return {width:bounds.width,left:bounds.left,right:bounds.right,
                        center:(bounds.left+bounds.right)/2,lines:lines.length,
                        maxLine:Math.max(...lines.map(line=>line.width)),
                        iconOffset:Math.abs(icon.getBoundingClientRect().top-lines[0].top),
                        wrap:getComputedStyle(text).textWrap};
                    })()'''.replace('SAMPLE', json.dumps(sample)))
                    assert measurement['wrap'] == 'wrap', (width, sample, measurement)
                    assert measurement['left'] >= 11.5 and measurement['right'] <= width-11.5, (width, sample, measurement)
                    assert abs(measurement['center']-width/2) <= 1, (width, sample, measurement)
                    assert measurement['iconOffset'] <= 2, (width, sample, measurement)
                    assert measurement['width']-measurement['maxLine']-56 <= 45, (width, sample, measurement)
                    if sample.startswith('The portal') and width >= 390:
                        assert measurement['lines'] == 1, (width, sample, measurement)
                    quote_layout.append({'viewport':width,'length':len(sample),'lines':measurement['lines']})
            author_layout = await tab.js('''(()=>{
              const text=byId('lock-quote-text'),author=byId('lock-quote-attribution');
              const originalAuthor=author.textContent, wasHidden=author.classList.contains('visually-hidden');
              text.textContent='The portal opens after one more test.';
              author.textContent='Ada Lovelace'; author.classList.remove('visually-hidden');
              KlaudeLockScreen.fitQuote();
              const quote=document.querySelector('.lock-quote').getBoundingClientRect();
              const textRect=text.getBoundingClientRect(),authorRect=author.getBoundingClientRect();
              author.textContent=originalAuthor;
              author.classList.toggle('visually-hidden',wasHidden);
              return {below:authorRect.top>=textRect.bottom,contained:authorRect.right<=quote.right-10&&authorRect.bottom<=quote.bottom};
            })()''')
            assert all(author_layout.values()), author_layout
            await tab.js('byId("lock-quote-text").textContent='+json.dumps(original_quote))
            await tab.js('KlaudeLockScreen.fitQuote()')
            await tab.command('Emulation.setDeviceMetricsOverride', {'width':1920,'height':1080,'deviceScaleFactor':1,'mobile':False})
            report['quote_layout'] = quote_layout

            async def shot(name):
                await asyncio.sleep(.25)
                result = await tab.command('Page.captureScreenshot', {'format':'png'})
                (OUT/name).write_bytes(base64.b64decode(result['data']))

            # CDP inserts through the native password editor; the decorative
            # layer is inspected only for counts, selection and shape identity.
            await tab.js('byId("login-password").focus()')
            await tab.command('Input.insertText', {'text':'fixture'})
            assert await tab.js('byId("lock-password-shapes").children.length') == 7, await tab.js('JSON.stringify({count:byId("lock-password-shapes").children.length,nativeLength:byId("login-password").value.length,ready:byId("lock-password-field").className,missing:KlaudeLockScreen.passwordShapes.filter(n=>!KlaudeExpressive.shape(n).querySelector("path")),active:document.activeElement.id})')
            assert await tab.js('JSON.stringify([...byId("lock-password-shapes").children].map(e=>e.dataset.shape))') == json.dumps(['clover-4','arrow','pill','soft-burst','diamond','clam-shell','pentagon'], separators=(',',':'))
            assert await tab.js('byId("lock-password-shapes").textContent===""&&byId("login-password").type==="password"&&getComputedStyle(byId("login-password")).webkitTextFillColor==="rgba(0, 0, 0, 0)"')
            await tab.js('byId("login-password").setSelectionRange(1,5);KlaudeLockScreen.syncPassword()')
            assert await tab.js('byId("lock-password-shapes").querySelectorAll(".selected").length') == 4
            await tab.command('Input.insertText', {'text':'x'})
            assert await tab.js('byId("lock-password-shapes").children.length') == 4
            await tab.js('byId("login-password").value="fixture";byId("login-password").setSelectionRange(7,7);byId("login-password").blur();KlaudeLockScreen.syncPassword()')
            await shot('reference-desktop-1920.png')
            assert await tab.js('[...document.querySelectorAll(".lock-island")].every(e=>e.offsetHeight===56)&&byId("access-status").offsetHeight===0')
            report['native_typing_selection_and_replacement'] = True

            # Use the existing appearance controller; measure painted colors,
            # including glass over worst-case black/white wallpaper pixels.
            theme = await tab.js('''(()=>{
              const canvas=document.createElement('canvas');canvas.width=canvas.height=1;
              const context=canvas.getContext('2d',{willReadFrequently:true});
              const rgb=value=>{context.clearRect(0,0,1,1);context.fillStyle=value;context.fillRect(0,0,1,1);return [...context.getImageData(0,0,1,1).data].map(x=>x/255)};
              const color=(selector,property,pseudo=null)=>rgb(getComputedStyle(document.querySelector(selector),pseudo)[property]);
              const blend=(rgba,base)=>rgba.slice(0,3).map((v,i)=>v*rgba[3]+base[i]*(1-rgba[3]));
              const lum=values=>values.slice(0,3).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((v,x,i)=>v+x*[.2126,.7152,.0722][i],0);
              const ratio=(a,b)=>{a=lum(a);b=lum(b);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
              const pairs=[
                ['quote','.lock-quote','color','.lock-quote','backgroundColor',4.5],
                ['status','.lock-status','color','.lock-status','backgroundColor',4.5],
                ['username','#login-username','color','.lock-account','backgroundColor',4.5],
                ['utilities','.lock-utilities','color','.lock-utilities','backgroundColor',4.5],
                ['password','.password-shape-slot','color','.shape-password-field','backgroundColor',4.5],
                ['submit','#login-submit','color','#login-submit','backgroundColor',4.5],
                ['day','.cookie-day > span:last-child','color','.cookie-day','color',4.5],
                ['month','.cookie-month > span:last-child','color','.cookie-month','color',4.5],
                ['help','.lock-help-content','color','.lock-help-content','backgroundColor',4.5],
                ['error','#access-status','color','#access-status','backgroundColor',4.5],
                ['caps','#lock-caps','color','#lock-caps','backgroundColor',4.5],
                ['bootstrap','.lock-bootstrap','color','.lock-bootstrap','backgroundColor',4.5],
                ['numerals','#lock-clock-hour','fill','.cookie-clock-face','color',3],
                ['hour hand','#lock-hour-hand','fill','.cookie-clock-face','color',3],
                ['minute hand','#lock-minute-hand','fill','.cookie-clock-face','color',3],
              ];
              const sources=[...paletteNames.map(palette=>({palette,colorSource:'preset'})),
                {palette:'lavender',colorSource:'custom',accent:'#007f87'},
                {palette:'lavender',colorSource:'image',accent:'#e36040'}];
              const failures=[],minimum={text:100,clock:100};let cases=0;
              try {
                for(const source of sources)for(const variant of Object.keys(MaterialColors.variants))
                  for(const mode of ['light','dark'])for(const transparency of [0,20]){
                    const value={...appearance,...source,variant,theme:mode,transparency};
                    applyAppearance(value,true);cases++;
                    const root=getComputedStyle(document.documentElement),lock=getComputedStyle(byId('local-access'));
                    for(const token of ['primary','primary-container','tertiary-container','on-surface','error'])
                      if(root.getPropertyValue('--'+token)!==lock.getPropertyValue('--'+token)) failures.push({token,reason:'Lockscreen overrides theme'});
                    for(const [name,fg,fgProp,bg,bgProp,limit] of pairs){
                      const fore=color(fg,fgProp),back=color(bg,bgProp);
                      for(const paper of [[0,0,0],[1,1,1]]){
                        const painted=blend(back,paper),score=ratio(blend(fore,painted),painted);
                        const kind=limit===3?'clock':'text';minimum[kind]=Math.min(minimum[kind],score);
                        if(!Number.isFinite(score)||score<limit) failures.push({name,score,limit,...source,variant,mode,transparency});
                      }
                    }
                    const hint=color('#login-password','color','::placeholder'),field=color('.shape-password-field','backgroundColor');
                    const score=ratio(hint,field);minimum.text=Math.min(minimum.text,score);
                    if(!Number.isFinite(score)||score<4.5)failures.push({name:'placeholder',score,...source,variant,mode});
                  }
              }finally{applyAppearance(appearance,true)}
              return {cases,minimum,failures:failures.slice(0,12),failureCount:failures.length};
            })()''')
            assert not theme['failureCount'], theme
            report['theme_contrast'] = theme

            for mode,palette in (('light','lavender'),('dark','ocean'),('light','cocoa'),('dark','cocoa')):
                await tab.js('applyAppearance({...appearance,theme:'+json.dumps(mode)+',palette:'+json.dumps(palette)+'},true)')
                assert await tab.js('document.querySelector(".lock-quote").dataset.quoteId') == quote
                for width,height in ((390,844),(1440,900)):
                    await tab.command('Emulation.setDeviceMetricsOverride', {'width':width,'height':height,'deviceScaleFactor':1,'mobile':False})
                    await shot(f'theme-{mode}-{palette}-{width}.png')
            await tab.js('applyAppearance({...appearance,theme:"system"},true)')
            for mode in ('dark','light'):
                await tab.command('Emulation.setEmulatedMedia', {'features':[{'name':'prefers-color-scheme','value':mode}]})
                await tab.wait('document.documentElement.style.colorScheme==='+json.dumps(mode))
            await tab.command('Emulation.setEmulatedMedia', {'features':[]})
            await tab.js('applyAppearance(appearance,true)')
            report['lockscreen_follows_live_theme_and_system_mode'] = True

            async def centered():
                geometry = await tab.js('''(()=>{const main=document.querySelector('.lock-main').getBoundingClientRect(),group=document.querySelector('.lock-center').getBoundingClientRect(),footer=document.querySelector('.lock-bottom').getBoundingClientRect(),screen=byId('local-access');return {error:Math.abs((group.top+group.bottom-main.top-main.bottom)/2),noOverlap:group.bottom<=footer.top&&group.top>=main.top,footerInside:footer.bottom<=screen.getBoundingClientRect().bottom,noScroll:screen.scrollHeight<=screen.clientHeight&&document.documentElement.scrollHeight<=innerHeight};})()''')
                assert geometry['error'] <= 1 and all(geometry[key] for key in ('noOverlap','footerInside','noScroll')), geometry
                return geometry

            for width,height in ((320,740),(390,844),(390,650),(390,568),(320,480),(390,360),(768,1024),(768,600),(1440,900),(1920,1080),(844,390)):
                await tab.command('Emulation.setDeviceMetricsOverride', {'width':width,'height':height,'deviceScaleFactor':1,'mobile':False})
                await asyncio.sleep(.2)
                geometry = await tab.js('''(()=>{const screen=byId('local-access'),form=byId('account-login').getBoundingClientRect(),clock=byId('lock-clock').getBoundingClientRect();return {fits:document.documentElement.scrollWidth<=innerWidth&&screen.scrollWidth<=screen.clientWidth,formVisible:form.left>=0&&form.right<=innerWidth&&form.bottom<=innerHeight,clockClear:clock.top>=0&&clock.bottom<form.top,threeIslands:screen.querySelectorAll('.lock-island').length===3};})()''')
                assert all(geometry.values()), (width,height,geometry)
                if width <= 720:
                    if height > 400:
                        assert await tab.js('''(()=>{const form=byId('account-login').getBoundingClientRect(),account=document.querySelector('.lock-account').getBoundingClientRect(),utility=document.querySelector('.lock-utilities').getBoundingClientRect();return form.top>=Math.max(account.bottom,utility.bottom)+9&&Math.abs(form.left-account.left)<1&&Math.abs(form.right-utility.right)<1;})()'''), 'Phone password belongs on the full-width bottom row'
                if width <= 768:
                    geometry['centering'] = await centered()
                    geometry['clock_shown'] = await tab.js('getComputedStyle(byId("lock-clock")).display!=="none"')
                    if height >= 480:
                        assert geometry['clock_shown'], 'Keep the current clock size whenever it fits'
                else:
                    assert await tab.js('getComputedStyle(document.querySelector(".lock-center")).position==="absolute"&&getComputedStyle(document.querySelector(".lock-toolbar")).position==="absolute"'), 'Desktop keeps the existing positioning'
                report['layouts'].append({'width':width,'height':height,**geometry})
                await shot(f'login-{width}-{height}.png')

            await tab.command('Emulation.setDeviceMetricsOverride', {'width':390,'height':844,'deviceScaleFactor':1,'mobile':False})
            await tab.js('byId("local-access").style.paddingTop="30px";byId("local-access").style.paddingBottom="34px"')
            await centered()
            assert await tab.js('Math.abs(byId("local-access").getBoundingClientRect().bottom-document.querySelector(".lock-toolbar").getBoundingClientRect().bottom-34)<1'), 'Nonzero safe-area padding leaves toolbar clearance'
            await tab.js('byId("local-access").style.removeProperty("padding-top");byId("local-access").style.removeProperty("padding-bottom")')
            await tab.js('byId("lock-caps").hidden=false;byId("access-status").textContent="Fixture connection message with enough detail to wrap. ".repeat(15)')
            await centered()
            assert await tab.js('byId("lock-caps").getBoundingClientRect().bottom<=byId("access-status").getBoundingClientRect().top'), 'Multiple notices share real footer space'
            await tab.js('byId("lock-caps").hidden=true;byId("access-status").textContent="";KlaudeLockScreen.show({passwordLogin:false})')
            await centered()
            assert await tab.js('!byId("lock-bootstrap").hidden&&byId("account-login").hidden&&document.querySelector(".shell").inert'), 'Legacy browser-link presentation stays contained and protected'
            await tab.js('KlaudeLockScreen.show()')
            await tab.js('document.querySelector(".lock-help").open=true')
            assert await tab.js('document.querySelector(".lock-help-content").getBoundingClientRect().bottom<=document.querySelector(".lock-account").getBoundingClientRect().top'), 'Help popup must stay above its relocated mobile toolbar row'
            await shot('mobile-help-390.png')
            await tab.js('document.querySelector(".lock-help").open=false')
            original_username = await tab.js('byId("login-username").value')
            await tab.js('byId("login-username").focus();byId("login-username").select()')
            await tab.js('window.actualLockViewport=visualViewport;Object.defineProperty(window,"visualViewport",{configurable:true,value:{height:340,offsetTop:0}});dispatchEvent(new Event("resize"))')
            await asyncio.sleep(.1)
            assert await tab.js('getComputedStyle(document.querySelector(".lock-account")).display!=="none"&&document.activeElement===byId("login-username")'), 'Opening the mobile keyboard must not hide or blur the focused username'
            await tab.command('Input.insertText', {'text':'fixture-editor'})
            assert await tab.js('byId("login-username").value==="fixture-editor"&&document.activeElement===byId("login-username")'), 'Native username editing must continue after the viewport shrinks'
            await tab.command('Emulation.setDeviceMetricsOverride', {'width':390,'height':360,'deviceScaleFactor':1,'mobile':False})
            assert await tab.js('getComputedStyle(document.querySelector(".lock-account")).display!=="none"&&document.activeElement===byId("login-username")'), 'A keyboard that resizes the layout viewport must preserve username focus too'
            await tab.command('Emulation.setDeviceMetricsOverride', {'width':390,'height':844,'deviceScaleFactor':1,'mobile':False})
            await tab.wait('byId("local-access").dataset.keyboard==="true"')
            await tab.js('byId("login-password").focus()')
            assert await tab.js('document.activeElement===byId("login-password")&&document.querySelector(".lock-account").getBoundingClientRect().bottom<byId("account-login").getBoundingClientRect().top'), 'Both login fields remain accessible when switching focus'
            assert await tab.js('byId("local-access").dataset.keyboard==="true"&&getComputedStyle(byId("lock-clock")).display==="none"&&byId("account-login").getBoundingClientRect().bottom<=340&&document.querySelector(".lock-center").getBoundingClientRect().bottom<byId("account-login").getBoundingClientRect().top'), await tab.js('JSON.stringify({keyboard:byId("local-access").dataset.keyboard,clock:getComputedStyle(byId("lock-clock")).display,form:byId("account-login").getBoundingClientRect().toJSON(),center:document.querySelector(".lock-center").getBoundingClientRect().toJSON()})')
            await centered()
            await shot('keyboard-390-340.png')
            await tab.js('Object.defineProperty(window,"visualViewport",{configurable:true,value:{height:210,offsetTop:48}});dispatchEvent(new Event("resize"))')
            await centered()
            assert await tab.js('byId("account-login").getBoundingClientRect().bottom<=258&&byId("local-access").getBoundingClientRect().top===48')
            await tab.js('byId("access-status").textContent="Fixture connection message with enough detail to wrap. ".repeat(8)')
            await centered()
            assert await tab.js('byId("account-login").getBoundingClientRect().bottom<=258&&byId("access-status").closest(".lock-notices").scrollHeight>byId("access-status").closest(".lock-notices").clientHeight'), 'Long feedback scrolls internally while the keyboard keeps the password accessible'
            await tab.js('byId("access-status").textContent=""')
            await tab.command('Emulation.setDeviceMetricsOverride', {'width':844,'height':844,'deviceScaleFactor':1,'mobile':False})
            await tab.js('Object.defineProperty(window,"visualViewport",{configurable:true,value:{height:340,offsetTop:0}});dispatchEvent(new Event("resize"));byId("login-username").focus();byId("access-status").textContent="Fixture connection notice"')
            assert await tab.js('document.activeElement===byId("login-username")&&byId("access-status").getBoundingClientRect().bottom<=document.querySelector(".lock-account").getBoundingClientRect().top&&document.querySelector(".lock-account").getBoundingClientRect().bottom<byId("account-login").getBoundingClientRect().top'), 'Wide keyboard layouts preserve username focus and keep notices above both fields'
            await tab.command('Emulation.setDeviceMetricsOverride', {'width':390,'height':844,'deviceScaleFactor':1,'mobile':False})
            await tab.js('byId("access-status").textContent="";byId("login-password").focus()')
            await tab.js('Object.defineProperty(window,"visualViewport",{configurable:true,value:actualLockViewport});dispatchEvent(new Event("resize"))')
            await tab.js('byId("login-username").value='+json.dumps(original_username))
            report['simulated_keyboard_clearance'] = True
            report['username_focus_and_editing_survive_keyboard_resize'] = True
            await tab.command('Emulation.setEmulatedMedia', {'features':[{'name':'forced-colors','value':'active'}]})
            assert await tab.js('getComputedStyle(document.querySelector(".shape-password-mask")).display==="none"&&getComputedStyle(byId("login-password")).webkitTextFillColor!=="rgba(0, 0, 0, 0)"')
            await shot('forced-colors-390.png')
            await tab.command('Emulation.setEmulatedMedia', {'features':[{'name':'prefers-reduced-motion','value':'reduce'}]})
            assert await tab.js('parseFloat(getComputedStyle(byId("lock-password-shapes").firstChild.firstChild).animationDuration)<.01')
            report['forced_colors_and_reduced_motion'] = True
            await tab.command('Emulation.setEmulatedMedia', {'features':[]})

            await tab.js('byId("lock-password-field").classList.remove("shape-mask-ready")')
            assert await tab.js('getComputedStyle(document.querySelector(".shape-password-mask")).display==="none"&&getComputedStyle(byId("login-password")).webkitTextFillColor!=="rgba(0, 0, 0, 0)"')
            await tab.js('byId("lock-password-field").classList.add("shape-mask-ready")')
            report['native_mask_fallback'] = True

            # Wrong credentials use the actual account/rate-limited HTTP route.
            await tab.js('byId("login-username").value="admin"')
            await tab.js('''window.lockFetch=fetch;window.lockLoginAttempts=0;window.fetch=async(resource,options)=>{
              if(new URL(resource,location.href).pathname==='/api/v1/auth/login'){lockLoginAttempts++;await new Promise(resolve=>window.releaseLockLogin=resolve)}return lockFetch(resource,options)}''')
            await tab.click('#login-submit')
            await tab.js('byId("account-login").requestSubmit()')
            assert await tab.js('lockLoginAttempts===1&&!authenticated&&byId("login-password").readOnly&&byId("account-login").getAttribute("aria-busy")==="true"&&byId("lock-state").textContent==="Signing in…"')
            await tab.js('releaseLockLogin()')
            await tab.wait('!byId("login-submit").disabled&&Boolean(byId("access-status").textContent)')
            await tab.js('window.fetch=lockFetch')
            assert await tab.js('!authenticated&&byId("login-password").value.length===0&&byId("lock-password-shapes").children.length===0&&byId("login-password").getAttribute("aria-invalid")==="true"&&document.querySelector(".shell").inert')
            assert await tab.js('document.querySelector(".lock-quote").dataset.quoteId') == quote
            assert await tab.js('byId("access-status").getBoundingClientRect().bottom<=document.querySelector(".lock-account").getBoundingClientRect().top'), 'Mobile error feedback must clear the account row'
            await centered()
            await shot('invalid-password-390.png')
            report['invalid_login_clears_and_stays_locked'] = True
            report['pending_and_duplicate_submission_guard'] = True

            await tab.js('''window.fetch=(resource,options)=>new URL(resource,location.href).pathname==='/api/v1/auth/login'?
              new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Fixture timeout','AbortError')),{once:true})):lockFetch(resource,options);
              byId('login-password').value='fixture';byId('account-login').requestSubmit()''')
            await asyncio.sleep(15.2)
            await tab.wait('!byId("login-submit").disabled')
            assert await tab.js('!authenticated&&byId("access-status").textContent.includes("timed out")&&byId("login-password").value.length===0')
            await tab.js('window.fetch=lockFetch')
            report['timeout_retains_lock_and_allows_retry'] = True

            await tab.js('byId("login-password").value='+json.dumps(host.accounts.initial_password()))
            await tab.wait('byId("lock-password-shapes").children.length===byId("login-password").value.length')
            await tab.js('byId("login-password").focus()')
            await tab.js('byId("login-password").setSelectionRange(byId("login-password").value.length,byId("login-password").value.length);KlaudeLockScreen.syncPassword()')
            await asyncio.sleep(.1)
            assert await tab.js('(()=>{const cursor=document.querySelector(".shape-password-cursor"),r=cursor.getBoundingClientRect(),field=byId("lock-password-field").getBoundingClientRect();return cursor.hidden||(r.left>=field.left&&r.right<=field.right)})()'), 'Native editor and decorative cursor must stay inside the field'
            await tab.command('Input.dispatchKeyEvent', {'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'text':'\r'})
            await tab.command('Input.dispatchKeyEvent', {'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
            await tab.wait('authenticated&&latest?.session_id&&byId("local-access").hidden')
            assert await tab.js('!document.querySelector(".shell").inert&&byId("login-password").value.length===0')
            report['autofill_and_enter_authenticate'] = True
            await tab.js('showView("settings");showSettingsSection("theme")')
            await tab.click('input[name="appearance"][value="dark"]')
            await tab.click('input[name="palette"][value="cocoa"]')
            await tab.click('#theme-apply')
            assert await tab.js('appearance.theme==="dark"&&appearance.palette==="cocoa"'), 'Use the real Theme Settings Apply workflow'
            await tab.command('Emulation.setDeviceMetricsOverride', {'width':1440,'height':900,'deviceScaleFactor':1,'mobile':False})
            await shot('theme-dark-cocoa-settings.png')
            await tab.js('stream?.close();stream=null;clearInterval(pollTimer)')
            await tab.command('Network.clearBrowserCookies')
            await tab.js('snapshot().catch(showError)')
            await tab.wait('!authenticated&&!byId("local-access").hidden')
            assert await tab.js('byId("lock-state").textContent==="Session expired"&&document.querySelector(".shell").inert')
            next_quote = await tab.js('document.querySelector(".lock-quote").dataset.quoteId')
            assert next_quote != quote, 'An actual new lockscreen opening advances the shuffled bag'
            assert await tab.js('performance.getEntriesByType("resource").every(r=>new URL(r.name).origin===location.origin)'), 'Login and quotes must use only same-origin resources'
            report['quotes_bundled_attributed_stable_and_rotate_on_reopen'] = True
            report['mobile_password_bottom_row'] = True
            report['mobile_group_centered_in_available_space'] = True
            report['session_expiry_relocks'] = True
            assert await tab.js('document.documentElement.dataset.theme==="dark"&&document.documentElement.dataset.palette==="cocoa"&&getComputedStyle(byId("local-access")).getPropertyValue("--primary-container")===getComputedStyle(document.documentElement).getPropertyValue("--primary-container")')

            # A user-supplied timestamp exercises midnight and timezone conversion
            # through the actual shared renderer's pure local-time projection.
            state = await tab.js('KlaudeLockScreen.clockState(new Date("2026-12-31T17:00:00Z"))')
            assert (state['hour'],state['minute'],state['day'],state['month']) == ('00','00','1','01'), state
            await tab.command('Emulation.setTimezoneOverride', {'timezoneId':'America/New_York'})
            state = await tab.js('KlaudeLockScreen.clockState(new Date("2026-12-31T17:00:00Z"))')
            assert (state['hour'],state['day'],state['month']) == ('12','31','12'), state
            await tab.command('Page.removeScriptToEvaluateOnNewDocument', {'identifier':frozen['identifier']})
            await tab.command('Page.reload', {'ignoreCache':True})
            await tab.wait('typeof KlaudeLockScreen!=="undefined"&&document.documentElement.dataset.startup==="ready"')
            assert await tab.js('byId("lock-clock-hour").textContent===String(new Date().getHours()).padStart(2,"0")')
            assert await tab.js('document.querySelector(".lock-quote").dataset.quoteId') != next_quote, 'Reload resumes the bag without repeating the previous quote'
            report['timezone_midnight_and_live_reload'] = True
            assert await tab.js('document.documentElement.dataset.theme==="dark"&&document.documentElement.dataset.palette==="cocoa"&&getComputedStyle(byId("local-access")).getPropertyValue("--primary-container")===getComputedStyle(document.documentElement).getPropertyValue("--primary-container")'), 'Saved appearance is restored before sign-in'
            report['saved_theme_survives_expiry_and_login_reload'] = True
            assert not tab.errors, tab.errors
            report['browser_exceptions'] = tab.errors
            (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({**report,'layouts':len(report['layouts'])}))
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == '__main__':
    fixture.verify = verify
    fixture.main()

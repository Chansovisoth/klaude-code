"""Authenticated source/Markdown preview checks in isolated real Chrome.

Run: uv run --frozen --offline python scripts/webui_file_preview_smoke.py
No live models, personal files or external network requests are used.
"""

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
from klaude_tools.toolkit import Workspace
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import LocalWebHost
from PIL import Image
from webui_control_smoke import Tab
from webui_library_browser_smoke import CODE_PREVIEW, verify_code_preview

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.unit.test_webhost import _app  # noqa: E402

MARKDOWN = (
    '# Read me\n\n**Bold** and [unsafe](javascript:alert(1)).\n\n'
    '<script>window.previewExecuted=true</script>\n\n'
    '![remote](https://example.invalid/image.png)\n\n'
    '```python\ndef greet():\n\treturn "hello"\n```\n'
)
SOURCES = {
    "sample.py": CODE_PREVIEW,
    "sample.html": '<!doctype html>\r\n<html>\r\n\t<script>window.previewExecuted=true</script>'
                   '\r\n</html>\r\n',
    "sample.css": '/* multiline\r\n comment */\r\nbody { color: red; }\r\n',
    "sample.js": '// comment\nconst value = "hello";\n',
    "sample.ts": 'interface Value { name: string }\nconst value: number = 1;\n',
    "data.json": '{\n\t"name": "設計",\n\t"count": 2\n}\n',
    "readme.md": MARKDOWN,
    "long.txt": 'long ' * 6000,
    "many-lines.py": 'print("line")\n' * 110,
    "empty.txt": '',
}


async def verify(host, root, chrome):
    output = Path("/tmp/klaude-file-preview")
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
            await tab.command("Emulation.setDeviceMetricsOverride", {
                "width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False,
            })
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait('typeof byId!=="undefined" && !byId("local-access").hidden')
            await tab.js('byId("login-password").value=' + json.dumps(
                host.accounts.initial_password()
            ) + ';byId("account-login").requestSubmit()')
            await tab.wait('latest?.session_id && pollTimer!==null')

            async def activate(selector):
                point = await tab.js('''(() => {
                  const button=document.querySelector(''' + json.dumps(selector) + ''');
                  button.scrollIntoView({block:'nearest',inline:'nearest'});
                  const r=button.getBoundingClientRect(), x=r.x+r.width/2, y=r.y+r.height/2;
                  if (!r.width || !r.height || !button.contains(document.elementFromPoint(x,y)))
                    throw Error('Control is obscured: '+button.id);
                  return {x,y};
                })()''')
                for kind in ("mousePressed", "mouseReleased"):
                    await tab.command("Input.dispatchMouseEvent", {
                        "type": kind, **point, "button": "left", "clickCount": 1,
                    })

            async def open_file(name):
                if await tab.js('artifactDialog.open'):
                    await activate("#artifact-close")
                await tab.js('byId("artifact-query").value=' + json.dumps(name) + ';'
                             'byId("artifact-filter").requestSubmit()')
                await tab.wait('filePage?.total===1 && '
                               'filePage.items[0].name===' + json.dumps(name))
                await activate(".file-item button")
                await tab.wait('selectedArtifact?.name===' + json.dumps(name) +
                               ' || byId("artifact-preview").textContent.includes("Could not")')
                assert await tab.js('selectedArtifact?.name===' + json.dumps(name)), await tab.js(
                    '({preview:byId("artifact-preview").textContent,selected:selectedArtifact})'
                )

            await activate("#nav-library")
            await tab.wait('filePage?.items.length>0')
            await verify_code_preview(tab, activate, output)
            for name in ("sample.html", "sample.css", "sample.js", "sample.ts", "data.json"):
                await open_file(name)
                state = await tab.js('''(() => {
                  const preview=byId('artifact-preview'), pre=preview.querySelector('pre');
                  const first=preview.querySelector('.source-line-text').getBoundingClientRect();
                  const viewport=preview.getBoundingClientRect();
                  return {text:pre.textContent,tokens:pre.querySelectorAll('.token').length,
                    lines:pre.querySelectorAll('.source-line').length,
                    firstVisible:first.top>=viewport.top && first.top-viewport.top<=20,
                    unsafe:!!preview.querySelector('script,iframe,object,img,style') ||
                      !!window.previewExecuted};
                })()''')
                assert state["text"] == SOURCES[name], (name, state)
                assert state["tokens"] > 0 and state["firstVisible"] and not state["unsafe"], state
                assert state["lines"] == len(SOURCES[name].splitlines()) + 1, state
            await open_file("readme.md")
            assert await tab.js('byId("artifact-mode-preview").ariaPressed==="true" && '
                                '!!byId("artifact-preview").querySelector("h1,strong,.token") && '
                                '!byId("artifact-preview").querySelector("script,img,iframe") && '
                                '!window.previewExecuted && '
                                '![...byId("artifact-preview").querySelectorAll("a")].some('
                                'a=>a.protocol==="javascript:")')
            for theme in ("light", "dark"):
                for width in (360, 390, 768, 1280):
                    await tab.command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": 820, "deviceScaleFactor": 1, "mobile": False,
                    })
                    await tab.js('document.documentElement.dataset.theme=' + json.dumps(theme))
                    await asyncio.sleep(.3)
                    assert await tab.js('document.documentElement.scrollWidth<=innerWidth && '
                                        'artifactDialog.scrollWidth<=artifactDialog.clientWidth')
                    shot = await tab.command("Page.captureScreenshot", {"format": "png"})
                    (output / f"markdown-{theme}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
            await activate("#artifact-mode-source")
            assert await tab.js('byId("artifact-preview").querySelector("pre").textContent===' +
                                json.dumps(MARKDOWN))
            if await tab.js('artifactDialog.dataset.details==="closed"'):
                await activate("#image-details")
            await tab.wait('artifactDialog.dataset.details!=="closed"')
            assert await tab.js('byId("artifact-metadata").textContent.includes("readme.md")')
            await activate("#image-details")
            await open_file("long.txt")
            assert await tab.js('byId("preview-truncation").textContent.includes("truncated") && '
                                'byId("artifact-preview").querySelector("pre").textContent.length===16384')
            # The original download remains complete and byte-identical.
            downloaded = await tab.js('''(async()=>{
              const r=await fetch(byId("artifact-download").href);
              return {status:r.status,type:r.headers.get("Content-Type"),
                disposition:r.headers.get("Content-Disposition"),text:await r.text()};
            })()''')
            assert downloaded["status"] == 200 and downloaded["text"] == SOURCES["long.txt"]
            assert downloaded["type"] == "application/octet-stream"
            assert downloaded["disposition"].startswith("attachment;")
            downloads = root / "downloads"
            downloads.mkdir()
            await tab.command("Browser.setDownloadBehavior", {
                "behavior": "allow", "downloadPath": str(downloads),
            })
            await activate("#artifact-download")
            for _ in range(100):
                if (downloads / "long.txt").exists():
                    break
                await asyncio.sleep(.05)
            assert (downloads / "long.txt").read_text() == SOURCES["long.txt"]
            await open_file("many-lines.py")
            assert await tab.js('byId("preview-truncation").textContent.includes("truncated") && '
                                'byId("artifact-preview").querySelectorAll(".source-line").length===101')
            # The source region retains native keyboard scrolling.
            await tab.js('byId("artifact-preview").focus();'
                         'byId("artifact-preview").scrollTop=0')
            for kind in ("keyDown", "keyUp"):
                await tab.command("Input.dispatchKeyEvent", {
                    "type": kind, "key": "PageDown", "code": "PageDown",
                    "windowsVirtualKeyCode": 34,
                })
            await tab.wait('byId("artifact-preview").scrollTop>0')
            await open_file("empty.txt")
            assert await tab.js('byId("artifact-preview").querySelector("pre").textContent==="" && '
                                '!byId("preview-text-controls").hidden && '
                                'byId("preview-truncation").textContent===""')
            await activate("#artifact-close")
            # Exercise a stale file / failed authenticated metadata request.
            await tab.js('window.realPreviewFetch=fetch;window.fetch=(input,options)=>'
                         'String(input).includes("/library/item?") ? Promise.resolve(new Response('
                         'JSON.stringify({error:{code:"fixture",'
                         'message:"Fixture preview unavailable"}}),'
                         '{status:400,'
                         'headers:{"Content-Type":"application/json"}})) : '
                         'realPreviewFetch(input,options);'
                         'artifactDetails.clear()')
            await tab.js('byId("artifact-query").value="sample.py";'
                         'byId("artifact-filter").requestSubmit()')
            await tab.wait('filePage?.total===1 && filePage.items[0].name==="sample.py"')
            await activate(".file-item button")
            await tab.wait('byId("artifact-preview").textContent.includes("unavailable")')
            assert await tab.js('byId("image-toolbar").hidden && !selectedArtifact')
            await activate("#artifact-close")
            await tab.js('window.fetch=realPreviewFetch')
            assert not tab.errors, tab.errors
            assert await tab.js('!performance.getEntriesByType("resource").some('
                                'entry=>new URL(entry.name).origin!==location.origin)')
            result = {
                "source_wrap_layouts": 16, "markdown_layouts": 8,
                "syntax_languages": ["HTML", "CSS", "JS", "TS", "Python", "JSON"],
                "exact_source_whitespace": True, "literal_html": True,
                "copy_native_and_fallback": True, "download_complete": True,
                "truncation_empty_and_errors": True, "keyboard_scroll": True,
                "browser_exceptions": 0,
                "external_requests": 0, "screenshots": str(output),
            }
            (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    chrome = os.environ.get("KLAUDE_TEST_CHROME") or str(next(
        (Path.home() / ".cache/puppeteer/chrome-headless-shell").glob(
            "*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    ))
    with tempfile.TemporaryDirectory(prefix="klaude-file-preview-") as temporary:
        root = Path(temporary)
        config_module.CONFIG_DIR, config_module.DATA_DIR = root / "config", root / "data"
        cfg = Config(models={"coder": "fixture"})
        app = _app(root)
        app.agent.workdir, app.agent.workspace = root, Workspace(root)
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        service = LibraryManagement(cfg, root)
        for name, text in SOURCES.items():
            service.artifacts.import_bytes(text.encode(), "document", name)
        service.artifacts.import_bytes(b"binary\0bytes", "document", "unknown.bin")
        image = io.BytesIO()
        Image.new("RGB", (100, 60), "teal").save(image, "WEBP")
        service.artifacts.import_bytes(image.getvalue(), "media", "image-49.webp")
        accounts = AccountStore(cfg.config_dir)
        accounts.initialize()
        host = LocalWebHost(app, accounts=accounts, library=service, staging_dir=root / "staging")
        host.local_models = lambda: []
        serving = threading.Thread(target=host.serve_forever, daemon=True)
        serving.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, chrome), 120))
        finally:
            host.stop()
            serving.join(3)


if __name__ == "__main__":
    main()

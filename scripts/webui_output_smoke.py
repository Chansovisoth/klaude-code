"""Real Chromium checks for math, passive previews and exact file downloads.

Uses a temporary authenticated host and deterministic output; no model work.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import websockets
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_webhost.accounts import AccountStore
from klaude_webhost.host import STATIC, LocalWebHost
from PIL import Image
from webui_control_smoke import Tab
from webui_markdown_smoke import CHROME

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jz1kAAAAASUVORK5CYII="
)
SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 220">'
    '<rect width="400" height="220" rx="30" fill="#7653b9"/>'
    '<circle cx="110" cy="110" r="60" fill="#fff"/>'
    '<text x="200" y="120" fill="white" font-size="24">Klaude</text></svg>\n'
)
HTML = """<!doctype html><html><head><style>body{background:#eadfff}h1{color:#532c84}</style>
<meta http-equiv="refresh" content="0;url=https://example.invalid/leak"></head><body>
<h1>Preview works</h1><img src="https://example.invalid/leak" onerror="parent.pwned=1">
<script>parent.pwned=1;window.pwned=1;fetch('/api/v1/session')</script>
<a href="https://example.invalid/leak">Link</a><svg viewBox="0 0 10 10"><circle r="3"/></svg>
</body></html>\n"""
CODE = {
    "sample.py": 'print("Hello")\n',
    "sample.cpp": "int main() { return 0; }\n",
    "sample.cs": 'public class Greeter { public string Name = "Klaude"; }\n',
    "player.gd": 'extends Node2D\nfunc _ready():\n    print("Hello")\n',
    "sample.java": 'public class Main { public static String name = "Klaude"; }\n',
    "sample.txt": "Hello, Khmer ខ្មែរ\n",
    "drawing.svg": SVG,
    "page.html": HTML,
}
SYNTAX = {
    "cpp": CODE["sample.cpp"],
    "c++": CODE["sample.cpp"],
    "cs": CODE["sample.cs"],
    "c#": CODE["sample.cs"],
    "csharp": CODE["sample.cs"],
    "py": 'def greet():\n    return "Hello"\n',
    "python3": 'print("Hello")\n',
    "gd": CODE["player.gd"],
    "gdscript": CODE["player.gd"],
    "jar": CODE["sample.java"],
    "java": CODE["sample.java"],
    "html": '<div class="test"><script>window.syntaxExecuted=true;</script>Hello</div>\n',
    "xml": '<note id="1">Hello</note>\n',
    "svg": SVG,
    "css": ".test { color: red; padding: 10px; }\n",
    "js": 'const greet = () => "Hello"; // comment\n',
    "ts": 'const name: string = "Hello";\n',
    "language-cpp": CODE["sample.cpp"],
    "CSharp": CODE["sample.cs"],
    "script.gd": CODE["player.gd"],
    "main.cpp": CODE["sample.cpp"],
    "jsx": 'const view = <div title="Hello">Plain text {name}</div>;\n',
    "tsx": "const view: JSX.Element = <div>{name}</div>;\n",
    "php": '<div><?php echo "Hello"; ?></div>\n',
    "rs": 'fn main() { let greeting = "Hello"; }\n',
    "go": 'package main\nfunc main() { println("Hello") }\n',
    "kt": 'fun main() { val name = "Hello" }\n',
    "swift": 'let name: String = "Hello"\n',
    "rb": 'def greet\n  puts "Hello"\nend\n',
    "lua": 'local name = "Hello"\nprint(name)\n',
    "sh": 'echo "Hello" # comment\n',
    "ps1": 'Write-Output "Hello" # comment\n',
    "bat": "@echo off\nREM comment\necho Hello\n",
    "sql": "SELECT name FROM users WHERE id = 1;\n",
    "json": '{"name": "Hello", "ok": true}\n',
    "yml": 'name: "Hello"\nenabled: true\n',
    "toml": 'name = "Hello"\n',
    "dockerfile": 'FROM python:3.12\nRUN echo "Hello"\n',
    "cmake": 'set(NAME "Hello")\n',
    "gql": "query { user(id: 1) { name } }\n",
    "proto": 'syntax = "proto3"; message Hello { string name = 1; }\n',
    "tf": 'resource "local_file" "hello" { content = "Hello" }\n',
    "dart": 'void main() { final name = "Hello"; }\n',
    "jl": 'function greet()\n    return "Hello"\nend\n',
    "pl": 'my $name = "Hello"; # comment\n',
    "fs": 'let name = "Hello"\n',
    "vb": 'Dim name As String = "Hello"\n',
    "glsl": "uniform float time; void main() { gl_Position = vec4(1.0); }\n",
    "hlsl": "float4 main() : SV_Target { return float4(1, 0, 0, 1); }\n",
    "scss": "$color: red; .test { color: $color; }\n",
    "less": "@color: red; .test { color: @color; }\n",
    "nix": '{ name = "Hello"; enabled = true; }\n',
    "zig": 'const name: []const u8 = "Hello";\n',
    "ex": 'defmodule Hello do\n  def greet, do: "Hello"\nend\n',
    "erl": '-module(hello).\ngreet() -> "Hello".\n',
    "hs": 'greet :: String\ngreet = "Hello"\n',
    "clj": '(defn greet [] "Hello")\n',
    "sol": "pragma solidity ^0.8.0; contract Hello { uint value = 1; }\n",
}
SOURCE = (
    r"Inline $E=mc^2$ and \(\frac{a}{b}\), literal `$not_math$`, cost $5 and $10."
    "\n\n$$\n\\int_0^1 x^2\\,dx = \\frac{1}{3}\n$$\n\n"
    "\\[\\sum_{n=1}^{\\infty} \\frac{1}{n^2} = \\frac{\\pi^2}{6}\\]\n\n"
    + "\n\n".join(
        f"```{name.rsplit('.', 1)[-1]} filename={name}\n{code}```" for name, code in CODE.items()
    )
    + "\n\n![Pixel](data:image/png;base64,"
    + base64.b64encode(PNG).decode()
    + ")\n"
    + "\n```png filename=pixel.png\n"
    + base64.b64encode(PNG).decode()
    + "\n```\n"
    + "\nUnfinished $\\frac{\n\n```txt\n$leave code alone$\n```\n"
)


async def verify(host, root, remote, requests, jpg):
    downloads = root / "downloads"
    downloads.mkdir()
    profile = root / "chrome"
    process = subprocess.Popen(
        [
            CHROME,
            "--no-sandbox",
            "--disable-gpu",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        active = profile / "DevToolsActivePort"
        for _ in range(100):
            if active.exists():
                break
            await asyncio.sleep(0.05)
        port = int(active.read_text().splitlines()[0])
        with urlopen(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")) as r:
            target = json.load(r)
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=10_000_000) as ws:
            tab = Tab(ws)
            await tab.command("Runtime.enable")
            await tab.command("Page.enable")
            await tab.command(
                "Browser.setDownloadBehavior",
                {
                    "behavior": "allow",
                    "downloadPath": str(downloads),
                },
            )
            await tab.command("Page.navigate", {"url": host.origin})
            await tab.wait("typeof byId !== 'undefined' && !byId('local-access').hidden")
            await tab.js(
                'byId("login-username").value="admin";byId("login-password").value='
                + json.dumps(host.accounts.initial_password())
                + ';byId("account-login").requestSubmit()'
            )
            await tab.wait("authenticated && latest?.session_id && typeof katex !== 'undefined'")
            await tab.wait(
                "document.documentElement.dataset.startup==='ready' && "
                "!document.querySelector('.shell').inert"
            )
            await tab.js("window.outputArticle=messages.querySelector('.message.assistant')")
            assert await tab.js("outputArticle.querySelectorAll('math').length===4")
            assert await tab.js("outputArticle.querySelectorAll('.chat-math-display').length===2")
            assert await tab.js("outputArticle.textContent.includes('cost $5 and $10')")
            assert await tab.js("outputArticle.querySelector('code').textContent==='$not_math$'")
            assert await tab.js(r"""(() => {
                const doc=ChatMarkdown.renderDocument(
                  '$\\href{javascript:alert(1)}{bad}$ and $\\def\\a{\\a}\\a$');
                return !doc.querySelector('a,script,img') &&
                  doc.querySelectorAll('.chat-math-source').length>=1;
            })()""")
            await tab.wait("outputArticle.querySelector('.chat-output-thumbnail').naturalWidth===1")
            assert not requests, requests
            syntax = await tab.js(
                """((fixtures) => {
              const results=[];
              for (const [language,source] of Object.entries(fixtures)) {
                const article=document.createElement('article');
                article.className='message assistant';
                article.append(ChatMarkdown.renderDocument('```'+language+'\\n'+source+'```'));
                messages.append(article);
                const code=article.querySelector('.code-block code');
                const tokens=[...code?.querySelectorAll('.token')||[]];
                results.push({language, exact:code?.textContent===source,
                  tokens:tokens.length, colored:tokens.some(token=>
                    getComputedStyle(token).color!==getComputedStyle(code).color)});
                article.remove();
              }
              return results;
            })("""
                + json.dumps(SYNTAX)
                + ")"
            )
            assert all(item["exact"] and item["tokens"] and item["colored"] for item in syntax), (
                syntax
            )
            assert await tab.js("!window.syntaxExecuted")
            components = json.loads((STATIC / "vendor/manifest.json").read_text())[
                "prism_components"
            ]
            assert await tab.js(
                "((names)=>names.every(name=>name==='core'||"
                "Object.hasOwn(Prism.languages,name)))(" + json.dumps(components) + ")"
            )
            for language in ("unknown_language", "constructor", "__proto__", "txt"):
                assert await tab.js(
                    """((language) => {
                  const doc=ChatMarkdown.renderDocument('```'+language+'\\nhello\\n```');
                  const code=doc.querySelector('.code-block code');
                  return code?.textContent==='hello\\n'&&!code.querySelector('.token');
                })("""
                    + json.dumps(language)
                    + ")"
                )
            assert await tab.js("""(() => {
              const doc=ChatMarkdown.renderDocument('```jar\\npublic class Main {}\\n```');
              return !!doc.querySelector('[aria-label="Download code.java"]');
            })()""")
            for name, code in CODE.items():
                await asyncio.sleep(0.2)  # Stay below Chromium's rapid-download throttle.
                await tab.click('[aria-label="Download ' + name + '"]')
                for _ in range(100):
                    if (downloads / name).exists():
                        break
                    await asyncio.sleep(0.05)
                assert (downloads / name).read_bytes() == code.encode(), name
            for name in ("image.png", "pixel.png"):
                await asyncio.sleep(0.2)
                await tab.click('[aria-label="Download ' + name + '"]')
                for _ in range(100):
                    if (downloads / name).exists():
                        break
                    await asyncio.sleep(0.05)
                assert (downloads / name).read_bytes() == PNG, name
            for name, content in (("image.jpg", jpg), ("remote-photo.png", PNG)):
                await asyncio.sleep(0.2)
                await tab.click('[aria-label="Download ' + name + '"]')
                for _ in range(100):
                    if (downloads / name).exists():
                        break
                    await asyncio.sleep(0.05)
                assert (downloads / name).read_bytes() == content, name
            assert requests[0][0] == "/remote-photo.png", requests
            assert not requests[0][1].get("Cookie") and not requests[0][1].get("Referer")
            for language in ("SVG", "HTML"):
                await tab.click('[aria-label="Preview ' + language + '"]')
                await tab.wait("document.querySelector('.chat-output-frame')!==null")
                await asyncio.sleep(0.15)
                tree = await tab.command("Page.getFrameTree")
                frame = tree["frameTree"]["childFrames"][0]["frame"]["id"]
                context = await tab.command("Page.createIsolatedWorld", {"frameId": frame})
                inspection = await tab.command(
                    "Runtime.evaluate",
                    {
                        "contextId": context["executionContextId"],
                        "returnByValue": True,
                        "expression": "({svg:!!document.querySelector('svg[viewBox]'),"
                        "active:!!document.querySelector('script,iframe,meta[http-equiv],a[href],img[src]'),"
                        "title:document.querySelector('h1')?.textContent,"
                        "color:document.querySelector('h1')&&getComputedStyle(document.querySelector('h1')).color})",
                    },
                )
                state = inspection["result"]["value"]
                assert state["svg"] and not state["active"], state
                if language == "HTML":
                    assert (
                        state["title"] == "Preview works" and state["color"] == "rgb(83, 44, 132)"
                    )
                assert await tab.js(
                    "!window.pwned && document.querySelector('.chat-output-frame')"
                    ".getAttribute('sandbox')===''"
                )
                for theme in ("light", "dark"):
                    for width in (1440, 768, 390, 320):
                        await tab.command(
                            "Emulation.setDeviceMetricsOverride",
                            {
                                "width": width,
                                "height": 640,
                                "deviceScaleFactor": 1,
                                "mobile": width < 600,
                            },
                        )
                        await tab.js("document.documentElement.dataset.theme=" + json.dumps(theme))
                        assert await tab.js("document.documentElement.scrollWidth<=innerWidth")
                        assert await tab.js(
                            "(() => {const r=document.querySelector('.chat-output-dialog')"
                            ".getBoundingClientRect();return r.left>=0&&r.right<=innerWidth"
                            "&&r.top>=0&&r.bottom<=innerHeight})()"
                        )
                result = await tab.command("Page.captureScreenshot", {"format": "png"})
                (Path("/tmp") / f"klaude-chat-{language.lower()}-preview.png").write_bytes(
                    base64.b64decode(result["data"])
                )
                await tab.click('.chat-output-dialog [aria-label="Close preview"]')
                await tab.wait("!document.querySelector('.chat-output-dialog').open")
                await tab.wait(
                    "document.activeElement.getAttribute('aria-label')==='Preview " + language + "'"
                )
            await tab.click('[aria-label="Preview Pixel"]')
            await tab.wait("document.querySelector('.chat-output-stage img')?.naturalWidth===1")
            await tab.js("document.dispatchEvent(new Event('klaude-chat-session-changed'))")
            await tab.wait("!document.querySelector('.chat-output-dialog').open")
            await tab.click('[aria-label="Preview Remote"]')
            await tab.wait("document.querySelector('.chat-output-stage img')?.naturalWidth===1")
            await tab.click('.chat-output-dialog [aria-label="Close preview"]')
            for name in ("linked.svg", "linked.html"):
                await tab.click('[aria-label="Preview ' + name + '"]')
                await tab.wait("document.querySelector('.chat-output-frame')!==null")
                await tab.click('.chat-output-dialog [aria-label="Close preview"]')
            await tab.click('[aria-label="Download blocked-photo.png"]')
            await tab.wait("outputArticle.querySelector('.chat-file-status')!==null")
            # A late preview preparation must never reopen private content.
            await tab.js(
                "window.originalJSON=jsonRequest;window.pendingPreview=null;"
                "jsonRequest=(...args)=>args[0]==='/api/v1/chat-previews'?"
                "new Promise(resolve=>pendingPreview=resolve):originalJSON(...args)"
            )
            await tab.click('[aria-label="Preview SVG"]')
            await tab.js(
                "document.dispatchEvent(new Event('klaude-auth-reset'));"
                "pendingPreview({url:'/api/v1/chat-previews/'+'a'.repeat(32)});"
                "jsonRequest=originalJSON"
            )
            await tab.wait(
                "!document.querySelector('.chat-output-dialog').open && "
                "!document.querySelector('.chat-output-frame')"
            )
            assert not tab.errors, tab.errors
            print(
                "Chat output smoke passed: math, exact text/image downloads, isolated HTML/SVG, "
                f"{len(syntax)} syntax fixtures, 320–1440px light/dark, focus return, "
                "session/sign-out and late responses"
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


def main():
    from klaude_tools.toolkit import Workspace

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.unit.test_webhost import _app

    with tempfile.TemporaryDirectory(prefix="klaude-output-smoke-") as temp:
        root = Path(temp)
        config_module.DATA_DIR = root / "data"
        config_module.CONFIG_DIR = root / "config"
        accounts = AccountStore(Config(models={"coder": "fixture"}).config_dir)
        accounts.initialize()
        app = _app(root)
        app.agent.workdir = root
        app.agent.workspace = Workspace(root)
        app.turns.bind_workspace(app.session_id, str(root), expected_revision=0)
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), (100, 40, 160)).save(buffer, format="JPEG")
        jpg = buffer.getvalue()
        requests = []

        class RemoteImage(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                requests.append((self.path, dict(self.headers)))
                content, mime = {
                    "/remote-photo.png": (PNG, "image/png"),
                    "/blocked-photo.png": (PNG, "image/png"),
                    "/linked.svg": (SVG.encode(), "image/svg+xml"),
                    "/linked.html": (HTML.encode(), "text/html"),
                }[self.path]
                self.send_response(200)
                if self.path != "/blocked-photo.png":
                    self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

        remote_server = ThreadingHTTPServer(("127.0.0.1", 0), RemoteImage)
        remote = f"http://127.0.0.1:{remote_server.server_port}"
        remote_thread = threading.Thread(target=remote_server.serve_forever, daemon=True)
        remote_thread.start()
        source = (
            SOURCE
            + "\n\n![JPEG](data:image/jpeg;base64,"
            + base64.b64encode(jpg).decode()
            + ")\n\n"
            + f"![Remote]({remote}/remote-photo.png)\n\n"
            + f"![Blocked]({remote}/blocked-photo.png)\n\n"
            + f"[Linked drawing]({remote}/linked.svg)\n\n"
            + f"[Linked HTML]({remote}/linked.html)\n"
        )
        app.memory.log_turn(app.session_id, "assistant", source)
        host = LocalWebHost(app, accounts=accounts)
        host.local_models = lambda: []
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(asyncio.wait_for(verify(host, root, remote, requests, jpg), 90))
        finally:
            host.stop()
            thread.join(3)
            remote_server.shutdown()
            remote_server.server_close()
            remote_thread.join(3)


if __name__ == "__main__":
    main()

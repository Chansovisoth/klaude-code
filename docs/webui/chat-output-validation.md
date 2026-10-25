# Assistant math, previews and downloads

Implemented 2026-10-25 for the experimental browser host.

## Behavior

Assistant replies, AI Review and other shared Markdown readers support inline
`$…$` / `\(…\)` and display `$$…$$` / `\[…\]` LaTeX. Code spans and fences remain
literal. KaTeX 0.19.1 translates formulas into native MathML, using the browser's
math layout and fonts without a CDN or remote font dependency. Invalid,
unsupported or incomplete expressions retain readable source. Each formula is
bounded to 8,192 characters, 500 expansions and a 20-em requested size; macros
are fresh per expression and trusted HTML/URL commands are disabled. Existing
128,000-character Markdown and 10,000-token bounds remain in force.

Every code fence has Copy and Download. Known language names map to conventional
extensions (Python → `.py`, C++ → `.cpp`, HTML → `.html`, text → `.txt`, and so on).
The optional info field `filename=example.py` or a filename as the first fence
word supplies a sanitized download name. Downloaded text preserves the parsed
code's whitespace and UTF-8 characters; downloading never writes workspace files
or imports a Library record. SVG and HTML fences add Preview. Base64 PNG, JPEG,
GIF and WebP fences validate their format signature and download decoded bytes;
invalid raster fences remain text with a `.txt` suffix.

Markdown images provide Preview and Download. Embedded raster data and allowlisted
authenticated Library/attachment URLs show inline thumbnails. External images
load only after an explicit Preview or Download click, with no referrer. Common
file links also gain Download and, for supported images/HTML/SVG, Preview actions.
Remote downloads use browser CORS, omit credentials, reject redirects, have a
20-second deadline and stop at 8 MiB. A source that blocks access keeps its
original link and gets visible guidance to save from that source. No server-side
image proxy or public artifact URL is introduced.

The native viewer supports Escape, an explicit Close button, outside dismissal,
focus return and bounded phone/desktop geometry. Conversation switches, sign-out
and page exit close previews, abort downloads and revoke object URLs; asynchronous
preparation results cannot reopen a closed viewer.

## Syntax coloring

The local Prism 1.30.0 bundle now contains over 75 language grammars, with 80
components including core and dependencies. Coverage includes C/C++, C#, Python,
GDScript, Java, HTML/XML/SVG, CSS/SCSS/Sass/Less, JavaScript/TypeScript/JSX/TSX,
PHP, Ruby, Go, Rust, Swift, Kotlin, Scala, Dart, Lua, R, MATLAB, Julia, Perl,
PowerShell, Bash, batch, SQL, JSON/JSON5, YAML, TOML, Markdown, Docker, CMake,
Makefile, GraphQL, Protocol Buffers, Terraform/HCL, Nix, Zig, F#, VB.NET,
Objective-C, GLSL/HLSL, assembly, WebAssembly, Elixir, Erlang, Haskell, Clojure,
Fortran, Groovy, Solidity, VHDL/Verilog, Lisp, Pascal and COBOL. The manifest's
`prism_components` is the exact bundled inventory.

Language names are case-insensitive. Common extension aliases include `cpp`,
`c++`, `cs`, `c#`, `py`, `gd`, `js`, `ts`, `kt`, `rs` and `ps1`; filename fences
such as `main.cpp` and `player.gd` also resolve their grammars. `language-cpp`
and `lang-csharp` prefixes work. `jar` fences use Java source coloring and default
to a `.java` download; actual binary JAR archives have no source syntax coloring.
Download extensions also follow canonical grammar names for aliases.

Prism's before/after tokenize hooks preserve embedded PHP and JSX/TSX text. All
resulting tokens still become bounded text nodes and spans; the renderer never
inserts Prism-generated HTML. Keywords, strings, comments, numbers, functions,
built-ins, constants, variables, annotations and decorators share existing theme
colors. Unknown names and code beyond the existing 12,000-character highlighting
bound retain exact readable text with Copy and Download.

Vendor refresh uses the pinned `components.json` metadata to include required
dependencies and order selected optional/modified grammars correctly. Bundles
remain entirely local and retain verified npm integrity, MIT notices and asset
hashes in `vendor/manifest.json`.

## Preview isolation

`chat_previews.py` serializes allowlisted passive HTML/SVG into a standalone
document. Text and attribute values are escaped; scripts, embedded frames,
templates, forms, refresh directives, event handlers, navigation targets and
external resource URLs are removed. Inline CSS and raster data images are
supported. HTML/SVG previews are static; interactive JavaScript and remote assets
are unavailable. Original Download preserves the original source independently
of the preview serialization.

Preparing a preview uses owner cookie, Origin and CSRF checks. The host retains
at most eight documents in memory with five-minute expiry, and sign-out/shutdown
revoke them. An owner-scoped GET loads the document into an iframe with an empty
sandbox attribute. Its response independently applies CSP `sandbox`,
`script-src 'none'`, `connect-src 'none'`, `form-action 'none'`, `frame-src 'none'`
and `frame-ancestors 'self'`. Inline styles are allowed only in this passive
response. The parent page keeps `script-src 'self'`, `object-src 'none'`,
`frame-ancestors 'none'`, and adds same-origin frames plus HTTP(S) image and
browser download connections. These presentation operations never claim control,
start a model turn or use the domain mutation journal.

## Source and maintenance

- `static/markdown.js`: math tokens, native MathML, download controls, viewers,
  file links, source validation, bounds and private-result lifecycle.
- `chat_previews.py` / `host.py`: passive serialization, owner cache, protected
  routes, preview-specific CSP, fixed KaTeX asset route and parent CSP.
- `static/style.css` / `index.html`: responsive controls/viewer and local script.
- `main.py`: model formatting instructions describe supported math and previews.
- `static/app.js`: startup respects an inert sign-in screen during its exit
  animation, so completing startup restores chat interaction and focus.
- `scripts/vendor_webui_math.py`: verifies npm archive SHA-512 integrity and
  vendors only the pinned browser build/license; `vendor/math-manifest.json`
  records version, provenance and asset SHA-256 hashes. No package scripts run.

KaTeX's [options](https://katex.org/docs/options) and
[security guidance](https://katex.org/docs/security) inform the trust and
expansion limits. Native MathML requires a browser with MathML Core support.

## Validation

Focused server and Chromium checks use isolated temporary workspaces/accounts;
they perform no live model work or production-host restart. The browser fixture
checks native equations, currency/code preservation, exact UTF-8 code and image
download bytes, passive frame content/styles, 320/390/768/1440px light/dark
geometry, focus restoration, session/sign-out cleanup and late-response rejection.
The existing Markdown fixture covers streamed block identity, copy/selection,
message actions and conversation links.

Results: **64 passed** across preview, host, Library and image-handoff unit tests.
Both `webui_output_smoke.py` and `webui_markdown_smoke.py` passed in Chromium.
The output fixture additionally verifies real JPEG bytes, remote CORS downloads
without credentials/referrers, explicit remote-image loading, linked HTML/SVG
previews, visible blocked-download feedback and bounded untrusted math fallback.
The syntax extension checks every component is registered and exercises actual
colored DOM tokens, exact source preservation, untrusted HTML-as-code and safe
unknown-language fallback across **58 language/alias fixtures**. C#,
GDScript and Java source downloads are compared byte-for-byte as well.
JavaScript syntax checks, focused Ruff checks and mypy for the three changed
production Python files passed. Viewer screenshots are
`/tmp/klaude-chat-svg-preview.png` and `/tmp/klaude-chat-html-preview.png`; existing
Markdown screenshots are under `/tmp/klaude-markdown-preview`.

Commands:

```sh
.venv/bin/python -m pytest tests/unit/test_chat_previews.py tests/unit/test_webhost.py \
  tests/unit/test_webhost_lens.py tests/unit/test_web_library.py -q
.venv/bin/python scripts/webui_output_smoke.py
.venv/bin/python scripts/webui_markdown_smoke.py
```

Existing running hosts need a restart and browser reload for the new fixed
asset/preview routes and model instructions. Missing preview routes show explicit
restart guidance; missing KaTeX leaves readable formula source. This implementation
does not establish that a running production host has loaded these changes.

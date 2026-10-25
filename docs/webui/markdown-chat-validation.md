# WebUI Markdown chat validation

Validated 2026-10-20. Assistant replies now render Markdown during streaming and
when loading saved history. User messages remain literal text. Storage and exports
retain the original response text.

## Behavior

- CommonMark-based paragraphs, headings, emphasis, lists, blockquotes, inline and
  fenced code, plus tables, strikethrough, autolinks and disabled task checkboxes.
- Local syntax highlighting for common programming/configuration languages.
  Unsupported languages retain readable plain code. Code and tables scroll inside
  their own containers on narrow screens.
- Code headers pin the language and icon-only Copy control within the code block
  as the conversation scrolls. Copy shows a checkmark after success and retains
  its accessible name; internal code scrolling keeps the header visible too.
- Copy controls preserve the original response or exact code text, including a
  trailing newline. The HTTP clipboard fallback selects a temporary text node
  without focusing an input or shifting the viewport.
- Streaming updates are coalesced. Unchanged blocks retain their DOM nodes;
  selected or focused blocks defer replacement. The completed response reuses its
  streaming article through the authoritative session snapshot. Readers who have
  scrolled up keep their position.
- A browser-only system instruction requests useful Markdown while respecting
  explicit plain-text or structured-output requests. Terminal prompts are unchanged.

## Reply action row

Assistant replies, including saved history, have five controls beneath the body:
overlapping-square Copy, speaker Read aloud (Stop during playback), connected-node
Share, vertical-dot More options, and an open book with Sources. All wait for the
reply to finish streaming. The compact row fits a 320-pixel viewport.

Copy preserves raw Markdown. More opens a compact menu with the saved timestamp,
Branch in new chat and Retry; details and behavior are in
[message-menu validation](message-menu-validation.md). Read aloud uses browser speech synthesis with 1,200-character
chunks, prefers a matching local voice, and cancels on Stop, sign-out, page exit
or removal of its message. Unsupported speech is disabled; speech errors reset
playback and announce that a device voice may be unavailable.

Share opens a dialog with **Copy link** and **Share via**. The link identifies
the selected saved message and its conversation on the current server. It
requires owner sign-in and is not a published transcript snapshot. Links exclude
bootstrap fragments and
unrelated query parameters. Share via calls `navigator.share({title, url})` directly
from the click, preserving its transient user activation. It checks the secure
context, API availability and optional `navigator.canShare` result. The dialog
also shows a two-column grid of labeled WhatsApp, Telegram, Discord and Email
icons, including when native sharing is available. WhatsApp, Telegram and Email
prefill the selected message URL. Discord opens the native device share sheet
directly from its click, with guidance to choose Discord. It has the same plain
icon-and-name label as the other apps. It does not copy the link automatically
or claim delivery to Discord. If system sharing is unavailable or blocked, the
dialog explains the restriction and points to the browser's Share menu or the
separate Copy link action. Native sharing
requires a secure context: localhost may qualify, while plain HTTP LAN addresses
do not. App destinations receive only the selected message URL when clicked.
Cancelling native sharing is silent. No public hosting or anonymous access is
enabled.

Conversation links select their session only after authentication, through the
normal controlled session selector and workspace/runtime checks. An active turn
or queue blocks switching. A handled link records browser history state so a
later reload preserves the tab's selected page. Explicit session changes update
the linked session and clear the old message target, avoiding a return to an
older conversation on reload.

Message links carry the exact saved reply ID as well as the session ID. Opening
one focuses, highlights and scrolls to that reply. The border stays visible for
three seconds and fades over 400 ms without removing focus. Reduced motion keeps
the same three-second hold and clears the border immediately. If it has fallen outside the
latest 100-message window, a session-scoped public read returns that single
message (at most 16,000 text characters), with a visible gap before recent
messages. The selected earlier message survives later snapshots without losing
DOM identity or focus. Missing targets report that the message is unavailable;
malformed or duplicate identifiers are rejected. No public access is enabled.

The link-sharing browser follow-up verified the two exact action labels,
token-free URL copying, native URL-only share payload, HTTP clipboard fallback,
return to the selected conversation after sign-in, rejection of malformed links,
and Settings remaining selected on reload. The synthetic model uses the shared
runtime-checked resume service in place of live Ollama catalog verification;
production model verification is unchanged. The exact-message follow-up also
verified different links for two replies in the same session, an older target
after 120 newer messages, focused target retention across snapshots, message
navigation after sign-in, unavailable targets and malformed message IDs.
Focused WebUI/session tests passed: **49 passed**. Ruff, JavaScript syntax and
production mypy passed for the changed production files. No full repository
suite or live model evaluation is claimed for this follow-up.

Sources deduplicates up to 100 HTTP/HTTPS links cited in the reply, excluding
image URLs, unsafe destinations and code samples. The dialog describes these as
references linked in the reply and explicitly says when none were included.
The current public message contract has no independent verified-source inventory;
linked references are not proof that a tool fetched or verified a page.

The extended `scripts/webui_markdown_smoke.py` passed for row placement,
streaming action gates, Copy link, native URL share payload and HTTP fallback,
authenticated link navigation and page-preserving reload, Sources and its empty
state, timestamp menu, exact-message branching, Retry, speech chunk/stop/sign-out
behavior with API doubles, and all four viewport widths. Native OS share sheets
and audible device voices still need device-level checks. JavaScript syntax and
Ruff checks passed. The initial action-row follow-up did not rerun the Python
suite; the subsequent message-menu change has focused Python validation in the
linked notes.

The 2026-10-20 app-sharing follow-up exercised native support, `canShare=false`,
denied native sharing and silent cancellation in real Chrome with API doubles.
A second Chrome run used an actual insecure HTTP origin (without replacing
`navigator.share`): `isSecureContext` was false and the API was absent. It verified
the visible WhatsApp, Telegram and Email links, intercepted all three navigation
destinations, and checked 1440, 390 and 320 pixel layouts with 44px actions and no
console exceptions. This validates the browser's app-link handoff and URL payload;
physical iOS/Android/desktop OS sheets and installed-app delivery remain untested.

The social-icon follow-up added locally embedded WhatsApp, Telegram and Discord
SVG paths from pinned [Simple Icons 15.13.0](https://github.com/simple-icons/simple-icons/tree/15.13.0/icons),
plus the app's outline envelope icon for Email. Original SVG hashes, source URLs
and the CC0 license ship in `static/share-icons-LICENSE.txt`; opening the dialog
does not fetch external icon resources. The icons inherit the current palette
and keep text labels and accessible names.

The earlier social-icon follow-up verified local icons and the then-current
Discord copy/open fallback. That fallback has now been replaced by native
sharing at the user's request. The separate Copy link action still owns copying.
The browser cannot choose a target app, discover whether Discord is installed,
or confirm which app received a share: the user selects a target in the native
sheet. See the [Web Share target selection contract](https://www.w3.org/TR/web-share/#share-method)
and [privacy model](https://www.w3.org/TR/web-share/#privacy-considerations).
Discord's [Embedded App SDK](https://docs.discord.com/developers/developer-tools/embedded-app-sdk#sharelink)
belongs to Discord Activities; this browser host does not embed that SDK.

The replacement Chrome smoke passed with a trusted Discord-button click:
`navigator.share({title, url})` received the exact message URL with active user
activation, both native-share buttons remained disabled while its promise was
pending, and cancellation cleared the status and restored the buttons. An API
double verified the native handoff; no clipboard call occurred. The same smoke
retained its four viewport sizes, sixteen palette combinations, message actions
and streaming checks, with no JavaScript exceptions or external requests.
A real insecure HTTP run confirmed that Discord reports the system-sharing
restriction, performs no copy, and keeps all four app targets within 320, 390 and
1440 pixel layouts. Actual OS target lists and delivery remain device checks.
JavaScript syntax, Ruff for the smoke script and `git diff --check` passed.

Browser API references reviewed 2026-10-20:
[Web Share](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/share),
[speech synthesis](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis),
and [utterance lifecycle](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance).

## Rendering boundary and dependencies

`static/markdown.js` builds an explicit set of DOM elements from markdown-it
tokens; model output is never inserted as HTML. Raw HTML is disabled. Links allow
absolute HTTP, HTTPS and mailto destinations with isolated new tabs. Relative and
unsafe destinations are inert. External images retain explicit preview/download
actions; only embedded raster and allowlisted authenticated image paths have
automatic thumbnails. Prism tokens become text nodes and spans, without its HTML
renderer. Scripts remain restricted to local assets; user-requested HTTP(S) image
previews and browser CORS downloads have explicit CSP allowances.

Markdown parsing is bounded at 128,000 characters and 10,000 tokens. Code
highlighting is bounded at 12,000 characters per block. Oversized text or an absent
parser uses literal text. LaTeX now renders through local KaTeX/native MathML;
HTML and SVG code fences have isolated static previews. Mermaid remains code.
See [chat output support](chat-output-validation.md) for the newer controls,
security boundary, limits and browser coverage.

Pinned browser bundles are markdown-it 15.0.2 and Prism 1.30.0, including their
licenses and bundled dependency notices. `static/vendor/manifest.json` records
archive integrity and asset hashes. `scripts/vendor_webui_markdown.py` rebuilds
the fixed bundles from verified archives without npm installation or package
scripts. Browser rendering requires no CDN or external service.

The host serves the new scripts through its fixed asset allowlist. Restart a host
running older Python code and reload the browser to load the renderer. The app
retains literal-text fallback when the renderer is unavailable.

## Evidence

Focused tests: **52 passed in 45.10s** across `test_webhost.py`,
`test_web_accounts.py` and `test_web_library.py`. They include the local asset
allowlist, exact bundle hashes, licenses, unchanged CSP, path traversal rejection
and WebUI formatting instruction.

`scripts/webui_markdown_smoke.py` passed in headless Chrome against an isolated
loopback host, temporary profile/stores and a deterministic agent emitting real
shared-worker SSE events. It verified:

- Streamed Markdown, final snapshot promotion and saved-history reload.
- Formatting, task/table semantics, local syntax highlighting and literal user text.
- Response/code copy and the HTTP fallback's exact text without viewport movement.
- Stable code scrolling and text selection through streaming and completion.
- Layouts at 320, 390, 768 and 1440 pixels and six theme combinations.
- Coalesced updates, deferred selected blocks, reader scroll preservation,
  oversized-text fallback and missing-parser fallback.
- Logout cleanup, no external resource requests and no JavaScript console errors.

Clipboard APIs and fallback copy events use controlled browser fixtures to verify
payloads; this does not certify OS clipboard permission behavior on every device.
Viewport emulation does not certify physical mobile keyboard/browser-bar behavior
or full assistive-technology acceptance. No live model/provider generation was
needed for these checks.

Ruff, JavaScript syntax checks and production WebUI mypy passed. The WebUI wheel
built successfully, was installed into an isolated target, and its installed
scripts, licenses and asset hashes were verified. The full repository suite and
seven-package distribution smoke were not run for this change.

### Running-host follow-up

The live managed host was still running Python loaded before the Markdown asset
routes were added. It served updated `index.html` and `app.js` from disk but
returned HTTP 401 for `/markdown.js` and both vendor scripts, triggering literal
fallback in every session. A browser refresh alone could not update these routes.

After confirming the host was idle with no queued work, it was stopped through
its managed control socket and restarted with the exact workspace, session and
LAN listener. The public saved history was unchanged, and all three scripts
returned HTTP 200 with bytes matching source. Headless Chrome loaded those live
scripts and rendered the actual saved `bbd8dc84` replies (14 bold spans, six lists,
14 list items and 13 code spans), plus the other recent workspace session. No
messages were submitted, session switches performed or model generation invoked.
Existing browsers need to reload and sign in after the managed restart.

Run the browser check with the workspace development environment and `websockets`
installed:

```sh
.venv/bin/python scripts/webui_markdown_smoke.py
```

Set `KLAUDE_TEST_CHROME` when Chrome is not discoverable and
`KLAUDE_MARKDOWN_SCREENSHOTS` to change its screenshot directory (default
`/tmp/klaude-markdown-preview`). The script owns and stops its temporary host and
browser; it does not use a running user session.

## Primary references reviewed

Markdown is a practical shared baseline for AI chat, rather than a promise of
identical behavior across proprietary renderers. These sources informed this
implementation (reviewed 2026-10-20):

- [CommonMark-based GFM specification](https://github.github.com/gfm/) for familiar
  formatting extensions.
- [OpenAI ChatGPT prompting guide](https://developers.openai.com/cookbook/examples/chatgpt/chatgpt_prompt_guide/chatgpt_prompt_guide)
  and [Claude Sonnet system prompts](https://platform.claude.com/docs/en/release-notes/system-prompts/claude-sonnet-4-5)
  for Markdown output conventions.
- [markdown-it security guidance](https://github.com/markdown-it/markdown-it/blob/master/docs/safety.md)
  and [release history](https://github.com/markdown-it/markdown-it/blob/master/CHANGELOG.md)
  for raw HTML, links and the pinned parser version.
- [Prism token API](https://prismjs.com/extending.html) and
  [1.30.0 release](https://github.com/PrismJS/prism/releases/tag/v1.30.0).
- [W3C chat log technique](https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA23.html)
  for polite, non-atomic chat updates. The message log uses these attributes;
  full screen-reader acceptance remains separate.

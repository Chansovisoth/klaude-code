# Loading skeleton validation

Implemented and checked 2026-10-20. Slow data reads show compact, themed skeletons
instead of a blank area or a stand-alone “Loading…” line. A 120 ms delay avoids
showing placeholders for fast responses. Static page headings, forms and controls
remain available.

## Covered surfaces

| Surface | Pending presentation |
| --- | --- |
| Initial conversation, session changes and older linked messages | Conversation lines outside the streaming message log |
| Conversation drawer | Five compact session rows |
| Local model inventory | A text placeholder in the model status area |
| Library and Skills | Card shapes; file/image blocks only where the card has artwork |
| Library/Integration counts | Blank pill shapes while unknown; known counts remain visible |
| Knowledge sources | Source cards in the visible sources section |
| Workspace browsing, file reads, search and Git reads | Code-like lines in the result area |
| Saved item preview | Dialog opens immediately with a bounded preview placeholder |
| Activity operation inventory | Operation rows on its initial read |
| Image thumbnails | Stable existing thumbnail area pulses until load/error |

Settings is currently local UI and needs no fabricated loading state. Live agent
activity, accepted operation progress and review/submit status keep their real
controls and progress text.

## Lifecycle

`beginLoading` in `app.js` owns each target's timer, placeholder and `aria-busy`
state. Only the current request can finish its loader. A new filter, page or
resource clears content from the previous context; a refresh of the same context
keeps loaded content visible. Library/workspace refresh errors retain valid old
data with a real error message. Model refresh failures retain the known catalog.

Requests finish loaders on success, empty results and errors. Logout cancels all
active timers, clears private displayed content and rejects late read results.
Closing a pending preview invalidates its request, so a response cannot reopen
the dialog or activate actions for another item. Workspace reads check their
request, auth and session identity; Library requests retain their existing
generation guards. Normal snapshot refreshes never replace streamed chat DOM with
a skeleton.

Placeholder bars are decorative and non-interactive. Loading status and busy
attributes describe the real wait. Both system reduced-motion preferences and
the app's reduced-motion setting disable the pulse animation. No new assets,
external services, dependencies or HTTP routes are required.

## Validation

`scripts/webui_loading_smoke.py` passed against an isolated loopback host and a
temporary Chrome profile. Initial authentication/history reads use the host;
domain reads use controlled browser responses and delays. It checks:

- Initial chat, session and model skeletons; normal chat refresh retains its DOM.
- Library, counts, Sources, Skills, workspace and operation skeletons.
- Preview opens before its data arrives; closing it rejects the late result.
- A fast preview response inserts no skeleton, verified with a DOM observer.
- Same-context refresh retains the original node, including after read failure.
- An old response cannot replace new data or clear a newer request's busy state.
- Empty responses finish loading and display the actual empty state.
- Reduced motion, 320/390/1440-pixel layouts and no page horizontal overflow.
- Logout clears active skeletons and prevents late Library/model responses from
  repopulating private content.

No JavaScript console errors were recorded. Screenshots were inspected under
`/tmp/klaude-loading-preview`.

The current `scripts/webui_markdown_smoke.py` also passed: streaming/selection,
copy, code scrolling, message links/sign-in, Branch/Retry, speech API fixtures,
page restoration, four widths and six color themes remained covered.

JavaScript syntax checks for `app.js` and `library.js`, Ruff for the loading smoke
script, and `git diff --check` passed. This change adds no Python production code;
the Python suite was not rerun. Browser fixtures do not certify physical mobile
keyboard behavior, native OS speech/sharing or full assistive-technology
acceptance.

Run with the workspace development environment and `websockets` installed:

```sh
.venv/bin/python scripts/webui_loading_smoke.py
```

`KLAUDE_TEST_CHROME` can select a Chrome executable. The script owns and stops its
temporary host/browser and performs no live model generation or user-session
mutations. Reload the WebUI to load the updated scripts and markup.

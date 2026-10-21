# File preview refinement

## Plan and constraints

Inspected the dirty worktree, native `artifact-detail` viewer/gestures, shared
CSS, bundled Prism/Markdown renderer, `ArtifactStore.preview()` and the application
detail projection. Preserve all concurrent Activity, attachment and UX changes.
No dependencies, new routes, commit or push.

1. Add optional bounded source text to the existing preview contract. Preserve
   tabs, indentation and line endings without changing the legacy CLI lines.
   Keep the existing 16 KiB read and 100-line bounds, private/authenticated IDs
   and control-character sanitization; report source truncation separately.
2. Expose the existing bounded DOM-only syntax and Markdown rendering helpers.
   Add a read-only numbered source view, contextual Wrap/Copy/Markdown controls,
   shared compact Download/Details and clear source-limit notices.
3. Reuse the image viewer header/content/toolbar and metadata sheet; apply text
   layout rules only to non-image content. Uploaded HTML/scripts remain text,
   Markdown raw HTML stays disabled and images remain explicit links.
4. Check real authenticated text/code/Markdown previews, whitespace, bounds,
   long lines, clipboard/download, errors and responsive themes in Chrome.
   Recheck existing image gestures and shared Markdown rendering.

## Validation

Final focused suite: **81 passed** across `test_library_artifacts.py`,
`test_library_management.py` and `test_web_library.py`. Includes exact CRLF/tabs,
long lines, the byte/line limits, a multibyte character crossing the read bound,
invalid text/control replacement, empty BLOBs, unchanged saved bytes and legacy
terminal lines, authenticated public projections and complete attachment downloads.

Real authenticated Chrome 148 with isolated stores:

- `scripts/webui_file_preview_smoke.py`: 16 code Wrap/No wrap states across
  light/dark and 320/390/768/1440px; eight Markdown layouts across light/dark and
  360/390/768/1280px. HTML, CSS, JS, TS, Python and JSON use the bundled
  highlighter. Checks exact DOM source text and line numbers, the first visible
  line, internal scrolling, control sizing, native/HTTP clipboard paths,
  Markdown modes, details, truncation, empty/binary files, failed previews,
  keyboard scrolling and a real downloaded file matching the original.
  Zero browser exceptions or external resource requests.
- `scripts/webui_image_preview_smoke.py`: all 12 responsive light/dark layouts
  passed, including portrait/landscape, pinch/pan/swipe/double-tap, keyboard
  navigation, metadata caching, reviewed source/tags/archive/delete, deletion
  cancellation, reduced motion and sign-out cleanup.
- `scripts/webui_markdown_smoke.py`: all 24 existing checks passed, including
  streamed Markdown, selection/scroll retention, clipboard paths, literal unsafe
  content, theme palettes and missing-parser fallback.
- `scripts/webui_loading_smoke.py`: all 19 existing checks passed, including
  preview cancellation/errors, retained refresh content, stale responses,
  narrow layouts and sign-out cleanup.

Visually inspected the captured 320px code, 360px Markdown and 1440/1280px desktop
previews. Content starts near the top of its own scroll surface, long source
lines scroll within that surface, and the compact controls remain below it.
Desktop retains the adjacent details panel; mobile retains the existing optional
details sheet and safe-area frame. Duplicate collection text in the header and
an existing empty-BLOB preview exception found during checks were fixed.

Repository Ruff, production mypy (212 files), both changed JavaScript syntax
checks and `git diff --check` passed. All seven workspace wheels built/installed,
package imports and both installed CLI help commands passed. The first packaging
attempt was blocked by sandbox DNS; the network-enabled isolated retry passed.
No dependencies or lockfile changes were introduced. The full repository unit
suite was not run for this targeted change.

Artifacts (temporary local paths):

- `/tmp/klaude-file-preview/results.json`
- `/tmp/klaude-file-preview/code-{wrap,no-wrap}-{light,dark}-{1440,320}.png`
- `/tmp/klaude-file-preview/markdown-{light,dark}-{360,390,768,1280}.png`
- `/tmp/klaude-image-preview/` and `/tmp/klaude-markdown-preview/`

## Changed files

| File | Purpose |
| --- | --- |
| `apps/webhost/src/klaude_webhost/static/library.js` | Numbered source DOM, language selection, modes/Copy/Wrap, compact actions, consistent metadata and errors |
| `apps/webhost/src/klaude_webhost/static/markdown.js` | Reuse bounded DOM-only highlighting and safe document rendering |
| `apps/webhost/src/klaude_webhost/static/index.html` | Shared header subtitle and source-limit notices |
| `apps/webhost/src/klaude_webhost/static/style.css` | Text-only density, line gutters, wrapping and responsive toolbar rules |
| `packages/core/src/klaude_core/library_artifacts.py` | Optional faithful bounded source projection; empty-BLOB fix |
| `packages/application/src/klaude_application/library_management.py` | Allowlisted source/fallback fields on the existing detail contract |
| `tests/unit/test_library_artifacts.py` | Source fidelity, bounds, sanitization and empty-file regression tests |
| `tests/unit/test_web_library.py` | Authenticated source projection and unchanged download security |
| `scripts/webui_file_preview_smoke.py` | Real-browser source/Markdown/download regression fixture |
| `scripts/webui_library_browser_smoke.py` | Update shared source checks for exact trailing newlines and numbered DOM |
| `AGENTS.md` | Current preview behavior and compatibility boundaries |
| `docs/webui/coverage.md` | Browser coverage update |
| `docs/webui/library-browser-validation.md` | Link historical text-control evidence to this refinement |
| `docs/webui/file-preview-refinement.md` | Plan, decisions, changed files, evidence and limitations |

All other dirty worktree changes were preserved. No commit or push.

## Architecture and limitations

The application extends the existing authenticated typed-ID detail read. No new
endpoint, filesystem path input, renderer dependency, iframe or execution path
was added. Existing native dialogs, tonal surfaces, typography, tokens, icons,
reviewed actions, source/tag editing, image cache/gestures and focus restoration
remain shared. Code tokens are created as DOM text/spans; uploaded HTML is never
inserted as HTML. Markdown uses the existing HTML-disabled renderer and safe-link
policy; embedded images remain explicit links. Line-number gutters are hidden
from assistive technology and excluded from Copy. Mode changes reuse the loaded
source and do not refetch it.

Preview remains a prefix: at most 16 KiB and 100 source lines (a trailing newline
can create a final empty numbered row). Download retrieves the complete original.
Text uses UTF-8; mostly binary/non-text files remain unsupported previews. Invalid
UTF-8/control replacements are disclosed; saved bytes do not change. The existing
highlighter falls back to readable plain text for unsupported grammars or sources
above 12,000 characters/token bounds. Older running hosts lack the optional source
fields and use their normalized/clipped lines until a safe host restart.

Desktop and mobile checks used Chrome emulation. Physical iOS/Android, Safari,
screen-reader and complete WCAG acceptance testing were not performed. Native
touch gestures were verified through the existing image regression fixture;
text scrolling uses the browser's native behavior.

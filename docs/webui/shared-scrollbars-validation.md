# Shared WebUI scrollbars

Updated 2026-10-22. The existing chat scrollbar appearance now lives in the
shared `expressive.css`: thin native scrollbars, the current theme's outline
color for the thumb, and a transparent track. The shared rule applies to page
panels, navigation, dialogs, inspectors, inputs and horizontal content scrollers.
The generated `style.css` includes it through the existing Expressive bundler.

Chat keeps its 8px message inset and stable gutter. Other containers keep their
existing layout, overflow and scroll behavior. The mobile section chips keep
their intentionally hidden scrollbar. Forced-colors mode restores native colors.
There are no JavaScript, backend, dependency or persistence changes.

Validation used the existing isolated real-HTTP/Chrome WebUI fixture, with
temporary profile data and no live model calls:

- `/tmp/klaude-shared-scrollbars-smoke.py` passed **176** page/dialog combinations
  across light/dark, lavender/ocean, and 1440/850/390/320px viewports. It checked
  computed styles on all scroll containers, textareas and the root, normal
  vertical scrolling, horizontal code scrolling, chat inset/gutter preservation,
  no page overflow, and forced-colors behavior. Zero JavaScript exceptions.
- Settings light desktop and dark mobile screenshots were inspected. Evidence:
  `/tmp/klaude-shared-scrollbars-preview/` and
  `/tmp/klaude-shared-scrollbars-smoke.{json,log}`.
- Both static asset bundle checks and `git diff --check` passed.
- The running WebUI returned HTTP 200 for the updated CSS, including the shared
  scrollbar and forced-colors rules. A browser refresh loads it; no host restart
  is required.

Changed files: `static/expressive.css`, generated `static/style.css`, `AGENTS.md`
and this record. Unrelated worktree changes were preserved. These are focused
Chrome checks, not a full-suite, cross-browser or physical-device claim. Backend
tests were not rerun for this CSS-only change.

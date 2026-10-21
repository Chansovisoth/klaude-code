# Models page validation

Validated on 2026-10-21.

The previously disabled main Models destination now opens a configured model
catalog. It shows the current conversation model, configured connections,
searchable model rows and 20-item pages. Each row retains its complete model
name/reference in accessible text and tooltips while truncating visually.
The existing public catalog supplies reasoning effort labels; the page does
not infer new capabilities. Model Defaults opens Settings → Models.

Use model calls the composer's existing fenced, revision-checked configured-model
action and changes the current idle conversation. It neither changes startup
defaults nor generates a response. Pending selections prevent duplicate submits;
the shared selector retains the user's chosen thinking effort before rendering
its pending state. Failure keeps the confirmed current model and offers retry.

Refresh retains previously loaded models if the catalog is unavailable. Changing
connections clears the old connection's catalog before loading. Generation and
authentication checks reject obsolete reads, and sign-out clears private catalog,
connection and draft data. Legacy local-only hosts use their existing endpoint.
The main view participates in URL/history/reload navigation. Phones keep the
five-destination bar and open Models through the keyboard-accessible More menu.

No endpoints, dependencies, provider settings or persistence rules were added.
Connection creation/credentials, Model Manager, downloads, serving and SSH remain
terminal features. Settings' reviewed Model Defaults and image-service forms are
preserved.

Validation completed:

- `.venv/bin/python scripts/webui_models_smoke.py` passed configured and legacy
  hosts: connection selection, search, pagination, exact current-chat selection,
  duplicate prevention, preserved thinking effort, failure/retry, refresh failure,
  empty/disabled connections, busy controls, drafts, history/reload, keyboard
  navigation and late-response sign-out cleanup. The HTTP and application runtime
  paths are real; provider discovery/runtime construction and failure conditions
  are fixtures. Busy presentation is simulated without inference.
- Ten light/dark layout combinations passed at 320/390/768/1024/1440px,
  including a short 320px viewport. No horizontal overflow; row actions retain
  44px targets. Desktop and phone captures were visually inspected.
- The existing Settings smoke passed password/bootstrap hosts and all **90**
  panel/theme/viewport combinations, including reviewed saves, Model cancellation,
  draft preservation and legacy Images migration. Zero browser exceptions in
  the Models and Settings checks.
- Existing browser management and media integration: **25 passed in 56.57s**.
- Repository Ruff, production mypy (**222 source files**), changed JavaScript
  syntax, Python compilation and `git diff --check` passed. Offline packaging
  built/installed **seven wheels**, verified static assets/imports and both
  CLI help commands.

During test development, the reload assertion returned a serialized DOM node
instead of a Boolean, and a refresh click raced a pending catalog read. Both
fixture assertions were corrected; the final run passed. No full-suite,
live-provider or physical-device coverage is claimed.

Evidence: `/tmp/klaude-models-finish-smoke.json`,
`/tmp/klaude-models-finish-smoke.log`,
`/tmp/klaude-models-settings-regression.json`,
`/tmp/klaude-models-mcp-{backend,ruff,mypy,package}.log`, and
`/tmp/klaude-models-mcp-preview/`.

Changed implementation: `static/index.html`, `static/app.js`, `static/media.js`,
`static/management.js` and `static/style.css`. The reusable Models smoke is in
`scripts/webui_models_smoke.py`; MCP evidence is recorded in
`connections-layout-validation.md`. `AGENTS.md` and `coverage.md` reflect the
supported browser surface. Unrelated dirty-worktree changes were preserved.

# Model Store and Models settings completion

Date: 2026-10-25. Continues the [original implementation](implementation-validation.md)
and [handoff](klaude-model-store-image-studio-codex-handoff.md).

## Delivered behavior

Models retains Discover, Top charts, Categories, Installed, Downloads and
Connections. Curated Ollama discovery remains available offline. The explicit
Hugging Face GGUF source adds search, most-downloaded/recently-updated ordering,
real repository counts, source links and exact downloadable files. Charts clearly
identifies Hub repository downloads rather than Ollama usage. A direct Download
by tag dialog supports other exact native Ollama tags through the same review.

Public catalog reads use the documented Hub API, anonymously, with bounded
responses/timeouts and no weight requests. Each query returns at most 20 records;
details offer at most 64 top-level single GGUF files, excluding split weights and
projector-only files. Public queries are identified in the UI. A one-hour cache
retains source/checked time, shows stale errors and bounds storage to 64 records.
Installed inventory and its separate revision-scoped offline cache keep working
when the public catalog fails. Unknown capabilities, context, license, size and
device fit are not inferred from filenames. Installed and configured inventories,
and the role picker, reuse the application's numbered pager/chevrons.

The Hub documents Ollama's full-filename tag syntax used by this integration:
[Ollama integration](https://huggingface.co/docs/hub/en/ollama).
The metadata integration uses [Hub API](https://huggingface.co/docs/hub/en/api)
model list/detail responses, with descending `downloads`/`lastModified` ordering.
A live, read-only query for Qwen3.5 returned 20 repositories with actual download
counts; its first detail response offered 25 supported GGUF files. No real weight
transfer was made for verification.

Settings → Models includes:

- Searchable native primary/fallback model pickers, connection selection,
  per-role capability labels and shared pagination. Selection stages the existing
  settings draft; Apply/Discard and exact saved-state recovery remain authoritative.
  Unknown capability labels never claim verification. Existing defaults are not
  automatically changed, and the current chat keeps its model.
- Enabled Vision requires a primary model; disable it before clearing that model.
- Connection inventory, add-disabled, edit name/address/routing, explicit saved-key
  authentication, test, enable/disable and removal. Local Ollama works without a
  key when authentication is off. Credential authentication can be enabled in the
  connection editor; save its key separately before enabling the connection.
- Write-only API keys/tokens, replacement and explicit removal. Public responses,
  reviews, activity and journal intent never include the credential. Connection
  removal retains installed weights and credentials, as its review explains.
- Independent image-service Test reads observed capabilities, model and limits;
  it neither saves settings nor generates an image. Background refreshes preserve
  the explicit test result. Image Studio retains aspect ratios, dimensions,
  steps/seed, reviewed generation, owned jobs, cancellation, output recovery and
  the existing Generated preview/download flow.

Connection changes use `ModelConnectionService.save_definition`, the existing
fixed Library worker and operation journal. Definitions and credential revisions
are rechecked inside publication locks. HMAC witnesses precede the effect gate;
a lost acknowledgement leaves an unknown, fenced result. Check saved state
compares exact local definitions or credential/revision state without contacting
a provider or replaying the change. Credential publication uses the existing
provider-secret writer with an optional prepublication callback. The two-file
credential/revision publication can remain unknown after a partial failure; the
browser never guesses success or automatically retries it.

Admin model/connection mutations retain authentication, CSRF/Origin,
request receipts, chat/queue idle checks and profile-operation conflict guards.
The active conversation connection and its shared credential cannot be changed;
select a different conversation model first. Referenced default roles prevent
incompatible definition changes or removal. The subsequent
[admin-role update](admin-role-validation.md) permits authenticated administrators
on local and LAN listeners. Non-admins cannot manage models/settings; connection
addresses are omitted from their management projection. Embedded bootstrap hosts
retain their existing loopback-only authority.

## Changed contracts

- `GET /api/v1/models/store` optionally accepts the explicit Hugging Face source,
  bounded query, ordering and refresh. `GET /api/v1/models/store/detail?id=…`
  returns allowlisted public single-file variants.
- `GET /api/v1/settings/model-connections` returns definitions, credential-present
  booleans, allowed adapters and the pending shared operation, never secrets.
- `POST /api/v1/settings/model-connections/test` checks an exact saved definition;
  `POST /api/v1/settings/models/image-test` checks the supplied image endpoint.
- Existing Library review/submit gains fixed `model-connection-*` operations.
  Snapshots declare `model_settings` and `model_store_catalog`; older hosts show
  restart guidance rather than sending unsupported calls.

Primary files: application `browser_model_settings.py`, `model_connections.py`,
`provider_secrets.py`, `model_store_catalog.py`, `library_management.py` and
`browser_media_settings.py`; core `config.py` and `ai_defaults.py`; web
`huggingface.py`; WebUI `host.py`, `media.js`, `index.html`, `library.js`,
`expressive.css` and bundled `style.css`. No new job database, model downloader or
subprocess owner was introduced.

## Validation

The isolated Chrome Store/Studio walkthrough passed browsing, real-count charts,
exact files, direct-tag review/cancel, reviewed native pull, receipt reload,
chat/default preservation, eight-page shared pagination/focus, offline inventory,
back navigation, studio parameters/drafts, fixture PNG generation/output preview
and sign-out cleanup. The settings walkthrough passed searchable role selection
and Apply, image-service Test, add-disabled, credential privacy, enable/Test,
reviewed removal and sign-out. Both passed 320/390/768/1440px, light/dark and zero
JavaScript exceptions. Store also checks reduced motion and forced colors.
Screenshots: `/tmp/klaude-model-store-evidence/` and
`/tmp/klaude-model-settings-evidence/`.

Focused unit coverage includes real isolated HTTP/worker effects, default-role
protection, local/LAN/auth/CSRF boundaries, stale reviews, credential changes
between review and effect, credential-free native setup, definition/credential
acknowledgement loss, witness tampering, recovery without replay/provider calls,
private credential exclusion, actual/missing Hub counts, exact-file selection,
cache/offline bounds and Vision's primary-model invariant.

Final focused command:

```sh
PYTHONPATH=. .venv/bin/pytest -q \
  tests/unit/test_browser_model_settings.py tests/unit/test_model_store_catalog.py \
  tests/unit/test_model_store.py tests/unit/test_ai_defaults.py \
  tests/unit/test_model_connections.py tests/unit/test_model_management.py \
  tests/unit/test_config.py tests/unit/test_huggingface.py \
  tests/unit/test_application_operations.py tests/unit/test_library_management.py \
  tests/unit/test_web_management.py
```

Result: **204 passed in 164.32 seconds**. The retained configured-model Chrome
smoke also passed configured/legacy catalogs, current-chat selection and effort,
failures, history/reload, keyboard and 320/390/768/1024/1440px light/dark layouts
with zero browser exceptions.

Production mypy passes all 229 source files. Focused Ruff, JavaScript syntax,
Expressive bundle verification and whitespace checks pass. The original full
`make check` reached its 240-second bound around 40%; it remains an incomplete
full-suite run. The initial repository-wide Ruff findings remain outside this
scope; new modules/tests/smokes pass focused lint.

## Running-host verification

After an exact-identity, idle/queue/review/operation check and saved-session
preflight, the managed host was reloaded from instance `3309152:70150526` to
`3329295:70498183`. The restart preserved workspace
`/mnt/HDD1/draft/playground`, session `efc02e7db5654c0589bfc5e2c4fcd83e`,
`ollama/qwen3-coder:30b`, Standard mode, password account mode and LAN origin
`http://192.168.100.244:50000`. All four Store/Studio/settings/live-catalog
capabilities are present. Existing browser clients need reload/sign-in.

Authenticated local HTTP checks returned 200 for connection settings (5
connections), role settings (8 fields), curated discovery (3 families), live GGUF
search (20 repositories, fresh cache), exact detail (25 files), installed inventory
(30 models), downloads (0 jobs) and image capabilities (service disabled).
Read-only native connection Test also returned 30 models. The temporary
verification client signed out. No real connection, credential, role default,
weight inventory or image-service setting was changed by this verification.
Private evidence: `/tmp/klaude-model-completion-live-result.json`.

## Explicit limits

Interactive Codex/OAuth login, arbitrary environment variables, serving processes
and SSH configuration remain terminal features. This browser supports the
existing fixed adapters; it does not add arbitrary HTTP proxies or workflows.
Hardware-fit estimates remain unavailable. Other image-output engines, including
Ollama image output, remain unavailable unless an actual supported adapter is
verified. Historical private image prompts/parameters are not recovered after
reload; Generate another retains the current draft. Unknown native downloads
whose final state cannot be witnessed remain fenced for explicit inspection.

Real model-weight pull/deletion, real image inference, physical touch devices and
the entire repository test suite were not exercised here. Existing dirty work
was preserved. Nothing was committed or pushed.

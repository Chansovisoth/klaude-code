# S2a: model connection settings and maintenance

Date: 2026-10-13. Parent checkpoint: `0db42b4`.

S2a is **complete locally**, on the [S1 foundation](s1-model-connections-validation.md).
The connection UI and [maintenance follow-up](#s2a-maintenance-follow-up) are
recorded below. [S2b AI Defaults](s2b-ai-defaults-validation.md) is now complete
locally; S2c adapters remain unstarted in
[the delivery plan](odysseus-settings-and-features-plan.md#s2--models-pages-and-ai-defaults).

The S2a evidence below is historical: S2b intentionally separates session model
selection from saved startup defaults and extends removal reviews to Utility roles.

## Connection UI foundation

- `/settings models`: Added Models, Add Models and Session model landing page.
  `/model` retains the existing session/provider/login flow. Back follows the
  visible parent, including the new Models landing page after model selection.
- Local drafts: native Ollama or OpenAI-compatible. API drafts: implemented
  OpenAI API, Gemini API, OpenRouter or custom compatible endpoint. Codex links
  to its existing account page. Unsupported provider presets are not selectable.
- Name, normalized endpoint, adapter/provider, masked key, Test, Add and Cancel.
  URL/adapter changes clear the entered key and previous test. A new draft starts
  unfiltered; field editing within a draft retains navigation/search state.
- Test checks only a bounded catalog in an owned cancellable worker. A draft
  check never saves a definition, key or catalog, invokes generation, pulls
  models or changes the chat runtime. Failure categories remain distinct.
- Add runs on the existing ordered session action lane, without requiring the
  session database. The accepted immutable definition survives navigation/exit.
  Untested Add requires a separate review, initially focused on Cancel.
- Added Models reads bounded public snapshots off the UI thread. Endpoint
  detail offers Manage models and Test; catalog Filter, Reload models and
  manual model-ID entry precede the table. Endpoint identities keep equal model
  IDs separate. Manual selection captures credential revisions and preserves
  slashes. Listing a model supplies no verified tool-capability claim.
- Saves acknowledge success/failure in the footer. Keys use unique private
  environment references and never return through action acknowledgements.
  Known unpublished definitions remove their newly saved key. If replacement
  succeeds but directory sync fails, the key remains with the definition and
  the save is reported unconfirmed. Multi-file crash atomicity is not claimed.

The focused controller/pages live in `klaude_cli/model_settings.py`; `main.py`
wires the shared panels/editors/jobs. Existing registry, private credential
storage, catalog publication guards and preference/action writers are reused.

## Problems found and corrected

- A late inventory result could reopen the parent while a URL/key editor was
  active. Snapshot acceptance now preserves transient editor ownership and is
  scoped to the current session; stale test identities/revisions are dropped.
- A new draft could inherit the previous form's filter. Only the four draft
  page states are cleared when a new draft begins.
- Catalog capability text wrapped into a small column at 80 columns. The table
  now uses Model / Status / Capabilities, and counts use the shared heading's
  muted description field. Filter/reload controls remain above the header.
- Direct catalog selection during a running turn needed to close its panel and
  restore the unsent composer after accepting the next-prompt model. It uses
  the existing immutable runtime and pending-selection path.
- Credential rollback must distinguish failed publication from failed durability
  after replacement. Regression coverage requires a published definition to
  keep its key after a simulated directory-sync failure.

## Real CLI/TUI evidence

The real bare `klaude` executable was launched in an isolated workspace with
temporary config/data and a real PTY. Session: **TEST KLAUDE FEATURES S2**,
model **gemma4:e2b**, native Ollama at `http://localhost:11434`. A separate
loopback HTTP fixture supplied deterministic authentication responses.

Successful final run:
`.klaude/data/s2-models-xhbikecg/result.json` and terminal captures alongside it.

1. Tested an unsaved Ollama-compatible draft; verified no registry existed.
2. Cancelled it; verified no definition/key was saved.
3. Tested and added native Ollama using `/api` input; verified normalization,
   acknowledged save and retention of the current chat model.
4. Reloaded its real catalog and inspected the layout at 120 and 80 columns.
5. Entered a canary in the API form's masked editor, cancelled, and verified no
   private dotenv file was created.
6. Received explicit HTTP 401 authentication failure from the fixture; changed
   URL and confirmed the draft key cleared; received a separate unreachable
   connection failure.
7. Re-entered authentication, tested successfully, and added the fixture.
   The key appeared only in owner-only dotenv storage, not the registry,
   rendered terminal stream or session database.
8. Followed Back/Escape through Settings, exited cleanly with code 0, restarted
   bare `klaude`, and verified both newly added endpoints remained (seven total
   including the five migrated native definitions). The second exit was also 0.

Captures include `models-home-120.txt`, `local-draft-tested-120.txt`,
`model-inventory-120.txt`, `model-inventory-80.txt`, `added-endpoints-80.txt`,
`masked-api-input-80.txt`, `authentication-error-80.txt`, `network-error-80.txt`
and `restart-added-models-80.txt`. No live paid-cloud generation was performed.

Earlier walkthrough attempts exposed the filter/layout issues above. Other
failed harness attempts incorrectly passed `--model` to bare `klaude`, appended
searches to an existing page filter, or typed `/exit` before closing the Settings
home; their results are retained as failed attempts, not successful product
validation. The final walkthrough uses the actual command registry and visible
navigation semantics. No passing restart claim is derived from a killed process.

## Connection UI validation

The first connection UI slice's completed gate on Python 3.12.3 (historical,
before maintenance):

- `make check`: **2525 passed, 19 skipped**; Ruff passed; production mypy passed
  for **89 source files**. All three checks exited 0.
- `make package-smoke`: all **five wheels**, fresh isolated installation,
  public-package imports and installed `klaude --help` passed.
- `git diff --check`: passed.

The completed logs and walkthrough script are retained in the successful
run's directory. Python 3.11/3.13 CI has not run for these uncommitted changes;
S0's prior cross-version CI is not claimed as validation of S2 source.

Coverage includes draft-test isolation, key/URL binding, masked cancellation,
session and editor ownership, untested review, credential publication/rollback,
ordered saves without a session DB, manual model revision capture, queued model
selection/composer restoration, cross-endpoint cache identity, filter preservation
and table/control width at 38, 80 and 120 columns. Existing S1 and session action
regressions remain in the full gate.

## S2a maintenance follow-up

### Implemented

- Added Models puts Reload endpoints, Probe enabled endpoints and Clear offline
  above the endpoint table. Counts now reflect enabled/total models. Probe runs
  serially through owned cancellable catalog jobs, skips disabled endpoints and
  does not generate or load models. Explicit Test can check a disabled endpoint.
- Check status and age persist as bounded public metadata, scoped to the endpoint
  definition and credential revision. Authentication, rate limits and service
  failures remain distinct from network/timeout failures. Failed checks retain
  the previous catalog; a stale check cannot publish new health or catalog data.
- Endpoint enable/disable and model Enabled, Pinned and Hide from session picker
  controls save through the existing ordered action lane. Per-model fields merge
  independently, survive missing catalogs, and remain separate for equal model
  IDs on different endpoints. Missing models and unknown tool capabilities are
  labeled honestly. Hidden models remain available through explicit selection;
  disabled models cannot bypass the setting through manual or legacy references.
- Catalog Filter offers All, Enabled, Disabled, Hidden and Pinned, scoped to each
  endpoint. Pinned models appear first in session pickers; hidden/disabled models
  are omitted. Reload retains the current query and logical focus.
- Remove endpoint and Clear offline require separate reviews, initially focused
  on Cancel. Clear offline selects only network/timeout failures and rechecks the
  exact reviewed health and credentials at save time. An authentication failure
  is never classified as an offline endpoint to delete.
- Disabling/removing the saved startup endpoint or model requires an explicit
  enabled replacement or unset. Replacement changes the startup preference,
  while the open session keeps its accepted runtime. Unset persists an explicit
  selection-required marker; bare startup opens Models and shows Not selected
  in the banner/page/footer, without generating through a fallback model.
- New turns reject removed/disabled endpoints or models before dequeuing their
  prompt. Pending/unconfirmed maintenance holds new work until acknowledgement
  or inventory reload. Already accepted running work retains its runtime.
- Removal purges only that endpoint's catalog, choices and health metadata;
  credentials and conversation history are retained. Definition/startup/cache
  writes use the existing lock order and report partial failures as unconfirmed.
  Multi-file crash atomicity and remote credential revocation are not claimed.
- Environment-only endpoint keys travel through the worker's private request
  channel. A saved replacement/removal overrides a stale process environment
  value. Key values never enter public inventory/action results.

Core maintenance is isolated in `klaude_core/model_management.py`; the focused
`model_settings.py` controller and existing session action/background worker
lanes provide UI ownership, cancellation and persistence. No second settings
writer or model orchestration layer was introduced.

### Observed problems and corrections

- A search used to reach Filter carried into the selected inventory mode,
  hiding every result. Applying the explicit filter now clears that control
  navigation search, while ordinary Reload keeps the user's inventory query.
- A removal review inherited a previous review's search, hiding its target and
  startup choice. Every new destructive review starts unfiltered with Cancel
  focused; editor and navigation state on unrelated pages is retained.
- After unset, the page/footer correctly showed no selected model, but the
  startup banner named the unused initial agent model. The banner now also
  shows Not selected; a separate real startup repeat checked all three labels.
- Maintenance needed guards beyond its UI: stale health cannot justify Clear
  offline, stale definition/startup reviews cannot overwrite another client's
  choices, and manual selection cannot bypass a disabled model. These checks
  now live in the shared core mutation/reference functions.

### Real CLI/TUI evidence

Session: **TEST KLAUDE FEATURES S2 MAINTENANCE**, real bare `klaude` in an
isolated workspace/config/data. Native **gemma4:e2b** and a separately registered
compatible endpoint used the same local Ollama daemon. Loopback fixtures supplied
401 and unreachable endpoints; another endpoint started disabled. No paid-cloud
generation or real account credential mutation was performed.

Successful maintenance run:
`.klaude/data/s2-models-apjnk_5a/maintenance-result.json`.

1. Probed enabled endpoints; confirmed the disabled endpoint was skipped and
   authentication/network categories remained distinct.
2. Pinned and hid a real catalog model, filtered Pinned, resized from 120 to 80
   columns, and confirmed persisted independent fields.
3. Disabled and re-enabled that model with acknowledged saves.
4. Selected the hidden model explicitly. Cancelled its endpoint-disable review
   and confirmed no definition/startup mutation occurred.
5. Chose an explicit native Ollama startup replacement, confirmed disable, and
   verified the open session still used its compatible runtime.
6. Reviewed and removed that endpoint, then used Clear offline to remove only
   the unreachable fixture; the authentication-failing endpoint remained.
7. Disabled the startup endpoint with explicit unset. Exited normally, restarted
   bare Klaude, verified Models opened without a selected model, and confirmed
   the selection-required marker remained.
8. Enabled the endpoint, explicitly selected the model, confirmed the marker
   cleared, and exited normally. Both processes exited **0**.

Captures: `added-after-probe-120`, `model-controls-120`, `pinned-inventory-80`,
`affected-startup-review-80` and `unset-startup-restart-80` (`.txt` and `.svg`).
The first and second terminal streams are retained separately. Controls precede
headers; model/status/capability columns fit at 80 columns; review details and
Cancel remain visible. The 120-column layout uses the additional width for
endpoint status and catalog health.

The final banner correction was repeated through a separate real 80-column
startup in `.klaude/data/s2-models-w9p3ey5t/startup-result.json`: banner/page/footer
all indicated no selection, the marker was unchanged, and exit was **0**.

The maintenance captures inherited the harness environment's `NO_COLOR` setting.
A separate read-only visual walkthrough in `.klaude/data/s2-models-5f5tx2s9`
enabled truecolor and captured Added Models at 120 columns and the inventory/model
detail at 80 columns; its normal exit was **0**. This checks the actual theme
rendering separately from the earlier monochrome layout captures. Visual review
confirmed aligned columns, muted metadata, accent breadcrumbs and a subtle focus
background; controls stay above the headers and the detail toggles stay aligned.

Earlier retained attempts are not passing evidence: `ba43xrwx` contained a
harness assumption about a retained search; `g0qv_f6f` exposed the Filter problem;
`ggv0zmwl` exposed the inherited-review search. The successful maintenance run
followed both UI fixes. No clean-exit claim comes from a terminated process.

### Regression validation

Final source on Python 3.12.3:

- `make check`: **2540 passed, 19 skipped** in 132.79 seconds; Ruff passed;
  production mypy passed for **90 source files**. The command exited **0**.
- `make package-smoke`: all **five wheels**, fresh isolated installation,
  public-package imports and installed `klaude --help` passed with exit **0**.
  A subsequent banner-only correction was covered by the final full gate and
  separate real startup repeat; it did not change package metadata or imports.
- `git diff --check`: passed.

Completed logs, drivers and a source hash manifest are retained in the successful
maintenance evidence directory. Python 3.11/3.13 CI has not run on these
uncommitted changes. The first broad maintenance run failed on a test fixture
that wrote a qualified catalog under the legacy backend scope; correcting its
endpoint scope resolved that fixture, rather than relaxing the cache guard.

Tests cover independent field merges, stale definition/startup/health rejection, scoped
catalog invalidation, explicit replacement/unset, partial-save failure, missing
model preferences, manual-reference enforcement, environment credential
precedence, fresh-review focus and endpoint-scoped filters. Existing S1 runtime,
queued selection and session action regressions remain in the full suite.

## Remaining scope and limits

- Editing an installed endpoint/authentication. The first flow adds new drafts;
  native provider account/key management remains accessible through Session model.
- S2b Default Chat/session separation, Utility consumers and explicit fallbacks
  are recorded in [their follow-up](s2b-ai-defaults-validation.md).
- DeepSeek and native Anthropic adapters (S2c). No provider certification is
  inferred from a compatible local test.
- Additional real llama.cpp/vLLM, LAN and paid-provider runs; compact terminal
  height/very large inventory usability beyond the bounded rendering tests.

No S3–S6 work, agent-orchestration phase, release/version/lock change, commit,
push, reset, stash or unrelated worktree cleanup was performed.

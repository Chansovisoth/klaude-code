# Models UX and reliability review

Status: investigation and implementation proposal only. No product code changed.
Reviewed on 2026-10-21 against `dc6a803faa319d7714bc3d3951d8d52e37b9518b`.
The worktree was clean at inspection; this report is the only repository change.

## Direction and scope

The next implementation milestone should be a shared searchable model picker.
Klaude is a local-first coding agent with multiple configured runtimes, separate
model roles and explicit effects. Its configuration workflow needs to explain
those choices without rebuilding Settings.

Preserve the wide Settings container, Material 3 tokens/components, vertical
Account/Theme/Agent/Models/Memory navigation, grouped Agent accordions, live Theme
preview and Apply, and user-controlled side panels. Keep Chat, Workspaces,
Library, Models, Integrations, Activity and Settings as main destinations.
Library stays Uploads/Generated; Knowledge stays under Integrations. Defer
Settings search and further navigation layers. Keep Tools and Permissions
separate. Investigate memory and connection reliability as separate workstreams.

The findings below distinguish code inspection, deterministic reproductions and
unverified live conditions. No owner memory, private conversation content or live
provider configuration was inspected. No external inference was performed.

## Existing architecture and reusable contracts

| Surface | Current contract | Consequence for the picker |
| --- | --- | --- |
| Connection inventory | `BrowserModels.inventory()` exposes configured ID, name, adapter, Local/Cloud source and enabled state; at most 64 connections | Group by configured connections and source; preserve disabled and unavailable states |
| Model catalog | Catalogs are scoped to an enabled connection, filtered by configured model choices and bounded to 1,000 models | Search loaded metadata without inference; distinguish incomplete inventory from no matches |
| Model identity | `backend@connection_id/model_id`, plus legacy native Ollama references | Key choices by exact reference, never display name; identical names on different endpoints are different choices |
| Current chat | The Models page and composer call the fenced runtime-selection path; an active turn or pending queue blocks a change | Keep choosing a chat runtime distinct from saving a startup default |
| Model Defaults | `purpose=defaults` returns per-role true/false/unknown hints; review captures expected field values and definition/credential bindings | Selection can remain a draft; only the existing explicit review submits a default change |
| Persisted defaults | A shared journaled writer owns the defaults resource and witnesses before/after preference fields | Keep deduplication, stale-state rejection and unknown-outcome recovery; presentation alone cannot create atomic grouped saves |

Sources: [BrowserModels](../../packages/application/src/klaude_application/browser_models.py#L26),
[ModelInfo identity](../../packages/core/src/klaude_core/model_runtime.py#L149),
[HTTP catalog projections](../../apps/webhost/src/klaude_webhost/host.py#L1001),
[current runtime controls](../../apps/webhost/src/klaude_webhost/static/app.js#L1023),
[review preparation](../../packages/application/src/klaude_application/browser_media_settings.py#L123),
[shared defaults writer](../../packages/application/src/klaude_application/model_default_settings.py#L56).

### Role semantics to retain

| Role | What it controls | Unset behavior and constraints |
| --- | --- | --- |
| Chat / Startup chat | Default for fresh conversations; existing conversations retain their runtime | Unset requires explicit model selection; native chat requires declared completion and tools |
| Utility | Bounded recap/name work | Uses the current chat model when unset; supports up to three ordered explicit fallbacks; bounded generation and Standard mode are required |
| Research | Separate generated Research jobs | The browser can explicitly use the Research default or current chat; requires bounded Standard generation and tools |
| Vision | Library image analysis/tagging service | Requires an enabled Vision setting and a primary model; up to three explicit fallbacks; image support and analysis constraints are checked |

Codex is excluded from bounded Utility/Research/Vision role hints. Known
mandatory-Thinking models are excluded from those roles. Tool capability may
remain unknown for some non-native providers; see finding F4.

Image attachments in chat use the **active chat model**, together with the Vision
enable setting and an exact active-model image check. Assigning an image-capable
Vision default does not add image support to a text-only Chat model. Explain
this distinction beside the role controls and attachment compatibility warning.

Sources: [defaults schema](../../packages/core/src/klaude_core/ai_defaults.py#L49),
[role rules](../../packages/application/src/klaude_application/browser_media_settings.py#L47),
[Utility candidate order](../../packages/core/src/klaude_core/utility.py#L115),
[Research model selection](../../apps/webhost/src/klaude_webhost/static/management.js#L242),
[Vision preparation](../../packages/core/src/klaude_core/vision.py#L402),
[active chat image model](../../packages/core/src/klaude_core/chat_images.py#L402).

## Verified findings

### F1 — The selection experience is fragmented and hides identity

The main Models destination already has connection selection, text search and
20-item pages. The composer and role/fallback forms still use native selects.
Role choices load one connection at a time, show saved references outside that
catalog and preserve drafts during refresh. Labels truncate in the controls;
the Models list also truncates names and references, exposing full values only
through titles. Reuse the existing catalog/search behavior and native dialogs
rather than introducing another model-management destination.

Sources: [Models browser](../../apps/webhost/src/klaude_webhost/static/media.js#L5),
[role select construction](../../apps/webhost/src/klaude_webhost/static/media.js#L153),
[truncation rules](../../apps/webhost/src/klaude_webhost/static/style.css#L1256).

### F2 — Local/Cloud is configured routing information, not measured location

Provider/adapter, connection identity and execution location are different axes.
`ModelConnection.source` is owner-configured Local/Cloud, while `backend` identifies
the adapter. The validator accepts a remote HTTPS Ollama URL labeled Local;
the isolated constructor probe reproduced this without contacting that URL.
An OpenAI-compatible adapter likewise does not establish the actual provider.

Display the configured source and named connection, but do not claim that a
model runs on this machine solely because its backend is Ollama or its source
says Local. If physical execution location is displayed, it needs a separate
verified contract. For the first milestone, label it as configured routing and
show an unambiguous connection identity. Any future endpoint summary should be
sanitized and must omit credentials and private URL details.

Source: [connection validation and source](../../packages/core/src/klaude_core/model_connections.py#L48),
[model provider/source properties](../../packages/core/src/klaude_core/model_runtime.py#L172).

### F3 — Rich capability evidence exists privately but is not in picker payloads

The ordinary catalog HTTP response exposes ID, name and effort levels. The
defaults response adds role hints but not individual capability values, evidence
or freshness. `ModelCapabilities` already carries tools/images evidence, context,
output limits and Thinking declarations. A list response alone proves neither
tool support nor context size.

Native Ollama defaults inspection uses `/api/show`, batches of eight and four
concurrent inspections, stopping new batches after a 20-second inspection budget.
Remaining or failed checks stay unknown. Vision has stricter endpoint-specific
inspection, catalog declarations and exact reviewed profiles. Reuse these
authoritative readers; do not infer capabilities from model names, family names,
parameter counts or generic provider branding. Existing catalog classification
and adapter defaults are not additional verification evidence.

Sources: [HTTP projection](../../apps/webhost/src/klaude_webhost/host.py#L1019),
[capability schema](../../packages/core/src/klaude_core/model_runtime.py#L114),
[bounded native inspection](../../packages/application/src/klaude_application/model_capabilities.py#L41),
[defaults metadata budget](../../packages/application/src/klaude_application/browser_media_settings.py#L47),
[catalog evidence](../../packages/core/src/klaude_core/model_discovery.py#L190),
[Vision verification](../../packages/core/src/klaude_core/vision.py#L157).

### F4 — “Verify on review” does not guarantee verified cloud tool support

For a synthetic OpenAI-compatible model with unknown tool evidence, the actual
catalog projection reports Chat/Research as unknown and Utility as true. With
only the catalog/current-definition calls mocked, the real Research binding
function accepts that same model. `BrowserModels.verify()` requires fresh
completion/tool declarations for native Ollama, but the non-native check accepts
the default `supports_tools=True` despite `tools_evidence="unknown"`.

This demonstrates an admission/evidence mismatch; it does not demonstrate that
the synthetic model cannot use tools. Keep unknown visible after review unless
an authoritative check actually resolves it. Decide compatibility policy in the
shared service, consistently for composer and defaults. Do not silently reject
all unknown cloud choices or promote them to verified in the UI.

Sources: [select wording](../../apps/webhost/src/klaude_webhost/static/media.js#L153),
[verification](../../packages/application/src/klaude_application/browser_models.py#L61),
[role binding](../../packages/application/src/klaude_application/browser_media_settings.py#L106).

### F5 — Vision fallbacks without a primary are dormant; clearing an enabled primary is inconsistent

The defaults schema accepts `vision=null`, `vision_enabled=false` and a nonempty
fallback list. Enabling Vision rejects this state with “Choose a Vision model
before enabling image input.” Analysis also rejects it before reading pixels.
These fallbacks do not automatically become a primary or become a Chat fallback.
Keeping a disabled draft can be useful if the UI makes its inactive state clear.

A second, unmocked temporary-store probe starts with enabled Vision and a primary,
then prepares a reviewed change clearing only the primary. Preparation accepts
it, and the shared candidate validator accepts the resulting `vision_enabled=true`
with `vision=null`. This probe did not submit a persistent browser operation;
the save path uses the same candidate validator. Analysis guards fail closed,
but the settings can describe enabled functionality that cannot run.

Require validation of the complete resulting Vision configuration in the shared
writer. If clearing a primary also disables Vision, show both changes together
for explicit confirmation. Retain a disabled fallback draft with an explanation,
or require a primary before activation; do not silently choose one from the list.

Sources: [schema validation](../../packages/core/src/klaude_core/ai_defaults.py#L49),
[save validation](../../packages/core/src/klaude_core/ai_defaults.py#L123),
[enable review guard](../../packages/application/src/klaude_application/browser_media_settings.py#L160),
[analysis guard](../../packages/core/src/klaude_core/vision.py#L402).

### F6 — Auto-memory can persist questions and quoted instructions

`auto_memory_candidates()` checks for substring hints such as “always”, “never”
and “I prefer”, then returns the cleaned whole message. This is a deterministic
heuristic, not an LLM extraction-quality issue. The explicit remember parser has
a question guard, but the subsequent hint path can still accept that question.
The WebUI invokes auto-memory after a successfully completed turn.

Temporary-store reproductions:

| User message | Actual extracted value |
| --- | --- |
| `Why do I always get this error?` | The entire question; also confirmed persisted through `auto_remember_turn()` |
| `Can you explain why I prefer tabs?` | The entire question |
| `The log says 'never retry this request'. What does it mean?` | The entire quoted-log question |
| `Can you remember that I prefer concise replies?` | The entire question |
| `Please remember that I prefer concise replies.` | `I prefer concise replies` |

Fix candidate selection before expanding Memory UI. Prefer rejecting ambiguous
questions, quotations, code/log blocks and transient task instructions. Extract
only a clear durable assertion, retaining sensitivity filtering and deduplication.
Preserve explicit reviewed memory actions and automatic-memory opt-out. Evaluate
a labeled fixture set including durable facts/preferences, questions, negation,
quoted content and supported-language coverage; record both false positives and
missed durable facts. Do not delete or rewrite existing owner memory automatically.

Sources: [heuristics](../../packages/core/src/klaude_core/memory.py#L76),
[persistence](../../packages/core/src/klaude_core/memory.py#L530),
[browser completion hook](../../packages/application/src/klaude_application/browser_tools.py#L230),
[completed-turn invocation](../../packages/application/src/klaude_application/service.py#L1028).

### F7 — Healthy event-stream rotation produces “Reconnecting”

The host deliberately closes SSE responses after 30 seconds, with heartbeat
comments every 15 seconds. An isolated authenticated HTTP probe with a completed
fixture conversation measured HTTP 200, one heartbeat and EOF after **30.08s**;
a subsequent session request still returned 200. This reproduces healthy stream
rotation, not a host/network outage.

The browser closes the stream on every `onerror`, displays “Reconnecting” and
schedules a snapshot after 1.2 seconds. A 2-second polling fallback retries while
no stream exists. Conversely, a successful snapshot sets “Connected” before any
stream-open confirmation. Thus HTTP snapshot reachability and live stream health
are conflated. Repeated connection labels alone cannot prove provider, LAN or
agent instability. Actual outage frequency on the owner's device is unmeasured.

Investigate the intended bounded-stream lifetime before changing it. Preserve
resource limits, owner-cookie revocation, cursor replay, authentication epochs
and pending interaction identity. Distinguish initial connection, routine stream
renewal, degraded polling, actual offline and expired sign-in states. Use bounded
retry/backoff with jitter and one retry owner; avoid simultaneous SSE/timer retry
loops. Mark the stream live on confirmed open, and record only bounded connection
diagnostics without chat text or secrets. Test normal rotations, not just failures.

Sources: [SSE lifecycle](../../apps/webhost/src/klaude_webhost/host.py#L2140),
[error/retry handling](../../apps/webhost/src/klaude_webhost/static/app.js#L1223),
[snapshot status](../../apps/webhost/src/klaude_webhost/static/app.js#L884),
[polling fallback](../../apps/webhost/src/klaude_webhost/static/app.js#L1729).

## Searchable Material 3 picker proposal

Adapt the existing native dialog, search field, keyed model rows, pagination,
loading ownership, muted metadata, focus restoration and theme tokens. Share one
picker presentation between the Models page, composer and role/fallback inputs;
keep their submission adapters separate.

1. Open with a purpose-specific title: “Choose chat model”, “Startup chat model”,
   “Utility model”, “Research model”, “Vision model” or an explicit fallback slot.
   Start with the current choice visible and a labeled search field.
2. Provide Local/Cloud configured-source groups with connection names and adapter
   labels. Group rows within their actual connection. Default to the current
   connection; allow explicit browsing of others. Global search must search
   loaded, bounded inventories and clearly disclose unloaded connections.
   Do not contact every cloud endpoint merely because a user types a character.
3. Show a wrapping primary name and secondary full model reference/connection.
   Full identity must be accessible on touch without relying on a hover title.
   Use 14–16px readable text, sensible line-height and existing 44px targets.
4. Show capability chips only with evidence: tools, image input, Standard/Thinking
   and numeric limits when known. Use “Unknown” or “Not checked” distinctly from
   supported and unsupported, with a concise explanation and metadata refresh.
   Role eligibility is separate from verified individual capabilities.
5. Keep known-incompatible models discoverable in an optional unavailable-results
   group with an exact reason. Keep missing/disabled saved choices visible with
   a warning. Never remove or replace a saved model silently on refresh.
6. Selecting a role/fallback updates its draft and returns focus to its trigger.
   The existing Review then presents before/after identity and consequences.
   For current chat, retain the existing explicit Use model action and idle
   checks; do not additionally save a startup default or reset thinking effort.
7. Offer explicit role-specific empty choices: Chat “Choose when starting a new
   chat”, Utility “Use current chat model”, Research “No separate default”, and
   Vision “No primary model”. Do not give all four the same ambiguous “Unset”.

Retain the responsive role grid and existing chat/wrench/search/eye icons. A
wide desktop dialog may show list and selected-model details side by side; on
phones use one scrollable column. Escape/outside dismissal, focus return,
keyboard traversal, screen-reader selected state, reduced motion and forced
colors must work. Support long references and 200% text without horizontal overflow.

### Required metadata projection

Extend the existing authenticated catalog projection additively. A model row
needs exact reference, model ID, connection ID/name, adapter, configured source,
tri-state capabilities, per-role eligibility/reasons and public evidence source
with freshness/definition scope. Snapshot freshness at read time; no timestamp
currently exists in this HTTP contract. Evidence must bind to the exact model,
connection revision and credential revision internally. Do not expose credential
material or assume a previous check remains valid after configuration changes.

Native metadata inspection must stay bounded, cancellable from obsolete views
and isolated from inference. A metadata check must not load a model, send a test
prompt, alter defaults or switch to another provider. Preserve old-host behavior
and show an explicit unavailable/restart message for unsupported additive fields.

### Ordered fallbacks and compatibility

Present a numbered ordered list of up to three entries per supported role, with
Add, Remove and accessible Move up/Move down actions. Dragging can supplement
these controls. Show primary identity, effective Utility chat inheritance and
inactive Vision fallback state. Show each fallback's own connection/source and
role check; remove a redundant primary or duplicate through explicit editing,
not silent normalization. Reordering remains a draft until reviewed.

Describe fallback semantics accurately: existing execution proceeds to another
model only for eligible transport/timeouts and selected transient/rate-limit
statuses. Authentication, configuration, protocol and output-quality failures
do not generally authorize fallback. Vision prepares/checks the configured models
before analysis, so an invalid fallback can prevent preparation; its presence
is not an unconditional promise of recovery. Do not add an implicit cloud or
larger-model fallback.

Source: [failure eligibility](../../packages/core/src/klaude_core/utility.py#L90),
[Vision preparation/attempt order](../../packages/core/src/klaude_core/vision.py#L402).

## Review/save architecture

Keep the shared review dialog and visible pending/accepted/unconfirmed states.
The current API saves one defaults field or one Agent field at a time. Gathering
several UI values and sending those requests concurrently would not make them an
atomic group and could contend on the same defaults fence.

For the picker milestone, preserve current field-level Review. A later phase can
add “Review changes” within one coherent domain, with a list of explicit old/new
values, affected future actions, local/cloud routing changes and Cancel/Confirm.

For Model Defaults, design one fixed batch request that validates the complete
candidate, captures every model binding, checks expected values under the owned
locks, and records one before/after witness and durable receipt. Reject stale
changes as a group and preserve unrelated preferences. Preserve explicit recovery
for a lost acknowledgement; do not replay an uncertain write.

Agent execution limits can be a separate bounded group using the existing
field-level expected-value writer. Research has its own reviewed defaults contract;
do not promise atomicity across these domains/files. Keep tool availability and
permissions separately reviewed. Availability controls disabled tool names;
permissions control the execution gate, with additional enforced ask behavior
for configured MCP and file edits. The distinct semantics are source-verified.
Theme continues live preview/reset/Apply independently of these shared saves.

Sources: [defaults request schema](../../packages/application/src/klaude_application/browser_media_settings.py#L152),
[journaled writer](../../packages/application/src/klaude_application/model_default_settings.py#L56),
[Agent request/save contracts](../../packages/application/src/klaude_application/browser_settings.py#L152),
[tool availability and gates](../../packages/application/src/klaude_application/browser_tools.py#L200).

## Implementation phases and acceptance criteria

| Phase | Scope | Gate |
| --- | --- | --- |
| 0. Establish baseline | Resolve the existing CI failures separately; agree on tri-state capability wording and metadata projection | Python matrix green; no unsupported capability claims |
| 1. Searchable picker | Shared Material 3 picker, connection/source identity, role-aware results; integrate composer and defaults through existing adapters | Explicit selection/review retained; no new inference or silent runtime/default changes |
| 2. Fallback workflow | Ordered lists, compatibility reasons, inheritance/inactive messaging | Exact order survives reload; duplicates/stale bindings rejected; no implicit fallback |
| 3. Grouped review | Fixed Model Defaults batch, then separately scoped Agent execution group | Complete-candidate invariants, atomic owned effects, stale/unknown recovery verified |
| R1. Memory reliability | Correct extraction and evaluate labeled durable-memory cases | Questions/quotes/logs do not become durable facts; opt-out and explicit reviewed memory preserved |
| R2. Connection reliability | Instrument routine renewal versus failure; refine status/retry ownership | Healthy rotation avoids outage messaging; offline/restart/auth expiry/cursor recovery remain correct |

R1/R2 are independent reliability slices, not reasons to postpone the entire
picker behind another Settings redesign. Vision state/evidence corrections belong
in the shared backend and require their own regression tests before shipping
claims based on them. Side-panel preference preservation is a separate small
slice: existing controls already collapse panels, but `updatePanelLayout()` resets
Activity visibility at its breakpoint. Preserve explicit preference across resize;
keep mobile drawer dismissal accessible without adding automatic desktop collapse.
Source: [panel controls](../../apps/webhost/src/klaude_webhost/static/app.js#L438).

Validation must include:

- Exact configured references, duplicate names across connections, Local/Cloud
  source ambiguity, missing credentials, disabled/missing saved models and long
  model names. No capability inferred solely from a name or provider label.
- Known true/false/unknown completion/tool/image/Thinking metadata, inspection
  budget exhaustion, connection/credential changes during inspection and review,
  and the same admission policy in composer and defaults.
- All role unset semantics; active Chat image support distinct from Vision
  analysis; disabled Vision drafts and clearing an enabled primary; mandatory
  Thinking and bounded-adapter exclusions. Validate the entire candidate.
- Ordered fallback saves, empty lists, primary duplication, reorder/remove,
  eligible versus ineligible failures, and an unavailable configured fallback.
- Refresh/reload/Back/Forward, draft retention, stale results, cancellation,
  sign-out and late responses; accepted work remains owned after navigation.
- Keyboard and screen-reader selection, focus return, 320/390/768/1024/1440/1920/
  2560px, short viewports, 200% text, light/dark, reduced motion and forced colors.
  Test with either side panel explicitly collapsed and with both open.
- Grouped saves: one review/receipt, whole-group rejection on stale fields,
  concurrent CLI/TUI writes, unrelated preference preservation, worker loss,
  idempotent request IDs and exact-state recovery without replay.
- Connection renewal beyond two 30-second cycles, offline/online, host restart,
  401/410/429/5xx, background/foreground tabs, dropped heartbeats and replayed
  approvals/questions. Read-only reconnect must never claim session control.
- A memory fixture set with negative examples, source/opt-out checks, redaction
  and duplicate handling, while leaving existing owner memory untouched.

## Evidence, limits and handoff

Existing focused tests run during this investigation on Python **3.12.3**:

```sh
.venv/bin/pytest tests/unit/test_memory.py tests/unit/test_web_media_settings.py tests/unit/test_model_capabilities.py -q
```

Result: **76 passed in 33.33s**. These tests do not cover all newly reproduced
memory negatives or the enabled-Vision clearing invariant; their success does not
invalidate those findings. No production or test source files were changed.

Minimal reproduction for F5/F6, using only a temporary preferences file:

```sh
.venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from klaude_application.browser_media_settings import prepare_media_setting
from klaude_core.memory import auto_memory_candidates
from klaude_core.settings_store import update_settings

print(auto_memory_candidates("Why do I always get this error?"))
# ['Why do I always get this error?']
with TemporaryDirectory() as directory:
    cfg = SimpleNamespace(data_dir=Path(directory), models={"coder": "fixture"})
    saved = {"chat": None, "vision": "ollama/fixture", "vision_enabled": True}
    update_settings(cfg.data_dir / "chat-preferences.json", {("ai_defaults",): saved})
    fields, _, _ = prepare_media_setting(cfg, {
        "operation": "defaults-save", "field": "vision",
        "value": None, "expected": "ollama/fixture",
    })
    print(fields["change"]["value"])  # None: review preparation accepts the clear.
PY
```

To repeat F7 without the local probe file, create `LocalWebHost(_app(tmp_path))`
using the deterministic fixture in `tests/unit/test_webhost.py`. Submit and finish
one fixture turn so the session has a public replay cursor, authenticate through
its bootstrap fixture, then read `/api/v1/events?after=<snapshot cursor>` to EOF
with a client timeout above 30 seconds. Measure elapsed time and heartbeat lines,
then verify `/api/v1/session` still returns 200. Use a temporary host/store and
never print bootstrap credentials or cookies. This measures the server lifetime;
a separate browser check is required to measure the visible reconnect interval.

Temporary evidence files, useful locally but not part of the pullable repository:

- `/tmp/klaude-models-review-probes.py` and
  `/tmp/klaude-models-review-probes.json`: memory extraction/persistence, dormant
  Vision, mocked unknown-capability admission, configured source and the final
  successful HTTP stream timing probe. Unknown-capability calls use mocked
  catalog/current-definition reads; they are not live provider validation.
- `/tmp/klaude-models-review-vision-clear.json`: unmocked review preparation and
  candidate validation for clearing an enabled Vision primary, in a temporary store.
- `/tmp/klaude-models-review-tests.log`: focused pytest result.
- `/tmp/klaude-models-review-ci-312.log`: existing failed checkpoint CI log.

The first stream probe used an empty replay cursor and returned 410; the final
probe seeded a deterministic fixture conversation and measured healthy 30.08s
rotation. The report's timing comes from that successful probe. It is an HTTP
measurement plus source inspection of browser state, not a physical-device or
LAN reliability test. The fixture runtime returns deterministic text and performs
no model generation. Actual installed model compatibility and the owner's stored
memory entries remain unverified.

The checkpoint's [CI run](https://github.com/Chansovisoth/klaude-code/actions/runs/39617028563)
fails unit tests on Python 3.11/3.12/3.13; lint/types and installed-wheel smoke
passed. The [Python 3.12 job](https://github.com/Chansovisoth/klaude-code/actions/runs/39617028563/job/119280692127)
reports **4 failed, 4159 passed, 20 skipped**: three workspace-reader tests raise
`FileNotFoundError: rg`, and one workspace-read assertion receives 400 instead of
200. This investigation read the failure log but did not fix CI or reproduce the
complete matrix. Restore the CI baseline separately before merging implementation.

Handoff: start with Phase 1, reusing the existing Models browser and dialog/review
seams. Keep F4/F5 visible as backend correctness constraints, and schedule F6/F7
as bounded independent reliability fixes. No Settings navigation rebuild, global
confirmation removal, automatic side-panel collapse, Settings search, model
replacement or Memory UI expansion is proposed.

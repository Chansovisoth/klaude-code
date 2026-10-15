# S5a — Native Ollama Model Manager

Date: 2026-10-14. This implements the native lifecycle slice of the
[S5 plan](odysseus-settings-and-features-plan.md#s5--model-manager), following
[S4's completed Library and Research work](s4b-deep-research-validation.md).
S5b managed serving, S5c dependencies/SSH and S6 remain unstarted.

## Delivered interaction

- `/model-manager` opens a workspace outside Settings. **Settings → Models →
  Model Manager** opens the same owner and returns to Models on Back.
- The home page offers **Endpoint, Installed models, Download model, Discover
  models, Service status, Hardware**. Only enabled Local native Ollama connections
  are offered; registered LAN endpoints work without being treated as this
  machine's hardware. Existing endpoint/default ownership stays in Models settings.
- Installed models places **Filter, Sort, Reload models, Download model** before
  the table. Filter switches All/Loaded; sort cycles Name/Size/Recent; 100-record
  pages expose Previous/Next. Tables separate model name, size/state and details.
  Detail actions precede parameters, quantization, role selections and digest.
- Download accepts an Ollama model tag or `hf.co/owner/repository:tag`. A review
  identifies the exact server/model and initially focuses Back. New reviews clear
  old filters and have endpoint/model/action identities. Cancelling review makes
  no pull/delete request. Download does not load a model or change any model role.
- Accepted download/delete work retains the captured target through navigation.
  Progress shows stage and **Current file** bytes, avoiding a false overall-model
  percentage. Cancel/Ctrl+C closes and reaps the owned request. CLI terminals
  update progress in place; captured output reports stage changes instead of
  every byte update. Unknown outcomes advise Reload without claiming rollback.
- Discover searches at most 20 Hugging Face GGUF repositories. Selecting a result
  fills an editable download tag; it does not download. The credential link reuses
  the existing Provider credentials page; Back/Escape returns to Discover.
- Service status reads Ollama version and loaded models, including available
  VRAM/context metadata. Hardware reuses this machine's CPU/GPU/RAM probes;
  missing measurements stay unknown. Neither operation generates or loads models.
- Shared panels retain fixed breadcrumbs/footer, ordinary terminal scrollback,
  composer draft, field editors, page search and logical Back navigation.

## CLI and ownership

The canonical command registry and actual Typer implementation provide:

```text
klaude model-manager list [--endpoint ID] [--offset N]
klaude model-manager status [--endpoint ID]
klaude model-manager pull MODEL [--endpoint ID] [--yes]
klaude model-manager delete MODEL [--endpoint ID] [--yes]
klaude model-manager hardware
klaude model-manager search QUERY
```

Pull/Delete require confirmation unless `--yes` explicitly accepts it. Verified
operations exit 0; failures/unknown outcomes exit 1; Ctrl+C exits 130. Cancelling
a review exits 0 without a mutation. Existing `klaude models`, endpoint settings,
roles and chat model commands retain their meanings.

`klaude_core.ollama_manager` owns fixed native operations, shared by the CLI and
TUI through `OwnedBackgroundJobs`. Browsing does not migrate/create a connection
registry, load models or select one. The transport reuses the existing cancellable
HTTP owner, without optional cloud SDKs, shell commands or process management.
Endpoint key references and inherited credentials travel through the private
worker pipe; credentials never enter argv, public progress or model context.
Connection-owned and custom environment references were tested with real workers.
Hugging Face's API key authenticates discovery. Private Ollama pulls instead use
the Ollama server's own Hugging Face access; no claim of equivalent credentials.

Before mutation the worker rechecks definition/credential revisions, installed
digest and fresh loaded-model state. Delete additionally rechecks configured,
session, Default Chat, Utility/fallback and Research selections. Endpoint aliases
with the same normalized URL share role protection and cache invalidation.
Loaded models, including loaded aliases sharing the target digest, are protected;
unknown loaded state fails closed. Successful operations require a fresh tags
check. Normal failed/uncertain mutation attempts invalidate scoped model caches,
preserving other endpoints. Registry/preferences/credential locks cover the short
delete check/API sequence. Endpoint-scoped locks serialize Klaude mutations.

Active chat, Knowledge, Research, Utility and setup work gate mutations; accepted
manager mutations gate new local model work in this client. Reads are replaceable
and session/store/endpoint scoped. Leaving a page cancels only its read. Accepted
work keeps its original target; late acknowledgements do not steal navigation.
Successful inventory snapshots are reused for 30 seconds, while explicit Reload
checks immediately. Failed reloads retain the original timestamp and mark cached
inventory stale. Provider/definition changes prune obsolete snapshots.

## Bounds and failure behavior

| Surface | Bound |
| --- | --- |
| Model inventory | 1,000 records; 100 per displayed page |
| Native metadata | 2 MB; connect 3 seconds/read 5 seconds |
| Pull stream | 32 MB of progress; 8,192-byte NDJSON lines |
| Pull request | 30-second read stall; 30-minute owned job |
| Public progress | At most twice per second, plus terminal success |
| Worker output | Existing 2 MB final/progress aggregate limit |
| HF discovery | 20 results; 1 MB; connect 3 seconds/read 5 seconds |
| Private model/query input | Printable bounded identity/query, at most 200 characters |

Metadata, duplicate names/digests and progress structures are validated. Pull must
receive explicit terminal success and an observed installed tag. Incomplete or
malformed streams, oversized responses, authentication/rate-limit errors, network
timeouts and disk-full errors remain failures. Raw provider error prose is not
published because it can contain private paths or credentials. Tags/ps failures
remain distinct partial status rather than being reported as an empty inventory.
The additive progress protocol retains ordinary final-result responses and their
existing bound. Cancellation kills/reaps only the owned worker group.

## Validation and observed fixes

### Real CLI/TUI protocol walkthrough

Used bare `klaude` in an isolated workspace/config/data store, with the session
named **TEST KLAUDE FEATURES MODEL MANAGER**. A localhost native-API/HF fixture
recorded every request; no chat/generate/create request occurred. The final
walkthrough passed all eleven scenarios:

1. Settings link, endpoint selection and read-only installed inventory.
2. Controls/table wrapping at 40, 70 and 120 columns.
3. Selected-model deletion protection and Back-focused review.
4. Private download editor and cancelled review without mutation.
5. Owned streamed download progress and verified installation.
6. Reviewed deletion retaining original models and connection.
7. Worker cancellation/reaping and actual HTTP stream closure.
8. Bounded GGUF discovery and credential-owner Back navigation.
9. Owned local hardware read with honest unknown fields.
10. Service status without generation or service control.
11. Real CLI pull/delete with shared workers and correct successful exit codes.

The walkthrough also preserved a pre-existing workspace file byte for byte and
the fixture's two original models. PTY SVG/text captures were visually inspected:
wide tables align headers/values/details and use available width; narrow tables
wrap into labelled rows within the scrolling body. Shared 40-column startup/chat
chrome remains cramped; manager content stays bounded. Geometry was checked from
actual captures, not a redesigned mockup. Captures inherited NO_COLOR, so this
does not certify every theme's colors. Semantic feedback uses shared panel styles.

Local walkthrough evidence: `.klaude/data/s2-models-4c_jlykw/manager-result.json`,
its `manager-*.txt`/SVG captures, and `/tmp/klaude-s5a-final-visual-walkthrough.log`.
These are ignored local QA artifacts, not production configuration.

A separate real CLI PTY check verified a single live progress row, successful
pull/delete exit 0, and actual SIGINT cancellation exiting 130 with its HTTP
stream closed and original fixture models retained. The initial raw ETX attempt
did not signal a child without a controlling terminal; the harness then delivered
SIGINT directly. This is CLI signal/cleanup evidence, not a claim about that
initial terminal setup.

CLI signal evidence: `.klaude/data/s2-models-18fbxqxo/cli-progress-result.json`;
the acceptance log is `/tmp/klaude-s5a-cli-progress-verified.log`.

An additional real TUI fixture withheld `/api/ps`. The inventory showed Unknown,
the Loaded filter reported unavailable status rather than no matches, and the
download review was blocked. No POST/DELETE request occurred. Evidence:
`/tmp/klaude-s5a-unavailable-status.log` and its named local captures.

Observed product issues fixed during testing:

- A retained `back` filter could hide a new confirmation. New reviews reset their
  filter and focus Back while retaining independent inventory navigation state.
- Enter on legacy Provider Back bypassed generic panel/cancel hooks. The actual
  settings action route now returns to Discover; Enter/Escape have regression tests.
- Installed/discovery rows originally lacked table schema/header alignment.
  They now use the shared navigation-table renderer with explicit column/section IDs.
- Fresh navigation reread the same endpoint unnecessarily. A truthful 30-second
  snapshot is reused; explicit Reload and stale snapshots still trigger owned work.
- CLI inventory could lose custom inherited credential references, and the worker
  rejected connection-owned references. Selected references are now passed through
  the private pipe without forwarding unrelated API keys.
- Per-byte CLI log output was excessive. Live terminals reuse one progress area;
  captured logs emit stage changes. Worker protocol review also scoped the smaller
  event limit to progress rather than imposing it on legacy result packets.
- Unavailable loaded state could look like an empty Loaded filter. It now stays
  visibly unknown in TUI/CLI, and download blockers use an action-specific label.

Driver/setup failures were distinguished from product failures: a retained test
search hid a new inventory row, an offscreen hint was incorrectly awaited and a
driver CLI environment helper was missing. Those attempts were not reported as
successful final walkthroughs. The final rerun uses the unchanged eleven scenarios.

### Actual native Ollama lifecycle

Tested the installed **Ollama 0.33.3** service through the real manager CLI and
owned worker. Baseline was **22 installed models, zero loaded**. The QA tag
`all-minilm:22m` was initially absent; it is an approximately 46 MB public embedding
model, used solely to validate download lifecycle, not coding/embedding quality.

- Cancelled the actual transfer after **425,984 / 45,949,216 bytes** reported for
  its main file. Worker cleanup completed; the tag was not installed afterward.
- Retried through `klaude model-manager pull all-minilm:22m --yes`: exit **0**,
  approximately **45.5 seconds**, explicit success and observed installed tag.
- Deleted only the newly downloaded QA tag through the manager CLI: exit **0**.
- After cleanup, all **22 original names/digests were unchanged**, with zero
  loaded models. No user's model, endpoint, role or file was removed.

Native evidence: `/tmp/klaude-s5a-native-acceptance/native-result.json` and its
captured CLI output, with `/tmp/klaude-s5a-native-acceptance.log`.

The protocol fixture covers disk-full, invalid progress, stream truncation,
missing ps, changed definitions/credentials/digests, role aliases, network timeout,
cache scopes and late results. No real disk exhaustion, paid generation, private
HF download or remote-serving failure was induced.

### Automated and packaging validation

Final local validation used Python **3.12.3**:

- `UV_CACHE_DIR=/tmp/klaude-s5-uv-cache make check`: **2,890 passed, 19 skipped**
  in 168.55 seconds; Ruff passed; mypy passed **116 production source files**.
- Focused lifecycle/actual-worker/credential checks: **63 passed** after the final
  failure-state fix. Provider-owner Back checks passed for both Enter and Escape.
- `make package-smoke`: all **five wheels** built, installed together in an
  isolated temporary virtual environment, imported and ran installed `klaude --help`.
- `git diff --check`: passed. No dependencies, lock file or version changed.

Earlier full-suite attempts exposed two registry/landing expectation failures;
both were fixed while retaining chat as the primary help entry. A later full
attempt failed the existing concurrent-secret test when its 200 ms lock deadline
expired: **1 failed, 2,888 passed, 19 skipped**. The settings module then passed
all **15 tests** in isolation; the final complete gate above passed with packaging
and terminal walkthroughs no longer running concurrently. Production lock bounds
and the existing test were retained. These failed attempts are not green gates.

Logs: `/tmp/klaude-s5a-release-check.log`,
`/tmp/klaude-s5a-final-focused.log`, `/tmp/klaude-s5a-settings-recheck.log` and
`/tmp/klaude-s5a-release-package.log`.

## Remaining S5 scope and limits

- S5b still needs installed llama.cpp/vLLM engine integration, reviewed launch
  fields, owned process/log/cancel control, port/health failures and endpoint
  registration only after successful health checks. Nothing launches/adopts them yet.
- S5c still needs dependency inspection/explicit installs/rebuilds and SSH server
  connection, model-directory and server hardware/process ownership.
- Ollama can retain/share partial blobs after cancellation; request cancellation
  does not promise server storage rollback or stop another client's transfer.
  A killed worker may miss its final cache invalidation. Reload the affected
  endpoint/model choices after an uncertain outcome. There is no durable transfer
  queue or automatic restart; retry the same tag explicitly.
- Native APIs cannot conditionally delete by digest. Klaude rechecks and serializes
  its own work, but external clients can race the last check and server mutation.
- GGUF discovery is repository-level; choose quantization/file tags manually.
  Hardware is this machine's measurements, not remote hardware, a fit estimate,
  throughput test or model tool-capability evidence.
- Unit/static/packaging gates are local. Python 3.11/3.13 CI and release publication
  have not been run for this uncommitted slice. No dependencies/version/lock changed.

Next implementation slice: **S5b managed serving**. S5 overall is not complete.

## Primary protocol references

Inspected official documentation on 2026-10-14:

- [Ollama native API definitions](https://github.com/ollama/ollama/blob/main/docs/api.md)
  for tags, ps, version, pull stream success/cancellation and server-side deletion.
- [Ollama installed inventory](https://docs.ollama.com/api/tags) and
  [loaded-model status](https://docs.ollama.com/api/ps).
- [Hugging Face GGUF through Ollama](https://huggingface.co/docs/hub/en/ollama)
  for repository/tag syntax and the server's private-repository authentication.
- [Official all-minilm:22m catalog](https://ollama.com/library/all-minilm:22m)
  for the small lifecycle-test artifact.

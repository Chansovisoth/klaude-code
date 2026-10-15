# Model settings capability discovery

Date: 2026-10-15. Base revision: `4a64ce6`, including the live uncommitted
worktree. Existing Library/navigation and phase-verification changes were
preserved. No commit, push, provider-default change or model generation was
performed for this update.

## Problem and root cause

Settings → AI Defaults → Vision → Ollama → Model listed installed model names
with `Images: unknown · checked before saving`. The inventory normally came
from the cached `/api/tags` catalog, which does not establish image support.
The actual `/api/show` inspection ran only after selection. Consequently users
could not identify suitable models while browsing, although the server already
exposed the relevant metadata.

## Implemented behavior

- AI Defaults model lists and Models → Added Models → Manage models
  automatically inspect native Ollama capability metadata in background workers.
- Labels use explicit declarations, never model-name/family guesses:

  | Server capability | Picker label |
  | --- | --- |
  | `vision` | Vision: image input/understanding |
  | `completion`, without image/audio capabilities | Text only |
  | `tools` | Tools |
  | `thinking` | Thinking |
  | `embedding` | Embeddings |
  | `image` | Image generation (server) |
  | `audio` | Audio (server) |
  | `decision` / `insert` | Decision / Fill in middle |

- Generation and audio labels describe the server's declaration; they do not
  add a Klaude consumer. Klaude's existing image-generation settings and native
  stable-diffusion.cpp workflow remain separate from Vision image input.
- The Vision list marks known incompatible entries `No vision` and disables
  their selection. Pure non-chat entries are marked `Not chat`; Manage Models
  still permits their inventory management but prevents using a known non-chat
  model for the session.
- Missing, malformed, timed-out or inaccessible metadata remains `Unverified`,
  with a short reason. Failed metadata is never converted into false positive
  or negative capability evidence. Unknown Vision choices retain the existing
  fresh inspection before saving; successful picker checks also retain that
  save-time gate.
- `Refresh capabilities` sits above the AI Defaults table. Manage Models uses
  its existing `Reload models`. Controls and purpose text remain outside the
  table, and capability text wraps in narrow terminals.

The capability names follow the current upstream
[Ollama capability definitions](https://raw.githubusercontent.com/ollama/ollama/main/types/model/capability.go).
Ollama also documents image generation as a separate, experimental capability
in its [image-generation announcement](https://ollama.com/blog/image-generation).
These sources establish terminology, not successful inference for every model
or support through Klaude's generation consumer.

## Bounds, ownership and privacy

- Only the selected, enabled native Ollama endpoint is queried. Compatible
  llama.cpp/vLLM and cloud endpoints retain their existing catalog/profile
  evidence; no native Ollama requests are sent to them.
- Each job handles at most eight models with four concurrent metadata reads.
  The existing bounded Vision HTTP transport caps metadata at 1 MB, connects
  within three seconds and bounds each metadata request to six seconds. The
  existing owned process worker has a 20-second outer deadline.
- One browse scan covers at most 1000 distinct models per endpoint. Requests
  are finite even when a scan takes longer than the cache duration. A whole-job
  failure stops the remaining scan and requires explicit refresh/re-entry.
- Advisory results stay stable while browsing, are reused for 60 seconds
  across navigation, and are invalidated by session, connection or credential
  revision changes. They are not written to a second persistent cache.
- Leaving cancels the owned scan. Late results cannot replace another
  endpoint/session's state. Selection and search focus use stable existing row
  IDs, and background updates preserve focused models.
- Workers recheck registered/legacy connection definitions and credentials
  before and after requests. Environment-only keys use the existing private
  worker pipe and stored credential changes take precedence.
- Only bounded capability labels/reasons leave the worker. Raw Modelfiles,
  templates, provider responses, local model paths and secrets are excluded.
  No chat request, inference, model loading, download or settings write occurs.

## Actual CLI/TUI verification

Used the real bare `klaude` executable in an isolated temporary workspace,
config/data directory and session named
`TEST KLAUDE FEATURES MODEL CAPABILITIES`, against this machine's actual
`http://localhost:11434` Ollama server.

- All **22 installed models** were scanned. The observed scan completed in
  **1.93 seconds** after entering the model picker, including owned-worker
  startup and UI polling; this is one local observation, not a latency promise.
- Installed Gemma 4 12B/31B/E2B/E4B and GLM-OCR showed declared Vision support.
  GPT-OSS 20B/120B showed `No vision` and text/tool/thinking declarations.
- Actual Gemma metadata also declared audio on several entries; these display
  `Audio (server)` without advertising an audio workflow in Klaude.
- Automatic checks, filtered Gemma/GPT-OSS rows, explicit refresh, Back
  navigation and clean exit passed. The same declarations appeared in the
  real Manage Models page.
- Captured the Vision list at **40, 80 and 120 columns** and inspected rendered
  screenshots at 40/120. Shortened new controls/purpose text after the initial
  narrow-layout check. Tables align at wide sizes; narrow rows wrap their
  status and capabilities without crossing the terminal width.
- No installed image-generation model was exercised. Its label and non-chat
  eligibility were verified with metadata fixtures, without generation.

Evidence is local and untracked: successful complete walkthrough receipt and
terminal captures in `.klaude/data/s2-models-8bbejtma/`; the earlier successful
Vision walkthrough and inspected PNG renders are in
`.klaude/data/s2-models-yjrg1_p0/`. Earlier incomplete harness attempts were
retained. Their failures concerned waiting for asynchronous inventory and
clearing picker search before another slash command; corrected walkthroughs
passed.

## Automated validation

- Model capabilities, model settings, AI Defaults, model connections, native
  Vision and HTTP Vision regression run: **193 passed in 75.60 seconds**.
- After the final endpoint-cache bound correction, settings/controller tests
  and relevant CLI tests: **80 passed, 844 deselected in 7.11 seconds**.
  These runs overlap; their counts must not be summed as unique tests.
- New coverage includes malformed/oversized metadata, precise unknown states,
  privacy, definition changes during a request, session/endpoint/credential
  staleness, partial failures, large foreign inventories, finite scans across
  cache expiry, fresh save-time inspection, focus and width preservation.
- A real owned-worker cancellation fixture blocked four parallel localhost
  metadata requests, cancelled the scan, verified worker cleanup and confirmed
  no late result or additional batch was published.
- Repository Ruff passed. Production mypy passed across **147 source files**.
  Initial localhost fixture runs were sandbox-blocked; they were rerun with
  localhost access. The full application suite and packaging were not rerun
  for this settings-specific change.

## Implementation and remaining scope

- `apps/cli/src/klaude_cli/model_capabilities.py`: bounded worker and shared
  scoped settings inventory.
- `apps/cli/src/klaude_cli/background_worker.py`: fixed worker dispatch.
- `apps/cli/src/klaude_cli/ai_default_settings.py`: role labels/eligibility,
  refresh and lifecycle integration.
- `apps/cli/src/klaude_cli/model_settings.py`: Manage Models labels/details and
  known non-chat selection guard.
- `tests/unit/test_model_capabilities.py`: metadata, lifecycle and UI regressions.

Capability declarations are advisory, not an inference certification. Older
servers that omit metadata remain unverified; other provider catalogs can also
remain unknown. This update covers settings discovery/eligibility. It does not
implement the separate image preparation, request-budget or provider-error
repairs in [the image attachment reliability plan](image-attachment-reliability-plan.md).

# S2c: DeepSeek adapter slice

Date: 2026-10-13. Parent checkpoint: `0db42b4`.

DeepSeek is implemented and validated locally. S2c's native Anthropic adapter is
next; S3–S6 remain unstarted. This record follows
[S2b AI Defaults](s2b-ai-defaults-validation.md).

Follow-up: [native Anthropic is now implemented and validated locally](s2c-anthropic-validation.md).
The observations below describe this earlier DeepSeek slice.

## Implementation

- DeepSeek is selectable in Add API Models and the existing Cloud model picker.
  Add DeepSeek endpoint opens the same unsaved, masked-key form. Its shortcut
  clears previous draft keys/test results and respects an already accepted save.
- `klaude model-connections add ID --adapter deepseek --url URL` requires HTTPS
  and defaults to the `DEEPSEEK_API_KEY` environment reference. It never stores a
  key in the public registry or silently seeds a new global provider connection.
  TUI drafts retain independent connection-owned keys. Existing connections,
  defaults, sessions and embedding roles are preserved.
- The machine-local `config/model-connections.json` is now gitignored, matching
  its private settings role. Its current contents were preserved.
- Models use `deepseek@CONNECTION/MODEL` references in session selection and AI
  Defaults. Availability/revision/credential checks remain effective. Utility
  inherits the adapter or uses an explicit DeepSeek override; its bounds and
  typed explicit fallback policy remain unchanged.
- `DeepSeekRuntime` specializes the existing HTTPX Chat Completions transport.
  It shares bounded SSE parsing, completed-call publication, sanitized typed
  errors, independent child transports and cancellation before response headers.
  No cloud SDK or dependency/lock change is needed.
- Standard mode explicitly sends `thinking: disabled`; thinking sends enabled
  with low → low and medium/high → high. Provider defaults do not override the
  selected mode. Native GPU/context allocation options are not forwarded.
- Reasoning is retained as private continuation, with a 256,000-character bound.
  It is emitted to the agent only after a complete response and echoed to native
  tool-enabled requests only for the same endpoint, connection/credential revision
  and model. Final continuation is saved in owner-only `model_content`, restored
  separately from visible content and counted in compaction. Generic compatible,
  Ollama and other provider requests omit it; tool-free Utility receives public
  dialogue only. No reasoning is displayed or treated as a verified tool result.
- Catalog checks remain metadata-only. A catalog entry still has unknown tool
  capability evidence, rather than claiming live tool certification. The native
  adapter declares its supported effort contract without inferring it from names.
- `DEEPSEEK_API_KEY` crosses the existing private job pipe for inventory checks,
  including the first read; saved credential removals/replacements still win.

## API contract reviewed

The current official docs were researched before implementation. DeepSeek's
thinking/tool API requires previous reasoning to be echoed for tool-enabled
requests, including previous final answers. A generic Chat Completions adapter
that strips all reasoning cannot meet that contract. This justifies the dedicated
adapter while preserving generic endpoint behavior.
[Thinking and tool continuation](https://api-docs.deepseek.com/guides/thinking_mode/).

The implemented payload uses the documented thinking toggle, effort mapping,
max-token cap and streamed tool-call fields.
[Chat Completions contract](https://api-docs.deepseek.com/api/create-chat-completion/).
Model IDs are catalog-driven and manually enterable; no current model names or
prices are hardcoded.
[Catalog contract](https://api-docs.deepseek.com/api/list-models/).

## Real CLI and terminal evidence

Successful isolated run:
`.klaude/data/s2-models-rw2g7tuf/s2c-result.json`.
Session name: **TEST KLAUDE FEATURES S2C**.

This used the bare executable, real PTYs and HTTP loopback DeepSeek protocol
fixtures. It is an integration test, not a live cloud model evaluation or the
previous CSV implementation benchmark. The fixture connection was explicitly
marked Local to allow loopback HTTP; production API registration requires HTTPS.

1. Navigated Add Models → Add API Models → Provider → DeepSeek. The official URL
   and required masked key were visible. A missing-key test did not save a
   connection, write credentials or generate text. Escape/cancel preserved the
   original registry bytes.
2. Navigated `/model` → Cloud → DeepSeek. The explicit endpoint shortcut opened
   a fresh unsaved form. Captures at 120/80 columns were visually inspected:
   aligned values at 120, wrapped URLs/descriptions at 80, muted explanatory
   text, visible breadcrumbs/footer and separate controls.
3. Selected the qualified fixture model through the real session flow. Ordinary
   chat and inherited `/recap --ai` sent tool-free requests with thinking disabled
   and the unchanged 512-token cap. Empty saved dialogue refused Utility before
   generation. The TUI exited **0**.
4. Ran `klaude ask --model deepseek@fixture-deep/catalog-model` with configured
   thinking and a read-only two-file request. The agent executed real `read_file`
   tools for `challenge.md` and `notes.md`, then returned their combined
   requirements. The fixture required the private continuation on both tool
   responses; the three-request round-trip completed, exit **0**.
5. Neither the key canary nor the reasoning canary appeared in terminal/one-shot
   output. The fixture recorded five POSTs total: two tool-free requests and
   three tool-enabled requests. No retries or hidden extra calls occurred.

Captures: `deepseek-preset-120`, `deepseek-missing-key-120`,
`deepseek-model-picker-80`, `deepseek-shortcut-80`, `deepseek-utility-80`.
Terminal output and `ask.log` are retained. SVG previews reconstruct terminal
colors/geometry with a local monospace font, not another terminal's exact pixels.

The initial driver run in `s2-models-cm0idrgk` stopped while inspecting a field
hidden by its own retained page-search query. The driver now clears that query
before inspecting the full form. That failed run is retained, not counted as
passing evidence.

## Regression validation

Final source on Python 3.12.3:

- Full locked `make check`: **2,599 passed, 19 skipped** in 132.28 seconds,
  exit **0**. Ruff passed; production mypy passed for **94 source files**.
- `make package-smoke`: all **five wheels**, isolated installation, public
  imports and installed `klaude --help` passed, exit **0**.
- Final focused provider/picker checks: **34 passed, 857 deselected** before the
  last private-pipe regression. That focused inventory set passed **3 cases**.
- A real owned-worker IPC check in
  `.klaude/data/s2c-private-pipe-1tj_fqyk/result.json` passed the environment-only
  DeepSeek key through the private request pipe, with no credential file, no
  network request and no secret in the public result.
- `git diff --check` passed. Logs, drivers and final source hashes are retained
  with the successful terminal run. The source snapshot includes existing dirty
  S1/S2a/S2b implementation, not just files authored in this slice.

Targeted coverage includes private tool/final continuation and restore; endpoint,
connection identity and model isolation; unchanged shared history; standard and
thinking modes; output bounds; malformed/oversized reasoning; malformed-call
recovery; output-limit/incomplete-stream rejection; typed sanitized 400/401/403/
429/503 failures; HTTPS registration; connection-owned secrets; fresh-draft/
pending-save behavior; private environment-key IPC; Utility construction; and
both streaming/non-streaming cancellation before headers for both HTTP adapters.

Earlier broad checks exposed a shortcut calling the wrong controller method,
an overlong tip wrapping an exact-fragment assertion and legacy picker fixtures
reading the ambient registry. The shortcut is fixed, the tip is concise and
those fixtures use isolated config paths. A later full run passed all 2,598 unit
cases but failed lint on a newly wrapped test signature; that formatting issue
was corrected. The final full gate, not those earlier attempts, is authoritative.
Final whole-suite runs use isolated default config/data paths to protect live
settings from test workers. No ambient registry cleanup was performed.

## Remaining limits

- Live paid DeepSeek generation/authentication is unverified. Catalog, payload,
  transport, tools, error and cancellation behavior are validated through local
  protocol fixtures and primary documentation, not a real DeepSeek account.
- This slice implements the documented stable Chat Completions API. Beta strict
  schemas, DeepSeek Responses/Anthropic formats and vision attachments are not
  enabled or claimed. Older model aliases must support that current contract;
  incompatible requests fail honestly.
- DeepSeek is managed through explicit endpoint connections. There is no second
  global Login/Logout credential store. Existing endpoint credential maintenance
  and partial-save limitations remain as documented in S2a/S2b.
- Large reasoning outputs can exceed the finite output/continuation bounds.
  Incomplete responses remain failures; they do not cause silent model switches.
- Current-source Python 3.11/3.13 CI and native Anthropic are pending. No commit,
  push, release, version/lock change or unrelated worktree cleanup was performed.

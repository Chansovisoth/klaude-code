# S2c: Native Anthropic adapter

Date: 2026-10-13. Parent checkpoint: `0db42b4`.

Native Anthropic is implemented and validated locally. This completes the named
DeepSeek/Anthropic adapters in S2c, following
[DeepSeek](s2c-deepseek-validation.md). S3–S6 remain unstarted; next is S3a Search.
Live paid Anthropic generation is unverified.

## Implementation

- Add API Models offers Anthropic; `/model` → Cloud → Anthropic has an explicit
  Add Anthropic endpoint shortcut. Both use the existing unsaved draft and masked,
  connection-owned credential flow. Cancellation does not save. CLI registration
  accepts `--adapter anthropic`, requires HTTPS and defaults to the private
  `ANTHROPIC_API_KEY` reference. It does not seed an unsolicited endpoint or change
  current/default models, embedding roles or existing credentials.
- Qualified `anthropic@CONNECTION/MODEL` references work in session selection,
  Default Chat and eligible Utility selections. Existing connection, credential,
  availability and pending-selection revision checks apply.
- Catalog discovery uses native authentication/version headers and pagination:
  at most ten pages, 1,000 models and 1 MB combined JSON, with existing owned-job
  deadlines. Repeated/invalid cursors and malformed capability data fail without
  publishing a partial catalog. Authentication, rate limiting, offline and
  malformed responses stay distinct. No generation occurs during catalog checks.
- Public cache metadata retains declared thinking types, effort levels and
  output-token limits. Missing thinking metadata stays unknown; model names do
  not determine capabilities. A successful catalog is not live tool certification
  and does not inflate the configured conversation window.
- `AnthropicRuntime` implements native Messages with the shared cancellable
  HTTPX transport and bounded SSE parsing. There is no optional SDK, dependency,
  lockfile or version change. Top-level system text, tool schemas, assistant
  `tool_use` and user `tool_result` blocks follow the native protocol. Only
  completed tool pairs are replayed; shared history is not mutated.
- Signed thinking, redacted thinking and complete response blocks are retained
  privately, unmodified, for the same endpoint, connection/credential revision
  and model. They survive owner-only `model_content` restoration and count toward
  compaction. Public transcript, recap/naming and other provider requests omit
  that continuation. Limits are 256,000 private thinking/signature/data characters,
  1 MB total serialized continuation and 64 response blocks.
- Tools publish only after a valid completed native message. Incomplete streams,
  output limits, mismatched stop reasons, missing signatures and duplicate tool
  IDs fail honestly. Malformed JSON arguments enter existing bounded agent
  recovery. Typed HTTP errors omit upstream bodies; native overload errors use
  HTTP 529 for the existing explicit Utility fallback policy.
- Input usage includes cache reads/creation; cumulative streamed output updates
  replace earlier values rather than double counting. Missing usage stays partial.
- Standard explicitly disables thinking. Thinking uses the declared adaptive or
  manual configuration, supported effort and unchanged output cap. Manual
  thinking needs a cap above 1,024 tokens; insufficient budgets fail clearly.
  Unknown thinking profiles require catalog metadata, without another discovery
  call during generation or silent budget enlargement.
- Known always-on models visibly select Thinking with the lowest supported effort;
  mode/effort pickers and direct controls respect declared capabilities. Known
  disabled-only models cannot be switched into Thinking by an effort command.
  Known always-on models are unavailable for the tool-free, thinking-disabled
  Utility/fallback role; runtime checks also enforce that constraint. Utility
  remains opt-in, bounded and explicit about fallbacks.

## API contract reviewed

Implementation used current primary documentation. The native Models API declares
thinking configurations, effort support and output limits, and uses cursor-based
pagination. Capability metadata is kept separate from successful generation
evidence. [Models API](https://platform.claude.com/docs/en/api/models/list).

Messages requires native content blocks, top-level system instructions and
authentication/version headers. A generic Chat Completions payload is insufficient
for direct Anthropic endpoints.
[Messages API](https://platform.claude.com/docs/en/api/messages/create).

Thinking/tool continuation requires preserving complete signed or redacted blocks;
manual and adaptive thinking have distinct controls. This state is private model
continuation, never user-visible scratchpad or verified tool evidence.
[Thinking contract](https://platform.claude.com/docs/en/build-with-claude/thinking).
Streaming uses block start/delta/stop events, cumulative usage and explicit message
termination. [Streaming contract](https://platform.claude.com/docs/en/build-with-claude/streaming).

## Real CLI and terminal evidence

Clean successful run:
`.klaude/data/s2-models-mbwlo56c/anthropic-result.json`.
Session: **TEST KLAUDE FEATURES ANTHROPIC**.

This used the bare executable, real PTYs and an HTTP loopback native Anthropic
fixture. It verifies integration/protocol behavior, not live paid model capability
or the earlier CSV benchmark. The fixture connection was explicitly Local to
permit loopback HTTP; production API registration requires HTTPS. Fixture IDs are
arbitrary and contain no model-family inference.

1. Ran `klaude model-connections test fixture-anth` through the real owned
   background worker and private credential pipe. It returned two qualified
   models, exit **0**, with unknown tool capability evidence. Native thinking
   capabilities survived publication and subsequently controlled the picker.
2. Opened the Anthropic API preset and inspected URL/required authentication.
   A missing-key Test and cancellation preserved the original registry bytes.
   Cloud → Anthropic → Add endpoint reopened a fresh unsaved draft.
3. Selected the catalog-declared always-on fixture through `/model`. The mode
   panel offered Thinking; effort offered the declared low/high choices. Selecting
   low sent native adaptive thinking/low with the unchanged 512-token cap.
4. Switched to the catalog model in Standard and ran `/recap --ai` and
   `/rename --ai`. Both inherited the native runtime, sent no tools, explicitly
   disabled thinking and retained the 512-token budget. TUI exit code: **0**.
5. Ran `klaude ask --model anthropic@fixture-anth/catalog-model` with configured
   thinking and a read-only request for `challenge.md` and `notes.md`. Real file
   tools read both files, and the final answer combined their requirements. The
   fixture required original signed blocks on both subsequent requests. The
   three-request round-trip completed with exit code **0**.
6. No key, thinking or signature canary appeared in public output. The fixture
   recorded one catalog GET and six generation POSTs: ordinary chat, two Utility
   operations and three file-task requests. There were no hidden generation
   retries or discovery calls during those turns.

The fixture intentionally supplies private blocks even on thinking-disabled
responses to stress output isolation; this is not a claim about live model behavior.
It requests file tools only when `read_file` is advertised. Earlier failed driver
runs are retained: two expected old panel hints/titles, and another fixture
requested an unavailable file tool. Klaude rejected that call with its bounded
retry and reported failure. Those runs are not passing product evidence. A
clean corrected run is the authoritative walkthrough.

Captures: `anthropic-preset-120`, `anthropic-cloud-80`, `anthropic-draft-80`,
`anthropic-required-mode-80`, `anthropic-effort-80`, `anthropic-utility-80`.
The successful repeat in `s2-models-g528fvxs` supplied the visually inspected
120/80-column form and mode/effort captures: aligned values, wrapping URLs and
muted hints, stable breadcrumbs/footer, visible exit controls. SVG previews
reconstruct terminal geometry/colors with a local monospace font; they are not
another terminal's exact pixels. `tui.log` and `ask.log` are retained with the
clean run, along with `catalog-test.log`, drivers, gate logs and source hashes.

## Regression validation

Final production source on Python 3.12.3:

- Full locked `make check`: **2,630 passed, 19 skipped** in **136.34 seconds**;
  Ruff passed and production mypy passed for **95 source files**.
- `make package-smoke`: all **five wheels**, isolated installation, public imports
  and installed `klaude --help` passed.
- Broader provider/settings/CLI regressions: **970 passed, 1 skipped** in 74.92s.
  Final focused native/mode checks: **93 passed, 782 deselected** in 5.86s.
- Real streaming and non-streaming cancellation before response headers is
  covered for compatible, DeepSeek and native Anthropic transports.
- Native tests cover signed tool/final round-trips, session restore, fragmented
  JSON/signatures, endpoint/model/revision isolation, other-provider omission,
  history nonmutation, cumulative/cache usage, manual/adaptive budgets, typed
  errors, incomplete/output-limit/malformed recovery and bounded pagination.
  Existing reliability, dirty-tree, defaults and settings tests remain in the
  full gate; no broad agent-loop redesign was made.
- Whole-suite checks used isolated default config/data paths to protect live
  preferences. `git diff --check` passed. Baseline hashes identify pre-existing
  dirty S1/S2 work; this slice did not reset, stash, discard or clean that work.

Earlier development checks caught a test that incorrectly expected only the
initial system prompt, omitting real controller messages; the assertion now
checks native top-level system handling. Type errors were resolved before the
final gate. Final validation above is authoritative, not earlier failed attempts.

## Remaining limits

- No live paid Anthropic authentication/generation was attempted. Public docs and
  local protocol fixtures cannot certify every account or model behavior.
- Older/manual model entries without declared thinking metadata can use Standard
  if supported upstream; Thinking requires metadata. Utility for an unknown
  always-on model can still fail upstream honestly. No silent model substitution.
- The stable Messages API is implemented. Vision uploads, beta strict schemas,
  server tools, tool pausing/resumption, Bedrock and Vertex adapters are outside
  this slice. An unsupported block or nonterminal `pause_turn` fails explicitly.
- Finite output/private-state bounds can end large responses. Manual thinking
  requires a user-configured budget above its minimum; no default is inflated.
- Existing S2a/S2b endpoint credential maintenance/partial-save limits remain.
  Current-source Python 3.11/3.13 CI is pending. No commit, push or release was
  performed. S3a Search is planned, not started.

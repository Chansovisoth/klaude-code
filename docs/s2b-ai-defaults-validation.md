# S2b: AI Defaults with working consumers

Date: 2026-10-13. Parent checkpoint: `0db42b4`.

S2b is complete locally, following [S2a](s2-model-settings-validation.md).
S2c provider expansion and S3–S6 remain unstarted.

## Behavior and implementation

- Settings → AI Defaults, also `/settings ai defaults` and `/settings defaults`,
  owns Default Chat, Utility, ordered Utility fallbacks and Utility output.
  Selectors use owned background public inventories, endpoint identities,
  cached model catalogs and manual IDs. Model lists use the shared table layout.
- Default Chat migrates the effective legacy startup choice once, preserving an
  explicit unset. It is independent of the active session. `/model` and queued
  session selections record session history without rewriting Default Chat.
  Bare startup and `/new` use the saved default; `ask` uses it when an AI Defaults
  section exists. Explicit CLI `--model` overrides it. Unavailable/unset choices
  refuse generation or open selection, rather than silently choosing another model.
- Utility defaults to **Same as chat**, resolving the current session model when
  the job starts. An explicit endpoint/model overrides that inheritance. Up to
  three ordered explicit fallbacks can be added, reordered or removed. Canonical
  identities deduplicate legacy/qualified aliases and prevent repeated attempts.
- Consumers are explicit `/recap --ai` and `/rename --ai`, in TUI and line-oriented
  chat. Ordinary chat, deterministic `/recap`, automatic first-input titles and
  context compaction make no additional Utility calls. Generated recaps are public
  session output, not replacement context, memories, verified tool results or
  recursively summarized compaction state.
- Utility reads only recent saved public user/assistant turns: at most 24 records
  and 6,000 characters. It excludes `model_content`, attachments stored there,
  tool output, system records and private reasoning. No tools or workspace actions
  are exposed to the Utility model. Reads do not initialize/migrate the session DB.
- Generation has a 40-second aggregate budget and a 45-second outer kill deadline
  in the TUI, with at most four logical attempts. Earlier candidates have at most
  12 seconds; the final eligible candidate can use the remaining aggregate time.
  Each transport gets a corresponding timeout. Native Ollama inherits the active
  GPU/thread overrides, requests 4,096 context tokens and disables thinking;
  compatible endpoints retain server-owned allocation
  and reasoning. SDK Utility clients disable hidden retries and close owned clients.
- Utility output defaults to **512 tokens**, with explicit 128/256/512/1024/2048
  presets. It includes provider reasoning when the provider counts that against
  its output limit. Native Ollama title requests use at most 128 tokens. Visible
  text is separately bounded; titles must fit 80 characters. Output-limit, invalid
  text and quality/protocol failures do not trigger an automatic model switch.
- Eligible fallbacks are typed network/timeout, 429 and temporary 5xx failures.
  Authentication/configuration failures stop the primary attempt; unavailable
  fallback entries are skipped. No cloud fallback is supplied implicitly. TUI
  receipts identify the actual endpoint/model, fallback use, elapsed time and
  aggregate token usage, or explicitly unknown usage. Line-oriented receipts name
  the actual model and fallback use. Unknown failed-attempt usage
  does not become a fabricated zero.
- TUI generation uses a cancellable owned worker, a progress panel and the shared
  spinner/footer. Escape, Ctrl+C, the Cancel row and exit drop late results and
  terminate the owned process group. The unsent composer draft is retained.
- Defaults writes use the ordered action lane, field comparisons and captured
  definition/credential revisions. Independent fields merge; stale selections and
  same-field conflicts fail rather than overwrite another client. Pending reads
  cannot replace accepted live intent. Failed intent remains visibly unconfirmed;
  active chat stays usable, while Utility requires confirmed settings.
- Removal/disable reviews show affected Default Chat, Utility and fallback roles.
  Utility requires an explicit unset; reviewed fallback removals preserve other
  entries. Core mutations recheck the reviewed role state before saving. Active
  runtimes, unrelated preferences, credentials, embedding configuration and session
  history remain protected.
- AI naming uses a conditional SQLite mutation on the action lane. A concurrent
  manual rename wins. A successful title save is acknowledged even if its separate
  history entry fails; that history failure is reported independently.

Core role configuration lives in `klaude_core/ai_defaults.py`, generation in
`utility.py`, and presentation/ownership in `klaude_cli/ai_default_settings.py`.
Existing model connection, action worker, private job pipe and panel primitives
are reused. No new agent orchestration or automatic background model loop was added.

## Observed problems and corrections

1. Session model selection previously rewrote startup preferences. Separate role
   state now freezes the migrated startup choice and keeps session changes local.
2. The first real compatible Utility recap ended at its 512-token output limit.
   The generic failure obscured the actual cause. Output-limit feedback now names
   the Utility output control, and its visible bounded presets let users choose
   a larger budget. The default remains 512; the model and prompt were unchanged.
   Provider reasoning can consume this budget; the compatible adapter does not
   override private server controls or expose reasoning text.
3. The shared info-row renderer let long values exceed a 38-column body, including
   Session model and Compaction rows. It now stacks/wraps those values with stable
   row ownership and styling. Home/model pages also retain scrolling wrapped rows.
4. Model selectors need more width than ordinary short setting labels. They now
   use the shared Model / Status / Capabilities table with controls above it.
5. SDK defaults could add retries outside the explicit Utility attempt budget.
   Utility requests now specify timeout/retry controls and output limits. Parameter
   shapes were checked against the locally installed OpenAI and Google SDKs, then
   covered by transport-construction tests. This is not paid-provider certification.

## Real CLI/session evidence

The bare executable ran in an isolated workspace/config/data with real PTYs at
120 and 80 columns. Session: **TEST KLAUDE FEATURES S2B**. Model: **gemma4:e2b**,
native Ollama and its separately registered compatible endpoint. Loopback fixtures
provided HTTP 503 and delayed response headers. No paid-cloud generation occurred.

Successful run: `.klaude/data/s2-models-igrmu0_7/s2b-result.json`.

1. Completed real native chat about a TTL cache, thread safety and pending
   validation. No Utility call accompanied the ordinary reply.
2. Changed Default Chat to the compatible Lab endpoint. Settings still showed the
   open session using native Ollama; the accepted runtime did not change.
3. Selected the failure fixture as Utility, explicitly selected a 1,024-token
   Utility output cap, and added Lab as an explicit fallback.
4. Deterministic `/recap` made no Utility fixture request.
5. `/recap --ai` received 503, used Lab once, and produced an attributed recap
   that correctly said no implementation was completed and validation remained
   pending. Public output showed `fallback 1` and honestly unknown aggregate usage.
   Recorded recap elapsed time was **11.3 seconds**.
6. `/rename --ai` followed the same explicit fallback and saved a bounded title.
7. Selected the slow fixture, started Utility, and cancelled before response
   headers. No fallback request followed cancellation and no late result applied.
8. `/new` selected the saved compatible Default Chat. Normal exit and a second
   bare startup both used that persisted choice; both processes exited **0**.

The fixtures recorded exactly two failed-primary recap/title requests and one
cancelled slow request. Their canary error body was absent from the terminal log.
Captures include `defaults-inherited-120`, `default-differs-from-session-120`,
`utility-fallbacks-80`, `ai-recap-fallback-80`, `new-session-default-80` and
`restart-defaults-80`, with separate first/second terminal streams.

The earlier run `.klaude/data/s2-models-6rf6872q` is retained as failed evidence:
native chat/default separation/deterministic recap passed, but the compatible
recap reached the 512-token limit. It is not a passing Utility certificate.

A real `ask` smoke in the successful workspace returned `S2B_SMOKE`, exit **0**,
using the saved compatible Default Chat. `ask-smoke.log` and its result are retained.

Native inheritance also passed real `klaude chat --no-tui` in
`.klaude/data/s2-models-bformdfb/native-result.json`: normal chat, deterministic
recap, AI recap, AI naming and `/new`, with Utility left **Same as chat** and its
unchanged **512-token** default. Both Utility actions reported native Ollama;
the line-oriented process exited **0**. This confirms the default itself remains
usable on the native runtime, separately from the compatible server's larger cap.

The final-source native rerun also passed with the same inherited model and
512-token cap: `.klaude/data/s2-models-yxwo32ns/native-result.json`, exit **0**.
Native GPU/thread option forwarding is separately covered by a request-packet
regression with explicit CPU-only and two-thread overrides; the live rerun used
the machine's existing automatic allocation, not that CPU-only fixture.

Final read-only visual navigation is retained in
`.klaude/data/s2-models-10zjnr52/visual-result.json`, exit **0**. Its four captures
show the AI Defaults home and model table at 80 and 120 columns. Visual inspection
confirmed aligned model/status/capability columns, the manual-entry control above
the table header, muted explanatory text, and wrapped home descriptions at 80
columns. Narrow overflow is also covered by the 38-column renderer regression.
The home and model body scroll inside fixed breadcrumbs/footer; offscreen rows
remain keyboard accessible. No generation or settings mutation was needed for
this visual run. SVG previews reconstruct captured terminal colors/geometry with
a local monospace font; they do not certify another terminal's exact font pixels.

## Regression validation

Final production source on Python 3.12.3:

- `make check`: **2571 passed, 19 skipped** in 138.19 seconds; Ruff passed;
  production mypy passed for **93 source files**. Overall exit **0**.
- `make package-smoke`: five wheels, isolated installation, public imports and
  installed `klaude --help` passed, exit **0**.
- Focused new role/consumer/SDK/panel regressions: **77 passed** before the final
  full gate. The full suite includes prior S1/S2a and agent reliability coverage.
- Final focused role/Utility checks: **27 passed, 840 deselected**, covering
  typed protocol failures without fallback and native GPU/thread option forwarding.

The initial broad pass failed on the narrow-row overflow and two startup-surface
fixtures without a coder model. The renderer was fixed; those presentation-only
fixtures now declare their coder. Earlier focused failures also exposed tests
that still expected session selection to rewrite defaults; their assertions now
verify the new separation, including responsiveness during an unrelated save.
The final full gate is the passing certificate, not those earlier attempts.

Logs, drivers and `s2b-validation-manifest.json` with final source hashes are
retained under `.klaude/data/s2-models-igrmu0_7`. The manifest notes the existing
dirty S1/S2a implementation; hashes capture the combined
validated worktree, not a claim that every changed file was authored in S2b.
Current-source Python 3.11/3.13 CI is pending. No commit, push, version/lock
change, release or unrelated worktree cleanup was performed.

## Remaining limits

- Codex account models can supply Default Chat through their existing account
  path. Utility is unavailable for that adapter until its broker can enforce
  this consumer's generation limits; select an explicit supported Utility endpoint.
- OpenAI API, OpenRouter and Gemini Utility request construction/bounds are
  mocked/SDK-shape validated, not live paid-provider verified. Physical LAN,
  llama.cpp and vLLM certification remains outside this pass.
- Compatible/model-server reasoning can exhaust small output budgets. The user
  can explicitly raise Utility output or choose a native bounded endpoint; an
  incomplete response is still a failure. Larger/slow models can exhaust the
  aggregate deadline. No success or exact token total is inferred on failure.
- Utility summarizes a bounded recent public window. It does not verify project
  state, retrieve attachments or replace deterministic compaction. Long/sparse
  conversations and generated title quality remain model-dependent.
- Registry/preferences/cache maintenance retains its documented partial-save
  behavior; multi-file crash atomicity is not claimed.
- Research, Vision, Image generation and email controls remain deferred to their
  functioning consumers. S2c additional provider adapters is the next slice.

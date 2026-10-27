# Chat admission and unrelated download recovery — 2026-10-26

The reported conversation was idle on `mistral:7b`, but a different model's unknown
pull held the global Model Store resource. Both new chat turns and model changes
checked that global resource. The turns handler then replaced the actual cause
with `Session is busy`. The snapshot did not tell the composer it was blocked.

The client also chose start versus queue from its last rendered snapshot. A
competing client starting a reply, or a reply ending, could make that choice stale
before admission reached the server.

## Changes

- `LibraryManagement.model_chat_blocked()` scopes chat separately from model
  mutations. A pending pull of another exact tag can coexist with chat. Matching
  pull targets remain protected; equal tags on the same configured URL remain
  blocked. Native deletions conservatively block native chat across aliases;
  cloud runtimes remain independent of native weight operations.
- A pull's private target must match the journal's immutable HMAC witness before
  it can establish independence. Missing/changed/unwitnessed targets keep the
  conservative gate. The read never reconciles or releases a mutation fence and
  never contacts a provider. Existing recovery callers of the journal witness
  check still require unknown state; admission readers explicitly opt into active
  receipts too.
- Hosted snapshots expose `chat_model_blocked` and `chat_auto_queue`. A real
  blocker disables Send, including the attachment refresh path, and preserves
  the draft with a visible Downloads action. Interrupted sessions offer New chat.
  The model picker remains reachable so an independent runtime can be chosen.
  Server errors retain a specific cause instead of the generic busy message.
- Updated clients send the capability-gated `auto` disposition. The shared
  application chooses start or queue while holding its turn lock. Existing queue
  and turn receipts are checked before choosing a new admission path. Repeated
  queued requests remain the same request after completion or removal; altered
  input/creator/session still fails existing validation. Attachments retain their
  wait-for-current-reply contract.
- Automatic send intent IDs no longer change just because the active turn
  changes. No uncertain mutation is automatically retried. Explicit `start` and
  `queue` API contracts and the legacy-host client fallback remain available.

No download was replayed, cleared or marked complete to unblock chat. Model
mutation exclusivity, owner authorization, endpoint locks and recovery proofs
remain in place.

## Validation

Focused deterministic suite: **142 passed** across:

```
tests/unit/test_application_bridge.py
tests/unit/test_application_coordination.py
tests/unit/test_application_operations.py
tests/unit/test_model_store.py
tests/unit/test_webhost.py
tests/unit/test_web_accounts.py
```

New regressions cover accepted/running/unknown pull/delete gates, same/different
chat targets, cloud independence, private-target tampering, retained mutation
fences, real chat during and after an uncertain stopped pull, one admission per
request before/during/after a reply, altered intents and removed queue receipts.

Isolated Chromium checks passed:

- `webui_composer_smoke.py`: actual Send from deliberately stale tab state queues
  exactly once, alongside desktop/mobile keyboard, sending/activity, failed-draft,
  duplicate-send, legacy fallback and sign-out cases.
- `webui_chat_layout_smoke.py`: 56 responsive light/dark layout cases plus blocked
  Send, retained draft, reachable model picker, recovery action and restored
  availability. Existing details-menu focus/lifecycle checks remain green.
- `webui_control_smoke.py`: two-client queue/steer/cancel, decisions, terminal
  handoff, 10 control layouts and fencing races.
- `webui_models_smoke.py`: configured/legacy model selection, Thinking/Plan,
  effort changes, failure retention and responsive selectors.

The five changed production Python modules pass mypy. Changed Python files pass
Ruff; JavaScript syntax, both deterministic asset bundles and `git diff --check`
pass. Repository-wide Ruff still has pre-existing line-length failures outside
this fix. This is focused verification, not the full repository suite, packaging,
physical-device or complete accessibility acceptance.

## Live activation

The host was verified idle with no queued or live leased work. Exact saved-runtime
resume preflight succeeded before shutdown. A graceful managed restart preserved
the current session, workspace, `mistral:7b`, Standard mode, Plan state, settings
revision, persistent account and LAN listener.

The updated live snapshot reports `chat_auto_queue: true` and
`chat_model_blocked: false`. The original unrelated download remains unknown and
owns its original mutation fence. The four served HTML/JS/CSS assets match the
worktree byte for byte. No live generation, pull, delete or Ollama restart was
performed. Browser sign-in is required again after the host restart.

Private local evidence: `/tmp/klaude-chat-admission-activation.json`.
Browser evidence remains in `/tmp/klaude-composer-preview`,
`/tmp/klaude-chat-layout-validation` and the existing control/model fixture outputs.
No commit or push was made; the preceding chat layout work is preserved.

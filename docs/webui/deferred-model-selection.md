# Model selection during a response

Model selection remains available while a hosted conversation is generating or
has queued messages. The selected model is used for the next prompt, including
messages queued before the selection. A later selection replaces the earlier
next-turn choice. The running response keeps its original model, runtime,
transport, tool loop and cancellation target until it finishes.

The selection is saved immediately through the existing revisioned runtime-choice
transaction. That transaction retargets queued/paused messages only when their
exact prior model/mode/definition/credential binding matches the previous
selection. Queue state, ordering, priority, creators and request identities remain
intact. Their fingerprints and revisions follow the explicit runtime change;
starting/submitted, mismatched and needs-review entries remain untouched. A
paused message is not resumed by selecting a model.

The application holds the verified next-turn model separately from the live Agent.
At an idle boundary it revalidates the configured definition and credentials,
installs the new runtime, then admits the queued/next prompt. The old transport is
closed only after the original worker has finished. No model download, inference,
chat default-role change or global Ollama stop occurs on selection. Other worker
leases remain fenced. Thinking and Plan retain their existing idle guards.

Browser snapshots expose `chat_deferred_model_selection` and
`model_selection_pending`, and the model/header display follows the next-turn
selection. Mobile/desktop picker rows, connections and configured-model actions
stay usable while generating. The picker explains next-prompt behavior and marks
a pending selection as Next prompt. Older hosts retain their previous locking
behavior until restarted. Menu placement measures untransformed dimensions so
its opening animation cannot push the final popup beyond the viewport edge.

## Focused validation

- Four new tests: local/configured cloud next-turn selection; prompts queued
  before/after selection; unchanged running Agent/transport; latest selection
  wins; stale revision rejection; saved selection after completion; queue receipt
  idempotency; foreign-worker fencing; paused-queue preservation.
- Existing application bridge and coordination tests passed; two HTTP tests
  passed for revisioned model selection and unchanged idle Plan behavior.
- Isolated Chromium exercised real model-selection HTTP requests while a fixture
  generation was blocked, at 390px and 1440px, for configured and legacy catalogs.
  Both model changes left the original response on its original model, then the
  queued prompt completed on the latest selection. No browser errors.
- The complete responsive models walkthrough passed for configured and legacy
  catalogs, including active-state pickers and the shared desktop/mobile sheet.
- Scoped Ruff, application service/coordination mypy, JavaScript syntax and app
  bundle verification passed. No real provider generation or live-host restart
  is claimed. Restart/reload is required for the new backend capability.

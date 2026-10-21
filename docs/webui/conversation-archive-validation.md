# Archive the current conversation

The conversation details Archive action now accepts the current conversation.
Its review explains that archiving the current conversation opens a new chat.
The browser displays the fresh chat, closes the conversation drawer and refreshes
its list. Existing history and attachments are retained and can be restored.

The HTTP submit path checks the existing control, turn and queue guards. Exact
review/request/resource admission occurs before opening the new chat through the
normal session-switch lifecycle, including startup defaults and file-edit cleanup.
Only a newly admitted request invokes that transition, before its archive worker
starts. Replays return the existing receipt without creating another conversation.
If starting a new chat fails, the archive never starts and its failed receipt
releases the session resource. If another conversation was selected before
confirmation, the reviewed conversation is archived without replacing that choice.

Archive retains its existing asynchronous worker and exact history/workspace
checks. A later worker rejection leaves the original conversation saved and the
new chat open; Activity reports the failed operation. Current-session deletion
remains blocked. CLI/TUI archive behavior is unchanged.

Validation uses isolated stores, local HTTP fixtures and a deterministic local
chat fixture; no real-profile conversation is changed as a probe.

- Focused session HTTP regressions: 8 passed, including current archive, retained
  messages, empty workspace-bound replacement, replay deduplication, busy turn/
  queue rejection, invalid admission, resource conflict, failed startup and a
  conversation change before confirmation.
- Library operation regression: 27 passed.
- Existing workspace/runtime session-navigation regression: 1 passed. Focused
  mypy, Ruff, Python compilation, JavaScript syntax and `git diff --check` passed.
- `scripts/webui_sessions_smoke.py`: Chrome at 390px passed review cancellation,
  archiving the current conversation, fresh-chat rendering, closed mobile drawer,
  replay and Restore, with zero JavaScript exceptions.

The managed host was checked idle with no pending questions/reviews, queued work
or management operations, then gracefully reloaded to load the Python changes.
Its workspace, conversation, saved model/mode and LAN listener were verified.
Reload revoked browser cookies; refresh and sign in again. No real conversation
was archived as a test.

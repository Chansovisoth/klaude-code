# Download failure handling and observed transfers

Request: investigate the unconfirmed `qwen3:0.6b` download and show live Ollama
pulls started outside the WebUI. This change preserves the existing model-detail
and Model Store layout work in the same dirty tree.

## Behavior

- Native manager errors now carry whether the HTTP mutation was attempted.
  Failed preflight inventory/authentication/connection checks finish as Failed
  rather than permanently fencing an operation whose mutation never started.
- An explicit native terminal pull error is distinguished from an interrupted
  stream. A fresh exact unchanged model inventory confirms failure of that
  request, without claiming partial-layer cleanup. Failure of that verification,
  missing success/error events, malformed streams, cancellation and transport
  loss retain the existing unknown/fenced behavior. No automatic retry is added.
- Provider prose remains private. Common EOF/retry/timeout transfer errors receive
  a fixed safe message. Download titles visibly separate model and connection.
- Shared core native pulls publish bounded private progress observations during
  their existing request. CLI, TUI and browser workers use this path. A separate
  WebUI instance sharing the profile can see exact model and current-file progress.
  PID start ticks prevent stale files from identifying reused worker processes;
  the progress file disappears when that worker exits its pull. Browser-owned
  active jobs are deduplicated against these observations.
- For enabled loopback HTTP connections matching the standard running Linux
  `ollama.service` port, the observer discovers its model directory from allowlisted
  system service settings. It inspects at most 10,000 directory entries, using
  regular main `sha256-<digest>-partial` metadata only. A first snapshot includes
  files updated in the last 10 seconds; subsequent metadata changes refresh the
  observation. After 15 seconds without writes the row says the outcome is
  unconfirmed; after 60 seconds it drops the observation. Old partials and symlinks
  do not establish activity. Sparse file size never establishes bytes completed.
- This generic local row says model identity and byte progress are unavailable.
  It can represent a pull from the Ollama CLI or another API client, but cannot
  prove which model is involved or whether a quiet request remains active.
- Observations appear separately from durable browser jobs in the API, with no
  request ID, cancellation/recovery handle or admission fence. The original client
  keeps control. Observation failure does not hide authoritative job history.
  Reload discovers current observations; sign-out clears the private browser rows.

## Limits and native API evidence

There is no universal read-only catch-all endpoint for external Ollama transfers.
`/api/ps` reports inference-loaded models, not downloads. Posting `/api/pull` to
"watch" can start a new operation and is intentionally never used here. Remote
servers, nonstandard/local container service arrangements, inaccessible stores,
manifest-only work, stalled requests without recent file writes, and pushes
without local partial writes cannot be exhaustively observed. The UI reports
remote observation unsupported and inaccessible local monitoring unavailable.

Primary source review:

- [Ollama server routes and terminal pull error behavior](https://github.com/ollama/ollama/blob/main/server/routes.go)
- [Ollama in-memory download manager and sparse partial-file allocation](https://github.com/ollama/ollama/blob/main/server/download.go)

Initial read-only verification found Ollama 0.33.3, 31 installed models,
and no `qwen3:0.6b` installation or local partial files. The old unknown receipt
`09d4a983245e4ee8c579ae5465ffda7d` initially retained its fence: its saved generic message is
not an authenticated terminal-result witness. Absence of the model alone cannot
prove an older request will never finish. Check outcome now explicitly reports
that the model is not currently installed rather than implying a completed pull.
No download was restarted and the daemon/model inventory was not changed.

The subsequent stale-request fix adds a separate, stronger recovery proof:
standard local daemon PID/start-clock/start-ticks must identify the same server
generation before and after fresh inventory, and that daemon must have started
after the unknown receipt. Only then may an exact prior witness reconcile the
stopped request as Failed. The same daemon, unavailable generation, offline
inventory, changed target/credentials and replaced deletion digest retain the
fence. Active owned workers are rejected before reconciliation. No pull is joined
or restarted, and neither remote cleanup nor successful installation is invented.

After the local daemon restarted independently, this proof resolved the exact
old receipt as `failed`/`reconciled`. Its dismissed warning disappears and model
management is unblocked. The journal receipt and private witness are retained.
No host/daemon restart or model mutation was performed by this recovery.
Evidence: `/tmp/klaude-stale-download-recovery-result.json`.
The permanent monitoring prose was removed from Downloads; actual observed
transfers keep their explanatory details.

Recovery validation: 38 focused Model Store/activity/model settings tests pass,
plus 2 deletion-digest recovery cases. The new negative cases retain the fence
for an old/missing/changing daemon, offline inventory and a modified private
target. All four changed production modules pass mypy. Focused Ruff, JS syntax
and diff checks pass; the existing unrelated host route-map E501 remains.
The isolated Downloads browser walkthrough passes Stop/Remove, retained
same-daemon uncertainty, four bar presets and reload/sign-out with no console
errors. A separate live authenticated browser check confirms empty Downloads,
enabled model actions, no obsolete warning/monitoring prose, no overflow at
320/390/1440px, and unchanged chat runtime/host identity. Evidence:
`/tmp/klaude-stale-download-regression-tests.log`,
`/tmp/klaude-stale-download-delete-tests.log`,
`/tmp/klaude-stale-download-browser-regression.log`, and
`/tmp/klaude-stale-download-live-result.json`.

## Validation

Focused tests cover actual HTTP worker terminal failures versus truncated streams,
failed preflight, exactly one external pull despite repeated observation reads,
safe fixed error messages, live shared progress, process/revision rejection,
symlink rejection, stale/quiet partial files, sparse preallocation, and remote
endpoint exclusion. The initial sandbox run could not open fixture sockets;
socket-dependent validation runs with the required host access.

`scripts/webui_model_activity_smoke.py` passes in isolated Chrome at 320, 390 and
1440 pixels in light/dark themes, including native progress, generic file activity,
no foreign cancellation controls, reload and sign-out cleanup. It starts zero
fixture pulls and downloads zero real model weights. Screenshots:
`/tmp/klaude-model-activity-evidence`; result:
`/tmp/klaude-model-activity-browser.log`. The complete Model Store/Image Studio
browser walkthrough also passes at 320–1440 pixels with no console errors:
`/tmp/klaude-model-activity-store-browser.log`.

The focused native-manager, Model Store, activity, model settings and catalog
regressions passed 76 tests, including the final malformed-error case.
Ruff passes for the changed Python files; mypy passes for all five changed/new
production modules. JavaScript syntax and `git diff --check` pass. This is scoped
validation, not a claim about the entire repository suite.

The read-only live monitor reports local observation available and no current
transfer observations. A controlled WebUI restart was stopped by its preflight:
the running host's newer empty session has no saved exact runtime choice, so
`create_application(..., session_id=...)` rejects resumption. The running host
was not stopped or replaced. A separate activation choice was requested because
starting a new empty conversation changes session identity; the implementation
and isolated validation are complete while that choice is pending.

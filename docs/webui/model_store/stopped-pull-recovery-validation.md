# Stopped native pull recovery and live activation

The reported `hf.co/mudler/locate-anything.cpp-gguf:locate-anything-q4_k.gguf`
entry was a stopped request with retained 45,520,265/4,716,320,320-byte progress.
Its worker was gone and Ollama logged the end of the 33.38-second request, but
the prior Stop path left a global unknown fence. Unlike the older Qwen case,
Ollama had not restarted after this request, so restart-only recovery was
insufficient.

## Changes

- Browser native pulls carry their random operation ID in the local HTTP query,
  `klaude_request=<id>`. It contains no model, key or user prompt. The fixed worker
  validates it; CLI and external pulls remain compatible without it.
- Read-only recovery matches an exact GIN POST `/api/pull` handler-end record from
  that same daemon PID and stable generation, using bounded private journal reads.
  Another request, another PID, an incomplete/unstructured entry, inaccessible
  logs or a changing daemon is not proof. Raw journal/proxy/provider prose never
  enters the UI or public receipt.
- A fresh exact target/endpoint/credential/inventory witness can then reconcile
  the ended request as Failed without waiting for an Ollama restart. It does not
  claim installation success or remote partial-file cleanup. Existing desired
  final-state and verified-newer-daemon recovery continue to work.
- Stop attempts recovery after its owned process exits. The existing lease keeper
  rechecks delayed handler-end evidence for at most 30 seconds, every three
  seconds. Remove also attempts proof-based recovery before dismissing the row.
  No pull/delete is retried. Without proof, genuine uncertainty retains its fence.
  Automatic checks do not contact Ollama for inventory until end proof exists.
- Native pull reads now use the existing 1800-second pull budget rather than the
  transport's 30-second metadata default; metadata reads retain their short limits.
- Empty conversation resume now accepts a matching workspace binding plus an
  exact saved runtime even before dialogue exists. Missing bindings/choices and
  wrong workspace/model identities still fail. This permits an exact-session
  controlled update without inventing dialogue or replacing the conversation.

Primary implementation reference: [GIN logs after handler return and includes the query](https://github.com/gin-gonic/gin/blob/master/logger.go),
[Ollama native routes](https://github.com/ollama/ollama/blob/v0.33.3/server/routes.go).
A read-only `/api/version` query confirmed correlation metadata is preserved by
this host's logger; no diagnostic pull was submitted.

## Existing entry and activation

The legacy request lacked a correlation query. Its one-time reconciliation used
the unique same-daemon native pull-end record within two seconds of its unknown
receipt, no current worker/observed transfer, fresh absent inventory and the
authenticated exact prior witness. Request
`bf8fdacc2065eab101d6bc9cc736216b` is now Failed/Reconciled and its dismissed row
is absent. The durable receipt and witness remain. No download, deletion or
Ollama restart was performed. Evidence:
`/tmp/klaude-hf-stopped-pull-recovery.json`.

The current model choice was saved through the normal private session API.
The final original reference is `ollama/qwen3-coder:30b`, Standard with no effort.
Exact-resume preflight passed after the empty-session correction. A controlled
idle WebUI restart activated the new backend, preserving conversation
`97ae5c81e5344dda8da56a47b462c3d9`, workspace `/mnt/HDD1/draft/playground`,
model, account and LAN origin. Instance `5914:61257` became `21970:347534`.
The running snapshot reports `model_download_recovery: true`. Evidence:
`/tmp/klaude-stop-recovery-activation.json`.

## Validation

- 95 focused native manager/activity/Store/model settings tests pass, including
  exact correlated record matching, negative evidence, stopped-request recovery
  without a restart, delayed handler-end evidence and no duplicate pull.
- 26 application bridge tests pass, including empty resume with saved runtime,
  wrong/missing runtime and workspace checks, and zero generation calls.
- Isolated Chrome passes Stop/Remove/reload/sign-out and four thin bar presets at
  320/390/1440px with no browser errors. Native effects use fixture servers only.
- Six changed production modules pass mypy. Focused Ruff/JavaScript syntax and
  diff checks pass; the existing unrelated host static-map E501 remains.

Results: `/tmp/klaude-stop-recovery-final-tests.log`,
`/tmp/klaude-empty-session-resume-tests.log`,
`/tmp/klaude-stopped-pull-browser.log` and
`/tmp/klaude-hf-stop-recovery-live-browser.log`.
This is scoped verification, not a full-repository suite claim.

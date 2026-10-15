# Model Defaults and settings navigation

Date: 2026-10-16. Base `4a64ce6`, current dirty worktree preserved. This follows
completion of the [image attachment implementation](image-attachment-reliability-validation.md).
No commit or push; all runtime checks used isolated config/data/workspace paths.

## Requested hierarchy

```text
Settings
  MODELS
    Models
    Model Defaults
  AGENT
    Search
    Tools
    MCPs
    Skills
    Memory
    Library
    Permissions
  ADVANCED
    Provider credentials
    Runtime
  APPEARANCE
    Theme
    Input Field
    Divider
    Spinner
    Reset appearance settings
```

Model Defaults replaces the public AI Defaults name, and Tools replaces Agent
Tools in breadcrumbs/help/cross-links. Canonical `/settings model defaults` and
`/settings tools` work; `/settings ai defaults`, `/settings defaults` and
`/settings agent tools` remain compatibility aliases. Storage keys, controller
IDs and persisted references are not migrated just to change labels. Root Settings
focus starts in Models; Back retains the selected row and existing picker behavior.

## Empty role selection

Opening Model Defaults starts an owned metadata-only scan when roles are empty.
Existing Chat, Utility, Research and Vision references are retained. Enabled
endpoints/models are inspected; local endpoints and the active model (when eligible)
are preferred. Remaining local models use declared parameter counts, not model-name
size guesses. Tool capability is preferred for Chat/Research. This is a role fit
policy, not a GPU-memory fit prediction.

Only completion-capable native Ollama entries qualify; embedding-only, disabled,
missing or unverified entries are skipped. Vision also requires declared image
support and a fresh exact-model inspection for the Standard-only Media consumer.
Utility/Research/Vision do not select thinking-required models. If no candidate is
verified, nothing is selected. Cloud metadata does not guarantee generation access.
Image generation remains the separate tested local service and is not assigned a
chat model merely because its server reports an image capability.

Proposals are saved through the existing ordered settings writer with field,
endpoint, credential and enabled-model checks. Cross-client selections and explicit
clears/inheritance win over automatic proposals, including a clear racing with an
in-flight scan. `model_default_selections` in private chat-preferences.json records
manual/automatic origin for the four roles. A manual `null` is an explicit choice,
so it is not repeatedly replaced each time the page opens.

Selection never enables Vision, loads models, generates, adds fallbacks or changes
the active chat/session choice. Manual navigation remains available during discovery
and cancels its unaccepted proposals; late results cannot interrupt the manual
selection. Leaving cancels/rejects unaccepted results; already
accepted settings writes drain. Reload explicitly repeats discovery. Metadata work
is bounded to 8 endpoints, 32 native model inspections per endpoint, 4 catalog reads
at a time, existing 8-model/4-read capability batches, a 40s scheduling budget and
60s owned worker deadline. Slow/very large catalogs can leave roles unverified;
manual selection or Reload remains available. Provider bodies and keys stay private.

## Actual TUI evidence

The real bare CLI was driven through a PTY at 120 columns, then 80 and 40. A
loopback proxy forwarded only `/api/tags`, `/api/show`, `/api/version` and `/api/ps`
to this machine's real Ollama server. All other routes, including inference, were
rejected and logged. No image or prompt generation ran during this settings test.

Isolated root: `.klaude/data/s2-models-fpwlw_qd`.

- `/settings` displayed Models first, Search immediately before Tools under Agent,
  Advanced followed by Appearance in the page model; screenshot/picker assertions
  cover the order and section ownership.
- `/settings model defaults` automatically saved Utility, Research and Vision as
  `ollama@default-ollama/gemma4:e2b` while keeping the existing default Chat value
  `ollama/gemma4:e2b` and the active session unchanged.
- Vision's detail page showed `Model: Ollama / gemma4:e2b` and `Enable Vision: OFF`.
- 25 metadata requests and zero inference requests were recorded. The client exited
  cleanly; widths 40/80/120 and Model Defaults/Vision views were captured. The
  120-column Settings and defaults renders were visually inspected.
- The first live pass exposed a legacy/qualified-reference mismatch that selected
  another declared model. Normalizing identities fixed the ranking; a regression
  now covers legacy active refs against qualified catalog refs.

Evidence files: `settings-result.json`, `metadata-requests.json`, private terminal
log and SVG/PNG captures under that isolated root. No production preferences changed.

## Automated validation

60 role-default/capability/core-default regressions passed. These cover unavailable
vision, explicit manual inheritance, disabled models, failed fresh inspection,
thinking-required exclusions, endpoint changes, ordered saves, unchanged active
session/view, cancellation/late results and legacy reference identity. Existing
full CLI/settings/defaults tests: 883 passed, one skipped in 85.41s; the exact
section/order assertion covers Search/Tools and Model Defaults.

The complete integration gate passed: 3572 tests passed, 19 skipped, Ruff and
production mypy (151 files); five-wheel packaging/imports/installed help passed.
Final manual-navigation responsiveness was additionally verified after the gate
started, including a final focused rerun. Details and test-count scope:
[attachment validation](image-attachment-reliability-validation.md#complete-integration-gate-and-distribution-check).

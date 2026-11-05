# Skill Store failure reporting and recovery

## Behavior

Skill Store installation retains its existing bounded GitHub download, commit
pinning, blob integrity, package limits and no-script execution rules. The
existing operation journal now stores private domain evidence in an additive
table. Public receipts contain only safe stage/error projections, never source
payloads or arbitrary exception messages. Other operation domains keep their
existing receipt contracts.
Source-validator failures use a dedicated exception type; unrelated ValueErrors
are classified as unexpected failures rather than blamed on the source.

Admission saves the resolved source. The worker records effect-start intent
under the existing Skill mutation lock, then checkpoints package/index identities
before indexing, before finalization, and before postcondition verification.
Each checkpoint checks the live fence and compares prior evidence, preventing a
stale attempt from replacing newer evidence. A failure before this boundary is
explicitly rejected; one after it remains unknown. Unexpected exceptions use a
fixed message and retain request ID correlation. Raw exceptions are not logged.

The completion postcondition checks pinned repository/revision/path, manifest,
CURRENT, full package content hash and exact active owner checksums across
libraries. An existing Knowledge owner blocks installation even when its package
directory is missing. A package name is never adopted solely because it matches.

## Recovery

Activity operation rows offer **Inspect recovery** for unknown Skill Store
installs. Inspection acquires the mutation lock without waiting for an active
installer, reads package/SQLite state, and makes no network or index calls.
It may expire a journal lease; it never releases an unknown resource merely by
inspecting it. The journal lazily creates its additive schema on first use.

- Verified complete: offer **Confirm installation**.
- Proven no effect: offer **Close failed attempt**; a fresh install needs a new review/request.
- Legacy, conflicting, partial or insufficient evidence: explain that the name
  remains reserved and retain the fence.

Applying re-inspects under the same lock and requires the inspection fingerprint.
An old worker waiting before the lock cannot cross its gate once the receipt is
unknown/settled. A worker already holding the lock prevents recovery. A lease
expiry alone is never treated as worker death.
Inspection bounds file size, total bytes, paths, depth and entry counts, refuses
symlinks/special files, and checks file stability while reading. Corrupt evidence
and missing/mismatched active Knowledge metadata grant no recovery authority.
Expected index checksums skip empty documents and normalize newlines exactly as
the indexer does. Package hashing preserves the installer's Path sort order.
Fingerprints also cover the published manifest and CURRENT, so changed metadata
requires another inspection. Activity labels each Skill by name, limits recovery
controls to administrators, announces inspection results and restores focus after
applying. CLI JSON keeps all confirmation text on stderr, including input echo;
decline/EOF and storage initialization errors return safe machine-readable results.

CLI equivalents:

```sh
klaude skill-store inspect REQUEST_ID --json
klaude skill-store reconcile REQUEST_ID --dry-run
klaude skill-store reconcile REQUEST_ID --apply
```

`--apply` reviews and confirms a proven decision. Exit 2 means active work,
insufficient evidence or unavailable recovery; exit 1 means declined recovery.
Local administrative retirement is available only through the explicit reviewed
legacy-empty-state path described below. Forced retry, pending-package repair and
automatic cleanup of abandoned staging directories are not provided. Existing package recovery
is not invoked speculatively. Old hosts lack recovery controls until restarted;
new assets only offer them for receipts carrying the new projection.

## Historical investigation, 2026-10-28

Read-only journal and Knowledge SQLite queries found unknown receipts for:

- Impeccable: `5ec5518d4de92446996a2948d7ffc4fe`
- REA: `3ceff3c2632ebb5cb54df3cded574af7`
- Design (inspection only): `b78c6a08f1fc8da7bd1822680ee1a83a`

All three lack before/after witnesses. No active owner or source-version rows
exist for these three Skill owners in the configured Knowledge database.
The requested installed directories and pending/staging markers were absent.
These observations do not prove historical failure or establish its cause.

The catalog cache currently retains one resolved Impeccable candidate:
`pbakaus/impeccable`, commit `8409a564d1baee90b2dde4f7a8f06288838e3921`,
`.agent/skills/impeccable/SKILL.md`. There is no durable link from this cache
entry to the original request; it must not be treated as its original source.
No resolved REA source remains in that cache. The user does not know the original
URLs. Both historical resources remain fenced; no source was substituted and
neither requested Skill was installed during this work. Design is unchanged.

## Validation

Focused tests cover actual package and SQLite checksum inspection, sanitized
download failures, indexing interruption, cancellation, evidence CAS, stale
inspection, legacy fencing, independent operation behavior, CLI JSON, and
browser admin/CSRF requirements. Subprocess tests use `os._exit` at six actual
installer boundaries, including lost acknowledgement; another resumes a worker
after reconciliation and verifies that publication is denied.

`scripts/webui_integration_store_smoke.py` exercises Inspect recovery, applying
a proven recovery and reload persistence in an isolated browser profile, alongside
the existing responsive Store checks. This is fixture validation, not a live
installation or a claim that the two historical receipts were recovered.

Audit validation: 223 tests passed across Skill recovery, integration Store,
shared operation journal, catalog validation, Skill management/package behavior,
background jobs, browser Library and browser management. This includes the real
KnowledgeIndexer and LanceDB with deterministic embedding vectors, rather than
only synthetic active-source rows. Seven relevant CLI command-reference/discovery
tests passed. Follow-up runs passed eight CLI/error-classification checks and
15 reconciliation checks after the final storage-init and fingerprint fixes.
The browser smoke passed with zero console errors; touched-file Ruff, Python
compilation and JavaScript syntax checks passed. Full-repository tests were not
run, and no live restart, install, recovery or cleanup was performed.

## Follow-up hardening, 2026-10-29

Source validation now carries typed error codes for integrity, manifest, file-count,
size and unsupported-entry failures. Receipt messages remain fixed allowlisted
text; unknown codes fall back to SOURCE_REJECTED. Package-write failures have
an explicit PACKAGE_INSTALL_FAILED code. Unknown outcomes with no persisted worker
failure display OUTCOME_UNCONFIRMED without guessing why the worker stopped.
The persisted receipt state, request ID and stage remain the recovery authority.

Generic journal reconciliation now rechecks the exact resource request and fencing
generation inside its write transaction, matching witnessed recovery's guard.
A stale ownership observation cannot settle a receipt. Regression tests cover
changed generations, unknown codes, safe messages and typed classifications.

Validation: 169 Skill recovery/catalog/install/management/background tests and
7 shared journal tests passed. Touched Python passed Ruff and whitespace checks.
The historical REA, Impeccable and Design receipts were rechecked read-only and
remain unknown. No historical fence was released, installation replayed or live
host restarted. Their original source identity and historical effect outcome
still require evidence before safe recovery.

## Authorized legacy REA retirement and successful install, 2026-10-29

A separate operation_retirements record now supports explicit operator retirement
of legacy Skill receipts without rewriting their historical unknown outcome.
Eligibility requires an unknown Skill install, no evidence/witness records, exact
resource generation, the Skill mutation lock, no package and no active or historical
Knowledge owner state. Apply rechecks its fingerprint and creates consistent
owner-only SQLite backups through the backup API before the journal transaction
records retired_unverified and releases only that generation. Old workers remain
unable to pass the effect gate. New evidence, local changes and stale ownership
reject retirement. Activity shows retired history separately from ordinary failures.

The local CLI is `klaude skill-store retire REQUEST_ID --reason REASON --apply`.
Without --apply it only inspects. Apply requires an explicit interactive
confirmation; decline exits 1. This is operator retirement, not proof of failure.

Following the user's explicit request to fix REA after the retirement review,
receipt 3ceff3c2632ebb5cb54df3cded574af7 was retired with its unknown state preserved.
Backups are in .klaude/data/skill-retirement-3ceff3c2632ebb5cb54df3cded574af7-cx_g42gl.
The user-selected morluto/rea source at commit
8f9af920efb39d22b5a915605403b67a1005bc0e,
.agents/skills/reverse-engineer-anything/SKILL.md, passed bounded verification:
8 files, 151205 bytes. Configured nomic-embed-text readiness passed with 768 dimensions.

Fresh request 8943c9bf51064c8b887e4f383295cbf3 completed under generation 2.
Full package/manifest/source digests and the exact Knowledge owner snapshot passed
verify_complete; no unresolved REA resource fence remains. The shared installed
Skills reader lists reverse-engineer-anything as enabled. No scripts ran.
Impeccable and Design's historical receipts were not retired or changed.

An independent image-file download may coexist with a Skill install; conflicting
Ollama model work still blocks admission. This avoids moving the same unnecessary
global block from model downloads onto Skill installs.

Validation: 87 recovery/integration/journal tests passed, plus two CLI confirmation
and consistent-backup cases after the final command fix. Tests cover unknown-history
preservation, old-worker denial, changed package/index/evidence/fingerprint refusal,
new-generation admission and image-download coexistence. Ruff, JS syntax and
whitespace checks passed. No production host restart was performed.

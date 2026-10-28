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
No administrative retirement, forced retry, pending-package repair or automatic
cleanup of abandoned staging directories is provided. Existing package recovery
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

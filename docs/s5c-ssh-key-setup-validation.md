# S5c, fourth slice — Reviewed SSH host trust and public-key enrollment

Date: 2026-10-14. Continues [SSH settings](s5c-ssh-validation.md) and
[owned remote CPU serving](s5c-remote-serving-validation.md).

This slice supports independently verified Ed25519 host pins and enrollment of
one existing Ed25519 public key through current verified SSH authentication.
S5c remains partial: additional GPU/vLLM dependency recipes, remote GPU/vLLM
profiles and build removal remain unfinished. S6 is unstarted. Existing dirty
S5 work is retained; no commit/push, version, dependency or lockfile change.

## User flow

Model Manager → Servers → saved server → Key setup provides:

- **Verify host key:** explicit candidate discovery, fingerprint selection,
  private single-line Verified fingerprint input, then a Back-focused review.
  The user must obtain the verified fingerprint from the server/admin separately.
  Discovery alone neither authenticates the host nor changes settings.
- **Save verified host:** saves a private pin and updates this definition's
  trust-file reference. Existing known-hosts files and identity selections remain
  intact. A revoked key in the selected trust file cannot be pinned around.
- **Enroll public key:** choose one existing `.pub` file, then review the public
  fingerprint, SSH account, exact remote authorized-key path and existing-key
  status. Acceptance uses the current verified identity/agent, preserving every
  existing entry and restriction. An already-present restricted key is retained
  without an unrestricted duplicate.
- **Cancel check / Cancel enrollment:** cancel the owned local worker. Enrollment
  stays gated until cleanup is acknowledged; a completed remote append may remain.

Identity selection stays manual in the server definition, followed by Test
connection. No automatic model selection, server launch, package installation,
password/passphrase prompt or private-key generation is added. Review pages
support PageUp/PageDown. Controls appear above the fingerprint table; narrow
terminals stack values, and wide terminals use the spare two-column width.
Setup inputs and results do not enter chat or model context.

Canonical CLI equivalents, registered in `main.py` and exercised as subprocesses:

```text
klaude model-manager ssh host-key ID
klaude model-manager ssh trust ID SHA256:VERIFIED_FINGERPRINT
klaude model-manager ssh enroll ID /absolute/key.pub
klaude model-manager ssh test ID
```

Trust/Enroll confirm the exact fingerprint/target and default to No; `--yes`
explicitly accepts the reviewed effect. Discovery is yellow, confirmed saves
are green, failures red and unknown outcomes yellow. CLI Ctrl+C cancels/reaps
the owned local worker, returns 130 and makes no remote rollback claim.

## Implementation and bounds

Core `ssh_setup.py` owns candidate scans, public-file validation, private host
pins, review/enrollment requests and whitelisted receipts.
`ssh_enrollment_program.py` is fixed remote Python supplied through the existing
strict SSH transport. CLI `ssh_setup_panel.py` shares typed panels and owned jobs;
trust saves use the existing ordered SSH settings writer. `ssh_commands.py`
provides the same operations without a second credential store or scheduler.

| Operation | Bound and checks |
| --- | --- |
| Host discovery | Installed `ssh-keyscan`, Ed25519 only, 3-second scan timeout, 8-second process deadline, 32-KiB combined output, at most eight candidates. |
| Trust acceptance | Saved-definition nonce, exact normalized host/port, matching SHA256 fingerprint and 120-second receipt age; owner-only content-addressed pins, at most 64 retained files. |
| Public input | One Ed25519 key in one non-symlink regular `.pub` file, at most 4 KiB, strict UTF-8 and no group/world writes; comments are not transmitted. |
| SSH enrollment | Existing strict host trust and explicit identity/agent; 3-second connect, 15-second transport, 20-second owned-job deadlines, 64-KiB transport output. |
| Remote work | Ten-second alarm, at most 256 KiB authorized-key text, 0.2-second advisory-lock wait, account-owned regular files and directories without unsafe writes. |
| Feedback | Public fingerprint, path, counts, hashes and typed outcomes only; no authorized-key bodies, private keys, password material or raw SSH stderr. |

Before acceptance, definition, local public-file metadata/fingerprint,
authentication references and remote authorized-file metadata/content are
rechecked. Remote file access anchors `.ssh` and `authorized_keys` to directory
descriptors, rejects symlinks/hardlinks/unsafe ownership and takes a per-account
advisory lock. Read-only review creates no directories or files.

Acceptance creates missing account SSH paths only as needed, appends one key
with one `O_APPEND` write and verifies a receipt. Existing file bytes, options
and permissions are retained; no replacement/chmod is performed on existing
authorized-key files. Missing final newlines are preserved before the appended
separator. Receipt checks include the existing prefix, selected key, file inode
and visible SSH directory inode. Post-write read/decode errors and lost transports
are Unconfirmed, without retrying the write or claiming rollback.

The advisory lock coordinates Klaude enrollment attempts; external writers do
not have to honor it. Snapshot/inode checks reject observed changes, and uncertain
post-write effects require a fresh review. This does not claim a distributed
transaction against arbitrary external account-management software/filesystems.

Accepted trust/enrollment work retains target/session/root/draft identity through
navigation and gates new model work. Late callbacks can release the gate and
update the settings inventory without replacing a newer page or private editor.
Navigation cancels pending reads, including an unfinished remote review.

## Real usage and fixes observed

The QA fixture runs the installed OpenSSH server on loopback with temporary
Ed25519 keys, private known-hosts and a separate QA account-home directory.
Only that daemon's configuration/authorized-key file is modified; real
`~/.ssh` files and real remote accounts are untouched.

Actual CLI/TUI runs cover candidate scans, mismatch/cancel/confirmed host pins,
strict connection retests, enrollment review/cancel/append, authentication with
the newly enrolled private identity, idempotency and unchanged selected identity.
The TUI rejects a changed remote policy after review without appending a key.
Screens are captured at 40/70/120 columns and wide/narrow renders are inspected.

The first terminal run exposed a cramped generic third column that split a
47-character SHA256 fingerprint across three lines even at 120 columns. The
redundant per-row status column was removed; the page's common verification
warning remains. The existing two-column renderer now displays wide fingerprints
on one line and stacks/wraps narrow layouts.

Review identified and fixed late enrollment/trust callbacks replacing newer
forms, including cancellation while a private editor is open. Tests exercise
draft, session, config-root and target changes. Revoked host keys are rejected
before private pin creation; post-write receipt errors report uncertainty.

The delayed-enrollment QA wrapper runs only in the temporary daemon and permits
live cancellation checks. Its first version attempted to execute the shell's
`exec` builtin directly and failed before reaching enrollment; correcting the
fixture to unwrap Klaude's fixed prefix required no product transport change.
Terminal automation uses paced key input/settled repaint checks rather than
assuming a fixed short repaint interval during concurrent suite load.

## Validation

- Focused SSH setup, diagnostics and remote serving: 66 passed in 43.98 seconds
  before the final private-editor cancellation guard.
- That guard and related navigation/cancellation cases: 10 passed in 0.37 seconds.
- Full first gate: 2,995 passed, 19 skipped in 221.65 seconds; Ruff clean and
  mypy clean for 130 production source files.
- Final real CLI/TUI walkthrough: nine scenarios passed, session named
  `TEST KLAUDE FEATURES SSH KEY SETUP`, normal TUI exit 0 and active CLI
  cancellation exit 130. Includes delayed SSH enrollment cancellation without
  claiming rollback. Its read-only database audit found zero public/model turns.
  Receipt: `.klaude/data/s2-models-4d9p24r6/key-setup-result.json`, audit
  `key-setup-privacy.json`, CLI/40/70/120-column text/SVG captures in that same
  isolated directory; driver log `/tmp/klaude-key-setup-walkthrough.log`.
- Colored wide cancellation and narrow 40-column review renders were inspected;
  warnings are yellow, the Back-focused review is paged, and private file paths
  wrap inside the available width. Earlier 70/120-column renders were inspected.
- Final full gate after the private-editor cancellation fix: **2,996 passed,
  19 skipped in 225.87 seconds**; Ruff clean, production mypy clean for **130
  source files**. Log: `/tmp/klaude-key-setup-release-check-complete.log`.
- Sequential packaging smoke: **all five wheels built and installed together**,
  public-package imports and installed `klaude --help` passed. Log:
  `/tmp/klaude-key-setup-release-package-complete.log`. The first sandboxed
  attempt could not resolve PyPI to fetch Hatchling; the approved network-enabled
  rerun passed without product/dependency changes.
- These gates ran locally on Python 3.12; no new CI/Python 3.11/3.13 run is claimed.

Focused coverage includes actual new-key login, exact old-byte preservation,
existing forced-command/no-forwarding key options, stale public/definition/remote
reviews, symlink/unsafe-mode rejection, missing-file creation, no-final-newline
handling, unknown post-write receipts, expired/revoked host pins, multi-key input,
owned-worker public metadata and stale UI/cancellation behavior.

## Remaining limits

- Linux/OpenSSH/remote Python 3 only in this slice. Physical LAN-host differences
  are unverified; real encrypted loopback transport is exercised.
- Discovery/enrollment require Ed25519. Existing broader OpenSSH authentication
  remains available, but key generation, passphrase/password bootstrap,
  certificate identities, jump hosts and SSH aliases are not implemented here.
- Enrollment explicitly targets that account's `~/.ssh/authorized_keys`. A host
  using a custom AuthorizedKeysFile/AuthorizedKeysCommand or central SSH policy
  may require administrator action and explicit connection testing.
- Disconnect/cancellation can leave a completed append. Fresh review/remote
  inspection is required before retrying; no private-key selection or removal
  is automatic. Old private host pins are bounded but not automatically reclaimed.
- GPU/vLLM dependency recipes and remote GPU/vLLM/adoption profiles remain
  separate S5c work. Prior local/remote CPU serving evidence is linked above;
  this pass adds no new inference or full coding-benchmark claim. S6 is unstarted.

## Primary sources

- [OpenSSH keyscan manual](https://man.openbsd.org/ssh-keyscan.1): discovery alone
  does not establish the authenticity of a host key.
- [OpenSSH keygen manual](https://man.openbsd.org/ssh-keygen.1): Ed25519 public keys
  and SHA256 fingerprint representation.
- [OpenSSH daemon manual](https://man.openbsd.org/sshd.8): authorized-key syntax,
  account file checks and key-specific authorization restrictions.

# S5c, sixth slice — Reviewed retained setup removal

Date: 2026-10-14. Follows [local engine recipes](s5c-engine-recipes-validation.md).
Adds working removal of one retained CPU/CUDA build or private vLLM environment.
S5c remains partial; remote GPU/vLLM/adoption extensions and S6 are unstarted.
No commit/push, dependency, version or lockfile changes were made in this slice.
Follow-up: [remote llama.cpp GPU profiles](s5c-remote-gpu-validation.md) now cover
that next slice; this record retains the removal slice's original scope/evidence.

## User flow

- Model Manager → Dependencies → Built/installed engines → select a setup →
  Review removal. Shows exact UUID, owned directory, recipe, estimated storage,
  permanent effect, blockers and any process-inspection limitation.
- Reviews initially focus Back, clear old review filters and support
  PageUp/PageDown for long wrapped details. Remove setup is beside Back, where
  narrow screens can reach it without a clipped action label.
- CLI: `klaude model-manager remove-build ID [--yes]`. Confirmation defaults to
  No. No mutation occurs on review or refusal. Verified removal exits 0;
  blocked/failed/unknown outcomes 1; Ctrl+C 130 after owned worker cleanup.
- Successful cleanup removes the exact setup from inventory and restores a
  retained-setup slot. Other builds, original source/wheel folders, external
  weights, model/default choices and retained server history are independent.
- Cleanup deletes **all files inside the reviewed directory**. Referenced model
  paths or the original source/wheel folder inside that directory block removal.
  Do not put unrelated private files into managed setup directories.
- Cancelled/failed cleanup may have removed some files. Reload and review the
  remaining directory again. No rollback is claimed; incomplete cleanup records
  cannot offer Use in Serve models or start through managed serving.

## Implementation and guards

Core `model_setup_removal.py` provides bounded read-only inspection and one fixed
owned mutation. Existing `model_dependencies`, dependency CLI/TUI and background
workers carry the operation; canonical command help lives in `main.py`.

- Require a valid retained UUID/record and owned directories with no writable
  group/other access or symlink ancestry. Refuse foreign-owned entries, special
  files and filesystem crossings. Descriptor-relative traversal and unlinking
  never follow nested environment symlinks, including Python/lib64 links.
- Bound reviews to 100,000 entries, depth 64 and 25 seconds; owned removal has
  a 120-second outer deadline. Receipts hash the full entry metadata and record,
  with directory device/inode identity. Recheck at acceptance and per entry;
  new/changed files are not silently swept into an earlier confirmation.
- Storage is an estimate of allocated blocks of uniquely linked regular files.
  Hard-linked storage is excluded; sparse files, snapshots and filesystem sharing
  mean this is not a guarantee of the disk-space increase after deletion.
- Protect live build/install workers, live managed helpers, referenced model
  paths, current/saved/configured/default Chat/Utility/Research selections and
  Utility fallbacks. Match qualified identities and normalized endpoint aliases.
  Still-enabled manager endpoints also require stop/reconciliation first.
- Inspect accessible same-account executable/argv/cwd/maps/open-file references.
  Linux blocks some protected OS session processes on this machine; incomplete
  checks are disclosed in the review. Available arguments still protect a setup
  when other process fields are denied. Process bodies/arguments stay private;
  only bounded reasons and the inspection limitation reach the UI.
- Build creation, local server acceptance and removal share the inventory lock.
  Server acceptance revalidates executable/model evidence and publishes Starting
  before releasing that lock. Removal also locks definitions and preferences,
  using the existing registry → preferences ordering. Read jobs stay disposable;
  accepted mutations retain their scope/target and gate new model work.
- Before unlinking, atomically mark the record Removing. Keep it until other
  files are gone so partial cleanup can be reviewed again; managed startup
  explicitly rejects that state. Cancellation reaps the owned process and
  unblocks queued model work only after acknowledgement.

## Problems found through actual use

1. **Worker configuration loaded too early.** Importing core modules before
   installing request-scoped config/data environment variables cached the wrong
   storage path. Removal reported “storage changed” in an isolated owned worker.
   Install overrides before importing the dependency dispatcher; real worker
   cancellation/retry and CLI/TUI now use the requested store.
2. **Universal process guard rejected an idle machine.** Blanket failure on a
   denied same-account `/proc` field included protected systemd/PAM/SSH services.
   Inspect available fields, retain mandatory managed-server/selection guards,
   disclose incomplete checks, and keep the warning stable rather than tying a
   stale setup receipt to an unrelated process count.
3. **Review action disappeared above the viewport.** Back focus on a wrapped
   review scrolled the first action out of sight. Put Remove setup beside Back
   and shorten its label; complete identity/path remain accessible by paging.
   Model Manager now uses the compact shared navigation hints.

## Actual CLI/session validation

Real bare `klaude` session: **TEST KLAUDE FEATURES SETUP REMOVAL**. Uses isolated
configuration/storage, an actual compiled CPU QA engine, offline installed QA
Torch/vLLM wheels, a loopback HTTP serving fixture, and real owned workers. It
does not certify upstream vLLM GPU inference or rerun a full native CUDA build.
The prior native CPU/CUDA evidence remains unchanged and those builds were kept.

Final walkthrough receipt:
`.klaude/data/s2-models-iu07uzzk/removal-result.json`; raw terminal log and
40/70/120-column SVG/text captures live alongside it.
Driver: `/tmp/klaude_s5c_removal_walkthrough.py`;
`/tmp/klaude-setup-removal-walkthrough.log`. Captures at 70 columns and the
beginning of the 40-column review were rendered and visually inspected; full
identity/path wrap, compact action and yellow partial-check feedback are visible.
Five scenarios:

1. CLI exact review/default No and invalid traversal ID: no deletion.
2. CLI active managed server blocks removal; actual stop exits 130 and reaps it,
   retaining external GGUF bytes.
3. Selected Default Chat blocks deletion after stop. Clearing the isolated QA
   default permits removal; retained server history remains present.
4. TUI inventory → Back-focused review → Back does not delete; capture and page
   complete details at 40/70/120 columns.
5. TUI removes an actual isolated vLLM environment, including interpreter links,
   refreshes to an empty inventory and exits 0. Dirty source bytes, original
   wheel bytes, workspace content and external weights remain unchanged. No
   public/private model turns were created by setup settings (public turns checked
   directly; no generation or Discuss/report actions used).

Actual CLI Ctrl+C during deletion is separately recorded in
`/tmp/klaude-removal-cancel-cli-vy311lxx/result.json` and
`/tmp/klaude-setup-removal-cancel-cli.log`: 18,000 disposable files before removal,
17,301 after cancellation, exit **130**, honest partial-effect message, retained
cleanup record. A new CLI request reviewed the remainder and completed with
exit **0**, retaining original content. No timing-only success inference.

## Automated validation

New tests cover confined removal of real CPU builds and offline vLLM environments,
stale receipts/content/metadata/directory replacements, symlink targets, unsafe
ancestry, special files/permissions, live workers/external processes, every model
role/fallback/alias, enabled endpoints, retained model paths, newly selected
defaults, lock contention, mid-removal new files, partial failure/retry, owned
cancellation/reaping, restricted process visibility, interrupted-setup launch
rejection, TUI target/focus/blocked controls and honest cancellation.
Additional guards cover informational-warning wording changes, newly reduced
process visibility requiring a fresh review, and same-filesystem bind mounts
through a kernel-format fixture, including an escaped-space mount target.

- New focused tests: **35 passed**, 14.09 seconds, live loopback/process fixtures;
  `/tmp/klaude-setup-removal-final-focused.log`.
- Removal/build/recipe/managed local+SSH regression pass before the final two
  guard tests: **100 passed**, 67.03 seconds;
  `/tmp/klaude-setup-removal-regressions.log`.
- Final `UV_CACHE_DIR=/tmp/klaude-s5-uv-cache make check`: **3051 passed,
  19 skipped**, 256.42 seconds; Ruff clean; production mypy clean across **132
  source files**. `/tmp/klaude-setup-removal-full-check.log`. Local Python 3.12
  only; no new CI/3.11/3.13 claim.
- Sequential `make package-smoke`: **all five wheels built/installed, public
  imports and installed `klaude --help` passed**;
  `/tmp/klaude-setup-removal-package.log`.
- Initial full run: **one failure, 3047 passed, 19 skipped**, 257.35 seconds.
  The receipt included warning presentation; a worker with the updated wording
  rejected the earlier receipt. `/tmp/klaude-setup-removal-initial-check.log`.
  This result was not a green gate. Informational warning wording/counts are now
  separate from strict filesystem receipts; newly incomplete visibility still
  requires renewed review. A full final rerun follows that fix.

## Remaining boundaries

External processes and same-account filesystem writers do not participate in
Klaude's acceptance lock. Accessible process references and changed-file checks
help, but cannot certify global filesystem quiescence or see protected process
internals. Stop externally launched engines before confirming. Missing/corrupt
metadata, oversized trees and unsafe directories need manual inspection; Klaude
does not offer arbitrary-directory deletion. Abrupt system failure in the final
metadata-unlink/directory-rmdir interval may leave an empty unlisted directory;
an unknown receipt requires checking the exact path, never a rollback claim.

Remote deletion, GPU/vLLM/adoption extensions, upstream vLLM inference,
online/system/other-platform installs and S6 remain outside this slice. The next
architectural step is reviewed remote GPU serving with observed engine/device
evidence, reusing SSH ownership/lease/cancellation rather than assuming hardware
capability from a configured recipe.

Mount-table field semantics were checked against the primary
[Linux mountinfo manual](https://man7.org/linux/man-pages/man5/proc_pid_mountinfo.5.html).
Live privileged bind mounting was not performed; parser/guard behavior uses the
kernel-format fixture. Descriptor traversal, real symlink environments and process
ownership were exercised against the actual filesystem/runtime.

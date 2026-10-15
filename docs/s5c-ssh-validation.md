# S5c, second slice — SSH settings and read-only diagnostics

Date: 2026-10-14. Continues the [local dependency/CPU-build slice](s5c-dependencies-validation.md).
This delivers SSH definitions and explicit, bounded connection/resource checks.
**S5c remains partially complete**: the later [owned remote CPU serving slice](s5c-remote-serving-validation.md)
is documented separately; key enrollment and additional GPU/vLLM work remain unfinished. S6
has not started. Prior dirty S5a/S5b/S5c work is retained; changes are uncommitted.

Follow-up: [reviewed existing-public-key enrollment and verified host-trust
setup](s5c-ssh-key-setup-validation.md) now implements that separate slice. The
scope, counts and evidence below describe this second slice's original validation.

## User flow

Model Manager → Servers lists This machine and saved SSH servers. Add SSH server
collects Name, Host, SSH port, User, Identity file, Known hosts, Models directory
and an explicit Use SSH agent toggle. Review initially selects Back. Saving
stores metadata and existing credential-file references; it does not connect,
load a model or change a chat/default model or HTTP endpoint.

Test connection verifies the host key, public-key authentication and the fixed
remote Python diagnostic protocol. Inspect server additionally reads CPU thread
count, architecture, total RAM, free disk space for the configured model
directory, bounded model-file/directory names and observed engine process names/
PIDs. GPU is explicitly **Not checked**. Process observations do not establish
ownership or permission to stop them. The later Serve CPU model action is an
explicit reviewed owned launch; Dependencies remains local.

Use as default has a concrete consumer: Inspect default server checks that SSH
server, or opens the existing local Hardware check for This machine. This is a
diagnostics default, independent of AI Defaults and model connections. Removing
its definition restores This machine as the diagnostics default and retains
remote files/processes, local key files and known-hosts entries.

Models/Processes show cached read-only snapshots; Reload diagnostics explicitly
rechecks the server. Controls appear above aligned tables, with common filter,
Back, private editor, scrolling and fixed header/footer behavior. A successful
connection retest retains the earlier inspection's original age; it does not
make old hardware/file data look freshly inspected. Failed checks and edited
definitions invalidate their old inspection data. Missing directories and
unavailable process inventories are distinct from empty inventories. Checking
feedback is muted, success green, missing-directory warning yellow and failures
red.

Canonical CLI commands:

```text
klaude model-manager ssh list
klaude model-manager ssh add ID --host HOST --user USER --identity-file PATH --known-hosts PATH
klaude model-manager ssh test ID
klaude model-manager ssh inspect ID
klaude model-manager ssh default ID
klaude model-manager ssh default local
klaude model-manager ssh remove ID [--yes]
```

Add also supports `--name`, `--port`, `--models-dir` and `--agent`; see its actual
help for defaults. Existing known-hosts and identity references are required;
there are no password/passphrase prompts or automatic host-key enrollment.
An encrypted key can be used through an explicitly selected existing agent.
Test/Inspect success, failure and Ctrl+C exit 0/1/130 respectively. Cancelling
removal confirmation exits 0 without modifying the definition.

## Architecture and limits

- Core `ssh_servers` owns validated definitions, revisioned writes, fixed
  OpenSSH arguments and typed diagnostic result projection; `ssh_diagnostics`
  owns the small fixed remote program. CLI `ssh_panel` and `ssh_commands` reuse
  the existing owned worker protocol and shared panel renderer.
- Owner-only `config/model-servers.json` stores at most 32 definitions, bounded
  to 256 KiB. Atomic writes use the existing settings lock. Definition nonces
  prevent stale edits/checks and ID reuse; default revisions protect concurrent
  default/removal changes. This store is separate from model-connections.json.
- TUI writes use SessionActionWriter's ordered action lane, execute independently
  of the session SQLite store, and drain accepted saves on shutdown. Captured
  session/draft/target identities prevent acknowledgements from reopening a
  later page or replacing another private editor.
- Replaceable read jobs capture request, configuration root, session/store,
  draft and target identities. Leaving cancels the read; late results are
  rejected. Saved definitions are rechecked after the SSH operation. Key-file,
  known-hosts-file and opted-in agent-socket references are also rechecked.
- Local key/known-hosts paths must be absolute regular non-symlink files, at most
  1 MB; a directly selected private key must have owner-only permissions. The
  application reads no private-key contents. Agent sockets must belong to this
  account; agent use is off by default. SSH receives a minimal environment,
  rather than ambient provider keys or proxy settings.
- Host and user fields cannot supply SSH options or shell text. OpenSSH uses
  explicit argument arrays, no user/system SSH configuration, no multiplexed
  connection reuse, no password prompts, strict existing known-host verification,
  no automatic host-key updates, proxy commands or agent/X11 forwarding. Remote
  parameters arrive as JSON stdin to one quoted fixed command, rather than
  interpolated shell text.
- Existing Linux OpenSSH and remote `/usr/bin/python3` are required. Each owned
  check has a 15-second outer deadline, 10-second SSH operation limit, 3-second
  connection timeout and 7-second remote diagnostic alarm. Combined response/
  stderr is limited to 64 KiB. Cancellation reaps the owned worker group and its
  SSH child; there is no persistent remote job to reconcile.
- Model inspection scans at most 500 directory entries and publishes at most
  100 names; symlink entries are skipped. It recognizes regular GGUF files and
  directories with config.json without reading model contents. Process metadata
  scans at most 4,096 /proc entries and publishes at most 32 matching names/PIDs,
  reading comm rather than command arguments or environment. Limits are visible.
- Engine executable presence is metadata only; binaries are not executed and
  models are not loaded. Unknown RAM/disk/architecture measurements remain
  unknown. No VRAM, hardware fit, process ownership or agent capability is inferred.
- Peer output is projected into bounded typed public fields, with terminal
  controls stripped. Unknown fields are discarded and raw SSH stderr is not
  exposed to the UI, logs or model context. Authentication, host-key, network,
  timeout, protocol and configuration failures remain distinguishable.

These controls bound Klaude's requested operation. They do not replace the
remote account's own SSH/shell startup configuration or create OS-level isolation.

## Actual validation

### Real CLI/TUI and transport

Bare Klaude ran **TEST KLAUDE FEATURES SSH** in an isolated already-dirty workspace.
The walkthrough used the installed OpenSSH client and a temporary unprivileged
loopback sshd with private QA host/client keys, authorized keys and verified
known-hosts. It changed neither the system SSH service/configuration nor the
user's existing SSH files.

Eight scenarios exercised:

1. Local/server inventory at 40, 70 and 120 terminal columns.
2. Private field editors and Back-focused cancelled review, without saving or
   connecting.
3. Ordered definition Save without a session/default model switch.
4. Actual encrypted Test/Inspect and RAM/CPU/disk/model/process snapshots.
5. Persisted default selection and its working Inspect default server consumer.
6. Definition editing, invalidated old data and a missing-directory warning.
7. Back-focused removal cancellation and confirmed removal, preserving remote
   files and local keys while restoring the local diagnostics default.
8. Actual CLI Add/Test/Inspect/Default/Remove through the same owned transport.

The dirty workspace file, remote original file, QA key/known-hosts bytes and
model-connections.json bytes were preserved. This is actual loopback SSH
transport evidence, **not a physical LAN-host or remote model-serving test**.
Final evidence: `.klaude/data/s2-models-v8i3aaq3/ssh-result.json`, its terminal
text/SVG captures and `/tmp/klaude-ssh-final-walkthrough.log`; all eight steps
passed and the interactive client exited 0. The final CLI commands all exited 0.

### Observed layout defect and fix

Visual inspection of a real 120-column capture found model headers in table
columns but INFO rows rendered inline. The shared renderer previously recognized
only NAVIGATION rows as table entries. Explicit table sections now also align
INFO, STATUS, ACTION and CHOICE rows; ordinary controls/metadata remain outside
their table. This also fixes the dependency inventory without inventing actions
for read-only metadata. Four focused regression cases cover INFO/ACTION rows at
70/120 columns, aligned values, controls above headers and non-table metadata.
The repeated real walkthrough's model capture confirms aligned NAME/TYPE/SIZE.
Captures used NO_COLOR to inspect geometry; they do not certify every theme.

### Automated coverage

The SSH tests cover private atomic definitions/defaults, stale revisions, invalid
fields, option/path injection, DNS/IPv6 normalization,
actual known-host/auth/network failures, opted-in ssh-agent, malformed peer
output, typed/sanitized projections, banner timeout, owned cancellation,
changed definitions, SQLite-independent ordered saves, stale configuration/
session/draft results and preserved inspection ages.

Focused SSH/shared-panel validation passed **78 tests** after the final metadata
changes. Prior source-build and serving evidence remain in their linked reports;
they were not rerun as part of this read-only SSH slice.

Final local gates, on Python **3.12.3**:

- `UV_CACHE_DIR=/tmp/klaude-s5-uv-cache make check` ran the full unit suite:
  **2,956 passed, 19 skipped**, in **190.41 seconds**. It then stopped at one
  Ruff E501 finding in the new manager help declaration; this invocation was
  not an all-green make check. Evidence: `/tmp/klaude-ssh-release-check.log`.
- The help declaration was line-wrapped without changing its value or runtime
  behavior. Subsequent `make lint typecheck` passed repository Ruff and production
  mypy, **125 source files**. Evidence: `/tmp/klaude-ssh-release-static.log`.
- Sequential `make package-smoke` passed all **five wheel** builds, isolated
  installation/imports and installed `klaude --help`. Evidence:
  `/tmp/klaude-ssh-release-package.log`.
- `git diff --check` passed. Existing dirty S5 work remains; no lock, dependency
  metadata, version, commit or push change was made. Python 3.11/3.13 CI was
  not run during this local pass.

## Remaining work

- Owned remote CPU serving, leases, tunnel registration and cleanup are delivered
  in the [follow-up](s5c-remote-serving-validation.md). Remote dependency recipes,
  GPU/vLLM serving and adoption remain unfinished. A process snapshot does not
  authorize remote mutation.
- Key generation/enrollment, host-key verification UX, certificate identities,
  jump hosts/SSH aliases and password authentication are not supported here.
- Physical LAN/SSH-host differences and GPU/vLLM resource checks still need
  live validation; this pass certifies Linux loopback transport and bounded
  metadata workflows only.
- Inspection is a bounded shallow snapshot, not recursive model discovery or
  a durable remote hardware inventory. Current data is held in the client and
  is rechecked explicitly, rather than stored as reusable capability evidence.
- Local build deletion/reclamation and additional GPU/vLLM installation recipes
  remain as described in the first S5c report. S6 is unstarted.

## Primary sources

- [OpenSSH client manual](https://man.openbsd.org/ssh.1), including explicit
  configuration and batch operation.
- [OpenSSH configuration manual](https://man.openbsd.org/ssh_config.5), including
  known-host verification, identity/agent selection and forwarding controls.
  Supported flags were also exercised with the installed Linux OpenSSH client.

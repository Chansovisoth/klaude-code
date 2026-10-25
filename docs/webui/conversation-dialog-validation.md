# Conversation dialog and background sessions

The Conversation dialog keeps the name field above a subtle divider. Enter
submits the name through the existing reviewed backend snapshot and durable
request receipt without opening another confirmation dialog. The field locks
while saving and its live status reports pending, failure or completion.
Download .md, Archive/Restore and Delete share one evenly spaced row using the
existing quiet text-button styling. Their height, padding, typography, icon size,
icon gaps, hover surfaces and focus outlines match; only Delete's foreground is
red. Buttons hug their contents and wrap when the dialog is too narrow for all
three. Permanent deletion remains an explicit reviewed action, with its
irreversible nature explained in that confirmation, and is available without
first archiving the conversation.

Deleting the selected idle conversation opens a fresh conversation after exact
request admission, before the deletion worker starts. Replaying the receipt does
not open another conversation. Browser deletion passes the reviewed archive
state to the transaction; workspace, history, active leases, unresolved work and
queued work remain checked. Existing terminal callers retain their archive-first
default. Deleted session IDs retain their existing tombstones.

Production hosts now inject an application factory and retain up to four
independent conversation applications. Switching away from a running reply
retains its Agent, runtime, broker, queue and durable lease. Selecting it again
returns to that instance. New-chat defaults remain authoritative; without an
explicit default the source model/mode is applied to a separate runtime.
Idle unselected instances can be closed to free a slot, never running or queued
ones. Hosts embedded without a factory retain their prior idle-only behavior.

The selected conversation is still shared across this host's owner clients;
this change does not introduce independent per-tab selections. The list marks
live workers with an accessible running icon and polls while any listed worker
is active. The icon respects both reduced-motion settings. In-flight file-edit
activation remains owned by its original application; LAN activation checks all
retained applications. Idle switches retain the previous edit-revocation rule.
Logout closes the client's interactions across applications, and shutdown drains
each retained application and closes its resources.

## Validation

- `tests/unit/test_webhost.py`, `test_webhost_parallel_sessions.py`,
  `test_web_management.py`, and `test_library_management.py`: 96 passed in the
  combined regression run, before the last two focused lifecycle cases were added.
- Final `test_webhost_parallel_sessions.py`: 4 passed, covering independent workers and
  queued replies, switching back, deletion refusal during work, capacity without
  cancellation, idle-instance eviction, chosen-model preservation, separate
  runtimes, background edit/LAN isolation and shutdown cleanup.
- `scripts/webui_sessions_smoke.py`: isolated Chrome checked Enter rename,
  rejected-name feedback, real Markdown download, side-by-side action geometry
  at 320/390/1000px, archive cancellation/archive/replay/restore, two concurrently
  running conversations, switching in both directions, running indicators, and
  deletion of the selected unarchived conversation. Zero JavaScript exceptions.
- Focused Ruff, JavaScript syntax, CSS/loading bundle consistency and diff checks
  passed.

All execution used temporary stores and deterministic runtimes. No real model
throughput or physical mobile keyboard was measured. The existing managed host
was not restarted; backend changes require a host restart before they are live.

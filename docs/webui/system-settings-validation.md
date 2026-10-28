# System settings

Settings adds System after Memory. It uses the shared heading, grouped rows,
responsive tab navigation and Settings search. Restart Web UI and Shut down
Klaude have separate actions and a native confirmation dialog. Cancel and Escape
return focus without changing runtime state. The confirmation describes browser
sign-out, unsaved input and the action's terminal-session scope.

Restart Web UI preserves the exact hosted session, workspace, port and LAN
address. It revokes browser authority and drains the old listeners, applications
and owned workers, then launches a replacement using the same interpreter and
fixed WebUI entry point. The launcher waits up to twenty seconds for readiness;
the browser waits a bounded interval for a new ephemeral instance, then reloads
to sign in again. An unavailable restart provides explicit Reload/start guidance.
Terminal sessions stay running through restart.

Shut down Klaude disables automatic WebUI startup and stops the WebUI plus the
reviewed running Klaude terminal processes for the same config/data profile.
Targets must match this installation's exact entry points and interpreter, OS
user, profile roots and Linux process birth identity. Signals use pidfds, with
normal interruption cleanup on updated terminal clients and a bounded force-stop
fallback for an unresponsive reviewed process. No arbitrary commands, PIDs or
paths come from the browser. Other profiles, unrelated Python processes, Ollama,
Stable Diffusion and external model services are outside these process targets.

Only authenticated administrators can read private System status or review/apply
actions. Mutations retain owner/client binding and Origin/CSRF checks. A review
expires after two minutes and binds the host, session, workspace, port/LAN and
exact process set. Active chat turns, queues, fixed-operation workers and leased
non-chat operations reject lifecycle changes. Apply rechecks those conditions
under the host admission lock before revoking authority. Duplicate accepted
request IDs cannot execute another action. Private receipts record acceptance
and completion/failure; neither HTTP response loss nor reconnect failure triggers
an automatic replay. The public health response contains only readiness and an
ephemeral random instance ID. Older/embedded hosts show capability guidance.

Validation:

- 16 focused System/terminal/managed-host tests passed. They cover authorization,
  CSRF, malformed reviews, owner/process/expiry binding, persistent shutdown
  intent, request deduplication, exact installation/profile matching, pidfd
  rejection after changed identity, unrelated-process survival and existing host
  launch/stop behavior.
- `scripts/webui_system_smoke.py` runs real isolated WebUI and CLI processes
  against a fixture model metadata server. The browser checks 320/390/768/1440px
  in light/dark themes, review cancellation and Settings search. Confirmed Restart
  produces a new runtime, preserves session/workspace/LAN, requires re-authentication
  and retains terminal sessions. Confirmed Shutdown stops that profile's WebUI
  and CLI while a second profile's CLI survives. No inference or production
  shutdown occurs. The run passed with zero console errors. Screenshots are in
  `/tmp/klaude-system-evidence`.
- Focused Ruff/mypy, JavaScript syntax, generated bundle and whitespace checks
  passed separately from the runtime/browser walkthrough.
- The final browser walkthrough also passed restoration of normal polling after
  a definite apply rejection, without retrying the action, and kept the selected
  System tab visible on phone screens.
- The live WebUI was updated only after idle/queue/leased-operation checks,
  preserving its exact conversation, workspace, LAN address and terminal.
  An authenticated phone browser opened System, read the one running terminal
  count, and cancelled both action confirmations. Runtime/session/process
  identities and saved settings remained unchanged, with zero console errors.
  The temporary verification session was signed out. Live Shutdown was not
  invoked.

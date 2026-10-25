# Admin role for Model Store and settings

Date: 2026-10-25. Replaces the address-based model-management restriction from the
[Store/settings completion](completion-validation.md).

The generated first account explicitly stores `role: admin`. Existing version-1
singleton account files without a role retain administrator identity, without a
password reset or credential rewrite. Explicit `user` records remain non-admin;
unknown roles fail closed. Password changes and local password recovery preserve
the stored role rather than promoting the account.

Account identities and browser sessions carry the server-owned username, role and
credential revision. Authentication revalidates all three against account storage.
A role change revokes the old login session even if the credential revision was
not changed. Login and `/api/v1/auth` return the validated username/role, never an
inferred role from username or a client-supplied field. This is a role boundary
for the existing singleton store; user creation and multi-user workspace ACLs
remain future work.

A shared HTTP admin check authorizes the following on either listener:

- Native model pull/delete review and submission, cancellation and reconciliation.
- Connection setup, edit, enable/disable, removal, write-only credentials and
  exact-state recovery, plus read-only connection testing.
- Persistent Model Defaults and image-service saves/recovery, plus image-service
  capability testing.
- Existing MCP definition management, using the same current-role authority.

Read responses return server-derived `management_allowed`; the UI enables admin
controls on LAN and uses admin-account guidance when management is unavailable.
Non-admins may browse models and choose their current conversation model through
its existing runtime action. Connection addresses are omitted from the non-admin
management inventory. Shared global settings controls become read-only.

Legacy bootstrap-only embedded hosts retain their established local authority;
they do not gain an administrator account or remote management. Production
password-authenticated hosts always check the actual account role, even on
loopback. Auth/Origin/CSRF, session/control/review ownership, exact revisions,
active-conversation/default-role protection, journals and unknown-outcome fences
remain in force. File-edit activation retains its separate local-only policy.

## Validation

- **107 tests passed in 178.94 seconds** across `test_web_accounts.py`,
  `test_browser_model_settings.py`, `test_model_store.py`,
  `test_web_management.py`, `test_web_media_settings.py` and `test_webhost.py`.
  The account suite was rechecked after requiring an explicit role for internal
  credential publication: **9 passed**.
- The new role matrix covers admin/user on local/LAN policy paths, server-derived
  management flags, connection-address projection, admin native pull/delete and
  defaults saves, denied non-admin review/test/cancel/recovery, CSRF rejection,
  role-change session/review revocation, legacy account compatibility and role
  preservation through password change/reset. The same username with a `user`
  role is denied, demonstrating that username does not grant permission.
- Both Chrome walkthroughs passed with `KLAUDE_TEST_ADMIN_LAN=1`, which signs into
  an isolated password-admin account and exercises the listener's LAN policy.
  Settings covers role selection/Apply, service Test, add-disabled, credentials,
  enable/Test, removal and logout. Store covers reviewed pull, receipt history,
  shared pagination, offline inventory and Image Studio. Both passed
  320/390/768/1440px, light/dark, with zero JavaScript exceptions. These are
  isolated fixture effects, not production weight downloads or inference.
- Production mypy passed all **229 source files**; focused Ruff, JS syntax,
  Expressive bundle verification and `git diff --check` passed. The unrelated
  preexisting static-route long line in `host.py` remains outside this change.

The managed host was reloaded only after exact process/session, idle/queue/review,
operation-journal and saved-session preflight checks. Instance changed from
`3329295:70498183` to `3335470:70585095`, preserving workspace
`/mnt/HDD1/draft/playground`, session `efc02e7db5654c0589bfc5e2c4fcd83e`,
`ollama/qwen3-coder:30b`, Standard mode, password account and LAN origin
`http://192.168.100.244:50000`.

Actual authenticated HTTP verification passed on both `127.0.0.1:50000` and
`192.168.100.244:50000`: role `admin`, management allowed for Store/downloads,
connection and role settings; 5 connections; native metadata Test returned 30
models. Connection reviews prepared successfully and were discarded, with an
unchanged saved inventory. Both temporary login clients signed out. No production
credentials, defaults, connection definitions or model weights were changed.
Private result: `/tmp/klaude-admin-model-live-result.json`.

Existing dirty work was preserved; nothing was committed or pushed. Reload and
sign in again after the host restart.

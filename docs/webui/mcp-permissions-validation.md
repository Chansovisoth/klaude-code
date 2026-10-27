# Per-MCP tool approval

Integrations → MCPs → connection details exposes shared segmented radio controls:
**Auto**, **Ask first**, **Deny**. Auto executes without a tool approval prompt;
Ask first asks for permission; Deny prevents execution. Disabled connections remain
unavailable independently of their saved policy. A server with no discovered tools
has disabled controls until discovery. Existing mixed per-tool policies have no
selected radio and an explanation; nothing is flattened until explicitly saved.

The reviewed setting updates all currently discovered namespaced tool permissions
in one atomic settings write, reusing the terminal's `permissions` fields. Exact
connection fingerprints and field compare-and-set checks reject stale saves without
partial updates. No network or discovery request occurs when changing policy.
Newly discovered tools retain their existing configured default (normally Ask first).
Settings apply on future turns and do not approve pending interactions.

The browser previously forced every MCP tool to Ask regardless of saved policy.
It now honors valid saved policies. Workspace/network checks, registry definition
rechecks, unresolved definition fences and file-edit review guards remain active.
Only administrators can review or submit these MCP permission changes. Existing
operation receipts deduplicate repeated submissions.

Focused validation:

- `test_browser_tools.py` and `test_mcp_browser_permissions.py`: 19 passed;
  includes actual Auto execution, Ask interaction, Deny non-execution, changed
  definitions, atomic stale-save rejection, isolation and new-tool defaults.
- `test_web_management.py`: 24 passed, including HTTP reviewed saves for all three
  policies, inventory persistence, stale reviews and repeated request receipts.
  An additional focused authorization test passed for review/submit role checks.
- `KLAUDE_TEST_CONNECTIONS_ONLY=1 python scripts/webui_management_smoke.py`:
  actual reviewed policy saves/reloads at 320, 390, 768 and 1440px; three controls
  stay on one row with 44px targets and no dialog overflow; no browser errors.
- JavaScript syntax and CSS bundle checks passed. Focused application mypy passed.
  Existing host mypy errors at the session-query path and pre-existing Ruff line
  lengths are outside this change; this is not a full repository validation.

The browser tests use temporary configuration, local HTTP fixtures and isolated
Chromium. The live host was not restarted; these backend changes require restart
and browser reload before they take effect there.

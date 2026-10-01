# MCP client reuse comparison

Date: 2026-10-01. Candidates selected from the late-September 2026 releases.

## Decision

Production now uses the official MCP Python SDK 2.2.0 high-level `Client`.
Discovery and persistent connections share one transport/auth factory. Both
built-in servers use SDK `MCPServer`. The per-server worker bridge remains to
connect the synchronous agent runtime to async MCP clients. It is not replaced
by another custom scheduling framework in this migration.

Both candidates passed the same synthetic fixture checks; full FastMCP did not
demonstrate an essential benefit for Klaude's current tools-only integration.
The official client avoids an additional framework and had the smaller measured
dependency footprint. FastMCP remains a reasonable alternative for future
requirements; its ClientGroup/config aggregation features were not evaluated
here, and its separate slim distribution was not benchmarked.

The root lockfile now selects SDK 2.2.0. Neither experimental adapter is imported
by production. No real account, MCP config, or credential files were loaded or
changed by the experiment or migration tests.

## Reproduce

Run from the repository root with a working network for initial dependency
installation and permission to bind local loopback sockets:

```bash
UV_CACHE_DIR=/tmp/klaude-mcp-reuse-cache uv run --isolated --no-project \
  --with 'mcp==2.2.0' \
  python scripts/compare_mcp_clients.py --backend sdk --mode auto

UV_CACHE_DIR=/tmp/klaude-mcp-reuse-cache uv run --isolated --no-project \
  --with 'fastmcp==4.0.10' --with 'mcp==2.2.0' \
  python scripts/compare_mcp_clients.py --backend fastmcp --mode auto
```

Repeat with `--mode legacy` for both candidates. `--isolated` matters: without
it, uv may layer candidates over the development environment and invalidate
dependency counts. Direct comparison versions are pinned; its transitive
dependencies are not locked, so later reproductions may differ. Production
dependencies use the root lockfile.

## Measured results

Both candidates passed **6/6 checks in auto mode and 6/6 in legacy mode**:

- Disabled adapters reject before constructing a client or starting a process.
- Stdio discovery, call, host permission denial, ambient secret exclusion,
  in-flight cancellation, and subsequent successful calls.
- Explicit stdio close/reconnect.
- Two independent simultaneous stdio connections.
- HTTP discovery/calls, cancellation, unknown-tool failure followed by recovery,
  and explicit close/reconnect.
- Actual shared SDK OAuth refresh flow over mocked HTTP, including rotated token
  storage and subsequent use of the new access token.

Representative final auto-mode runs, Python 3.12 on this Ubuntu host:

| Measurement | Official SDK | Full FastMCP |
|---|---:|---:|
| Installed distributions, clean environment | 28 | 68 |
| First client construction, including imports | 0.612 s | 1.041 s |
| First stdio connection, excluding construction | 0.690 s | 0.767 s |
| Complete fixture run | 5.571 s | 5.993 s |
| Main process peak RSS | 70.2 MiB | 88.2 MiB |

These are individual observations, not statistical benchmarks. Disk/package
caches were warm, candidates ran concurrently, child-process memory is excluded,
and existing Klaude dependencies overlap with both candidates. Do not interpret
the distribution difference as exactly 40 new production dependencies.

The report includes timings, package identities and exception types only, not
tool output, request headers, auth values or raw exception messages. Fixture
credentials are synthetic and memory-only. OAuth expiry is injected into the
SDK context solely in this test script; do not use that private API in production.

## Removable code versus retained application responsibilities

| Existing area | Migration direction |
|---|---|
| `MCPClient._run`: manual streams, ClientSession and initialization | Replace with maintained Client plus a thin transport/auth factory |
| `MCPClientManager._actor`: duplicated connection setup | Reuse the same client factory and owned connection lifecycle |
| Per-server queues/threads | Evaluate one owned async service; do not assume Client removes the synchronous-agent bridge |
| Tool schema/result bounds, namespacing | Retain; untrusted external tools remain bounded |
| `MCPRegistry`, disabled imports, definition fingerprints/CAS | Retain; these are application trust/configuration semantics |
| `MCPTokenStorage` and masked/headless UX | Retain or adapt with parity tests; never delegate secret policy blindly |
| TUI inventory, mutation acknowledgements and stale-result handling | Retain thin application adapters, consolidate only where equivalent |

The duplicated connection setup and result bounding have been consolidated. Neither
candidate makes cancellation equivalent to rollback, prevents an in-flight
remote mutation, or independently enforces Klaude permissions.

## Migration validation and remaining work

Completed implementation and regression coverage:

- Production storage refreshes expired credentials before its first request,
  saves rotated tokens privately, and refuses credentials bound to another URL.
- A narrow `_initialize` override restores token lifetime omitted by SDK 2.2's
  storage initialization. Refresh/discovery/PKCE remain SDK operations. Recheck
  this workaround when updating the SDK.
- Callback results preserve `iss`; duplicate code/state/issuer parameters fail.
  Revoked refresh, issuer mismatch and cancellation fail without forwarding an
  expired token. Existing manual login and loopback callback tests pass.
- SDK snake_case fields are translated into the existing persisted tool schema
  and result format. Discovery follows bounded pagination, rejecting repeated
  cursors. Structured-only results are preserved within the shared output limit.
  Disabled calls are rejected before any connection. Grouped transport failures
  display their sanitized underlying error instead of an opaque task-group label.
- Actual HTTP discovery/calls/reconnect and stdio process death are covered.
  A failed call is not replayed; the next explicit request can reconnect.
- Both built-in MCP servers register and execute through SDK v2 in tests, and
  knowledge mutations retain their opt-in boundary.

Remaining checks: live third-party browser/SSH login, arbitrary network-loss
patterns, and Python 3.11/3.13 execution (only 3.12 is installed on this host).
Production intentionally keeps legacy handshake mode; changing negotiation
defaults requires a separate compatibility decision.

The comparison's permission check is a host-side guard; the full repository
suite covers the actual agent permission gate. No FastMCP dependency was added
to production. Next: run the existing CI Python matrix and a live OAuth login
with a user-selected server, then reassess whether the remaining worker bridge
needs consolidation based on measured defects or latency.

## Repository validation

Final regression command (loopback-enabled execution; a two-minute outer bound):

```bash
timeout 120s uv run --offline pytest -q \
  tests/unit/test_mcp_suggestions.py tests/unit/test_mcp_reuse_comparison.py \
  tests/unit/test_mcp_client.py tests/unit/test_mcp_catalog.py \
  tests/unit/test_mcp_inventory.py tests/unit/test_mcp_mutations.py \
  tests/unit/test_cli_commands.py -k 'mcp or completion' \
  -o faulthandler_timeout=30

UV_CACHE_DIR=/tmp/klaude-mcp-reuse-cache uv run --offline ruff check .
UV_CACHE_DIR=/tmp/klaude-mcp-reuse-cache uv run --offline mypy \
  packages/core/src packages/knowledge/src packages/tools_local/src \
  packages/web/src apps/cli/src
```

The initial comparison regression run had **128 passed, 503 deselected**.

Production migration checks:

```bash
timeout 180s uv run --frozen --offline pytest -q tests/unit -o faulthandler_timeout=60
timeout 60s uv run --frozen --offline pytest -q tests/unit/test_mcp_v2.py \
  -o faulthandler_timeout=20
UV_CACHE_DIR=/tmp/klaude-mcp-reuse-cache uv run --frozen --offline ruff check .
UV_CACHE_DIR=/tmp/klaude-mcp-reuse-cache uv run --frozen --offline mypy \
  packages/core/src packages/knowledge/src packages/tools_local/src \
  packages/web/src apps/cli/src
UV_CACHE_DIR=/tmp/klaude-mcp-reuse-cache uv run --frozen python scripts/package_smoke.py
```

The full migration run passed **1,519 tests, 19 skipped**, in 67.15 seconds.
The structured-only result test was added afterward and passed with the focused
auth/result checks (**5 passed, 14 deselected**). The complete SDK v2 regression
file subsequently passed **19 tests**. Ruff passed; mypy passed on
**58 source files**. Packaging built and installed **five wheels**, imported
their public packages and successfully ran installed `klaude --help`.
Packaging resolves published transitive dependencies in its temporary environment;
the unit suite uses the frozen workspace lock.

The MCP search composer now suggests actual registry names using a 350ms
debounced owned background job. Completion remains an in-memory operation;
late results for older queries are ignored. Its popup moves two columns right,
and arriving search results focus the first server instead of the loading
screen's Back row. Regression coverage checks debounce, stale responses,
cancellation, and the loading-to-results selection transition.
The CLI and suggestions suite passed **563 tests, 1 skipped** in 26.34 seconds:
`timeout 90s uv run --frozen --offline pytest -q tests/unit/test_mcp_suggestions.py tests/unit/test_cli_commands.py -o faulthandler_timeout=30`.
This required loopback-enabled execution; the sandbox-restricted attempt reached
its 90-second timeout in the existing OAuth tests. Production mypy again passed
all 58 source files, and Ruff passed for the updated UI and test modules.

Earlier iterations exposed two introduced test/completion issues, fixed before
the final passing run. Two socket-restricted broader runs stalled in the existing
OAuth callback setup test and were interrupted; its loopback-enabled equivalent
passed in the final suite. Do not report the restricted runs as passing.

### Upstream references

- [Official SDK 2.2.0 release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.2.0)
- [Official v1-to-v2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/)
- [FastMCP 4.0.10 release](https://github.com/PrefectHQ/fastmcp/releases/tag/v4.0.10)
- [FastMCP client](https://gofastmcp.com/clients/client)
- [FastMCP OAuth](https://gofastmcp.com/clients/auth/oauth)

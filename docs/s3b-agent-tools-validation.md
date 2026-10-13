# S3b built-in tools and Settings navigation

Date: 2026-10-13. Follow-up to
[S3b execution validation](s3b-agent-execution-validation.md).
The pre-existing S1/S2/S3 worktree was preserved; no commit or push was requested.
S4-S6 and additional search adapters remain unstarted.

## Changes and causes

Previously, availability preferences covered ten retrieval tools, leaving the
other registered built-ins without settings controls. Agent Tools still opened
the old mixed controls page, while Search/URL Fetch owned duplicate switches.
The Settings home combined unrelated categories under Assistant.

Built-in Tools now derives its inventory from the actual `Agent.tools` registry.
Classification and labels are shared with Permissions; classification does not
register tools. Empty groups disappear, unknown registered built-ins use Other,
and external `mcp__` tools stay in MCPs. The real fixture workspace registered
30 built-ins across Workspace, Git, Web & Research, Knowledge & Sessions,
User Interaction and Orchestration. Counts mean enabled/registered, not
permission, authentication or network readiness.

Enter opens a group; Enter on a tool opens its purpose, Enabled switch and
focused Permission policy link. Space on a group tool row switches that tool.
Group switches show ON, OFF or MIXED; MIXED first enables the entire registered
group. Bulk writes are field scoped, atomic and ordered through the existing
preferences writer. A built-in reset enables only registered built-ins and
retains permissions, process grants, MCP state, Search/provider settings and
execution limits. Reset publishes explicit enabled defaults so other clients
can merge the acknowledged reset on their next save, including previously
disabled tools. A two-client regression verifies this round trip. A stale removed tool gives footer feedback instead of crashing.
Knowledge validation remains in Knowledge & Sessions. Web validation and
provider routing stay in Search. Availability is never a permission grant.

Agent Tools links to the existing MCPs/Skills pages. Their manage/search/import
flows keep their owners and return to the selected link. Search and URL Fetch
link to the tool detail instead of duplicating its switch, retaining caller
filter/focus on return. Permission detail returns to the selected tool.
Settings now groups Appearance, Models & AI, Agent and Advanced. Providers is
retained under Advanced as Provider credentials; its Hugging Face editor cannot
move to Model Manager until that workspace exists. Native credential editors and
the Search/fetch forwarding routes remain available. Existing settings aliases
and Runtime's hardware/context/calibration ownership remain intact.

The shared chat/ask factory now loads availability for every built-in rather
than just research tools. During implementation, inspection found that direct
execution rejected a live disable but subsequent schemas could still advertise
it. Capability snapshots and worker preparation could inherit that stale state.
Later schemas now recheck current disables, as do supervisor preparation and
child tool construction. Native/text recovery and explicit named-tool routing
retain their existing unavailable-call guards. Enabling during a turn does not
expand that turn's original tool selection; a subsequent turn can use it.

## Real interaction and protocol verification

An isolated PTY session named **TEST KLAUDE FEATURES AGENT TOOLS** used the actual
bare `klaude` entry point. Keyboard checks exercised Settings grouping, group
counts, mixed/bulk states, individual switches (including Space), purpose,
permission navigation, managed MCPs/Skills links, and Search/URL Fetch round
trips. Captured terminal screens were inspected at 80 and 120 columns; bodies
also render within 40 columns with stacked values and scrolling. The common
40-column status/composer chrome remains cramped, as in the earlier evaluation.

Interactive chat and `klaude ask` used an isolated localhost Chat Completions
protocol fixture. It deliberately attempted disabled `read_file`/`run_shell`
calls, then answered the real bounded recovery message. A text-form read attempt using Klaude's supported `<function=...>` format
was also checked through `klaude ask`. Assertions covered absent schemas,
unavailable-call feedback, untouched file canaries, no shell-created sentinel,
and honest final responses/exit codes. This verifies Klaude's actual routing,
provider protocol and orchestration; it does not certify native model capability
or a paid cloud endpoint.

Early driver runs expected a permission heading above the focused viewport,
mixed-case MCP headings, and an off-screen Hugging Face row. Those expectations
were corrected after inspecting the actual screens. The original malicious
fixture repeated its unavailable calls when recovery arrived as a model message
rather than a tool result; Klaude correctly stopped it with an error. The final
fixture responds to that real feedback and preserves bounded recovery behavior.

Final walkthrough artifacts:
`.klaude/data/s2-models-ami_1g9j/groups-result.json`,
`model-requests.json`, captured TXT/SVG screens and `groups-terminal.log` in
`.klaude/data/s2-models-ami_1g9j/`. The fixture made **two model requests per
scenario**: interactive native recovery, one-shot native recovery and one-shot
supported text recovery (**six total**). One-shot runs completed in approximately
**1.51 s** and **1.42 s**, both with exit code 0; the TUI exited with 0.
All disabled-tool schemas were absent and canary/sentinel checks passed.
A final real TUI reset run restored all **30** built-ins, persisted explicit
true defaults, restored the **8/8** Workspace count, retained permissions/runtime,
made **zero** model requests and exited with 0. Artifact:
`.klaude/data/s2-models-3ovxbmv6/reset-result.json`;
`/tmp/klaude-s3b-groups-reset-live.log`.
Artifacts are local ignored evaluation data, not tracked release inputs.

## Regression gates

Focused tests cover actual inventory, mixed-state rendering and width bounds,
bulk/individual persistence, permission/process-grant preservation, registered
reset scope, live intent through failed/stale saves, exact Back/filter/focus,
MCPs/Skills owners, native/text disabled calls, later schema refresh and stale
parent worker snapshots. Existing Search/fetch and CLI rendering tests were
updated to test their migrated owners. Full unit/static/package results and
local artifact locations follow:

- Final `make check`: **2,745 passed, 19 skipped** in 141.38 seconds,
  Local Python 3.12.3, Ruff clean, production mypy clean (103 source files).
  No fresh Python 3.11/3.13 CI run was requested.
  `/tmp/klaude-s3b-groups-final-check.log`.
- The 14 focused availability tests passed again after strengthening the
  native/text recovery assertion and adding the two-client reset regression.
  `/tmp/klaude-s3b-groups-last-focused.log`.
- Final `make package-smoke`: all five wheels built, installed and imported;
  installed `klaude --help` passed.
  `/tmp/klaude-s3b-groups-final-package.log`.
- A direct TUI-controller stale-inventory probe verified a removed tool's Space
  action reports a footer error with no crash, save or availability mutation.
- `git diff --check` passed. SHA256 comparison against all 67 initially dirty
  paths found no unrelated changed paths or missing files. New paths in this
  slice are the registry metadata module, follow-up evaluation and focused tests;
  the existing child supervisor received the current-availability guards.
  Baseline: `/tmp/klaude-s3b-groups-baseline.json`.

## Remaining limits

- Common terminal chrome at 40 columns needs separate responsive-layout work;
  migrated control bodies and scrollable navigation remain usable.
- Actual multi-worker model generation, native Ollama generation and paid
  provider calls were not certified by this UI/protocol fixture. Existing
  delegation, cancellation and provider regressions remain in the unit gate.
- Hugging Face configuration remains in Provider credentials pending S4.
- Other text envelopes, such as whole `<tool_call>{...}</tool_call>` JSON,
  are not the supported function-tag protocol. A probe left that envelope as
  public text without executing it. Broader malformed-envelope normalization
  remains a separate agent-recovery improvement; this pass verifies the existing
  native and supported text recovery paths.
- Changing availability preserves all hard safety boundaries and cannot make a
  denied, dirty-worktree-blocked, unauthenticated or unsupported tool callable.

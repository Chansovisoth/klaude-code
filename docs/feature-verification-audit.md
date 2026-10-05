# Agent capability verification

Date: 2026-10-04

## Scope and result

This pass inspected startup tool disclosure and the execution paths for
installed Skills, external MCP tools, and read-only subagent workers. It added
on-demand Skill reading and a startup inventory of enabled Skills. The named
`TEST KLAUDE FEATURES` session is now saved in the normal Klaude session store;
see [its live test ledger](test-klaude-features.md).

| Capability | Evidence | Result |
| --- | --- | --- |
| Startup disclosure | Configuration snapshot lists enabled tool names, MCP count, delegation, and readable Skill names/descriptions | Implemented; full Skill text stays out of the startup prompt |
| Skill use | Scripted model calls `read_skill`; reader enforces the Settings disabled-Skill database, bounded regular files, package containment, and paged output | Focused integration and safety tests pass |
| MCP use | Scripted model receives a relevant namespaced schema and calls the matching enabled server through an ask policy; disabled server is excluded | Focused integration test passes. A live local-model run selected the namespaced tool, called a temporary SDK-based stdio MCP fixture, and reported its result correctly |
| Subagent workers | Supervisor and CLI tests cover isolated context, scoped read-only tools, parent/child budgets, cancellation, ordered results, and lifecycle events | Focused tests pass; live local-model delegation called `delegate_task`, the child read the temporary file, and the parent reported the child findings correctly |
| Live local Skill probe | `qwen3.5:4b` called `read_skill` for a minimal temporary Skill and the installed coding Skill | Both answered the requested Python checks. The installed Skill succeeded after the default page was reduced to 2,000 characters and the continuation hint was made conditional |

Focused validation: 60 Skill/MCP/subagent tests passed, 12 selected CLI
delegation/MCP tests passed, and the selected cached MCP permission test passed.
The later full unit suite passed outside the restricted sandbox: 2301 passed,
19 skipped. Ruff passed on changed Python files; mypy passed on 55 CLI/core source files.
The five-wheel package smoke passed, and the built CLI wheel contains the new
Skill runtime module.
The named session also called its configured external Context7 MCP tool and
reported the Pydantic library ID from its successful result. The initial
SDK-based local fixture timed out only inside the restricted test sandbox: a
minimal AnyIO thread read also stalled there.
Outside that sandbox, Klaude discovered and called the SDK fixture, discovered
11 tools on its built-in knowledge MCP server, and the live model completed an
SDK fixture tool call. A protocol-level stdio fixture also passed. The first live
delegation attempt exposed a child routing
bug: it made no file-read call and incorrectly said the file was absent. After
the child received its prepared permission-scoped tools directly, the rerun
made one read call and returned the correct file values.
The long installed Skill initially exhausted the 4B model's output budget with
a 4,000-character page. A 1,500-character probe prompted repeated paging and
timed out. With a 2,000-character default and a conditional continuation hint,
the model read one page and produced three relevant checks.

## Design basis

The startup prompt carries concise capability descriptions, while current
request schemas remain authoritative for calls. Skill instructions are read
when relevant, by exact name and in bounded pages. External MCP content and
Skill files are treated as untrusted; tool execution remains subject to host
permissions. Delegation retains its existing read-only, budgeted child scope.

These choices follow the documented patterns in the
[OpenAI Agents SDK orchestration guide](https://developers.openai.com/api/docs/guides/agents/orchestration),
[OpenAI Skills guide](https://developers.openai.com/api/docs/guides/tools-skills),
[Claude Code Skills guide](https://code.claude.com/docs/en/skills),
[Claude Code subagents guide](https://code.claude.com/docs/en/sub-agents), and
[MCP tool specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

## Next verification

Continue the named session with disabled-Skill, memory, command-safety, and TUI
probes. Local knowledge retrieval and MCP permission denial passed live. Keep
live results separate from scripted coverage in the
[test ledger](test-klaude-features.md).

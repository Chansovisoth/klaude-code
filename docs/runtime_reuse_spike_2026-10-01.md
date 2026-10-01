# Agent runtime reuse spike (2026-10-01)

## Decision

Pilot Pydantic AI behind a compatibility adapter. Do not replace Klaude's loop
yet. The isolated Pydantic AI 2.52.0 spike passed async multi-tool dispatch,
stream event delivery, cancellation with tool cleanup, serialized completed
history, and a model change on the next run. It did not test a real Ollama model,
Klaude's permission policy, partial-turn persistence, or the TUI. Those are
migration gates, not assumed SDK properties.

Klaude's current `Agent._run` is about 1,700 lines inside a 5,868-line
`agent.py`; the CLI is 17,801 lines. A successful adapter could plausibly
replace 800–1,300 loop/lifecycle lines, while adding roughly 400–700 adapter
lines for Klaude-specific policy and events. The estimated net removal is
100–900 lines. This is an order-of-magnitude estimate from code boundaries,
not a measured diff. A real implementation must measure it before adoption.

## Executed checks

Installed `pydantic-ai-slim` 2.52.0 only in `/tmp/klaude-uv-cache`; no workspace
dependency or lockfile changed for this spike.

| Scenario | Isolated result | Klaude-specific gap |
| --- | --- | --- |
| Two async retrieval tools | Both dispatched; result contained both tool outputs | Model choice of tools was not tested; `TestModel` calls all tools |
| Streaming | Observed tool-call, tool-result, delta, and final events | Map events to Klaude's versioned lifecycle and TUI footer |
| Cancellation | `CancellationToken.cancel()` raised `RunCancelled`; waiting async tool's `finally` ran | Test actual Ollama socket cancellation and permission wait |
| Model switch | A second run accepted another model with prior history | Test actual provider state and context limits |
| Completed history | `ModelMessagesTypeAdapter` serialized tool results and restored them | Klaude must not persist arbitrary full tool bodies; use its bounded receipts and selective references |
| Sync tool adapter | Stalled in this host's Python 3.12 async executor teardown | Prefer async wrappers; separately test worker cleanup and shutdown |
| MCP | Slim package exposed MCP integration but required an optional `fastmcp` client | Keep Klaude's trust, OAuth, registry, and permission boundaries |
| Ollama | An `OllamaProvider` is available | No live model run was made; verify tool calling, options, streaming, and small-model behavior |

Pydantic AI can own model/tool turn iteration, validated function dispatch,
provider selection, run cancellation, and streaming event production if the
compatibility gates pass. Klaude should retain capability routing and
availability, local knowledge and web providers, MCP trust and OAuth,
permission decisions, dirty-worktree protection, session/lease storage,
source-use provenance, bounded result durability, and terminal presentation.
Follow-up resolution and correct source choice remain model-and-policy behavior;
the test runtime cannot prove them.

The next bounded adapter should expose one read-only local knowledge tool and
one web tool, enforce Klaude's permission/scope decisions before dispatch,
translate SDK events to existing `AgentEvent`s, and replay a saved interruption
with receipts. Run it against a local Ollama model and one cloud provider before
changing the production loop. Keep the existing loop as the comparison baseline.

## Reference implementation and licenses

`CLAUDE_EXAMPLES/src/QueryEngine.ts` shows a conversation-owned message list,
an explicit abort controller, permission wrapping, and ordered progress/result
persistence. Those patterns inform the proposed seams. No source from that file
was copied. The local reference tree has no license covering `src/QueryEngine.ts`;
its `system_prompts/LICENSE` applies to the separate prompt collection. The
official [Claude Code license](https://github.com/anthropics/claude-code/blob/main/LICENSE.md)
reserves rights, so substantial verbatim redistribution into MIT-licensed Klaude
is not justified by the evidence available. The older architecture review's
separation of loop, tools, context, persistence, and UI still fits the live code,
but its v0.1 package layout is historical context.

Pydantic AI is [MIT licensed](https://github.com/pydantic/pydantic-ai/blob/main/pyproject.toml).
Its [agent iteration](https://pydantic.dev/docs/ai/agents/),
[Ollama provider](https://pydantic.dev/docs/ai/models/ollama/), and
[MCP client](https://pydantic.dev/docs/ai/mcp/client/) are relevant APIs.
The [OpenAI Agents SDK streaming contract](https://openai.github.io/openai-agents-python/streaming/)
also has explicit cancellation and normalized resume state, but an OpenAI-first
model layer plus LiteLLM is a larger provider migration for Klaude. It remains
a comparison candidate, not this spike's chosen pilot.

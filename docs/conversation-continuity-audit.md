# Conversation continuity audit

## Scope and evidence

Inspected the 20 most recently active dialogue sessions in this checkout's
`.klaude/data/sessions.db`, ordered by their latest user/assistant timestamp:
111 user messages and 101 assistant messages. Read public dialogue, saved runtime
identities and public execution events with SQLite read-only connections. No
session content, saved runtime, preference, Skill receipt or model selection was
changed. Private summary metrics are in `/tmp/klaude-conversation-audit-20.json`;
the regression fixtures use synthetic dialogue instead of private transcripts.

Eight sessions contain context/memory-denial or redundant-clarification wording.
This is a screening count, not a claim that every such reply proves missing
history. Historical wire requests were not retained, so the exact payload that
caused each old answer cannot be reconstructed. Separate reproduced code faults
from interpretations of those answers.

| Session | Messages | Findings |
| --- | ---: | --- |
| `ec6ddd62173e4b2a9f95f9f120de480b` | 22 | Explicit meme Skill requests bypassed Agent orchestration for direct image generation; later capability/provider confusion and an explanatory question answered by a canned source receipt. |
| `49fba92f10ee4bbf82ad4e69686cd9c5` | 4 | Skill inventory and weather fetch worked; useful positive comparison. |
| `10eb0a1ddd91417f8e33a6eda1191838` | 4 | Described only Firecrawl tools while denying installed weather Skills. |
| `5c60ec9049834ac98f02918e68da4380` | 2 | Vague test prompt received verbose tool-oriented clarification; no preceding context to lose. |
| `0b56f0405c3045b78d769b68ce40661d` | 9 | Weather/Skill follow-ups turned into tool lists and redundant clarification; one recorded web search. |
| `5636104acd0a4741b53edf08b7a04c0d` | 4 | Weather capability denial and failure to resolve a short reference to available integrations. |
| `49ec6b8e130e40958a41fb5201adbd2c` | 6 | Numeric answer to the assistant's immediately preceding numbered choices was treated as context-free. |
| `dcb1c6bdb81e426c977db9159d20e21d` | 2 | Requested current workspace diff but asked the user to supply a diff; no tool execution recorded. |
| `c5db193176da4a88b021a67d66f7332b` | 4 | Workspace inspection and short project-name follow-up were not grounded in the workspace. |
| `aa02af0341a649f3911add90398a331e` | 43 | Generated-image history denied after a greeting; new-subject image follow-up lost context. Also distinct image-server failures, which are not evidence of chat-memory loss. |
| `2c6b2d4b9329429da268015f9c9be35c` | 2 | Single image request; no prior conversational context to lose. |
| `5db7f8ca6bea49c881a588ec9c73360b` | 2 | Single image request; no prior conversational context to lose. |
| `aef12669df3e4dd4a96e9eaf20abe9ac` | 2 | Single image request; no prior conversational context to lose. |
| `8543e540ee5d4658a4ba87bace953a85` | 5 | Short retry following research; recorded Firecrawl activity and a failed turn. Missing execution evidence cannot be reconstructed as successful research. |
| `06e6d025ca564a4592b1af0c30ff3ca8` | 67 | Long multi-topic/model session. SVG corrections and same-chat memory questions received unrelated Skill/search prose. Some earlier turns used correct workspace/search tools. |
| `1534824c39d44e43bf9b60ada6a87b95` | 19 | Earlier image pixels unavailable on a follow-up; separate unsupported image-profile failures and interrupted turns. Preserve distinctions between pixels, descriptions and dialogue. |
| `c8e9c54a2cd64ec3879878d7058499a6` | 2 | Single greeting; no preceding context to lose. |
| `88d6eac3f1bb4c9e8cbbe3202b2b3a1b` | 5 | Greetings produced irrelevant tool descriptions and grep activity; external tool vocabulary dominated replies. |
| `efc02e7db5654c0589bfc5e2c4fcd83e` | 2 | Workspace exploration routed toward unrelated external research, then reported inability to inspect. |
| `72a5b12acb8c4ac2abe339c8d2d963b4` | 6 | Diff/project questions received irrelevant MCP capability replies and nearly empty answers; credit-usage activity was unrelated to the task. |

## Reproduced faults and fixes

1. Browser startup supplied the entire external MCP inventory on every turn.
   The current registry contains 27 tools with about 54 KB of stored schema
   metadata. Small local context allocations could lose preceding turns while
   tool-specific vocabulary dominated the prompt. Browser routing now keeps
   external schemas lazy. Explicit named-server requests admit a bounded subset;
   other tools can be loaded using `discover_tools`. Loading never executes or
   authorizes a tool. Existing deny/ask/allow, exact-definition rechecks, scopes,
   disabled-tool settings and discovery budgets remain enforced. Browser built-in
   workspace/search/Skill tools stay available.
2. Gemini's text adapter selected only the first system message. The Agent stores
   extractive compaction recaps as later system messages, so this adapter silently
   discarded them. It now forwards all system messages, matching the native Gemini
   image adapter's existing treatment. Public dialogue and recap attribution remain
   intact; omitted tool results do not become evidence.
3. Recap prioritization could preserve many older user excerpts but omit the
   preceding assistant answer needed to interpret a short correction or numbered
   choice. The latest such pair is now prioritized alongside the initial objective.
4. Direct image generation in the application service could bypass explicitly
   requested installed Skill guidance. Such requests now enter the Agent path;
   known Skill names written with spaces also require `read_skill`. No scripts
   are automatically run, and Skill text cannot grant tool permissions.
5. Verbose Skill descriptions could consume the browser's inventory budget before
   later names appeared. Count and names now precede bounded description snippets.
6. The retrospective source shortcut also matched “Why did you use it?”, replacing
   a conversational explanation with a generic source-use receipt. Why/how
   explanations now go through normal dialogue; actual source-use questions retain
   their evidence-based path.
7. Browser prompt guidance explicitly distinguishes ongoing conversation, prior
   dialogue, compaction recaps, installed Skills, callable tools and fresh evidence.

No automatic model switches, larger local context defaults, mandatory web research,
arbitrary MCP execution, session rewriting or cross-session private-history injection
were added. Memory of another chat remains separate from this chat's supplied history.

## Validation and limits

Regression fixtures exercise short numbered choices, SVG corrections, generated
image references, new image subjects, restored sessions, large MCP inventories,
safe schema discovery, named-server permissions/rechecks, recap transmission,
requested Skill reads, inventory truncation and source-use explanation routing.
The Skill/image test uses the real application bridge and isolated image service,
asserting that no generation bypasses the requested guidance read.

Model answers are not guaranteed by payload correctness. A model may still produce
bad SVG geometry, ignore visible dialogue or mishandle a request; context windows
remain finite. Historical image-server outages and unsupported image profiles are
separate issues and are not claimed fixed by this continuity work. Existing image
history/modality regressions check that unavailable pixels are described honestly.

Changes take effect in a newly started host. Existing live sessions were not
restarted or modified during this audit. Validation results are recorded below.

- Isolated live `mistral:7b` smoke: the model remembered the synthetic project name
  AmberLake and its orange theme after a greeting; three requests, no tool calls,
  no errors. Context 8,192 and output limit 160; no cloud provider was used and
  no saved model choice changed. Evidence: `/tmp/klaude-continuity-live-smoke.json`.
- Browser application regression: two actual application worker turns with a
  large synthetic MCP inventory preserve the preceding numbered choices and
  keep external schemas out of the follow-up request. Saved transcript inspection
  agrees with the resulting response. This is a recording-runtime check, not a
  claim about arbitrary model output quality.
- Final focused suite: 366 tests passed across continuity, extractive compaction,
  capability routing, reliability repairs, provider runtimes, browser tools,
  conversational image actions, image history, application bridge and transcript
  replay. The additional browser worker-boundary regression passed separately.
- Ruff on all touched Python files, Python compilation and scoped diff whitespace
  checks passed. Full-repository tests were not run.
- Terminal compatibility follow-up: 51 selected command, Skill-discovery,
  provenance and compaction tests passed (849 unrelated cases deselected).

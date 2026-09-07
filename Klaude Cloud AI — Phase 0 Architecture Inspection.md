You are working on the **klaude-code** repository.

Before we implement Cloud AI support, I want you to inspect the **latest Klaude build** and understand exactly how the current model selection, Ollama integration, TUI, runtime, and agent loop work.

# IMPORTANT

For this task:

**DO NOT IMPLEMENT THE CLOUD PROVIDERS YET.**

Do not refactor files yet.

Do not add dependencies yet.

Do not modify `/model` yet.

Do not add OpenAI/Gemini code yet.

This is an architecture-inspection and implementation-planning pass only.

---

# 1. FIRST SYNC TO THE LATEST KLAUDE BUILD

Check the current Git state first.

Inspect:

```bash
git status
git branch --show-current
git remote -v
git log -5 --oneline
```

Protect local work.

If the working tree is clean and pulling is safe, update from the repository's current default working branch.

Do NOT destroy or overwrite uncommitted work.

Do NOT use:

```bash
git reset --hard
git clean -fd
```

or anything destructive.

If local changes prevent a safe pull, report that instead of discarding them.

The purpose is to make sure your analysis is based on the newest Klaude implementation.

---

# 2. UNDERSTAND THE CURRENT KLAUDE MODEL SYSTEM

Trace the implementation of:

```text
klaude chat
    ↓
TUI
    ↓
/model
    ↓
model picker
    ↓
reasoning-effort picker
    ↓
Agent
    ↓
Ollama
    ↓
streaming
    ↓
tool calls
    ↓
Klaude tools
```

Find exactly where each responsibility currently lives.

Inspect at minimum:

- `AGENTS.md`
- CLI entry point
- `apps/cli/src/klaude_cli/main.py`
- current `/model` implementation
- current `/models` implementation
- inline picker implementation
- picker rendering
- picker scrolling
- picker cancellation
- current model persistence
- reasoning-effort persistence
- chat preferences
- session metadata
- status telemetry
- model telemetry
- Agent construction
- `packages/core/src/klaude_core/agent.py`
- `packages/core/src/klaude_core/ollama.py`
- `packages/core/src/klaude_core/config.py`
- current model presets
- Ollama configuration
- model resolution
- streaming
- tool calling
- cancellation
- tests involving `/model`, `/models`, Agent, Ollama, and TUI
- relevant README/help documentation

Do not assume the architecture from an older Klaude build.

Use what exists now.

---

# 3. PAY SPECIAL ATTENTION TO THE NEW TUI

The latest Klaude has recently received major TUI improvements.

Preserve those design decisions.

The existing `/model` flow currently uses an inline arrow-key picker and then an effort picker.

Understand exactly how this works before proposing changes.

Do NOT propose replacing it with:

- a separate screen
- an external prompt
- a crude numbered menu
- a different TUI framework
- a blocking input loop

Cloud model support must extend the existing Klaude design.

---

# 4. DESIRED MODEL HIERARCHY

The future `/model` picker will no longer be an Ollama-only model picker.

It must represent **all models available to Klaude**.

The top-level categories must be:

```text
Cloud
Local
```

**Cloud comes first.**

Conceptually:

```text
Cloud
  OpenAI
    ...
  Google
    ...

Local
  Ollama
    ...
```

The exact visual formatting must follow Klaude's current inline picker design.

Do not implement this yet.

Instead, determine the cleanest way to represent hierarchical/grouped model options in the current picker architecture.

---

# 5. `/model` IS THE MAIN MODEL SELECTOR

The desired future behavior is:

```text
/model
```

opens the normal Klaude inline model picker.

It shows **both Cloud and Local models**.

Cloud should be at the top.

Example concept only:

```text
Select model

Cloud

  OpenAI
    ChatGPT / Codex
      GPT-...
      GPT-...

    OpenAI API
      GPT-...
      GPT-...

  Google
    Gemini API
      Gemini ...
      Gemini ...

    Gemini CLI
      Gemini ...

Local

  Ollama
    gemma...
    gpt-oss...
    qwen...
```

Do not blindly copy this formatting.

Inspect the existing picker and determine how headings and grouping can be introduced without ruining:

- keyboard navigation
- selected-row highlighting
- scrolling
- cancellation
- model search/resolution
- active-model indication
- compact terminal rendering

Category headings should preferably not behave like selectable models.

---

# 6. DIRECT MODEL SWITCHING MUST STILL WORK

Current Klaude supports:

```text
/model NAME
```

That behavior must survive.

Determine how direct model selection should work once model names can exist across multiple providers.

For example, potential ambiguity:

```text
/model gemini-...
```

or a model with the same identifier exposed by more than one backend.

Investigate whether Klaude should eventually support a canonical internal identity such as:

```text
provider:model
```

or:

```text
backend/provider/model
```

while keeping convenient short-name resolution when unambiguous.

DO NOT choose a complicated syntax just because it is theoretically clean.

Study Klaude's current `_resolve_model_name` behavior and recommend the smallest compatible extension.

---

# 7. IMPORTANT DISTINCTION: MODEL VS PROVIDER

Do not make users switch providers separately just to choose a model.

I want `/model` to be the primary selector.

For example, selecting:

```text
Cloud
  OpenAI
    ChatGPT / Codex
      <model>
```

should naturally imply the corresponding backend.

Similarly:

```text
Local
  Ollama
    qwen...
```

implies Ollama.

Internally, however, Klaude should know both:

```text
provider/backend
model
```

The UI should not require:

```text
/provider openai
/model ...
```

as a normal workflow.

Provider selection should follow from model selection.

---

# 8. DESIRED PARENT CATEGORIES

Use these exact parent concepts:

```text
Cloud
Local
```

Do not use:

```text
Remote
Online
Hosted
External
```

as the primary user-facing categories.

Under them:

```text
Cloud
├── OpenAI
└── Google

Local
└── Ollama
```

Further backend distinctions may exist internally.

For example:

```text
Cloud
└── OpenAI
    ├── ChatGPT / Codex
    └── OpenAI API
```

and:

```text
Cloud
└── Google
    ├── Gemini API
    └── Gemini CLI
```

But first determine whether exposing all of these backend distinctions directly in the model picker improves or hurts the current Klaude UX.

Report your recommendation.

---

# 9. CLOUD AI TARGETS

The planned Cloud integrations are:

## OpenAI

### A. OpenAI API

Official OpenAI API using:

```text
OPENAI_API_KEY
```

and the current OpenAI API.

This is separate from ChatGPT/Codex subscription authentication.

### B. ChatGPT / Codex

Official OpenAI Codex integration.

Authentication must use the official device-code flow:

```text
https://auth.openai.com/codex/device

XXXX-XXXX
```

Klaude displays the URL and code.

The user completes authentication themselves.

No automated web login.

Current official OpenAI Codex Python SDK:

```text
openai-codex
```

The SDK currently exposes:

```python
from openai_codex import Codex, AsyncCodex
```

and device-code auth through:

```python
login_chatgpt_device_code()
```

It also exposes model discovery through the Codex SDK.

Current official APIs include concepts such as:

```text
models()
account()
logout()
login_chatgpt_device_code()
verification_url
user_code
wait()
cancel()
```

Verify these against the current official SDK before implementation.

Because Klaude has an interactive/event-driven runtime, investigate whether `AsyncCodex` fits the architecture better than the synchronous client.

Do not implement it yet.

---

# 10. GOOGLE TARGETS

## A. Gemini API

Use Google's current official Python SDK:

```text
google-genai
```

with:

```python
from google import genai
```

Do NOT plan new work around the old:

```text
google-generativeai
```

package.

As of September 2026, Google's current recommended Gemini API interface for new projects is the **Interactions API**.

The Interactions API became Google's default interface in June 2026.

It supports streaming events and function/tool-call workflows.

The original `generateContent` API remains supported but is now considered legacy for new projects.

Investigate which current API maps cleanly to Klaude's existing:

```text
messages
streaming
tools
tool results
reasoning
usage
cancellation
```

without making Gemini itself the controller.

Klaude should remain the controller.

---

## B. Gemini CLI

Gemini CLI officially supports headless execution.

Current concepts include:

```bash
gemini -p "..."
```

and:

```bash
gemini -p "..." --output-format stream-json
```

The headless JSONL stream can contain events such as:

```text
init
message
tool_use
tool_result
error
result
```

Gemini CLI headless mode can reuse authentication that was already configured externally.

Klaude itself will **not perform Google's web login**.

If Gemini CLI is unauthenticated, Klaude should eventually instruct the user to authenticate it externally or configure a supported API/Vertex credential.

Do not implement this yet.

---

# 11. ABSOLUTE WEB-AUTH RULE

Klaude does **not** perform web logins.

Do not plan:

- Playwright
- Selenium
- browser automation
- browser session extraction
- browser cookie reuse
- ChatGPT webpage scraping
- Gemini webpage scraping
- unofficial consumer APIs
- browser profile inspection

For OpenAI ChatGPT/Codex, the allowed flow is:

```text
Klaude
    ↓
official Codex device-code API
    ↓
display auth.openai.com/codex/device
    ↓
display XXXX-XXXX
    ↓
user authenticates themselves
```

Klaude does not control the browser.

For Gemini CLI, Klaude does not initiate Google's browser OAuth flow.

---

# 12. MODEL DISCOVERY

One of the biggest things I want you to investigate is **dynamic model discovery**.

We should avoid maintaining giant hardcoded cloud-model lists if the official backend can provide them.

Current local behavior:

```text
Ollama
→ list installed models
```

Investigate equivalent supported mechanisms for:

```text
OpenAI API
ChatGPT / Codex
Gemini API
Gemini CLI
```

Current Codex Python SDK exposes:

```python
codex.models(...)
```

which should be investigated as the model source for ChatGPT/Codex.

Investigate the official OpenAI API model-list mechanism for OpenAI API.

Investigate Gemini's current official model-list mechanism.

Investigate whether Gemini CLI exposes reliable model discovery suitable for Klaude.

Report:

- what is dynamically discoverable
- what requires configuration
- what should be cached
- what should be refreshed
- what happens offline
- what happens when authentication is missing
- whether unavailable Cloud sources should simply disappear or appear disabled

Do not hardcode today's model names into the architecture.

---

# 13. `/model` SHOULD SHOW CLOUD AT THE TOP

This requirement is explicit.

The future picker order is:

```text
Cloud
...
Local
...
```

NOT:

```text
Local
...
Cloud
...
```

Even though Klaude remains local-first architecturally, Cloud models should be easier to see in the model selector.

Inside categories, determine a sensible stable ordering.

For example:

```text
Cloud
  OpenAI
  Google

Local
  Ollama
```

Models within a provider can follow the appropriate existing sorting behavior unless provider metadata gives us a better order.

---

# 14. ACTIVE MODEL INDICATION

Current Klaude marks the selected model.

Determine how active selection should work with grouped models.

The active identity should eventually include enough information to distinguish:

```text
model name
provider/backend
Local vs Cloud
```

For example, status may eventually display something conceptually like:

```text
Model: GPT-...
Cloud · OpenAI · ChatGPT/Codex
```

or:

```text
Model: qwen...
Local · Ollama
```

Do not redesign the status line yet.

Just identify every location that currently assumes:

```text
agent.model == Ollama model name
```

and report what needs generalization.

---

# 15. REASONING EFFORT

The current `/model` flow proceeds into the reasoning-effort picker.

Inspect this carefully.

Currently Ollama has model-specific thinking behavior and options.

Cloud providers expose reasoning differently.

Examples may include:

```text
OpenAI reasoning effort
Codex reasoning effort
Gemini thinking configuration
Ollama think
```

Determine how Klaude can preserve its single:

```text
/effort
```

user experience while translating the chosen Klaude effort into provider-specific settings.

The user-facing Klaude levels currently include:

```text
auto
off
low
medium
high
```

Do not assume every provider supports every level.

Recommend how unsupported effort levels should behave.

Do not implement it yet.

---

# 16. KLAUDE MUST REMAIN THE CONTROLLER

This is critical.

For native APIs, desired architecture is approximately:

```text
User
  ↓
Klaude TUI
  ↓
Klaude Agent
  ↓
Klaude context / memory / tools
  ↓
Model backend
  ↓
Cloud model
```

The model provider should not bypass Klaude's:

- permissions
- tools
- local RAG
- memory
- sessions
- web system
- project context
- cancellation
- TUI
- status
- tool loop

Pay particular attention to:

```text
Codex
Gemini CLI
```

because both can act as full agents themselves.

We do NOT want accidental double orchestration:

```text
Klaude Agent
    ↓
another autonomous coding agent
    ↓
its own shell/files/tools
```

Investigate how those integrations can be constrained or represented safely.

If an external-agent backend cannot behave cleanly like a normal model provider, say so.

Do not hide that architectural difference.

---

# 17. CURRENT OLLAMA COUPLING

Find every meaningful place where Klaude currently assumes the selected model is an Ollama model.

Search for things such as:

```text
Ollama
agent.ollama
ollama.list_models
ollama_options
ollama_think
ollama_code_options
ollama_code_think
OLLAMA_HOST
ollama_url
/models
/model
/restart
/stop
```

Categorize each occurrence:

```text
A. Truly Ollama-specific — keep it local/Ollama-specific
B. Actually generic model/runtime behavior — should eventually be generalized
C. UI wording only
D. Test fixture only
E. Knowledge/embed model path — should probably remain Ollama/local
```

This distinction matters.

For example, Klaude's embedding model used by local knowledge does NOT necessarily need to change just because the active chat model becomes Cloud.

Do not accidentally convert local embedding/RAG infrastructure into cloud-dependent infrastructure.

---

# 18. LOCAL MUST CONTINUE WORKING WITHOUT CLOUD

Cloud integration is optional.

Klaude must still work with:

```text
Local
  Ollama
```

when:

- there is no internet
- OpenAI credentials do not exist
- Gemini credentials do not exist
- Codex is not authenticated
- Gemini CLI is not installed

No Cloud dependency should prevent local startup.

Determine where optional dependency boundaries should eventually live.

---

# 19. INSPECT `/models` TOO

The immediate UI requirement is primarily `/model`.

However, also inspect:

```text
/models
```

and:

```text
klaude models
```

because they currently describe/list Ollama models.

Do NOT change them in this task.

Report whether, once Cloud support exists, they should:

### Option A

remain specifically informational about Ollama/local installed models,

or:

### Option B

become general model listings containing:

```text
Cloud
Local
```

Explain which behavior is more consistent with Klaude's current command semantics.

I want `/model` to definitely become the unified selector.

Do not assume `/models` must automatically have identical behavior.

---

# 20. CURRENT HELP SYSTEM

The help output is currently structured approximately as:

```text
Usage: klaude [OPTIONS] COMMAND [ARGS]...

OPTIONS
...

CLI COMMANDS
...

DOCS COMMANDS
...

CHAT COMMANDS
...
```

Current chat commands include:

```text
/models
/model
/effort
```

Klaude has centralized command metadata and tests keeping:

```text
/help
/
focused help
unknown-command suggestions
```

synchronized.

Inspect this architecture.

Any future model/provider changes must update command descriptions consistently.

For example, current wording such as:

```text
/models
List installed Ollama models and mark the active model.
```

and:

```text
/model NAME
Select an installed Ollama model...
```

will no longer be universally correct once Cloud support lands.

Identify every user-facing string that will need updating.

Do not change it yet.

---

# 21. CONFIGURATION

Inspect the current config system before designing Cloud config.

Klaude already has:

- `config.toml`
- `.env` loading
- `KLAUDE_*` paths
- Ollama config
- web provider credentials
- existing `GEMINI_API_KEY` usage for web search

Important:

The existing:

```text
GEMINI_API_KEY
```

may already be used by Klaude's Google web-search provider.

Determine whether the same environment variable can safely be reused for the Gemini model API integration.

Do not create duplicate secrets unnecessarily.

OpenAI API should eventually use:

```text
OPENAI_API_KEY
```

Codex device authentication should remain owned by the official Codex runtime/SDK.

Do not manually store ChatGPT access/refresh tokens.

---

# 22. SESSION AND PREFERENCE PERSISTENCE

Current `/model` selection persists for subsequent chats.

Inspect exactly how.

Determine what must eventually be persisted instead of only:

```text
model = "qwen..."
```

Possibly something conceptually like:

```text
source = cloud/local
provider = openai/google/ollama
backend = codex/openai-api/gemini-api/gemini-cli/ollama
model = ...
```

Do not over-design this.

Recommend the smallest durable model identity needed.

Also consider old existing preferences containing only an Ollama model name.

Backward compatibility matters.

An existing user's:

```text
chat-preferences.json
```

must not become unusable after the Cloud upgrade.

---

# 23. CANCELLATION AND SWITCHING

Current model switching has safeguards around active responses and pending tools.

Inspect those carefully.

Cloud switching must eventually preserve the same semantics.

Determine how cancellation currently works for:

```text
Ollama HTTP streaming
pending permission requests
active tool calls
queued turns
/model switching
```

Then report what abstractions will be needed for:

```text
HTTP cloud stream cancellation
Codex turn interruption
Gemini stream cancellation
Gemini CLI subprocess termination
```

Do not implement them yet.

---

# 24. TELEMETRY / CONTEXT WINDOW

The current TUI reads model/context information from Ollama-specific metadata.

Inspect:

```text
context window
prompt tokens
completion tokens
reasoning effort
model name
runtime state
```

Determine which fields are truly generic and should eventually move behind a model/runtime abstraction.

Cloud providers expose usage differently.

Do not let provider-specific response structures leak all over the TUI.

Again: report only for now.

---

# 25. DO NOT OVER-ENGINEER

I do not want an enormous generic plugin framework just to support four/five backends.

But I also do not want this:

```python
if provider == "ollama":
    ...
elif provider == "openai":
    ...
elif provider == "gemini":
    ...
```

repeated throughout:

```text
Agent
TUI
sessions
status
/model
tools
streaming
```

Find the smallest useful provider/model abstraction based on the CURRENT code.

The existing `Agent` module explicitly describes itself as the seam for future model/runtime swaps.

Use that fact in your analysis.

---

# 26. EXPECTED FUTURE MODEL STRUCTURE

Evaluate a lightweight internal model descriptor resembling this concept:

```python
ModelInfo(
    id=...,
    display_name=...,
    source=...,       # cloud | local
    provider=...,     # openai | google | ollama
    backend=...,      # codex | openai-api | gemini-api | gemini-cli | ollama
    capabilities=...,
)
```

This is only a concept.

Do not implement it merely because this prompt shows it.

Determine whether Klaude actually needs all those fields.

The final architecture should be as small as possible while still solving:

- grouped `/model`
- direct `/model NAME`
- provider routing
- model discovery
- effort mapping
- status
- session persistence
- backend switching

---

# 27. VERIFY CURRENT OFFICIAL CLOUD INFORMATION

Before giving your plan, verify the latest official documentation.

Prioritize:

## OpenAI

- official OpenAI Codex repository/docs
- official OpenAI developer documentation

Verify:

```text
openai-codex
AsyncCodex
login_chatgpt_device_code()
models()
Responses API
```

## Google

- official Gemini API docs
- official Gemini CLI docs/repository

Verify:

```text
google-genai
Interactions API
streaming
function calling
model listing
Gemini CLI headless mode
--output-format stream-json
headless authentication behavior
```

If anything differs from this prompt, report the newer official behavior.

Do not use random tutorials when official documentation exists.

---

# 28. NO CODE CHANGES IN THIS PASS

Again:

**DO NOT IMPLEMENT ANYTHING YET.**

I want a concrete report first.

No dependency changes.

No refactor.

No new provider files.

No new auth flow.

No TUI modifications.

No config modification.

No tests changed.

Only inspect, reason, and report.

---

# FINAL REPORT

Return a structured report with these sections:

## 1. Repository State

Include:

```text
branch
HEAD commit
whether pull/update was performed
working-tree status
```

## 2. Current Model Flow

Trace:

```text
/model
→ picker
→ selected model
→ preference persistence
→ Agent
→ Ollama
→ streaming
```

with exact relevant files/functions.

## 3. Current Ollama Coupling

List each important coupling and categorize it:

```text
generic behavior that should change
Ollama-specific behavior that should remain
```

## 4. Current `/model` Architecture

Explain:

- option generation
- sorting
- keyboard navigation
- highlighting
- scrolling
- cancellation
- direct `/model NAME`
- effort-picker transition
- persistence

## 5. Proposed Model Hierarchy

Show exactly how you recommend representing:

```text
Cloud
  OpenAI
  Google

Local
  Ollama
```

in Klaude's existing picker.

Cloud must be first.

## 6. Proposed Internal Model Identity

Recommend the minimum fields necessary to distinguish:

```text
Cloud/OpenAI/Codex
Cloud/OpenAI/API
Cloud/Google/Gemini API
Cloud/Google/Gemini CLI
Local/Ollama
```

while keeping `/model NAME` convenient.

## 7. Provider Boundary

Explain what minimal abstraction should replace direct Ollama assumptions.

Do not write the implementation yet.

## 8. Klaude Agent Ownership

Explain how:

```text
OpenAI API
Gemini API
Codex
Gemini CLI
```

can integrate without bypassing Klaude's own agent/tool/permission system.

Call out any backend that cannot safely act like a normal model provider.

## 9. Model Discovery

For each backend:

```text
Ollama
OpenAI API
Codex
Gemini API
Gemini CLI
```

state how models can be discovered and what auth is required.

## 10. `/models` Recommendation

Say whether:

```text
/models
klaude models
```

should remain Local/Ollama informational commands or become unified Cloud + Local listings.

Explain why.

## 11. Reasoning Effort

Explain how current:

```text
auto
off
low
medium
high
```

could map across the different backends.

## 12. Session / Preference Migration

Explain how existing Ollama-only preferences can remain backwards compatible.

## 13. TUI Impact

List the smallest changes needed to make the current picker support:

```text
Cloud
Local
```

without replacing the current TUI design.

## 14. Files That Would Need Changes

List likely files, but DO NOT modify them.

For each file state why.

## 15. Tests That Will Need Changes

Identify existing tests and new tests required.

## 16. Recommended Implementation Order

Give a staged implementation order.

Prefer something like:

```text
Phase 1 — model/provider abstraction
Phase 2 — grouped unified /model UI
Phase 3 — OpenAI API
Phase 4 — Gemini API
Phase 5 — Codex device-code integration
Phase 6 — Gemini CLI bridge
Phase 7 — docs/doctor/status polish
```

Change the ordering if the current architecture suggests something better.

## 17. Risks / Open Questions

Only include genuine unresolved issues.

Do not turn settled requirements into questions.

---

The goal of this pass is to understand **how Klaude works today** so Cloud AI becomes a native extension of the current architecture rather than a bolt-on rewrite.

The required user-facing model hierarchy is:

```text
Cloud
...
Local
...
```

with **Cloud first**, and `/model` as the unified model selector.
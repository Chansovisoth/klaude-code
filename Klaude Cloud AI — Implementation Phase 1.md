You are continuing work on **klaude-code** after completing the Phase 0 Cloud AI architecture inspection.

Use the findings from that inspection as authoritative context for the current repository.

Now implement the first production-ready Cloud AI foundation.

# GOAL

Add a proper model/runtime abstraction to Klaude and turn `/model` into the unified model selector for:

```text
Cloud
Local
```

with **Cloud always shown first**.

This phase should implement:

1. Generic chat-model identity
2. Generic model runtime/provider boundary
3. Ollama adapted to that boundary without regressions
4. Unified `/model` picker with Cloud + Local grouping
5. OpenAI API support
6. Gemini API support
7. Dynamic cloud model discovery
8. Provider-aware reasoning effort
9. Provider-aware telemetry/cancellation
10. Backward-compatible model preference persistence
11. Tests
12. Help/status/doctor/documentation updates necessary for these changes

Do **NOT** implement Gemini CLI or ChatGPT/Codex as autonomous-agent bridges yet.

Those will be a later phase because both runtimes can introduce a second tool/agent loop.

However, design the abstraction so they can be added later without another major refactor.

---

# 1. START FROM THE CURRENT REPOSITORY

Before editing:

```bash
git status
git branch --show-current
git log -3 --oneline
```

Protect local files and existing untracked files.

Do not destroy local work.

Use the current implementation discovered during Phase 0 rather than recreating the architecture from assumptions.

Important Phase 0 findings:

- `Agent` currently directly owns an `Ollama` instance.
- `/model` currently resolves models through `ollama.list_models()`.
- `/model` already uses the correct inline TUI picker.
- The picker already supports non-selectable section rows.
- `/models` and `klaude models` should remain Ollama/local diagnostics.
- Local embeddings and Knowledge indexing should remain Ollama-backed.
- Cloud chat model selection must not make local RAG dependent on Cloud.
- The existing TUI, picker scrolling, highlighting, cancellation, effort picker, and chat persistence should be extended rather than replaced.

---

# 2. REQUIRED USER-FACING MODEL HIERARCHY

The unified `/model` picker must use these exact top-level categories:

```text
Cloud
Local
```

Order:

```text
Cloud
...
Local
...
```

**Cloud must always appear before Local.**

The intended structure is:

```text
Cloud

  OpenAI

    OpenAI API
      <available OpenAI API models>

  Google

    Gemini API
      <available Gemini API models>

Local

  Ollama
      <installed Ollama models>
```

Do not add a `/provider` workflow.

The user selects a model through `/model`.

Selecting the model automatically selects the corresponding backend.

Conceptually:

```text
/model
   ↓
model row
   ↓
backend + model identity
```

not:

```text
/provider
/model
```

---

# 3. KEEP `/models` LOCAL/OLLAMA-SPECIFIC

Do NOT turn `/models` into the unified Cloud/Local selector.

Keep:

```text
/models
```

and:

```text
klaude models
```

focused on installed local Ollama models and Klaude's local model role assignments.

That existing diagnostic meaning is useful.

The unified selector is:

```text
/model
```

Update wording where necessary so the distinction is clear.

Example semantics:

```text
/models
List installed local Ollama models and mark the active one when applicable.

/model
Select an available Cloud or Local chat model.
```

Follow the project's centralized command metadata rules so:

```text
/help
/
focused help
unknown-command suggestions
```

remain synchronized.

---

# 4. INTRODUCE A SMALL MODEL DESCRIPTOR

Implement a lightweight canonical model identity.

Prefer something approximately like:

```python
@dataclass(frozen=True)
class ModelInfo:
    backend: str
    model_id: str
    display_name: str
    capabilities: ModelCapabilities
```

Do not blindly use this exact shape if a cleaner equivalent fits the repository.

Do NOT persist redundant properties if they can safely derive from `backend`.

For example, backend registry metadata may derive:

```text
backend: ollama
source: Local
provider: Ollama

backend: openai_api
source: Cloud
provider: OpenAI

backend: gemini_api
source: Cloud
provider: Google
```

Possible canonical refs:

```text
ollama/qwen3.5:9b
openai_api/gpt-...
gemini_api/gemini-...
```

The exact separator may differ, but it must be:

- stable
- human-readable enough for CLI usage
- unambiguous
- backwards compatible with existing bare Ollama names

Do not create UUIDs for models.

---

# 5. DIRECT `/model NAME` MUST REMAIN CONVENIENT

Current behavior:

```text
/model NAME
```

supports:

1. exact match
2. unique prefix
3. unique substring

Preserve this UX across all model backends.

Resolution should search available models.

Examples:

```text
/model qwen3.5:9b
```

should resolve directly if unique.

```text
/model gemini-...
```

should resolve if only one model matches.

If the same or similar identifier is ambiguous across backends, do not guess.

Show the matching candidates and require a qualified ref such as:

```text
/model openai_api/<model>
```

or:

```text
/model gemini_api/<model>
```

Use the chosen canonical syntax consistently.

Do NOT silently pick whichever provider appears first.

---

# 6. GENERIC MODEL RUNTIME BOUNDARY

The major architectural change is to stop making `Agent` depend directly on `Ollama`.

Introduce the smallest useful runtime abstraction.

It should cover what the Klaude Agent actually needs.

Conceptually:

```python
class ModelRuntime(Protocol):
    backend: str

    def list_models(...) -> list[ModelInfo]:
        ...

    def stream_turn(...):
        ...

    def cancel_active(...):
        ...

    def capabilities(...):
        ...
```

Adjust for async/sync design based on the current codebase.

Do not build a large generic plugin system.

The runtime boundary should primarily own:

- model discovery
- provider request serialization
- provider response parsing
- streaming
- tool-call translation
- usage metadata
- context metadata
- active-request cancellation
- backend-specific reasoning configuration

The Klaude `Agent` must continue owning:

- conversation history
- system prompt
- project context
- memory
- RAG
- Web
- available Klaude tools
- PermissionGate
- tool execution
- tool-loop continuation
- safety limits
- retries at the agent level where appropriate
- queue behavior
- sessions
- UI status events

---

# 7. NORMALIZE MODEL EVENTS

Provider-specific SDK objects should not leak into:

```text
Agent
TUI
sessions
status
```

Create or extend a normalized model-response/event representation.

It should support at minimum:

```text
text delta
reasoning delta when available
tool call
tool-call arguments
usage
context information when available
completion
error
```

Use the existing Agent event architecture where possible.

Do NOT unnecessarily create two competing event systems.

Provider translation belongs at the runtime boundary.

Conceptually:

```text
OpenAI event
    ↓
OpenAIRuntime
    ↓
Klaude model event

Gemini event
    ↓
GeminiRuntime
    ↓
Klaude model event

Ollama event
    ↓
OllamaRuntime
    ↓
Klaude model event
```

---

# 8. ADAPT OLLAMA FIRST

Before adding Cloud providers, migrate current Ollama chat behavior onto the new runtime boundary.

Existing Ollama behavior must remain functionally equivalent.

Preserve:

- chat streaming
- non-streaming fallback where currently used
- tool calls
- malformed tool recovery
- cancellation
- GPU/CPU recovery behavior
- reasoning configuration
- current context options
- telemetry
- active model selection
- existing tests

Do not move these local-only settings into generic Cloud configuration:

```text
num_ctx
num_thread
num_gpu
OLLAMA_HOST
GPU/CPU runtime preference
CUDA handling
```

Those remain Ollama-specific.

---

# 9. DO NOT GENERALIZE LOCAL EMBEDDINGS

This requirement is strict.

Klaude's local Knowledge/RAG system should continue using Ollama for embeddings.

Selecting:

```text
Cloud
  OpenAI
```

or:

```text
Cloud
  Google
```

must NOT cause Knowledge indexing or retrieval embeddings to move to Cloud.

Keep the existing local path:

```text
Knowledge
   ↓
Ollama embedding model
```

independent from:

```text
Chat Agent
   ↓
selected chat runtime
```

Add regression tests proving this.

---

# 10. OPENAI API BACKEND

Implement native OpenAI API support.

Authentication:

```text
OPENAI_API_KEY
```

Use the official OpenAI Python SDK.

Use the current **Responses API** for new implementation.

Do not make Chat Completions the new primary path.

Verify the latest official OpenAI documentation while implementing.

## Klaude owns tools

Expose Klaude's existing tool definitions to OpenAI as function tools.

Do NOT automatically enable provider-hosted tools such as:

- OpenAI web search
- shell
- computer use
- hosted file search
- provider-side coding agent tools

unless an existing Klaude feature explicitly calls for them.

The correct loop remains:

```text
OpenAI model
    ↓
requests Klaude tool
    ↓
Klaude PermissionGate
    ↓
Klaude tool executes
    ↓
tool result
    ↓
OpenAI model continues
```

---

# 11. OPENAI MODEL DISCOVERY

Use the official OpenAI model-list API.

Do not hardcode today's OpenAI model catalog.

Retrieve models dynamically when:

```text
OPENAI_API_KEY
```

is configured.

Filter obviously unusable model classes where necessary.

For example, `/model` should not become polluted with models that cannot perform the required conversational task.

Base filtering on official metadata/capability knowledge where available.

Do not rely on giant hardcoded allowlists.

If the API cannot provide enough capability metadata, implement a small defensible filtering rule and document it.

---

# 12. GEMINI API BACKEND

Implement native Gemini API support using:

```text
google-genai
```

Import from:

```python
from google import genai
```

Do NOT introduce new code using the obsolete:

```text
google-generativeai
```

package.

Verify Google's current official recommendation at implementation time.

As of the Phase 0 research, the Gemini **Interactions API** is the recommended new API.

Prefer it when it correctly supports Klaude's requirements.

Required capabilities:

- streaming
- tool/function calls
- function results
- multi-turn continuation
- thinking/reasoning where supported
- usage metadata
- cancellation behavior
- model discovery

If the current official Gemini API has a limitation that makes another `google-genai` API more appropriate for a specific required capability, use the supported approach and document why.

Do not choose an API based solely on naming/newness.

---

# 13. DISABLE GEMINI AUTOMATIC TOOL EXECUTION

Klaude must execute its own tools.

Do not let Google's SDK automatically call Python functions or otherwise execute provider-side tools.

Gemini should emit a function request.

Klaude then handles:

```text
Gemini
  ↓
function call
  ↓
Klaude canonical tool call
  ↓
PermissionGate
  ↓
Klaude tool
  ↓
function result
  ↓
Gemini
```

This is critical.

---

# 14. GEMINI MODEL DISCOVERY

Use the current official Gemini model-list API through `google-genai`.

Do not hardcode a fixed model catalog.

Filter model results so `/model` includes models appropriate for Klaude chat/tool usage.

Where available, use Gemini model metadata such as:

- supported generation methods
- context/token information
- model capabilities

Do not list embedding-only models as normal Klaude chat models.

---

# 15. GEMINI KEY REUSE

Klaude already supports:

```text
GEMINI_API_KEY
```

for its Google Web provider.

Reuse the same environment variable for Gemini chat API support.

Do not introduce:

```text
GEMINI_MODEL_API_KEY
GOOGLE_GEMINI_CHAT_KEY
```

unless an official API requires something different.

Make documentation clear that the same credential may therefore be used by:

```text
Google Web provider
Gemini chat models
```

and Cloud quota/billing may be shared.

Never log the actual key.

---

# 16. CLOUD MODEL DISCOVERY UX

Cloud discovery must degrade gracefully.

Possible states:

```text
Cloud

  OpenAI
    OpenAI API
      GPT-...
      GPT-...

  Google
    Gemini API
      Gemini ...
      Gemini ...

Local

  Ollama
    qwen...
```

If an API key is missing:

```text
Cloud

  OpenAI
    OpenAI API
      API key not configured

  Google
    Gemini API
      API key not configured

Local
...
```

Disabled/status rows should not be selectable.

Do not crash.

Do not block Klaude startup.

Do not require internet just to enter chat with Ollama.

If model discovery temporarily fails but a recent safe cached list exists, using cached metadata is acceptable.

Keep cache behavior small and explicit.

Do not create a complex synchronization subsystem.

---

# 17. OPTIONAL CLOUD DEPENDENCIES

Local Klaude should still work without Cloud dependencies.

Evaluate whether:

```text
openai
google-genai
```

should be optional package extras.

For example conceptually:

```text
klaude[openai]
klaude[gemini]
klaude[cloud]
```

Only do this if it fits the current package structure cleanly.

Regardless of packaging approach:

```text
import klaude
klaude chat
```

with Ollama must not fail just because an optional Cloud SDK is unavailable.

An unavailable backend should report something actionable like:

```text
OpenAI API support is not installed.
```

not a startup traceback.

---

# 18. UNIFIED `/model` PICKER

Extend the existing inline picker.

Do NOT replace it.

Use existing section-heading support.

The picker should conceptually contain data resembling:

```text
section: Cloud
section: OpenAI
section: OpenAI API
model
model

section: Google
section: Gemini API
model
model

section: Local
section: Ollama
model
model
```

Only model rows are selectable.

Ensure:

- Up/Down skip headings
- PageUp/PageDown continue working
- scroll centering works
- active-model marker works
- disabled provider-status rows cannot be selected
- Escape cancels
- model selection still enters effort selection
- cancelling effort restores the prior model/runtime
- Enter cannot select a heading
- terminal resizing/truncation remains correct

---

# 19. ACTIVE MODEL IDENTITY

Stop comparing only:

```python
agent.model == model_name
```

where that would become ambiguous.

The active model needs a canonical backend + model identity.

TUI may display only the friendly model name where space is tight.

Where useful, status can show:

```text
GPT-...
Cloud · OpenAI API
```

or:

```text
qwen3.5:9b
Local · Ollama
```

Do not clutter every line with provider metadata.

Use backend information where it aids disambiguation.

---

# 20. CHAT PREFERENCE MIGRATION

Existing Klaude users may have:

```json
{
  "last_model": "qwen3.5:9b"
}
```

Do not break this.

Migration behavior:

1. If a new canonical model reference exists, prefer it.
2. If only old `last_model` exists, interpret it as an Ollama model.
3. Continue functioning even if the remembered model is currently unavailable.
4. On successful new model selection, persist the canonical identity.
5. Do not rewrite unrelated preferences.

Use the project's existing chat-preferences system.

Do not introduce another preference file.

---

# 21. MODEL SWITCHING MUST KEEP CONVERSATION

Current `/model` changes model while preserving the current chat history.

Keep that behavior.

Switching:

```text
Ollama
→ OpenAI
→ Gemini
→ Ollama
```

should not clear the conversation.

However, ensure history is converted into the canonical message format required by each runtime.

Do not persist vendor SDK objects in Klaude session history.

Klaude's session format should remain provider-neutral.

---

# 22. REASONING EFFORT

Preserve Klaude's existing user-facing abstraction:

```text
auto
off
low
medium
high
```

Do not create separate user commands such as:

```text
/openai-effort
/gemini-thinking
```

Each runtime translates Klaude effort into backend-specific configuration.

Implement capability-aware behavior.

Preferred rule:

```text
auto
→ provider/backend default
```

Supported explicit level:

```text
low/medium/high
→ corresponding backend setting
```

Unsupported explicit level:

```text
show a clear error
```

Do NOT silently convert:

```text
high → medium
```

unless the provider officially defines them as equivalent.

For:

```text
off
```

only expose/use it if the backend genuinely allows reasoning/thinking to be disabled.

The effort picker may disable unsupported options rather than letting the user choose something invalid.

Follow the existing picker design.

---

# 23. CONTEXT WINDOW / USAGE TELEMETRY

Current TUI telemetry reads Ollama-specific state.

Generalize only the values that are truly generic:

```text
active model
backend
prompt/input tokens
completion/output tokens
context window when known
reasoning effort
```

Runtime-specific implementation should normalize these into a provider-independent metadata object.

Do not leak:

```text
OpenAI response object
Gemini usage object
Ollama raw response
```

directly into the TUI.

If a provider does not expose a value, show it as unknown/estimated using current Klaude conventions rather than inventing one.

---

# 24. CANCELLATION

Generalize active-response cancellation.

Current Ollama uses:

```text
agent.ollama.cancel_active()
```

Replace generic callers with a runtime-level method.

Required future behavior:

```text
/cancel
/steer
/model switch
exit
```

must be able to interrupt the active Cloud request at the next safe boundary.

For OpenAI/Gemini API streams:

- close/cancel the active request/task
- do not leave background streams consuming tokens
- do not corrupt the session

Preserve existing permission-request cancellation semantics.

Tools already executing may still need to complete according to the existing architecture.

---

# 25. ERROR NORMALIZATION

Add provider-aware errors without spraying provider-specific exception handling through the TUI.

Normalize at least:

```text
authentication error
missing credential
model unavailable
rate limit / quota
network failure
timeout
provider server error
stream interrupted
invalid tool response
unsupported capability
```

User-facing examples:

```text
OpenAI API key is not configured.
```

```text
Gemini API quota exceeded.
```

```text
The selected model is no longer available.
```

Do not reduce everything to:

```text
Model request failed.
```

But also do not dump raw SDK internals by default.

---

# 26. DOCTOR

Extend `klaude doctor` appropriately.

It should distinguish optional Cloud health from core Local health.

Concept:

```text
Local
  Ollama           ✓
  embedding model  ✓

Cloud
  OpenAI API       ✓ configured
  Gemini API       ✗ GEMINI_API_KEY missing
```

Missing Cloud credentials are not fatal if the user only uses Local.

Do not make `doctor` return a misleading overall failure solely because an optional Cloud provider is not configured.

Follow existing doctor semantics.

---

# 27. STATUS

Update relevant `/status` or `klaude status` output only where needed.

Show the active model and backend cleanly.

Do not dump all discovered models into status.

Possible concept:

```text
Model
  GPT-...
  Cloud · OpenAI API
```

or:

```text
Model
  qwen3.5:9b
  Local · Ollama
```

Follow current formatting style.

---

# 28. WEB PROVIDERS ARE NOT CHAT MODEL PROVIDERS

Klaude already has:

```text
packages/web/src/klaude_web/providers.py
```

with Google/Gemini and other search providers.

Do NOT merge Cloud chat provider architecture into Web search provider architecture just because some companies overlap.

These are separate concerns:

```text
Web provider
→ retrieves internet evidence

Model runtime
→ generates agent responses
```

The Google Web provider may share `GEMINI_API_KEY`, but should remain a separate subsystem.

---

# 29. TOOL SCHEMA TRANSLATION

Klaude has one canonical `Tool`.

Keep it canonical.

Implement translation:

```text
Klaude Tool
→ OpenAI function definition
```

and:

```text
Klaude Tool
→ Gemini function declaration
```

Then translate model function calls back into Klaude's canonical form.

Do not duplicate all Klaude tool declarations for every backend.

Test:

- string fields
- numbers
- booleans
- arrays
- nested objects if supported by current Klaude schemas
- required properties
- malformed arguments
- unknown tool names

Klaude's existing permission handling remains authoritative.

---

# 30. SECURITY

Cloud model output is untrusted.

Cloud providers must not bypass:

```text
PermissionGate
```

The only execution path should remain:

```text
model tool request
    ↓
Klaude parser/normalizer
    ↓
PermissionGate
    ↓
Klaude tool
```

Do not allow OpenAI or Gemini APIs to directly execute:

- shell commands
- workspace writes
- Git operations
- web access
- MCP calls

Provider-side automatic tool execution must remain disabled.

---

# 31. KEEP CODE/FAST MODEL ROLES SENSIBLE

Inspect current:

```text
cfg.models["coder"]
cfg.models["fast"]
cfg.models["vision"]
cfg.models["embed"]
```

These currently map to local model presets.

Do NOT automatically replace all of these with whichever Cloud model is selected.

The selected `/model` is the active interactive chat model.

Local internal roles such as embedding should remain independent.

If any current internal helper intentionally uses the selected chat model, preserve that semantics through the generic runtime.

If it intentionally uses a local role model, keep it local.

Document each distinction in code where it is not obvious.

---

# 32. TEST REQUIREMENTS

Do not make tests perform real billable Cloud requests.

Mock SDK/client boundaries.

At minimum add/update tests for:

## Model identity

- canonical refs
- backend inference
- Local/Cloud source mapping
- display name

## Existing Ollama compatibility

- list models
- stream text
- tool calls
- cancellation
- reasoning
- telemetry

## Unified picker

Verify:

```text
Cloud
```

appears before:

```text
Local
```

Verify hierarchy:

```text
Cloud
  OpenAI
    OpenAI API

  Google
    Gemini API

Local
  Ollama
```

Verify:

- headings not selectable
- keyboard navigation skips headings
- active marker
- cancellation
- effort transition
- effort cancellation restores original model/runtime
- scroll behavior still works

## Direct `/model`

Test:

- exact
- prefix
- substring
- backend-qualified model
- ambiguity
- no match

## Preference migration

Test existing:

```json
{"last_model":"qwen3.5:9b"}
```

still selects:

```text
ollama/qwen3.5:9b
```

## OpenAI discovery

Mock:

```text
GET /v1/models
```

or SDK equivalent.

Test:

- models listed
- unusable models filtered
- missing key
- auth failure
- network failure

## Gemini discovery

Mock `client.models.list()`.

Test equivalent cases.

## OpenAI streaming

Simulate:

- text
- tool call
- tool result continuation
- usage
- reasoning if supported
- completion
- cancellation
- error

## Gemini streaming

Same.

## Tool ownership

Explicitly prove model tool calls pass through:

```text
PermissionGate
```

## Local RAG regression

Select a Cloud chat model and prove:

```text
query_knowledge
embedding/indexing
```

still use the configured local Ollama embedding model.

This test is important.

---

# 33. UPDATE DOCUMENTATION

Update:

- `README.md`
- `AGENTS.md`
- command help
- config examples where appropriate

Keep setup concise.

Document:

```text
Local

Ollama
No Cloud credential required.
```

```text
Cloud

OpenAI API
Set OPENAI_API_KEY.
```

```text
Cloud

Gemini API
Set GEMINI_API_KEY.
```

Explain that:

```text
/model
```

is the unified model selector.

Explain that:

```text
/models
```

remains local Ollama diagnostics.

Mention that `GEMINI_API_KEY` may also be used by Klaude's Google Web provider.

---

# 34. DO NOT IMPLEMENT THESE YET

Do not add in this phase:

```text
Gemini CLI
ChatGPT / Codex device login
Codex SDK agent bridge
browser authentication
Playwright
Selenium
web-login automation
browser cookies
ChatGPT scraping
Gemini website scraping
```

But ensure the model runtime/identity design can later support backend IDs such as:

```text
codex
gemini_cli
```

without changing the persisted model identity format.

---

# 35. PREPARE FOR LATER CODEX SUPPORT

Do not implement the bridge yet, but account for this future backend:

```text
Cloud
  OpenAI
    ChatGPT / Codex
```

Authentication will use official OpenAI Codex device-code auth only:

```text
https://auth.openai.com/codex/device

XXXX-XXXX
```

Klaude will display the URL and code.

Klaude will NOT automate the browser.

The future implementation should use the official Codex SDK/runtime rather than manually implementing OAuth.

Do not add placeholders that pretend Codex works now.

Only design the current runtime registry so adding:

```text
backend="codex"
```

later is straightforward.

---

# 36. PREPARE FOR LATER GEMINI CLI SUPPORT

Likewise, future hierarchy may become:

```text
Cloud
  Google
    Gemini API
    Gemini CLI
```

Do not implement Gemini CLI now.

The later bridge must prove that Gemini CLI's own workspace/tool execution can be disabled or safely isolated before Klaude exposes it as a selectable model backend.

Do not fake model discovery for Gemini CLI.

---

# 37. IMPLEMENTATION ORDER

Use approximately this order:

```text
1. ModelInfo / capabilities / runtime interface
2. Ollama runtime adapter
3. Agent migrated away from direct Ollama chat dependency
4. Generic cancellation and telemetry
5. Preference migration
6. Unified grouped /model picker
7. OpenAI API runtime + discovery
8. Gemini API runtime + discovery
9. Reasoning effort mapping
10. doctor/status/help updates
11. documentation
12. full regression tests
```

Keep the application working between major steps where practical.

---

# 38. QUALITY RULE

Do not perform a superficial rename like:

```python
self.ollama
```

to:

```python
self.provider
```

while leaving Ollama assumptions inside the abstraction.

The point is to separate:

```text
Klaude Agent behavior
```

from:

```text
model transport/backend behavior
```

while retaining the small architecture Klaude currently has.

Likewise, do not build an elaborate enterprise provider/plugin framework.

The current `Agent` file already states that injected models/tools/permissions form the seam for a future framework/runtime swap.

Use that seam.

---

# FINAL EXPECTED UX

After this implementation, `/model` should approximately behave like:

```text
/model

Cloud
  OpenAI
    OpenAI API
      GPT ...
      GPT ...

  Google
    Gemini API
      Gemini ...
      Gemini ...

Local
  Ollama
      gemma...
      gpt-oss...
      qwen...
```

Cloud is first.

Selecting:

```text
GPT ...
```

automatically routes through OpenAI API.

Selecting:

```text
Gemini ...
```

automatically routes through Gemini API.

Selecting:

```text
qwen...
```

automatically routes through Ollama.

Then Klaude continues into its normal reasoning-effort picker.

The current conversation remains intact.

Klaude's own:

- tools
- PermissionGate
- RAG
- Web
- memory
- sessions
- queue
- `/steer`
- `/cancel`
- TUI

continue to work.

---

# FINAL REPORT

After implementation, return:

## Repository

- starting HEAD
- ending git diff summary
- files modified
- files added

## Architecture

Show:

```text
Agent
  ↓
ModelRuntime
  ├── Ollama
  ├── OpenAI API
  └── Gemini API
```

Explain the final interface.

## `/model`

Show the actual resulting hierarchy and direct model-resolution behavior.

## Model Identity

Show actual canonical identity format.

## OpenAI

Explain:

- SDK/API used
- discovery
- streaming
- tools
- reasoning
- cancellation
- error handling

## Gemini

Same.

## Ollama

Explain what changed and what stayed local-specific.

## RAG

Explicitly confirm local embedding/RAG still uses Ollama independently of Cloud chat selection.

## Preferences

Show old and new preference compatibility.

## Tests

List test commands and results.

## Limitations

Only genuine remaining limitations.

## Next Phase

State what is left for:

```text
ChatGPT / Codex
Gemini CLI
```

Do not implement those as part of this phase.

Most importantly:

**`/model` is now Klaude's unified Cloud + Local chat-model selector, with Cloud first, while `/models` remains Local/Ollama diagnostics and Klaude remains the agent/controller.**
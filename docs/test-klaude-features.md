# TEST KLAUDE FEATURES: live test ledger

Date started: 2026-10-04\
Klaude session: `4e92b5b386a44a0b94aae63b0e1bf318`\
Saved name: `TEST KLAUDE FEATURES`\
Workspace: `/tmp/klaude-feature-probe`\
Model: `qwen3.5:4b` through local Ollama

The session is stored in Klaude's normal session database and can be resumed
with `/resume 4e92b5b386a44a0b94aae63b0e1bf318`. Tests used a temporary
fixture workspace and read-only prompts. The session has been reopened and
resumed after code changes; those restarts preserved its name and transcript. Live results
below distinguish observed model behavior from scripted tests.

| Feature | Live observation in this session | Result and change |
| --- | --- | --- |
| Startup capabilities | Model named five installed Skills, two Context7 tools, and read-only delegation without a tool call | Capability snapshot reached the model. It initially inferred a purpose for a Skill whose description was unavailable. Prompt now tells it to preserve Unknown; retest answered `Description unavailable` from the snapshot. |
| Installed Skill, explicit use | Model called `read_skill` for `coding-standards` and answered a Python review question | Pass. It read three pages for a short request, so paging efficiency remains variable on 4B. |
| Skill, explicit no-read | Model initially called `read_skill` despite `Do not read the Skill` | Fixed with a specific schema suppression in the intent router and agent loop. Retest made no Skill tool call and answered from the startup snapshot. |
| Installed guidance, generic wording | Model initially read a Python file and answered without consulting a matching installed Skill | Fixed by one bounded required-tool retry when the user explicitly asks to use installed guidance. Retest emitted the retry and called `read_skill`. |
| Real external MCP | Model selected `mcp__context7__resolve-library-id`, permission prompt appeared, and tool returned a successful Pydantic lookup | Pass. Model reported `/pydantic/pydantic` and Pydantic. Only this configured external tool was exercised. |
| Denied external MCP permission | Model selected the Context7 library lookup for FastAPI; the permission prompt was answered `n` | Pass. Saved audit marked the call `executed: false`, and the model reported no result instead of guessing an ID. |
| One read-only subagent | Model initially read `delegation-note.txt` directly despite an explicit worker request | Fixed by routing `delegate_task` first and telling the model to delegate before direct inspection. Retest child read the file and parent reported `SABLE-47` and retry limit three. |
| Two workers | Model made two sequential `delegate_task` calls, each child read one fixture file, and parent reported Alpha then Beta | Pass for two workers and result order. A separate forced one-call `additional_tasks` probe failed after two invalid model calls; no child ran in that probe. The 4B model can use separate calls; scripted batch coverage passes. |
| Session resume and cancellation | Named session reopened several times after code changes; Ctrl+C interrupted one wrong-file follow-up and saved an interruption event | Pass for persisted name/transcript and interruption record. |
| Web search | Model called `web_search` for the official Python `pathlib.Path` documentation. Brave failed; the configured DDGS fallback returned seven search results, and the model answered with the Python documentation title and URL | Pass for tool selection and fallback execution. This was a search-result lead, not a fetched or independently verified page. The model's generated search query contained an unexpected non-English fragment, so query formation remains a quality concern. |
| URL fetch | Model called `fetch_url` for `https://docs.python.org/3/library/pathlib.html`; trafilatura returned a `src_001` record with the page title and content | Pass. Model correctly reported fetch success and the returned title, `pathlib — Object-oriented filesystem paths`. |
| Local knowledge, no-match control | Model called `query_knowledge` for a unique token; the tool returned `No sufficiently relevant local knowledge`, and the model reported no result | Pass for tool selection and honest no-match handling. |
| Local knowledge, positive retrieval | Model called `query_knowledge` scoped to `python-language`; the tool found one indexed public Python Language Reference chunk | Pass. Model identified syntax and core semantics and gave `https://docs.python.org/3/reference/`, matching the stored excerpt checked directly before the live probe. |
| Code-review accuracy | Initial generic review missed weak names and invented a “tight coupling” issue. A fresh three-line fixture review caught a shared mutable default and possible `IndexError`, but called the exception a silent failure and missed `q` | Added a file-evidence review rule. With an explicit filename correction, model re-read the correct file and fixed both claims. Ambiguous long-session follow-up still selected unrelated files before that correction; this is unresolved. |
| Named local prompt file | A later user session asked to read `challenge1.md`; its turn snapshot had `read_file` globally enabled but omitted it from callable tools because the routing rule required the literal word `file` | Fixed named-file routing and added a bounded required-read retry. One isolated `klaude ask` called `read_file` and reported the temporary file's marker. A second isolated one-shot called `read_file`, then `write_file`, and created only `result.txt` in its temporary workspace. The original long-prompt turn saved only its title and was recovered as interrupted; it was not a successful read attempt. |
| OpenRouter long build and workspace paths | A later OpenRouter session read the real `challenge1.md`, ran two shell calls, and wrote five city JSON files before a malformed function-arguments error stopped the turn | Fixed exact workspace paths missing their leading slash so file tools use the intended location and report its relative path. The five valid JSON files were relocated from the accidental nested `home/...` tree into the empty `data/cities` directory. Malformed OpenRouter calls now become private invalid-call markers, allowing the agent one bounded retry with tools still available; the malformed call never executes. Mocked runtime and agent integration passed. The site remains incomplete: only five of twelve city files exist, and templates/build output are absent. |

The saved event log, not just the model's prose, confirms successful
`read_skill`, Context7, `delegate_task`, `web_search`, `fetch_url`,
`query_knowledge`, and child lifecycle events. Three
children completed across the one-worker and two-worker probes. The forced
one-call batch probe ended as an invalid/unavailable tool-call error; it is not
counted as a passing batch. No repository file was edited by Klaude during the
live probes.

## Test boundaries and next checks

- The model in this session is small and sometimes reads too many Skill pages or
  mishandles ambiguous long-session references. Keep those as model-quality
  limits until an independent stronger-model comparison or a grounded fix.
- Test a disabled Skill in an isolated data store; the current named session
  uses the user's saved Skill inventory.
- Test local command safety, memory, and TUI navigation in later turns. Web
  search and URL fetch have one live probe each; cross-source validation and
  other web paths remain untested. Mark each separately; do not infer a passing
  feature from available-tool lists.
- The full unit suite passed outside the restricted sandbox: `2301 passed,
  19 skipped` in 111.22 seconds. The restricted sandbox had stalled on an
  isolated knowledge test; that test and both OAuth cancellation cases passed
  outside it. One Skill action assertion was updated for the existing success
  tone field before the full run. Ruff, production-source mypy, and
  `git diff --check` also passed in this verification pass.
- `make package-smoke` passed with a writable uv cache and build dependencies:
  five wheels built and installed in isolation, public packages imported, and
  installed `klaude --help` ran. The built CLI wheel contains the new
  `klaude_cli/skill_runtime.py` module.
- After the named-file fix, `tests/unit/test_intent.py`,
  `tests/unit/test_capability_routing.py`, and `tests/unit/test_cli_commands.py`
  passed together (`836 passed, 1 skipped`); Ruff, production-source mypy,
  and `git diff --check` passed. These focused results supersede the earlier
  full-suite count for the changed routing code; the full suite has not been
  rerun since this fix.
- After the OpenRouter and workspace-path fixes, the full unit suite passed
  outside the restricted sandbox (`2308 passed, 19 skipped`). A later
  feedback-path adjustment passed focused model-runtime and workspace tests
  (`114 passed`), Ruff, production-source mypy, `git diff --check`, and the
  five-wheel package smoke. The new OpenRouter retry was validated with
  provider-shaped mock streams, not a live paid OpenRouter request. A repeated
  malformed call still stops with an explicit error.

## Power-user coding evaluation

The later interactive/one-shot project evaluation, its isolated sessions,
observed failures, reliability fixes, and final validation are recorded in
[power-user-evaluation.md](power-user-evaluation.md). It includes the challenging
CSV transaction task on two local models, dirty-worktree safety, queued/resumed
implementation follow-ups, transport cancellation, and real-CLI provider failure
injection. Neither small model completed the full importer benchmark; passing
tool/feature probes above do not establish autonomous project-task completion.

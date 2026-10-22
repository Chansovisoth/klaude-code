# WebUI search reliability validation

Validated on 2026-10-22.

## Findings and changes

The shared query planner classified ordinary short proper names as ambiguous
names, then applied acronym rewrites to them. A synthetic request for
`Ada Lane Wu` produced `What does Ada stand for`, `Ada meaning`, and `Ada`.
Providers exhausted their bounded attempts on those queries; the exact-name
filter then correctly rejected the unrelated results.

Short named-entity searches now retain their complete subject and send the
original semantic name query. Genuine acronym, location, and education
relationship planning retains its existing paths. Search cache keys use v9 to
avoid reusing results obtained with the previous query plan. No provider order,
billing policy, retry budget, retrieval requirement, or model default changed.

The browser adapter also serialized complete provider result dictionaries into
model input. Two recent cached successful responses contained approximately
33,000 and 47,000 characters, exceeding the Agent's 12,000-character tool-result
limit. Large early snippets and scoring metadata could consume that limit before
later source URLs reached the model.

The adapter now reserves IDs, complete URLs, provider labels, and optional
publication dates before assigning bounded snippet excerpts within 11,000
characters. Extremely large sets of URLs end at a complete lead with an explicit
omission notice. Structured execution metadata retains the original results.
Failed search input includes redacted provider failures, filtering summaries,
actual attempted queries, and warnings instead of only an empty result array.
The successful-provider alias also supplies the Agent's execution-provenance
wording. Public snapshots and events retain their existing privacy boundary.

## Validation

- Added synthetic person, organization, and single-name query regressions, with
  and without inferred local context. All eight failed before the planner fix.
- Added adapter checks for 12 large results retaining every source link, default
  result-count and explicit provider forwarding, provider/filter failures, and
  no available provider.
- Added a deterministic browser application turn that searches, receives the
  eighth lead without truncation, explicitly fetches that page, and completes
  with source evidence. This uses the real Agent and browser tool adapter with
  scripted model and web transports.
- Focused suite: **315 passed** across `test_browser_tools.py`, `test_search.py`,
  `test_agentic_search.py`, `test_web_sources.py`, and `test_search_settings.py`.
- Scoped Ruff and `git diff --check` passed.
- A bounded live replay of the recent failing lookup returned zero usable
  results before the fix: Brave and SearXNG failed, while DDGS and Exa each
  returned eight unrelated results that were rejected. After the fix, DDGS
  returned two relevant leads, including the intended university staff page,
  in approximately five seconds. Brave remained unavailable; fallback worked.
  Diagnostic search caches and entity data used temporary directories, without
  changing user model or search preferences.
- Reloaded the idle managed WebUI with its current session, workspace, and
  listeners preserved. The replacement host returned HTTP 200 and its session
  snapshot was available. Existing browser cookies require a fresh sign-in.

This is focused regression and live-provider validation. It does not certify
every search provider, model, full test suite, or physical browser/device.
Other running Python hosts must reload to use the backend changes.

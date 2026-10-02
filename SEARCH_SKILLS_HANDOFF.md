# Klaude Code: design online Skills search

We are about to implement:

**Settings → Skills → DISCOVERY → Search**

Help us choose the best discovery sources and produce a concrete implementation plan. Research current services and their actual APIs. Prioritize broad coverage, useful popularity signals, dependable access, and trustworthy provenance. Do not assume one catalog contains every skill.

## Project and constraints

Repository: `/home/klaude/klaude-code`

Klaude is a local-first, multi-provider Python coding agent using a `uv` workspace and Prompt Toolkit.

Before implementation, inspect live `AGENTS.md`, Git status, relevant diffs, and source. The worktree contains extensive uncommitted user work: preserve it. Do not stash, reset, discard, commit, or push.

Preserve the normal-screen terminal experience and ordinary transcript scrollback. Do not migrate frameworks or rewrite the agent loop.

## Current Skills behavior

The page currently contains:

```text
▪ DISCOVERY
  Search                     Not available yet

▪ ADD SKILLS
  Import skills
  Drop ZIPs or skill files here: PATH, then import

▪ SKILLS                     1 installed
  Reload
  Delete skill

  installed-skill            3 files

  ← BACK
```

- Search is currently an inactive placeholder.
- Dropped ZIPs and supported text files live directly in `.klaude/data/skills/`.
- Background detection lists pending filenames and a count.
- **Detection does not import anything.** Users press Import skills explicitly.
- Empty imports report: `No new skill file. Add it to PATH`.
- Imports use bounded private snapshots, the configured embedding model, and existing indexing.
- Successful originals move into `skills/.imports/`.
- Existing installed skills are not silently overwritten.
- Deletion requires confirmation tied to the reviewed manifest identity.
- Reload, inventory loading, and mutations run through existing background infrastructure.

Relevant implementation:

- `apps/cli/src/klaude_cli/skills_panel.py`
- `apps/cli/src/klaude_cli/settings_panel.py`
- `apps/cli/src/klaude_cli/pickers.py`
- `apps/cli/src/klaude_cli/skill_actions.py`
- `apps/cli/src/klaude_cli/background_jobs.py`
- `apps/cli/src/klaude_cli/main.py`
- `packages/core/src/klaude_core/skill_drop.py`
- `packages/knowledge/src/klaude_knowledge/skills.py`
- `packages/knowledge/src/klaude_knowledge/skill_management.py`

## Preliminary source findings

These findings were checked on 2026-10-03. Reverify live APIs, access requirements, terms, and source code before implementation.

### 1. skills.sh — leading candidate for primary discovery

Its documentation describes search, popularity leaderboards, curated first-party entries, and audit metadata. However, the documented `/api/v1/` interface uses Vercel OIDC authentication. Verify whether that is practical for an independent Python terminal client. [API documentation](https://www.skills.sh/docs/api)

The upstream Vercel CLI currently calls a different endpoint, `/api/search`, without adding authentication. Investigate this discrepancy and endpoint stability before choosing an integration. Browser-tool probes could not retrieve the API responses; that does **not** establish an API outage. [Upstream search implementation](https://github.com/vercel-labs/skills/blob/main/src/find.ts)

The CLI implementation is MIT licensed. Compatible implementation patterns may be adapted with required attribution; this does not establish the license of catalog content or individual skills. [License](https://github.com/vercel-labs/skills/blob/main/LICENSE)

### 2. SkillsMP — alternative or optional additional catalog

Its documented REST API supports keyword search, pagination, and sorting by stars or recency. It documents limited anonymous access and higher authenticated quotas. Evaluate actual relevance, coverage, availability, terms, and quota suitability. [API documentation](https://skillsmp.com/docs/api)

### 3. GitHub — original-source verification and broader discovery

GitHub’s documented skill search finds `SKILL.md` files across public repositories through Code Search. Evaluate authentication, rate limits, and whether repository search or code search is appropriate. Repository stars must be labelled as repository popularity, not individual skill usage. [GitHub skill search](https://cli.github.com/manual/gh_skill_search)

### 4. First-party repositories and the format standard

Use first-party skill repositories as provenance references and potential curated starting points. Anthropic’s repository includes both open-source and source-available skills, so check individual licensing rather than assuming a uniform license. [Anthropic skills](https://github.com/anthropics/skills)

Use the Agent Skills specification to assess package compatibility; it is a format specification, not a universal registry. [Specification](https://agentskills.io/specification)

**Working recommendation:** evaluate skills.sh first, keep original repositories authoritative for package content, and consider SkillsMP/GitHub as complementary adapters. This is provisional, not a completed reliability benchmark.

## Decisions we need

Compare candidates in a table covering:

- Coverage and duplicate handling.
- Search relevance and empty-query browsing.
- Popularity metrics and their meaning.
- Publisher provenance and maintenance signals.
- Supported APIs, authentication, quotas, and terms.
- Availability, caching, and offline behavior.
- Package download and license information.
- Python integration effort and ongoing maintenance.

Separate **popular**, **relevant**, **first-party**, and **audited**. Do not collapse them into an unsupported “trusted” score.

Recommend one primary source and explain whether additional sources are necessary. Avoid claiming exhaustive coverage.

## Proposed product flow

```text
Skills → Search → Results → Skill detail
```

On first entry, show a useful curated or popular list where supported. If only local suggested queries are available, label them as suggestions rather than live results.

Results should show skill name, publisher/source, description, and clearly labelled popularity metadata. Long content must wrap rather than disappear behind `…`.

Detail should expose the original repository, skill path, description, available license information, and the exact revision when resolved.

Decide whether the first release should support discovery only or also explicit download/import. Search and preview must never install, index, execute scripts, or change agent permissions.

If installation is included, reuse the existing import lane, pin the selected source revision, preserve attribution, and require an explicit user action.

## Architecture and UX requirements

- Typed result records and stable identities independent of labels.
- Provider adapters in small modules.
- Background networking with bounded deadlines, response sizes, and pagination.
- Cancellation and rejection of stale results after query, page, or session changes.
- Honest distinction between no matches, authentication failure, quota exhaustion, and unavailable service.
- Cache successful metadata and clearly identify stale results.
- Preserve query, focus, viewport, and parent navigation.
- Fixed header/footer, muted descriptions, underlined section titles, and existing focus styling.
- One blank row above Back/Cancel controls.
- No network work in key handlers.
- Send only the intentional search query; never workspace paths, conversation content, credentials, or installed skill contents.
- Treat catalog metadata and downloaded instructions as untrusted.
- Preserve existing URL/download, archive, workspace, and permission boundaries.
- Do not shell out to `npx` merely to implement search.

## Required deliverable

Produce:

1. An evidence-backed source recommendation.
2. A proposed search/results/detail layout.
3. An adapter and lifecycle design.
4. A bounded implementation sequence.
5. Tests for empty entry, search, filtering, wrapping, cancellation, stale responses, rate limits, caching, duplicate identity, and navigation restoration.
6. Additional download/import tests if that scope is selected.
7. Known limitations and decisions requiring user input.

Do not treat catalog discovery as proof that Klaude supports every skill’s runtime dependencies or execution model.

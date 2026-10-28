# Store: MCPs and Skills

Store Discover now continues below Recently updated into Integrations. MCPs and
Skills have separate headings, descriptions, previews of up to four complete rows and See all
actions. They reuse Material surfaces, typography, touch targets and the Store's
scroll owner. Preview columns reuse Models' shared 290px minimum width and 8px
gap: a phone shows at most four cards; wider screens show four rows of cards.
Resizing reuses loaded metadata, with at most four supported catalog reads to fill
wider previews. An exhausted source retains only its available complete rows.
They are separate from model search, runtime filters, Installed
weights and Downloads.

The Store page uses `?view=store` throughout desktop/mobile navigation, the
command palette, the chat model sheet and Downloads shortcuts. Legacy
`?view=models` bookmarks, saved page choices and history entries migrate in place
without dropping model filters, integration detail state, paging or the URL hash.
The page, navigation, heading and refresh element IDs use `store-`. Model-specific
API endpoints and `models-*` query parameters retain their contracts, as does
Settings > Models. Back/Forward and direct reloads restore the canonical page.

The design follows the current official Impeccable guidance, consulted for this
change: [work within the existing design system](https://impeccable.style/docs/design-system/),
[group content with clear reading order and responsive spacing](https://impeccable.style/docs/layout/),
[handle data/error/input extremes](https://impeccable.style/docs/harden/), and
[polish the resulting interactions](https://impeccable.style/docs/polish/).
These guidelines were applied directly; no Impeccable plugin, hook or detector
was installed or claimed to have run. The section boundary uses whitespace and
a divider; related catalog cards stay close, without nested decorative panels,
invented rankings or fetched logo artwork.

Each collection loads metadata near the viewport, with independent loading,
cached/error/empty states and read-only Retry. Previews explicitly describe their
queries: search/research from the official MCP Registry, and coding from SkillsMP.
See all opens full Store browsing with search and item details. MCP results use
the existing bounded registry search with a forty-entry request; they do not
invent a continuation API. SkillsMP combines two supported twenty-item source
pages into each forty-item Store page, with deduplication, retained order and
reload/Back/Next continuity. An exhausted source stops early. skills.sh retains
its supported bounded single-page relevance search. Private cache records expire and are bounded;
catalog metadata does not imply trust, compatibility or first-party status.

Catalog pages place shared Library filter chips beneath Search: Source for
Skills, and Order with Stars / Recently updated for both collections. SkillsMP
uses its supported catalog order across both source pages. MCP Recently updated
orders the returned collection using the official registry's `updatedAt`
metadata, as specified in the
[Registry API schema](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/api/openapi.yaml).
MCP Stars and skills.sh Stars read repository counts for the current bounded
collection, then apply a stable descending order once reads settle. A status
explains that Stars applies to these results; unavailable counts remain last.
Focus and scroll are retained when rows move. No global MCP ranking is claimed.
skills.sh has no supported update-date ordering, so Recently updated is disabled
with guidance to choose SkillsMP. Dates appear only when source metadata provides
them. Query/source/order changes cancel obsolete reads, reset paging and retain
the order in the URL through details, Back and reload. Order caches are isolated;
the browser gates new parameters through `integration_store_sort` on older hosts.

MCP and Skill previews, catalog cards and details show GitHub repository stars.
A compact star/count sits to the right of the publisher; its accessible tooltip
includes the exact count and repository. Counts are read lazily from GitHub's
repository metadata through the existing bounded, credential-free helper. Stars
ordering also reads the current bounded collection before ranking it. Only
the saved catalog item's declared repository selects the read. SkillsMP stars
and skills.sh installs are not substituted for the GitHub response. Missing or
unavailable counts stay hidden; a verified zero remains visible. The server
shares at most 64 repository counts for one hour across catalogs and clients.
Failures cool down for five minutes and retain known counts for up to seven days
with a Cached label. At most two browser reads run together; sign-out clears
private state and discards late results. Older hosts omit the capability-gated
star requests. Star metadata never delays catalog loading or changes installation.

MCPs with a supported Streamable HTTP plan and no setup inputs can be added from
Store. A fresh exact registry plan is checked before the existing review creates
an immutable add-disabled definition. Actual discovery/enable remains in
Integrations. Packages, credential templates, other transports and interactive
OAuth direct users to terminal setup. Registry browsing never launches a server
or connects to a listed service.

Skills must resolve the original SKILL.md to a GitHub commit. A repository-only
listing asks for an exact original source URL in that same repository. Resolution
fetches only bounded source metadata/SKILL.md. A separate explicit review pins the
record and local name. Installation reuses the existing bounded, integrity-checked
GitHub folder downloader and indexed import, with no overwrite and no script
execution. The configured embedding model indexes text. Its operation fence is
checked before downloading and again under the Skill mutation lock immediately
before publication. Unknown outcomes remain actionable through Activity and are
never automatically retried. Credential-free public reads retain no-proxy,
no-redirect, response-limit and origin guards from the existing catalog clients.

Store integration reads and writes require authenticated owners. Installs retain
administrator checks at review and submit, CSRF/Origin validation, idle guards and
durable request IDs. Cached private records select effects; caller-supplied URLs,
registry payloads or commit identities cannot select an installation. The browser
clears caches/drafts on sign-out and discards late reads. Catalog/detail URLs
restore on reload, and native keyboard/focus controls remain available.

Validation:

- Store URL migration: the browser walkthrough passed initial login through an
  old Downloads URL, canonical heading/navigation links, Back/Forward, command
  palette, old saved-page preferences, preserved history/hash/filter state,
  Settings > Models, phone More menu, mobile model-sheet Store action and chat
  Downloads shortcut. The complete integrations flow then passed with zero
  console errors. Updated source and generated JS/CSS bundles were checked.
- The live LAN page at `http://192.168.100.244:50000/?view=store` returned HTTP
  200. An isolated authenticated browser opened the old Models Downloads URL,
  observed its canonical Store rewrite and reloaded Downloads successfully with
  zero console errors. The existing host runtime was preserved and the temporary
  session signed out. The Ollama/Stable Diffusion/All browser regression also
  passed detail reloads, fixture downloads, Stop/retry and responsive layouts.

- Order chips: 80 focused Store/MCP/Skills catalog tests passed, followed by 18
  Store tests after the cache compatibility adjustment. Browser checks passed
  chip ordering, URL/reload restoration, shared keyboard/Escape behavior,
  unsupported skills.sh dates and older-host parameter fallback without repeated
  reads. Search/Refresh retain one 48px row with a 4px gap at 320/390/1440px;
  filter menus remain single persistent instances. The full integration
  walkthrough completed with zero console errors.
- The idle live host was refreshed with conversation, workspace and LAN settings
  preserved. Authenticated Stars and Recently updated catalog reads returned HTTP
  200 for MCPs and Skills; all 37 MCP records in the recent collection had real
  update dates in descending order. The temporary verification session was
  signed out. No production integration was installed.

- GitHub stars: 30 focused Store/catalog tests passed, covering lazy reads,
  repository identity guards, shared persistent caches, distinct catalog metrics,
  zero, rate limiting, stale expiry, authentication and cached-catalog upgrades.
- Stars browser checks passed at phone and desktop widths, in light/dark themes,
  with zero console errors. The idle managed host was refreshed with the exact
  conversation, workspace and LAN configuration preserved. Authenticated live
  reads returned HTTP 200 and real GitHub counts for both an MCP and a Skill.
- Model See all/search pages now use complete rows near forty items; Discover
  landing previews retain their previous sizing. The Ollama/Stable Diffusion/All
  browser regression passed, including two larger combined pages, disjoint model
  identities, final-page handling, reloads and reviewed fixture downloads.
- Forty-item paging: 40 focused Store/MCP/model catalog tests passed. The browser
  walkthrough displayed forty MCP cards and forty Skills on page one, then twenty
  distinct remaining Skills on the last page. Reload and Previous restored the
  correct logical page without duplicate or skipped source reads. Four-row
  Discover preview geometry and the existing install/review flows still passed
  with zero console errors.
- After the final idle host refresh, authenticated live reads returned 37 eligible
  MCPs from a forty-entry registry request and 40 distinct Skills from two source
  pages. GitHub stars returned HTTP 200 for both collections. The temporary
  verification session was signed out; the saved conversation, workspace and
  LAN exposure were preserved.

- Catalog/Store/Skill import focused tests: 92 passed, then 32 focused tests passed
  after adding a real post-download publication-gate rejection check.
- Responsive browser walkthrough covers 320/390/768/1440px, light/dark themes,
  positioning after Recently updated, metadata-only previews, full details,
  reviewed MCP add-disabled through the real worker/journal, Skill verification
  and review, reload restoration, source entry, failure/retry, keyboard and
  older-host capability fallback. Evidence:
  `scripts/webui_integration_store_smoke.py` and
  `/tmp/klaude-integration-store-evidence`.
- Fixtures use temporary roots, mocked catalogs and a fake embedding store; they
  install no production integrations and perform no inference. Public live
  metadata probes also returned 20 SkillsMP items, 20 skills.sh items and six
  MCP Registry items. No package was fetched by those probes.
- JavaScript syntax, focused Ruff/mypy and generated bundle checks are recorded
  separately from the browser walkthrough.
- The existing Ollama/Stable Diffusion/All Store browser regression also passed,
  including model detail reloads, reviewed fixture downloads, Stop and retry.
- Four-row preview geometry passed at 320/390/768/1024/1440/1920/2560px and back
  down to phone width. Both collections used the Models column minimum and gap,
  retained complete rows, and stayed within four rows. Wider Skill continuation
  metadata was read only once and retained across subsequent resizes. The same
  browser walkthrough then passed catalog details, reviewed add, source checks,
  reload/error/keyboard/older-host paths with zero console errors.
- The live managed host was idle with no queued turns, interactions or leased
  background operations before a graceful restart. The exact saved conversation,
  workspace and LAN exposure were preserved. A temporary local administrator
  session then verified HTTP 200 with 29 fresh MCP Registry records, 20 fresh
  SkillsMP records and one successfully pinned original Skill source. That test
  session was signed out. No production integration was added or installed.

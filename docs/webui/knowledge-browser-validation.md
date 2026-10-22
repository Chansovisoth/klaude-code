# Knowledge browser overhaul

Implemented 2026-10-22. The Knowledge destination remains under Integrations.

## Behavior and design

- The starting inventory opens each library into its sources and chunk previews. Source counts and chunk counts describe the active index, including learned URLs, text uploads, saved Library files and compatible legacy rows. Crawler manifests no longer determine whether content can be browsed.
- Desktop places the source navigation beside chunk previews. Smaller windows use a Sources disclosure above the content, closed by default on phones. Breadcrumbs return to the library or all knowledge. Source selection, query and pagination participate in existing allowlisted URL history, reload and Back/Forward behavior.
- Search starts across all knowledge. Opening a library or source narrows its scope, shown in the breadcrumb and input placeholder. Search matches literal, Unicode case-insensitive text in library/source identities and complete indexed chunk text, before pagination. Punctuation such as C++ and FTS/SQL operators stays literal. Snippets include the matching passage and highlight it using DOM text nodes. Clearing search restores browsing.
- Chunk previews open a native modal reader. Text preserves indentation and line endings; uploaded HTML remains inert. Previous/Next can cross server pages without moving the underlying list. Copy uses the shared secure-context/HTTP clipboard support. Oversized chunks explicitly show a 65,536-character display limit. Escape, Close and shared backdrop dismissal restore the originating control's focus.
- Source and whole-library deletion use the existing Cancel-focused review, owner/CSRF/Origin/control checks, idle-turn gate, durable receipt and knowledge-index resource fence. Reviews name the exact scope and counts. The effect hashes and rechecks the stored scope under `BEGIN IMMEDIATE`, rejecting concurrent replacement or staging changes. Searchable text, version records and active pointers are removed atomically; unreferenced vector rows receive the same best-effort cleanup contract as existing index garbage collection. Original uploads, source files and installed Skills are retained; later explicit learning/refresh can index them again. This is index deletion, not a secure-storage erasure guarantee.
- Reads use SQLite in read-only mode with the existing three-second query deadline. They do not instantiate Knowledge/LanceDB, migrate schemas, start workers, embed text or contact a model. Current and legacy active-version filtering excludes staged, obsolete and disabled Skill content. Source labels resolve original Library filenames without importing files or altering artifact identity.
- Existing exact managed-source refresh remains available on applicable source rows. Its manifest fingerprint and reviewed worker are preserved. Closing/navigation/sign-out invalidates obsolete preparation and read results; unconfirmed deletion retains its original request identity and lock. Old running hosts show restart guidance for the additive routes.

The UI reuses Klaude Expressive surfaces, local icons, shared collection geometry, loading placeholders, native dialogs, focus styles, reduced motion and existing pagination. Primary reader controls have 44px targets. Design references checked in October 2026: [WAI modal-dialog practices](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/), [WCAG 2.2 target-size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), and [Material adaptive list-detail guidance](https://developer.android.com/develop/ui/compose/layouts/adaptive/list-detail).

## Implementation

- `packages/application/src/klaude_application/browser_knowledge.py`: read-only active-index browsing, full chunk reads, review fingerprints and the checked delete effect.
- `library_management.py` and `apps/webhost/src/klaude_webhost/host.py`: trusted service/worker binding and authenticated additive contents/source routes. Existing terminal APIs remain compatible.
- `apps/webhost/src/klaude_webhost/static/library.js`, `index.html`, `expressive.css` and the generated `style.css`: navigation, scoped search, source list, reader, reviewed deletion, stale-result protection and sign-out cleanup.
- `tests/unit/test_knowledge_browser.py`: real local index fixtures for active/legacy versions, scopes, full-text search, reader identity/limits, filenames, source paging/refresh and stale/deduplicated deletion.
- `scripts/webui_knowledge_smoke.py`: real HTTP/Chrome acceptance with isolated SQLite index fixtures, no user profile and no model calls.

## Validation

- Focused regression: `pytest tests/unit/test_knowledge_browser.py tests/unit/test_library_management.py tests/unit/test_browser_knowledge.py tests/unit/test_webhost.py -q` — **98 passed in 96.71s**.
- Real HTTP/Chrome acceptance: eight light/dark layouts at 1440/768/390/320px; confirmed source and whole-library deletion; no browser exceptions.
- Ruff, mypy for the three changed Python service/host files, JavaScript syntax, both generated bundle checks and `git diff --check` passed.

The socket-restricted sandbox prevents local HTTP/Chrome sockets and stalls LanceDB connections; those checks ran outside that restriction, using temporary fixture profiles only.

Browser screenshots and the machine-readable report are in `/tmp/klaude-knowledge-validation/`. Coverage includes 1440/768/390/320px light/dark layouts, short phone heights, reader scrolling and controls, global/scoped search, inert content, cross-page reading, Escape/focus restoration, deletion cancellation, confirmed source/library deletion, reload/history, ignored-abort late-search rejection and private sign-out cleanup.

No full-suite, physical-device or assistive-technology certification is claimed.

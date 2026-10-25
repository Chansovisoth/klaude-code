# Offline lockscreen quotes — 2026-10-23

The login screen rotates through **149 offline lines**: 19 curated English proverbs from
[geosfero/positivequotation-public-domain-quotes](https://huggingface.co/datasets/geosfero/positivequotation-public-domain-quotes).
The other 130 are locally authored or user supplied Easter eggs, listed below.
The requested dataset has exactly **30 reviewed rows**, one `train` split, and
equivalent CSV/JSON/JSONL files. The Easter eggs are explicitly separate from it;
no proverbs, authors, shortened passages or attributions were invented to reach
a target count. Every displayed line stays below the 80-character limit.

## Source, rights and reproducibility

Pinned dataset revision: `4c8151903a29476f8fc66b26237c5911e1199835`.

| Download | SHA-256 |
| --- | --- |
| `data.json` | `f9e8db216cc7e83dbb21dc24735d2d828a6047c709381ed4240e5e049e2bd7c4` |
| `README.md` | `df6dc3cec4e1e1f849341e8c6759d78f0aae77d8e9d1d70c7863cfccdf424b12` |
| `LICENSE` (empty upstream file) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Gutenberg `39281.txt.utf-8` | `1ae9bc98d49be7ec3d78d2015fa34951c3733f138230545ea89dc1af401d9f9e` |

Hugging Face marks the dataset's license **`other`**, deliberately. Its card
identifies the source edition as **public domain in the USA**, without claiming
CC0 or universal public-domain status. The book's
[catalog](https://www.gutenberg.org/ebooks/39281) confirms that scope. Only the
underlying proverb text and factual source metadata are bundled; neither the
Gutenberg eBook wrapper nor the dataset card is reproduced. Rights may differ in
other jurisdictions. The dataset's attribution/provenance guidance is retained
in `static/vendor/lockscreen-quotes-NOTICE.txt` with pinned source links and hashes.

Every selected *dataset* row keeps **all nine original fields**, including its stable ID,
`attribution`, numbered `source_entry`, `source_url`, source title/compiler,
detail URL and jurisdiction statement. Attribution is retained in the accessible
cite element and bundled metadata; the visible **English Proverb** label is
removed per the subsequent user request. Thomas Preston is credited only as the
historical compiler. The source title/entry are in the quote tooltip and the source URL is the
blockquote's `cite` attribute. No source links are fetched by the page.

## Local Easter eggs

`apps/webhost/src/klaude_webhost/static/lockscreen-quotes.json` is the single
editable collection for every quote: 19 proverbs, 38 pop culture lines, 71 memes
and 21 greetings. All 149 entries are unique and at most 80 characters.
Each Easter egg keeps its category, attribution and origin. The `original_microcopy`
origin preserves the 44 original Klaude lines; the other 86 are user supplied. User additions are never
attributed to Klaude or to an invented creator. None of these entries is part of
the Hugging Face proverb dataset. No franchise artwork or assets are included.

The validator derives the collection ID from all quote records and refreshes the
category counts. It preserves each line's category and origin.
Easter eggs have no fabricated source entry or URL. Their attribution stays in
accessible metadata while its visual label is hidden. Source-backed proverbs
retain their original provenance and rights notice.

The combined collection now contains **149 lines**. The former 100-entry cap
and fixed 25-per-category limits were removed to include the user's expanded
local collection. The per-quote 80-character bound remains.

Download the three dataset files from:

```text
https://huggingface.co/datasets/geosfero/positivequotation-public-domain-quotes/resolve/4c8151903a29476f8fc66b26237c5911e1199835/{README.md,LICENSE,data.json}
```

Download `https://www.gutenberg.org/ebooks/39281.txt.utf-8` into the same directory
as `gutenberg-39281.txt`. These are **maintainer downloads only**. Reproduce the
curation and verify the shipped files entirely offline:

```bash
python3 scripts/curate_webui_lock_quotes.py --source-dir /tmp/klaude-lockscreen-quotes-source --check
python3 scripts/bundle_webui_loading.py --check
```

For routine additions, edit only `lockscreen-quotes.json`. Give each new entry a
unique positive ID, `quote`, `attribution`, `source_kind: "easter_egg"`, category
(`pop_culture`, `meme` or `greeting`) and origin (`user_prompt` for user additions).
Keep the existing proverb records and source/license metadata intact. Then run:

```bash
python3 scripts/curate_webui_lock_quotes.py
python3 scripts/bundle_webui_loading.py
node scripts/webui_lock_quotes.test.cjs
```

There is no separate Easter egg JSON. The validator refreshes summary counts,
the rotation collection ID and the license notice without replacing quote text.
The optional `--source-dir` checks all four pinned source hashes and verifies the
complete original proverb records against the dataset and numbered book entries.
The browser uses the bundled collection and never fetches these source links.

## Editorial selection

| Quote ID | Book entry | Reason for inclusion |
| --- | --- | --- |
| 4591 | 15 | Dignity |
| 4592 | 44 | Curiosity and asking |
| 4594 | 140 | Humility |
| 4595 | 231 | Care |
| 4597 | 372 | Reflection on habits |
| 4599 | 520 | Perspective |
| 4600 | 579 | Taking an opportunity |
| 4602 | 717 | Restraint |
| 4603 | 852 | Thoughtful courage |
| 4604 | 889 | Kindness |
| 4605 | 910 | Work and activity |
| 4606 | 920 | Persistence |
| 4608 | 982 | Tolerance |
| 4609 | 989 | Thoughtful action |
| 4610 | 1000 | Affection |
| 4612 | 1025 | Courtesy |
| 4615 | 1421 | Fairness and sharing |
| 4616 | 1530 | Thoughtfulness |
| 4617 | 753 | Patience |

Excluded IDs: 4590, 4619, 4593, 4596, 4598, 4601, 4607, 4611, 4613, 4614,
4618. These focus on loss, fear, cruelty, death,
misfortune, judgment, inherited traits, religious framing or transactional advice
less suited to the requested positive lockscreen collection. This is an
editorial subset, not a claim that excluded proverbs are inaccurate.

The short fallback **“Make a little room for a new idea.”** is original Klaude
copy under the project's MIT license, explicitly attributed to Klaude. It is
separate from the source collection and used when data is absent or invalid.

## Runtime and mobile behavior

- `static/lockscreen-quotes.json` is the generated local collection, embedded
  in the existing `app.js` by the deterministic bundler. The small independent
  `lockscreen-quotes.js` helper shuffles a bag and exhausts each cycle before
  reshuffling. Adjacent cycles cannot immediately repeat a quote. The pinned
  dataset and the authored Easter egg file are the inputs to the curator.
- `KlaudeLockScreen.show()` draws only when the screen was closed. Typing,
  retries, failed login, resize, focus and clock ticks do not advance the quote.
  A successful login followed by expiry/sign-out, or a page reload, opens a new
  screen and advances the rotation. The authentication decision is unchanged.
- The existing end-4-inspired container retains its icon, Material tonal surface and
  proportions, with accessible attribution metadata. Text uses `textContent`.
  Nothing requests Hugging Face, PositiveQuotation or Gutenberg at runtime.
- Local storage holds only public quote IDs, remaining order and a collection
  identifier. Reloads resume the cycle. Invalid or unavailable storage falls
  back to an in-memory bag; without persistence, repetition across full reloads
  cannot be prevented. A single valid quote can necessarily repeat.
- On phones (through 720px), account/utilities occupy the upper toolbar row;
  the password fills the bottom row. Error feedback and the sign-in help popup
  stay above both rows. Through 768px a native grid centers the entire clock,
  quote and status in the space remaining above the footer. Notices occupy
  actual footer space; a bounded internal scroller handles long messages.
  Existing visualViewport measurements and safe-area padding retain the password
  and username above the keyboard without hiding either focused credential.
  Container-height queries progressively hide decorations
  only in compact regions; existing clock sizes remain when they fit. Desktop
  positioning, clock rendering, shape animation and authentication are preserved.

## Validation

All checks below passed against the final code on 2026-10-22.

- `node scripts/webui_lock_quotes.test.cjs`: seven tests covering provenance/
  limits, shuffled cycles, no adjacent repeats, reload persistence, invalid/
  blocked storage, sequential tab openings, collection changes, fallback and
  single-quote behavior.
- The offline curator verifies all selected texts against the pinned book bytes.
- The existing real-account browser smoke is extended to check accessible
  attribution, stability while open, actual expiry/reload rotation, same-origin
  resources, full-width phone password placement and error-message clearance.
  It retains real invalid/valid login, Enter, timeout, session protection,
  native mask, reduced motion, keyboard simulation and eleven viewport checks,
  including exact group centering, changing footer height, nonzero padding,
  browser-link mode and long feedback with a 210px visual viewport.
- Desktop and phone captures were visually inspected, including the relocated
  help popup and invalid-password feedback. The offline webhost wheel was built;
  quote JSON, runtime, notice and current UI bundles match the source bytes.
  Focused Ruff, JavaScript syntax, deterministic bundle checks and
  `git diff --check` pass.

Browser screenshots/report: `/tmp/klaude-lockscreen-validation/`. Physical
device keyboards, multiple simultaneous tabs' shared storage races and browser
engines other than the available Chromium fixture are not acceptance-tested.
No backend or authentication changes and no new runtime dependency or route.

On 2026-10-23, five further quotes from the same pinned 30-row dataset were
selected. The offline curator, bundle check, seven quote rotation tests and
`git diff --check` passed. The browser screenshots above predate this collection
update; layout and authentication code were not changed.

Later on 2026-10-23, 50 local Easter eggs were added. The curator checks the
25/25 categories, exact six requested examples, uniqueness, the 80-character
limit and the 100-line cap. Runtime validation accepts source-backed proverbs
and explicitly marked local Easter eggs; the shuffled rotation stays shared.
The seven quote rotation tests and the isolated Chrome lockscreen smoke passed,
including real invalid/valid login, session expiry, keyboard sizing, theme
contrast and zero browser exceptions. The smoke uses an isolated account; it
does not assert that the live host has been restarted.

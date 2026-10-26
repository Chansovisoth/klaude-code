# Downloads simplification and model carousel removal

User request: reduce clutter and repeated explanations, move secondary information
behind a button, and remove the image carousel from model details.

Downloads now uses a short, consistent list row: model/file name, one status or
byte-count line, the existing thin progress bar, and essential 44px icon controls.
Long Hub references use the GGUF filename as the row label; the exact full target
remains selectable in Details. Active owned pulls offer Stop; finished/failed
entries offer Remove. Unknown results say Needs check with a status-check action.
Foreign observed transfers remain read-only. Errors, connection identity, full
references, timestamps and ownership explanations appear only in the Info dialog.
The empty state has a title and Discover action without an explanatory paragraph.

The single native Info dialog supports touch/keyboard, Escape and outside
dismissal. Its close action returns focus to the current instance of its opener,
even after polling replaced a row. Polling preserves a focused row action too.
Dialog contents clear on sign-out, close on navigation, and disappear if the
record is removed. Existing authenticated actions and uncertainty fences remain.
The labels remain Stop/Remove: a true Pause/Resume capability was not invented.

Model details no longer creates a carousel. The dedicated artwork templates,
controls, swipe/keyboard handlers, resize observer and styling are removed.
About follows the summary/stats directly, retaining variants, pagination, source
links, selection/review behavior, history and scroll/focus restoration. Separate
Discover artwork remains.

## References

The user explicitly requested layout research. Primary references:

- [Chrome download tray](https://blog.chromium.org/2023/08/redesigning-chrome-downloads-to-keep.html): compact list and inline actions.
- [Firefox download management](https://support.mozilla.org/en-US/kb/where-find-and-manage-downloaded-files-firefox): essential per-download actions and details/history separation.
- [Material list reference](https://md3.io/docs/components/list/): short headline/supporting line with consistent leading/trailing content.

Klaude retains its own theme, shared icon registry, native dialog and thin loading
component; no new UI package was installed.

## Validation

The isolated Downloads Chrome walkthrough passes at 320/390/1440px in light/dark
themes, covering multiple rows, the long Hub filename, all four bar presets,
Info focus across polling, Escape focus return, error disclosure, Stop/Remove,
unknown recovery, reload and sign-out cleanup. Fixture downloads only; no real
weights or inference. Results: `/tmp/klaude-download-declutter-browser.log`;
screenshots: `/tmp/klaude-model-activity-evidence/`.

The detail walkthrough passes at 320/360/390/430/768/1440px in light/dark themes,
asserting no carousel or leftover gap while preserving model selection, review,
paging, history, scroll, source errors and sign-out. Result:
`/tmp/klaude-detail-no-carousel-browser.log`;
screenshots: `/tmp/klaude-model-detail-evidence/`.
The complete Model Store/Image Studio walkthrough also passes with no console
errors: `/tmp/klaude-declutter-store-browser.log`.
Static bundle checks, JavaScript syntax, focused Ruff and `git diff --check` pass.

An authenticated read-only check on the running WebUI also passes at
320/390/1440px: the existing completed download uses the compact row and Info
dialog, model details has no carousel, console errors are zero, and the current
conversation/model/mode/host identity are preserved. No production download,
deletion, generation or host restart was performed. Evidence:
`/tmp/klaude-store-declutter-live-result.json` and
`/tmp/klaude-store-declutter-live-evidence/`. Reload loads this static update.

## Live Discover follow-up — 2026-10-26

Discover now defaults to Hugging Face GGUF download rankings and recently updated
repositories, up to 20 each with cross-collection deduplication. Fixed promotions
and the curated shelf are removed from the live landing page. Store entry and
Refresh request fresh metadata, with cached cards retained during reads/failures.
Search defaults to the Hub; the bundled collection is an explicit offline option
and a fallback when no live results are available. Legacy default curated URLs
migrate to live discovery; explicit offline selection uses `models-source=offline`.

Focused live browser check passed at 390/1440 px: 40 live cards, both forced
refresh requests completed, default Hub search requested `query=qwen`, details
opened, no horizontal overflow or JavaScript errors. No model operations or host
restart. JavaScript syntax and diff whitespace checks passed; no broad suite run.

# Library image preview implementation

2026-10-20. Preserve the dirty Library browser/import work and supplied references.
The approved `klaude-image-preview-mockup-1.html` was rendered and inspected,
along with all three Solid Explorer screenshots. No WolfStash/Derpibooru files
are present. Use the mockup's hierarchy, not its standalone dark palette.

## Audit and constraints

- Vanilla DOM, Roboto, local SVG icons and existing Material 3 tonal roles,
  150/280/420ms motion and standard/expressive easing. Reuse native dialogs,
  the message-menu popover convention and 44px controls.
- Library already has authenticated, bounded 320px thumbnails and 2048px
  previews, exact revisions, a bounded image cache and gallery page navigation.
- The store is flat. `created` means added to Files; no modification/capture
  date, favorites or notes exist. Do not invent those fields or actions.
- Source URL does not exist. Add a private optional link table without rewriting
  old stores on read, a bounded HTTP(S)-only validator and a fixed revision-checked
  review/worker change. Never expose private `origin` host paths or fetch a link.
- Manual tags retain up to 20 printable comma-separated values of 40 characters,
  with explicit review. Chips are a draft editor for the same semantics.
- Delete requires an archived artifact. Keep Delete visible in the menu with
  actionable archive-first guidance; never bypass that rule or delete immediately.

## Incremental implementation

1. Adaptive native-dialog viewer: shared image stage, compact toolbar, desktop
   sidebar and mobile collapsed/partial/expanded details sheet using tonal tokens.
2. Structured metadata, reviewed source links at the bottom of File details,
   wrapping manual/AI tag chips with bounded show-more and manual draft editing.
3. Anchored menu and existing reviews for Archive/Restore/Delete; compact download.
4. Pointer-based pinch/pan/swipe, double-tap, keyboard zoom/fit/navigation and
   sheet focus/dismissal. Reset per image; bound metadata caching and discard
   obsolete loads; preserve Library scroll/focus/order.
5. Focused security/operation regressions, real Chrome desktop/phone/tablet and
   landscape checks in light/dark/reduced motion, lint/type/build validation.

## Verification

Record actual results, modified files and remaining limitations in
`image-preview-validation.md` when checks complete. Physical-device behavior and
full WCAG acceptance must not be inferred from emulated Chrome tests.

Completed: all five slices implemented and verified. 175 focused Python tests,
four Chrome scripts, repository Ruff, 211-file production mypy, JavaScript syntax
and seven-wheel packaging checks passed. Visual inspection caught and fixed a
portrait-image grid sizing regression; fit bounds are now asserted in screenshots.
The idle live host was gracefully reloaded with its exact session/settings and
verified with the existing WebP in desktop/phone/landscape sizes and three
palettes. Detailed evidence and scope limits are in the validation record.

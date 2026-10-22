# Appearance and chat density

Settings' Theme tab and heading are now **Appearance**. Existing `theme` tab IDs,
navigation keys and URLs stay compatible. The color-mode selector remains
System / Light / Dark, alongside palettes and reduced motion.

**Chat view** adds Comfortable and Compact using the existing native segmented
radio component. Comfortable keeps the current layout. Compact reduces message
gaps, user-bubble padding, line spacing, paragraph/list/heading gaps, code padding
and table-cell padding. Message text remains 15px, code retains its responsive
font sizes, and action buttons retain 44px touch targets. Styles are scoped to
Chat; Library previews, settings and the surrounding panels are unaffected.

The existing device-local appearance v1 preference gains optional `chatDensity`.
New/older preferences and invalid density values use Compact while retaining
valid theme, palette and motion values. Explicitly saved Comfortable preferences
remain Comfortable. Density participates in preview,
Discard and Apply, survives reload, and uses the existing cross-tab storage
handler. A failed Apply leaves the confirmed baseline unchanged. Existing behavior
on leaving Settings still discards an unapplied appearance preview.

Validation uses `.venv/bin/python scripts/webui_settings_smoke.py` with isolated
password/bootstrap hosts and no inference or owner-profile changes:

- Existing 162 light/dark Settings layout cases across 320–2560px.
- Both chat densities in light/dark at 320, 390, 768 and 1440px, for each host.
- Native density selection, Discard, failed device storage, Apply, category
  navigation and persistence through a real browser reload.
- Legacy and invalid preference migration without losing color/motion choices.
- Same text and code sizes, preserved touch targets and no horizontal overflow.
- The same rendered conversation occupies about 10–16% less vertical space in
  Compact in this fixture. This measures spacing, not a guaranteed reduction for
  every conversation.
- Existing Settings draft saves, confirmations, keyboard navigation and URL
  history, with the newer script route blocked and structuredClone unavailable.
- JavaScript syntax, focused Ruff, Python compilation and `git diff --check`.

Comparison screenshots are written under `/tmp/klaude-settings-tabs/` with
`comfortable-chat` and `compact-chat` filenames. This is simulated browser
viewport coverage, not a physical-device or full repository test run.

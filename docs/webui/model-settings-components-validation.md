# Settings Models component alignment

Settings → Models now follows the existing Settings surfaces and Library /
Integrations collection conventions. The implementation reuses Klaude's native
HTML, Material color/corner roles, shared card classes, icon registry, buttons,
disclosure decoration and popover menu styling.

- Model connections use grouped tonal cards with leading icons, readable provider
  labels, endpoint/credential metadata and compact Enabled/Disabled badges.
  Explicit scoped rules prevent inherited Settings separators from flattening
  the cards. Long names and endpoints wrap within each card.
- A local Search/Add toolbar shares 48px controls and keeps Add beside Search on
  mobile. Refresh actions use labeled icon buttons. Empty search results have a
  status message, and sign-out clears the search and private inventory.
- Test, Edit, Enable/Disable, Credential and Remove live in one icon context menu
  per connection. Native popovers support outside dismissal; arrow keys,
  Home/End, Escape and focus return work. Menus close on navigation, category
  hiding and viewport changes. Existing permissions, in-use protection and
  uncertain-operation recovery remain intact.
- Configured models occupies a matching collapsible Settings card. Its search,
  refresh controls, nested model cards and current-model action alignment follow
  the same layout. Selected cards retain their tonal state on hover.
- Redundant successful catalog guidance was removed. Defaults, image-service
  setup, role pickers, staged Apply/Discard, reviews and save receipts retain
  their existing controllers and values.

## Validation

Isolated Chromium checked 320, 390, 768 and 1440px in light/dark. The focused
checks cover page bounds, matching Search/Add geometry, real card surfaces,
filtering/empty results, menu icons, End/Escape, focus restoration and real pointer
outside dismissal. Desktop/mobile screenshots were inspected in
`/tmp/klaude-model-settings-review`.

`scripts/webui_model_settings_smoke.py` passed role picker/save, image-service
Test, add-disabled, credential save, enable/Test, removal and sign-out, with
responsive editor checks at the same four widths and no browser errors. Its
outdated editorial-tile selector now opens the actual offline model card.

JavaScript syntax, Expressive bundle and whitespace checks passed. This was a
frontend change; no live provider mutation or host restart was performed.

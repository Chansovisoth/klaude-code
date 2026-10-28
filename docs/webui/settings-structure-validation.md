# Settings structure

Account, Theme, Agent, Models and Memory remain the five Settings tabs. Theme
uses grouped Material surfaces while retaining its responsive live preview and
appearance controls. Agent retains its controls and help behavior.

Models opens a single-column overview with four default-role chooser rows and a
collapsed Advanced defaults disclosure, led by the Models heading and refresh.
Management screens use a Models breadcrumb with a return action. Connections, Connected models and Image
generation have dedicated screens within Models. `models-screen` URL state restores
the screen on reload and browser Back/Forward. Connected models supports provider
filtering, search and existing pagination; selecting a conversation runtime remains
in Chat. The overview omits the redundant Connected models link; Settings search
and existing URLs still reach the catalog. All connections is an explicit filter; initial reads use the selected or
first enabled provider, and partial provider failures retain successful results.

Defaults and image-service edits use separate draft categories and Apply/Discard
bars. Both retain their existing compare-and-set, reviewed save and witnessed
recovery paths. Connections retain their existing editor, credential, review and
recovery behavior. Navigation prompts before leaving a dirty editor and retains
its draft; browser close/reload uses native unsaved-change protection.

Account presents read-only local identity, Security and a separate Sign out action.
The existing password form lives in a native dialog. Memory retains the automatic
memory behavior and reviewed Add/Edit/Forget operations, with one shared editor
and compact text rows with overflow actions. Password and memory editors fill
phone screens at 560px and below; dismissal clears fields and returns focus.
Cancelling a memory review restores its editor draft. Private summaries, editor
fields and catalog results clear on sign-out.

## Validation

- `pytest tests/unit/test_web_media_settings.py tests/unit/test_web_accounts.py -q`:
  24 passed, using temporary loopback fixtures.
- `scripts/webui_model_settings_smoke.py`: isolated Chromium walkthrough covering
  default-role picker/save, independent image drafts, image-service testing,
  connection add/credentials/enable/test/remove, connected catalog, browser Back,
  Account and Memory editors, review and sign-out cleanup. Viewports: 320, 390,
  768 and 1440px. Screenshots: `/tmp/klaude-model-settings-evidence`.
- JavaScript syntax checks, scoped Ruff and `git diff --check`.

This is focused validation. The full repository suite and physical mobile keyboard
behavior are not certified. No live host restart or deployment is part of this change.

## Horizontal spacing follow-up

The Settings action rows use a 12px inline inset, including memory rows, so text,
values and overflow controls have a consistent boundary inside the existing
Material surfaces. Phone editors include system safe-area insets. The shared
workspace, Library, Integrations, Model Store and Activity page gutters restore
the intended 24px inset at intermediate viewport widths; phone and desktop
spacing continue to use their existing rules. The approach follows Impeccable's
product-layout guidance on predictable spacing, grouping and responsive structure:
<https://github.com/pbakaus/impeccable/blob/main/skill/reference/layout.md>.

The Settings browser walkthrough passed at 320, 390, 768 and 1440px with row
insets and visible child bounds checked. The Library/Integrations layout-only
walkthrough checks symmetric responsive page gutters, overflow and browser
exceptions in light and dark. A separate full Library/Integrations walkthrough
reached its refresh-failure check but did not observe the expected status text;
parameters, retained row, scroll position and request count matched. The Chat
layout walkthrough reached its final model-menu interaction but did not observe
the expected open state. These longer workflows are not reported as passing.

## Saved GPT reference layout

The saved GPT Settings pages in `docs/webui/GPT/Settings/` informed the stable
category navigation, restrained page headings, grouped settings rows, aligned
end actions and dividers. Account, Agent, Models, Memory and Theme adapt that
structure to Klaude's Material color roles and existing interactions. Theme's
responsive previews and shared page-bottom dock remain available. Agent preserves
the existing Help dialog and exclusions, and Model
Defaults and image-service settings retain separate draft and recovery scopes.
Account sign-out remains a separate action; Memory retains reviewed changes.

The reference-inspired update was checked with `webui_model_settings_smoke.py`
at 320, 390, 768 and 1440px and with `webui_settings_layout_smoke.py` across
100 light/dark layouts, including Agent Help focus, long labels, viewport
keyboard emulation, draft bars and Theme restoration. Both reported zero browser
exceptions. The older `webui_settings_smoke.py` still asserts that image service
and Defaults appear on the same Models page; it stopped at that obsolete layout
assertion and was not counted as passing.

## Page-bottom actions and Advanced defaults

Dirty Agent, Model Defaults, Image generation and Theme actions use the shared
page-bottom dock at desktop as well as phone and tablet widths. Their drafts
remain separate, and clean or inactive actions stay hidden. Advanced defaults
uses the same Material surface, outline and radius as the Model roles group.
The updated page dock passed 100 light/dark layout cases, including desktop
scroll clearance, mobile keyboard emulation, draft switching and Theme actions.

Settings reserves additional bottom clearance while its action dock is visible.
The layout smoke checks at least 24px between the last visible control and the
dock at scroll end, including the independently saved Image generation screen
at phone, short, tablet and desktop sizes.

Clean Settings pages retain a bottom inset even without an action dock. The
responsive walkthrough checks the last visible controls in Agent, Models,
Image generation, Theme and Memory at phone, short, tablet and desktop sizes;
the Account and Memory walkthrough also checks their clean bottom clearance.

Agent uses the same section-heading and outlined row-group composition as the
other Settings pages. Native category disclosures, individual controls, Help
dialogs, tool policies and the shared draft actions remain unchanged. On narrow
containers the timezone selector and URL fields occupy a full row so their values
remain usable; other fields retain compact label/control rows.

Theme's controls use grouped surfaces matching the other Settings categories.
The color mode, source, variants, palette, chat density, reduced motion, loading
indicators and transparency controls retain their existing preview and draft
behavior, including the direct inline accent editor.

Page descriptions now sit 8px below their headings, matching Theme. Account and
Memory no longer inherit the larger section spacing at that boundary. Refresh
actions are positioned independently of the heading flow, retaining their full
44px/48px touch targets without pushing Agent and Models titles down. Their
space is reserved horizontally, and the action ends at the description's top.
The Models overview uses the same header gap while preserving separation before
its management links.
An authenticated temporary Chromium inspection measured exactly 8px on all eight
pages (including Models subpages) at 1440, 390 and 320px, with no horizontal
overflow or browser exceptions. The follow-up alignment check also verifies
category titles start at the same height as Theme, refresh targets remain
unobscured, and Agent/Models refresh buttons can receive focus and reload their
settings at every size. Desktop and phone screenshots were inspected;
evidence is in `/tmp/klaude-settings-headers/` and
`/tmp/klaude-settings-headers.json`. CSS bundle consistency and whitespace checks
pass. This is focused header geometry validation, not a full Settings regression.

Settings search indexes labels and field names for all Agent definitions and tool
policies, Theme controls and choices, Account, Model Defaults, Connections,
Image generation and Memory. Choosing a result opens its category, management
screen and disclosure, and focuses the setting. Search uses labels rather than
saved values, reports Agent read failures, and clears its index at sign-out.

The focused Settings browser walkthrough checks discovery of every Agent field
returned by the host, search navigation across Agent, Models and Theme, empty
results, responsive dialog bounds and Escape focus return.

Settings search omits the old idle helper sentence. Up/Down highlights results
using the same Material selection colors as the command palette, announces the
active option and scrolls it into view while retaining query focus. Enter opens
the selected result; native Tab/Enter on result buttons remains available. New
queries and dialog dismissal clear selection. Escape closes the dialog even
with a nonempty search. The focused walkthrough (`KLAUDE_SETTINGS_SEARCH_ONLY=1
.venv/bin/python scripts/webui_model_settings_smoke.py`) passes with 46 Agent
fields, real keyboard navigation/activation/scrolling, no-result handling and
reopening at 1440/390/320px, with zero browser exceptions. JavaScript syntax,
bundle consistency and whitespace checks pass; the existing smoke file retains
four unrelated E501 line-length findings outside the search checks.

Agent category disclosures, including Advanced permission rules, start expanded
on first load and preserve user collapse choices across rerenders until sign-out.

For Ollama image generation, the editable Image model field includes Choose model.
The shared model chooser lists installed models from enabled configured Ollama
connections whose URL matches the image-service endpoint. The connection is
rechecked after the catalog read; unavailable or unmatched servers leave manual
entry available. Listing a model does not assert image-generation capability;
Test service and the existing reviewed save continue to verify it. The focused
browser walkthrough checks selection, manual entry, a nonmatching URL, draft
isolation, immediate reopening and the 320px layout.

Stable Diffusion also exposes Image model using the same Model Roles chooser
surface. It offers the current loaded model and the server's native recipes and
component files, with reviewed loading followed by a separate image-default
save. See `stable-diffusion-model-picker-validation.md` for its scope and evidence.

Agent setting and tool-policy dividers extend to their group borders, with the
content inset. Tool-policy groups use two columns when space permits and one
column on narrow screens. Their final divider spans the entire group, including
an unpaired final row.

Advanced defaults fallback and utility/Vision option dividers span the entire
group surface; settings remain in a single column with their usual content inset.

Image-service rows and nested permission disclosures likewise extend their dividers
to the group edges. Theme indicator controls use single-column rows with full-width
dividers, while retaining inset labels and controls. The responsive Settings
walkthrough checks these boundaries, and the model-settings walkthrough checks
the saved-memory row boundaries.

Utility output tokens and Theme indicator controls sit to the right of their
labels, including at phone widths. Longer URL and model-name fields retain room
to stack on narrow screens. The focused walkthroughs check row alignment.

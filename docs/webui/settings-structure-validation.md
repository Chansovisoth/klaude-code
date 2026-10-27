# Settings structure

Account, Theme, Agent, Models and Memory remain the five Settings tabs. Theme
keeps its existing layout apart from the shared page-bottom actions. Agent retains
its controls and help behavior.

Models opens a single-column overview with four default-role chooser rows and a
collapsed Advanced defaults disclosure. Connections, Connected models and Image
generation have dedicated screens within Models. `models-screen` URL state restores
the screen on reload and browser Back/Forward. Connected models supports provider
filtering, search and existing pagination; selecting a conversation runtime remains
in Chat. All connections is an explicit filter; initial reads use the selected or
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
end actions and dividers. Account, Agent, Models and Memory adapt that structure
to Klaude's Material color roles and existing interactions. Theme's content
layout is unchanged; its actions share the page-bottom dock. Agent preserves the existing Help dialog and exclusions, and Model
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

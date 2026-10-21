# Integrations toolbars and forms

Implemented on 2026-10-21.

Skills, Knowledge and Connections share Library's 48px search/plus layout.
Their plus buttons open the existing import, learning and MCP-add forms in a
shared native dialog. Form labels and review requirements are retained.
Knowledge search now debounces input for 200ms and still accepts Enter; there
is no separate Search button. On phones, its library selector occupies a row
above the search field and plus button.

Preparing a form captures its authentication epoch, tab and dialog generation.
Closing, switching pages or signing out makes late preparation obsolete. A late
review is discarded. Skill names and destination libraries are captured before
uploading, so later input changes cannot alter the prepared draft.

Validation completed:

- `KLAUDE_TEST_INTEGRATIONS_ONLY=1 .venv/bin/python scripts/webui_management_smoke.py`
  passed at 320, 390, 768 and 1440px with zero console exceptions: forms, 48px
  controls, Escape/focus restoration, real Skill import, real Knowledge upload
  and indexing, debounced text search, MCP-add review cancellation, obsolete
  review discard, navigation and sign-out cleanup.
- `.venv/bin/python scripts/webui_loading_smoke.py` passed, including Knowledge
  learning/source reviews, navigation, retained content and obsolete responses.
- JavaScript syntax, focused Ruff and changed-file whitespace checks passed.
- Phone dialog screenshots were captured after their opening animations.

All services and uploads above use isolated fixtures. The full management smoke
is not green: its broader Vision suggested-tag application case currently times
out waiting for a review. The focused Integrations result is separate from that
remaining failure.

# Create dialog / Image Studio redesign

Image and Research creation follow the image preview's AI Review pattern:
centered rounded icon and heading, a compact current-settings summary, a labeled
prompt textarea and a split primary action with a settings button. Image shows
the saved image model plus pixel dimensions and steps; Research shows the chosen
model and the actual saved context/output token budgets. Unknown metadata stays
unavailable; image generation never receives invented text-token settings.
Image/Research tabs reuse File inspector's Details/AI Review primary-tab classes,
equal-width targets and shared animated label-width indicator. Native tab keyboard
navigation, reduced motion and both creation drafts remain intact.

Image settings uses icon-only Landscape/Portrait segments followed by 1:1, 3:2,
16:9 and Custom segments, without a dropdown. Portrait reverses non-square preset
dimensions (2:3 and 9:16); square stays square. Custom opens Advanced and focuses
Width; orientation swaps custom dimensions too. Pixel dimensions remain visible,
and unsupported orientations/presets respect tested service limits. Image settings
retains the saved model and Advanced width/height/steps/seed.
Research settings retains Research default versus
current chat model and Report/Brief/Comparison. Native dialogs close with Done,
Close or Escape and return focus to their settings buttons. These controls remain
associated with their original forms, so validation, reset and draft semantics
survive moving them out of the main composer. Invalid advanced values reopen
settings and focus the relevant field before any review request.

Both tabs are compact single-column forms with no preview or output side panel.
Recent jobs is a disclosure below each form; open it for job controls without
cluttering the composer. The desktop Create dialog is capped at 560px. Phones up
to 540px use the existing full-screen native Create dialog. Compact Image/Research tabs preserve both drafts. The Image service
status and explicit Test service stay visible; Ready requires a real successful
capability check. Research creation still queues a reviewed job and requires a
separate Start review. No generation/research backend behavior changes.

Generated files remain available in Library. Recent image jobs retain Open output,
Download, repeat, Cancel and Recover through their existing action menu. Research
jobs retain Start, Stop and Open output. No preview metadata is fetched by the
creation dialog, and there is no redundant image canvas. Existing job inventory,
review, storage and cancellation paths are reused. No backend endpoints, job
stores, dependencies or polling loops were added. Sign-out clears previews and
drafts and fences late reads. Chat focuses the prompt before service checks, so
their completion cannot move focus away from another control.

## Focused validation

`uv run --frozen --offline python scripts/webui_image_studio_smoke.py` uses isolated
HTTP fixtures and Chromium. It checks:

- Chat attachment and mobile-menu entry points with Uploads selected.
- Widths 320, 390, 768, 900 and 1440; single-column layout without a preview side and no overflow.
- Light/dark output screenshots, a short 844×390 viewport, reduced motion and
  forced colors; radio labels and practical 44px targets.
- Landscape/Portrait icons, native arrow-key orientation selection, all four ratio
  segments, square preservation, custom dimension swapping and no ratio dropdown.
- Custom dimensions, seed, Image/Research draft retention,
  native settings dialogs, Escape/focus return and hidden-settings validation.
- Research model/budget summaries from real job metadata, mobile/desktop light/dark
  layouts, actual queued Research review/confirmation and form reset.
- Actual fixture generation through review, preview, Open, PNG download and repeat.
- Actual fixture cancellation through review; failed/cancelled/running inventory
  presentation, long model names, preserved history and keyboard job actions.
- Explicit service failure remains visible and disables generation.

Evidence: `/tmp/klaude-image-studio-evidence/` and
`/tmp/klaude-creation-review-layout.log`, `/tmp/klaude-image-orientation.log` and
`/tmp/klaude-create-primary-tabs.log`. Existing AI Review regression evidence is
in `/tmp/klaude-create-tabs-review-regression.log`.
These are browser viewport simulations, not
physical-device or production-host deployment checks.

Ruff passes for the new studio walkthrough and updated Model Store walkthrough;
Node syntax, Expressive bundle freshness and `git diff --check` pass. The broader
`KLAUDE_TEST_GENERATED_ONLY=1 scripts/webui_management_smoke.py` currently stops at
its earlier connection-review expectation (line 364), before reaching this studio.
That script also has pre-existing Ruff E501 errors outside the changed lines.
The full repository suite was not run.

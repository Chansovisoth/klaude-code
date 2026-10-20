# Eight browser palettes

Implemented and checked 2026-10-20.

Settings → INTERFACE → Themes & Colors now offers **Slate, Lavender, Sage,
Peach, Ocean, Rose, Teal and Amber**. Each preset defines coordinated light and
dark primary, secondary, tertiary and surface roles. Slate additionally defines
neutral text and outline roles, giving white/light and charcoal/dark appearances
without a purple tint. System appearance follows the browser's color scheme.

The picker uses four columns and two rows, with 44px swatches on phones and at
least 44×44px selection targets. Preview, Apply, Reset preview and cancellation
when leaving Settings retain their existing behavior. The version 1 storage
key still accepts the original presets and now accepts all eight; Lavender
remains the default. Saved choices synchronize between tabs on the same origin.

Validation completed:

- Real Chrome checked all sixteen light/dark combinations. Primary button,
  primary/secondary/tertiary container and body/muted/link text role pairs had
  contrast ratios of at least **4.86:1** across the checked surfaces. This checks
  those token pairs, rather than claiming a complete accessibility audit.
- Every new palette was previewed and applied through the actual radio controls.
  Saved values survived reload, synchronized with a second tab, and selected the
  corresponding control. Reset and leaving Settings preserved the saved choice;
  old and invalid preference values retained their expected behavior.
- System light/dark emulation switched Slate's surfaces and neutral text roles.
- At 1440×900, 768×900, 390×640 and 320×480, the picker retained four columns/two
  rows without horizontal overflow, clipped swatches or undersized targets.
- `scripts/webui_markdown_smoke.py` passed, including chat streaming, saved
  replies, code reading, message actions and all sixteen palette combinations.
  Both browser checks reported no JavaScript exceptions.
- JavaScript syntax, Ruff for the modified smoke script and `git diff --check`
  passed. This change affects browser assets only; the Python suite and wheel
  builds were not rerun.

Focused diagnostic: `/tmp/klaude-theme-check.py`. Screenshots:
`/tmp/klaude-theme-preview/` and `/tmp/klaude-markdown-preview/`.

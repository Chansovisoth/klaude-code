# Transient feedback toasts

Shared `KlaudeToast.show(message, {variant, position})` supports info, success and
error feedback, top by default or bottom. Existing chat errors and domain errors
use it; page-level error lines are cleared while contextual form/recovery details
retain their existing presentation. It uses existing Material colors and shapes,
without a framework dependency or new served asset route.

Each position holds at most five notifications. Identical active notifications
deduplicate. Close dismisses immediately with a short fade; automatic dismissal
starts after five seconds and pauses during hover or keyboard focus. Messages
are literal text, with accessible status/alert announcements and a labeled close
button. Reduced motion removes animation. Modal viewers/reviews retain usable
notifications above their backdrop. Session changes and sign-out clear messages
and timers. Vertical padding is 6px; close controls retain 44px height.

`scripts/webui_toasts_smoke.py` passed isolated Chromium checks at 320px, 390px
and 1440px: top/bottom viewport fit, stacking/deduplication, close and five-second
expiry, focus pause/keyboard dismissal, literal HTML, native modal ownership and
close, bounded stack, auth cleanup, stale/aborted errors and reduced motion. No
browser errors. Screenshots: `/tmp/klaude-toasts-validation/stacked-mobile.png`.
Bundling, JavaScript syntax, Ruff and whitespace checks passed. This is focused
browser validation, not a full repository or physical-device suite.

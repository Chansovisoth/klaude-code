# Chat XS split runtime controls

The 2026-10-26 chat layout refinement moves Model into a quiet header and keeps
Thinking/Plan below the input. The model faces use transparent header styling;
the same selectors, sizes, hit extensions and runtime contracts remain. During
active replies, narrow composers temporarily omit unavailable mode controls;
Conversation details retains their current values. See `chat-layout-validation.md`.

Desktop Model halves now open the shared searchable model dialog used on mobile,
instead of the older native-select popover. Existing runtime state and actions
are reused; see `mobile-chat-layout-validation.md` for focused UI evidence.

The model picker and Thinking use the same filled two-part design as AI Review,
adapted to md3.io's XS 32px faces, 2px gap and finite 16px outer corners. Shared
radius, state and motion tokens provide hover/press/focus behavior. Invisible
vertical hit extensions retain 44px targets without enlarging the visible faces.

Either Model half opens the existing connection/model selectors, Use model and
Refresh controls. Thinking's main action keeps its on/off behavior; its trailing
half opens the effort selector moved out of Model. The current runtime's
non-off effort levels determine availability, independently of any model merely
highlighted in the catalog. No Thinking control is shown for an unsupported or
not-yet-selected model. A single supported effort still has a usable selector.

Existing revisioned runtime requests, queue/active-turn locks, request IDs and
configured/legacy model flows remain in place. The panels close on outside
clicks, opening the other panel, sign-out or Escape. Escape restores trigger
focus. Successful effort selection closes its panel and focuses Thinking.
Panels clamp to the viewport and reposition on resize. Narrow composers may
wrap controls; model names truncate without hiding the selection affordance.

Validation: scripts/webui_models_smoke.py uses isolated Chrome and catalog/runtime
fixtures, without provider calls or personal settings. It exercises both panels
at 320/390/768/1440px, 32px geometry, viewport fit, Escape focus return,
unsupported capability projection, actual effort changes and Thinking toggles.
The existing configured and legacy catalog/search/pagination/runtime failure
checks remain in that fixture. The Expressive bundle consistency, JavaScript
syntax and diff whitespace checks cover the edited assets. This is fixture
coverage, not a live deployment or physical touch-device validation.


Selector panels use manual native popovers in the browser top layer, escaping
main-content overflow clipping and sidebar stacking. Fixed positioning follows
the split control and clamps to the visual viewport; composer/viewport resizing
and virtual-keyboard viewport changes reposition open panels. Leaving Chat closes
them. Hit-testing verifies the panels' visible corners, plus a desktop probe
extending beyond the chat's left clip edge over the conversation sidebar.


Plan also uses a 32px XS face with a 44px hit area. Thinking's two halves and
Plan share the existing tonal off colors and filled primary on colors. Browser
checks compare both states after real mode actions and verify Plan geometry.

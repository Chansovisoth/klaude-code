# Stable Diffusion image model selection

Settings > Models > Image generation now exposes the Image model chooser for
Stable Diffusion. It reuses the Model Roles dialog, search, pagination, focus
return and settings row styling. The current loaded model can be selected
without loading anything. Other choices are the image server's model recipes;
choosing one reveals its component selectors. Required components and required
alternative groups keep Load and use model disabled until complete.

The backend uses the native
[stable-diffusion.cpp model-management API](https://github.com/leejet/stable-diffusion.cpp/blob/master/examples/server/api.md#model-management).
Recipes, exact opaque file IDs and status come from bounded metadata reads at
the administrator's explicit service endpoint. Catalog browsing does not start
generation, download weights or load a model. Refresh explicitly requests the
native metadata rescan. Server-reported file categories determine component
choices, with no model-name or filesystem-path inference.

Load and use model reviews the exact recipe, component filenames and endpoint.
It explains that loading replaces the shared server runtime and consumes its
memory. The existing owned worker rechecks catalog/runtime identities, records a
private witnessed intent and sends one native load request. The worker has a
bounded ten-minute load wait. Explicit native rejection fails normally. Lost
acknowledgements retain a per-server operation fence. Check loaded state can
reconcile only the witnessed exact recipe/files observed ready on that server;
it never replays a load. Other/loading/empty states remain fenced. File contents
and external server clients cannot be locked by this API; changes observed
before loading are rejected, and the server retains its own busy checks.

After successful loading, the picker tests the loaded image model and stages its
name as the image-service draft. The existing reviewed Apply changes remains a
separate save. Discard does not unload a model. Saving an explicit SD choice
rejects a different current loaded model, and generation retains the existing
saved-model/capability rechecks. CLI chat model roles remain separate.

Reads and actions retain authenticated owner, Origin/CSRF and administrator
checks. Loads also retain idle admission, durable request IDs and exact request
deduplication. Closing, navigation or sign-out discard late UI reads; accepted
loads retain their durable receipts. Older hosts provide restart guidance via
`image_model_selection`. Empty native catalogs show the current loaded model and
explain that server model directories must expose the downloaded weights.

Validation:

- Focused native selection and existing browser media settings tests passed
  (21 tests before the metadata-refresh addition). Coverage includes read-only
  catalog discovery, admin/CSRF, exact file categories/slots, stale recipe/runtime
  rejection, one real owned fixture load, duplicate submit, explicit busy
  rejection, lost acknowledgement and read-only exact recovery.
- The final five native selection tests passed again after adding metadata
  refresh and explicit selected-model mismatch coverage. The native browser
  walkthrough also passed the final endpoint contract with zero console errors.
- `scripts/webui_sd_model_picker_smoke.py` passed at 320/390/768/1440px with zero
  console errors. It exercises current-model selection, required fields, cancel
  review, one confirmed fixture load, independent default save, empty catalogs,
  older-host guidance and dialog focus return. Screenshots live under
  `/tmp/klaude-sd-model-picker-evidence`.
- The existing `scripts/webui_model_settings_smoke.py` passed Model Roles, Ollama
  image selection, image testing/saving, connection credential actions and
  responsive layouts with zero console errors.
- Initial read-only inspection of the live server found one command-line-loaded
  SD 1.5 model, 108 recipe definitions and no model files exposed by its catalog.
  The existing weight is outside the categorized file catalog. No live model was
  loaded, unloaded, downloaded or changed during that inspection.
- The idle managed WebUI host was refreshed while preserving its conversation,
  workspace and LAN exposure. An authenticated phone-sized browser on the live
  LAN URL opened the chooser, found the loaded SD 1.5 model and recipe choices,
  verified empty-file guidance and focus return, and reported zero console
  errors. Exact saved settings and SD runtime status were unchanged. The
  temporary verification session was signed out.

Picker convention correction: the Stable Diffusion setting now uses the same
whole-row label/value/chevron control as Model Roles. Loaded models and recipe
rows use the shared model icon geometry, the current choice exposes pressed
state, and Refresh stays right-aligned when Connection is hidden. Recipe rows
are disabled during a shared load. The native responsive browser smoke passed
again at 320/390/768/1440px with zero console errors.

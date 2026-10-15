# S6a2: image input in ordinary coding chat

Implemented and exercised locally on 2026-10-15. This adds a provider-neutral
image message contract, private image snapshots and native Ollama delivery to
ordinary coding chat. S6a3 additional provider adapters, S6b generation and S6c
AI tags remain unstarted. The earlier separate Media analysis flow remains
documented in [S6a1](s6a-local-vision-validation.md).

## Product behavior

- Enable **Settings → AI Defaults → Vision** and explicitly select an
  image-capable native Ollama **Chat model**. Chat uses its active model and
  Runtime budgets; the separate Vision model/fallbacks belong to Media analysis.
  Attaching an image never switches models or starts a fallback.
- Use existing `/attach PATH` or inline `@PATH` / `@"path with spaces"` in chat.
  `klaude ask "Describe @capture.png"` also accepts inline attachments.
  Text files retain their bounded text context. Images become structured pixel
  input, rather than binary bytes decoded as UTF-8.
- Explicitly sending an image saves an immutable private Media copy associated
  with the session. The TUI confirms **Image snapshot saved in Library → Media**.
  Original files, stored artifacts, exported copies and indexed knowledge remain
  independent. This creates no tags, indexing or automatic analysis job.
- User turns retain ordinary public text. Owner-only `model_content` stores a
  small versioned envelope containing text, original request and bounded Media
  references. Base64 appears only in the actual approved model request.
  Transcript/export/search use public text and do not expose private references
  or pixel data. Opening Library does not add images to model context.
- Follow-ups and process restart/resume can reuse the snapshot after the source
  file changes or is removed. Tags/archive do not change its bytes. Permanently
  deleted or corrupt snapshots are unavailable, with an explicit omission notice.
- Approval is scoped to normalized native endpoint plus credential identity.
  Switching models or connection aliases on that same endpoint retains approved
  pixels only when the selected model declares image support. Switching endpoint
  or credentials omits old pixels; reattachment is required to authorize them.
  Other providers receive text with an unavailable declaration, never the pixels.
- Disabled Vision, unsupported models and invalid new images fail clearly.
  One-shot preparation errors exit 1 without a traceback or generation. Failed
  interactive preparation restores the question when the composer is empty,
  retains attachments and confirms they are ready for retry. Existing new drafts
  are preserved. Explicitly opening settings by replacing a draft is a user edit;
  resubmitting the original question does not require reattaching the image.

## Request and context contract

- PNG/JPEG only: **8 MiB/image**, **4096 pixels/side**, **4 megapixels**,
  **two images per message/request**. Duplicate paths/snapshots are deduplicated;
  history admits the latest two distinct approved snapshots. Headers/checksums
  establish bounds/integrity, not full image decoding; the server decodes images.
  GIF/WebP remain importable/exportable Media, outside this delivery adapter.
- Native `/api/show` must declare `vision`. Metadata is bounded and cancellable,
  with a 30-second per-agent capability cache scoped to model and endpoint/
  credential revisions. Metadata inspection does not load a model or infer tool
  capability. No model downloads or context-budget enlargement are performed.
- History contains `image_inputs` references. Request projection privately loads
  bounded, checksum-verified snapshots into neutral `image_content` blocks;
  Ollama translates these into native `images` strings on user messages only.
  Projection never rewrites shared history or tool call/result pairs.
- A request-local `image_input_state` tells the model the actual delivered count
  or that pixels are unavailable. Image text is untrusted data, not instructions
  or tool authorization. Refreshed tool capability snapshots retain that actual
  image count, including tool continuation requests and text-only provider switches.
- Compaction counts dimensions using a conservative patch estimate, excludes
  encoded bytes from text-token calculations and retains complete turn/tool units.
  Dropped images are explicitly described as absent; attributed recap text is not
  visual evidence. Request admission checks the final compacted prompt, reserves
  output/schema space, drops older image inputs when needed and rejects current
  inputs that exceed the estimated allocation. Actual image tokenization is
  model-owned; estimates are not a universal tokenizer or model-fit guarantee.
- File reading/capture and capability inspection run in the existing turn worker,
  off the TUI rendering path. Cancellation can wake metadata/generation requests
  before headers. A snapshot saved before cancellation can remain; no rollback
  is claimed. Regular-file reads have byte bounds; filesystem latency remains
  host-owned. Chat generation uses the existing native runtime deadlines and
  complete-response checks, distinct from the tool-free Media analysis deadline.

## Problems found and corrected

1. Binary attachments previously entered text context without pixels. A private
   snapshot/reference contract now separates text, persistence and pixel delivery.
2. Image admission ran during an unsent prompt-budget preview, before ordinary
   compaction. It rejected a tiny image and leaked a one-shot traceback. Admission
   now runs inside the guarded final request path; preparation errors are clean.
3. Attachment metadata influenced intent routing and triggered workspace
   inspection for a simple visual question. The envelope retains original user
   intent separately. Image questions require file discovery only when the
   user identifies a file/folder/directory/workspace; coding requests retain write,
   read and validation tools through the existing intent/permission logic.
4. Tool capability refresh replaced actual image counters. The turn now retains
   the count supplied in its last request while refreshing tool state.
5. A new preflight cancellation guard accidentally skipped saving a cancelled
   plain-text user turn. The guard now applies to attachment preparation only;
   existing cancellation ordering and error classification are retained.
6. The first full suite exposed a real routing regression: an image **file**
   question could select the text reader. File discovery again stays metadata-only
   for visual questions; explicit code inspection and implementation retain their
   ordinary tools. The existing regression test is retained unchanged.

## Real native CLI and terminal evidence

Final receipt:
`.klaude/data/s2-models-iswk74zf/chat-images-result.json`.
Driver: `/tmp/klaude_s6a2_real_chat.py`; output:
`/tmp/klaude-s6a2-real-chat-final.log`.
The observation proxy forwarded permitted native metadata/generation routes to
the installed local Ollama and retained counts/options, not image data.

- Installed **qwen3.5:4b**, thinking off, **8192 context / 256 output tokens**.
  No pull, delete, unload, service control or role changes outside isolated QA
  settings. All **22 installed model names/digests** and unrelated workspace
  bytes were retained.
- Actual valid **192 × 128 PNG**, three vertical red/green/blue bands, generic
  filename `u27.png`, SHA256
  `08495da3512a52229de30d36fb32933e88a6b7fac10cf454739836a9dde331b8`.
- Real `ask` returned **Red, Green, Blue**, exit 0, one native pixel request.
- Actual interactive chat returned the same colors. After removing the original,
  the next turn identified **Green** from the retained image.
- The process exited 0. A new process resumed the exact session and identified
  the rightmost color, **Blue**, with the retained snapshot still on the wire.
- The four final requests each supplied one image, with text payloads of
  **1511, 1511, 1593, 1663 characters**. They used unchanged explicit budgets.
  The preceding implementation sent about **15,600 characters** and made two
  requests for the one-shot answer; the final version used one request.
- Observed one-shot wall time: **63.03s before intent separation**, **5.52s after**.
  These are individual local runs, with model/cache state differences; the
  request count and payload reduction are stronger evidence than a general
  latency claim.
- Terminal captures at 40/70/120 columns and resumed-session capture were retained
  and visually inspected at 40/70 columns. Ordinary terminal scrollback already
  printed at a wider width cannot be rewrapped by the application on resize.
  This slice adds brief attachment feedback and no new tables/workspace panels.

Disabled/retry receipt:
`.klaude/data/s2-models-1o2pjpco/chat-image-retry-result.json`;
driver `/tmp/klaude_s6a2_retry_tui.py`,
output `/tmp/klaude-s6a2-retry-tui-post-repair.log`.
Disabled one-shot returned 1 without a traceback or generation. The real TUI
retained prompt/attachment and displayed the retry notice. Enabling Vision through
the actual Settings page and resubmitting the question without reattaching sent
one image, returned correct colors and exited 0. The test driver needed correction
to use typed Back actions then Escape on Settings home; extra Escape cleared its
draft, and `/BACK` on the legacy home became a filter. Neither failed driver run
is counted as product/retry success. Settings now explicitly says the Vision model
is for Media analysis and chat uses the active image-capable Chat model.

## Automated validation

- Focused final image/CLI cancellation/tool-routing regressions:
  **34 passed in 22.42s**. They cover actual HTTP delivery/restore/cancellation,
  private/public separation and export, bounded distinct history, disabled/text
  models, corrupted/deleted snapshots, allocation limits and compaction.
- Adapter-level fixtures verify native image/tool pairs and generic compatible
  requests after switching providers. These are protocol fixtures, not paid
  provider image-generation certification.
- First full gate: **3173 passed, 1 failed, 19 skipped in 451.81s**. Ruff/mypy
  were not reached by that failed `make check`. The unchanged image-file routing
  regression was corrected; focused repair coverage passed before repeating
  the complete gate.
- Repeated full frozen/offline `make check`: **3174 passed, 19 skipped in
  438.62s**; Ruff passed; production mypy **135 source files** passed.
  Log: `/tmp/klaude-s6a2-make-check-final.log`.
- Five-wheel frozen/offline `make package-smoke` passed: isolated installation,
  all public package imports and installed `klaude --help`.
  Log: `/tmp/klaude-s6a2-package-smoke.log`.
- `git diff --check` passed. Of 68 changed/untracked files recorded before the
  pass, 59 retain exact SHA256 hashes; the other nine received the reviewed
  S6a2 edits above, and none disappeared. New core `chat_images`, its tests and
  this document are intentional additions; previously clean `agent`/`ollama`
  receive the image contract changes. No dependency/lock/version changes,
  commit or push. Review: `/tmp/klaude-s6a2-worktree-review.json`.

## Remaining scope and limitations

Cloud/compatible image delivery needs S6a3 capability evidence and adapter tests;
no cloud pixel delivery is claimed here. No OCR accuracy benchmark, arbitrary
format decoding, resizing, screenshot capture, image editing, generation or AI
tags are added. Native vision quality depends on the model; the synthetic colors
prove actual pixel delivery and continuity, not general visual coding accuracy.

Follow-up: [S6a3a HTTP chat images](s6a3-http-chat-images-validation.md) adds native
Anthropic and declared compatible adapters. The native-only scope above records
the original S6a2 pass; Media analysis remains native Ollama in S6a3a.

Media snapshots remain durable independently of session deletion. Archive/delete
them explicitly through Library; deleting their bytes makes restored image input
unavailable. Stored copies may remain after later preparation/generation fails.
Private databases retain original pixels; exported/opened copies and original
files retain their own lifecycle. Context estimates can conservatively reject
large screenshots on small allocations; use a smaller image or visibly increase
Runtime context rather than silently changing allocation or models.

# Image generation providers

Image Studio is available from Library → Generated → Create. In Chat, choose
Create image from the attachment dialog (desktop/mobile) or the mobile chat menu.
The shared native dialog retains its explicit review, job history, preview,
download and Generated Library output. It does not submit the chat composer or
switch its model. Leaving Chat or signing out closes the dialog; late preparation
results cannot reopen reviews. Closing the dialog retains the current tab's draft.

## Configure

In Settings → Models → Image generation service:

- **Stable Diffusion (stable-diffusion.cpp):** enter the existing server root,
  Test service, enable, then Apply and review. The native capability endpoint
  supplies its loaded model and controls. This is the existing asynchronous
  native adapter, including exact-job cancellation and output recovery.
- **Ollama (experimental):** enter the existing server root and exact installed
  image model, Test service, enable, then Apply and review. A build/platform that
  implements Ollama's experimental image API is required. `/api/show` must declare
  `image`; `vision` means image input and does not qualify. Testing reads metadata
  only. It does not install, pull, load or generate with a model.

CLI example for a supported experimental Ollama server:

```sh
klaude library image-service --provider ollama --endpoint http://127.0.0.1:11434 \
  --model x/z-image-turbo --enable
klaude library generate 'A watercolor fox under a tree' --width 512 --height 512
```

Ollama support varies by server build; the official announcement describes an
experimental macOS release. SDK fields alone are not evidence that an installed
server supports image generation. Klaude checks the actual model capability and
installed digest before accepting work.

## Boundaries

Both adapters retain one reviewed image, dimensions in multiples of 64 within
256–1024, 1–50 steps, an explicit/random seed, a five-minute generation budget,
12 MB of response bytes and a validated PNG of at most 8 MiB matching the reviewed
size. Requests use the explicit saved endpoint without redirects, ambient proxy
credentials, arbitrary output URLs, automatic retries or model downloads.

Ollama uses one `/api/generate` NDJSON stream with `model`, `prompt`, `width`,
`height`, `steps` and `options.seed`. Its installed model digest is checked across
review, submission and publication. Results use the existing atomic Library
publication and provenance path. The stream has a 30-second idle read timeout
and the owned worker has its existing outer deadline.

Stopping the owned Ollama worker closes that stream. Remote cleanup remains
unconfirmed: this API has no retained per-generation job ID or output lookup.
Interrupted/malformed/lost streams remain unknown, are never automatically
resubmitted, and do not offer misleading Recover output/Cancel job actions.
Already saved images remain available. SD native jobs retain their existing
recoverable server IDs. Other APIs, including ComfyUI workflows and Automatic1111,
are not implemented by these adapters.

## Focused validation (2026-10-27)

- Existing image-generation suite: 58 passed (localhost native service fixture).
- Browser media settings plus initial Ollama checks: 23 passed; final Ollama suite:
  9 passed, including journaled provider/model saves, rejected Vision-only models,
  changed digests, exact payload/output publication, replay protection, interrupted
  streams, invalid image data/dimensions and byte bounds.
- Isolated Chromium: Chat attachment entry at 1440px and 390px; mobile menu entry;
  reviewed native generation completed and saved output while staying in Chat;
  provider disclosure works, no dialog overflow or browser errors.
- Scoped Ruff, Python compilation, JS syntax, two-file mypy and generated app
  bundle checks passed. No full repository suite, real GPU inference or live host
  restart is claimed. Restart the running host and reload to enable the new backend.

Sources checked:

- [Ollama experimental image generation announcement](https://ollama.com/blog/image-generation).
- [Ollama v0.14.3 image GenerateHandler](https://github.com/ollama/ollama/blob/v0.14.3/server/routes.go).
- [Official Ollama JavaScript request/response interfaces](https://github.com/ollama/ollama-js/blob/main/src/interfaces.ts).
- [stable-diffusion.cpp server API](https://github.com/leejet/stable-diffusion.cpp/blob/master/examples/server/api.md).

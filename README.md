# klaude-code

A local-first AI coding agent. The agent, models, memory, and knowledge base run on your machine by default: Ollama for models, SearXNG for web search, LanceDB for documentation you teach yourself. Optional providers such as Exa, Tavily, Hugging Face, or a remote Crawl4AI endpoint can use API keys when you choose to enable them.

```
you> add input validation to the signup route

-> read_file        src/routes/signup.ts
-> query_knowledge  "zod schema validation route handler"
-> edit_file        src/routes/signup.ts        [y/n/a]
-> run_shell        npm test                    [y/n/a]

done — committed on branch klaude/20260712-1430
```

## What it does

- **Codes with you**: reads, edits, greps, runs shell commands — each destructive action behind a y/n/always permission gate.
- **Learns documentation**: tell the chat `Learn this page and save it to knowledge: https://nextjs.org/docs`, or use `klaude learn https://nextjs.org/docs -l nextjs`. A chat request learns one page by default, infers a library name from the domain when you omit one, and asks before writing persistent knowledge. Explicitly ask to learn the documentation site or multiple pages to use the bounded same-domain crawler. The agent then answers from *your* knowledge base before touching the web (hybrid BM25 + vector + rerank retrieval).
- **Searches the web privately**: self-hosted SearXNG (70+ engines, no keys, no limits) + a clean-markdown fetch cascade. Optional providers such as Exa and Tavily can be enabled with API keys in `config/.env`.
- **Learns names locally**: RapidFuzz corrects conservative country, software, and entity-name typos against stable vocabulary and a compact local SQLite cache. An optional keyless Wikidata fallback can teach Klaude new canonical names and aliases without making search depend on Wikimedia.
- **Git-native**: never touches your branch. Works on `klaude/<task>`, one commit per edit — review everything with `git diff`, or in VS Code's Source Control panel, and revert any single action.
- **Remembers you**: `klaude remember "we use Tailwind"` — durable facts injected into every session.
- **Connects to MCP**: use external MCP servers such as Context7, Playwright,
  GitHub, Firecrawl, or MarkItDown inside Klaude. Its knowledge and web layers
  are also MCP servers usable from other agents.

## Quickstart (Ubuntu/Debian)

Prereqs: [Ollama](https://ollama.com/download), Docker, ~10GB disk for models.

```bash
git clone https://github.com/Chansovisoth/klaude-code && cd klaude-code
make setup          # docker services + uv sync + models for your RAM tier + doctor
uv run klaude       # or: uv tool install --editable apps/cli && klaude
```

`make setup` asks how you want to run Ollama — use an existing install (auto-detected, just press Enter), install system-wide, run it in Docker, point at a remote URL, or skip. Non-interactive installs (`curl | bash`, CI) skip the menu with sane defaults, or force a choice with `--ollama=existing|system|docker|url:URL|skip` and `--no-models`. Model pulls auto-detect your hardware: 32GB+ RAM pulls `qwen3-coder:30b` (30B MoE, the best local coding model that runs on CPU+RAM), 16GB pulls `gpt-oss:20b`, 8GB pulls `qwen3:4b` — and anything you already have is skipped, never re-downloaded.

### Experimental local WebUI

In the TUI, open `/settings web`, turn on **Enable Web UI**, then select
**Open Web UI**. Klaude starts a local host for the current workspace and opens
a local sign-in page. The enabled preference survives TUI exit, and the host
restarts on the next `klaude` launch if needed. Turn the switch off to stop it.
The default username is **admin**. Klaude generates a random initial password;
open `/settings web` → **Account** → **Show initial admin password** to reveal
it in the terminal. Select the row again to hide it. Reopen a CLI that was
already running before an update to load the new menu.
The account persists across restarts. The header's **Account** button opens
**Settings → Your local account**. Changing the password there signs out all
browsers and removes the initial password file.
If you forget it, run `klaude-webui --reset-admin-password` locally to generate
a new password. This also signs out all browsers. No public registration is exposed.
The managed local and LAN listeners both use TCP port **50000**.
One managed host serves one workspace per Klaude profile; disable it before
enabling it from a different workspace.
For another device on the same private network, turn on **LAN access** in
`/settings web`, choose the intended private IP if more than one is listed, and
select **Show LAN link**. Open that address on the device and sign in with the
same local account. LAN access is off by default, and network firewall rules may still
block the connection. HTTP on LAN does not encrypt passwords, chat, session cookies or
approvals, so use it only on a trusted private network. Do not port-forward
this preview.
Select **Check port exposure** in `/settings web` to test both listeners from
this computer. A successful LAN test proves the listener answers locally; it
cannot establish that another device can reach it through the firewall or
router. Settings marks device reachability confirmed only for five minutes after
a request actually arrives from another LAN device; older visits are labeled
historical. A failed device connection alone cannot distinguish a host firewall
from router, Wi-Fi isolation or routing problems.
The host serves one chat session with streaming and public history.
This preview uses the configured local Ollama coding model.
Workspace tools start with read/list/search/status/diff, with exact allow-once/
deny reviews when policy asks. Loopback browsers can explicitly activate file
edits after the clean-worktree check; LAN browsers retain read-only workspace
tools. Shell commands, full model management and most settings remain unavailable.
The browser's **Library** includes **Knowledge, Documents, Research, Media and
Archive**. Import files/images, preview/download saved copies, edit manual tags,
archive/restore and review permanent deletion. Knowledge supports indexed-text
search, explicit URL/text-file learning and refresh of existing docs sources.
**Integrations → Skills** supports installed packages, reviewed local imports,
enable/disable and deletion. Accepted operations appear in **Activity**.
These surfaces share the CLI's stores and workers; importing a document does not
automatically index it. WebUI v2 is still partial; see the
[current coverage checklist](docs/webui/coverage.md) for remaining features.
For foreground use, `klaude-webui --workspace /path/to/project` still works;
press Ctrl+C to stop that instance. To resume a saved session with the same
configured model and workspace, pass `--session-id ID` to this command.

## Commands

| Command | What it does |
|---|---|
| `klaude` | interactive agent session in the current repo (`klaude chat` also works) |
| `klaude ask "…"` | one-shot question, tools enabled |
| `klaude learn URL -l nextjs` | ingest docs into a named library |
| `klaude docs add react https://react.dev/llms.txt -l react` | install refreshable `llms.txt` docs |
| `klaude crawl https://docs.example -l docs --sitemap --include '*/docs/*'` | crawl same-domain docs pages into a refreshable library |
| `klaude docs update react` | refresh installed docs and snapshot old files if changed |
| `klaude docs update --online` | update sources listed in the configured online docs file, skipping unchanged indexing |
| `klaude import-skill crawl4ai-skill.zip -l crawl4ai` | install a skill package and index its text |
| `klaude query "…" -l nextjs` | inspect raw retrieval from a library (no LLM) |
| `klaude libraries` | list learned libraries |
| `klaude skills` | list installed assistant skills |
| `klaude model-connections list` | list model endpoint identities without connecting |
| `klaude model-connections test ID` | check and cache an endpoint's model catalog |
| `klaude search "…"` | web search via the configured provider |
| `klaude code-search "…"` | search programming docs and code examples |
| `klaude huggingface-search model "qwen coder"` | search Hugging Face Hub models, datasets, and Spaces |
| `klaude huggingface-readme model Qwen/Qwen3-Coder-30B-A3B-Instruct` | fetch a Hub model card, dataset card, or Space README |
| `klaude remember "…"` | save a durable fact |
| `klaude memory status` | inspect memory settings and locations |
| `klaude memory list` | list durable saved memories |
| `klaude memory search "DanTDM"` | search previous conversation sessions |
| `klaude auth login openai-codex` | sign in with a ChatGPT account using Codex device authentication |
| `klaude auth status openai-codex` | inspect Codex account authentication without exposing credentials |
| `klaude auth logout openai-codex` | sign out and remove credentials managed by official Codex |
| `klaude mcp list` | list external MCP servers connected to Klaude |
| `klaude mcp search QUERY` | search active entries in the official MCP Registry |
| `klaude mcp info REGISTRY_NAME` | inspect registry provenance and supported transports |
| `klaude mcp install REGISTRY_NAME` | save an exact-version registry definition as disabled |
| `klaude mcp import PATH` | safely import VS Code/OpenCode MCP JSON as disabled definitions |
| `klaude mcp auth login NAME` | sign in to a protected remote MCP server using OAuth + PKCE |
| `klaude mcp auth status NAME` | inspect non-secret remote MCP OAuth state |
| `klaude mcp auth logout NAME` | remove local OAuth credentials and disable the server |
| `klaude session-search "DanTDM"` | search previous conversation sessions |
| `klaude status` | show configured modes, storage, and tool permissions |
| `klaude system-info --json` | inspect normalized runtime context given to the model |
| `klaude doctor` | verify services, models, config |

`-l` / `--library` is the friendly name for a knowledge bucket. `-c` / `--collection` still works as a compatibility alias.

Inside the interactive chat, use `/help` to print the command reference
without asking the model to summarize it.

**Settings → Library**, directly below Memory, or `/settings library` opens the
durable-information workspace. Back returns to Settings; `/library` opens it
directly from chat. Library contains **Sessions, Knowledge,
Documents, Research, Media, Archive**. Sessions supports full-store text search,
100-record pages, recent public-turn previews, resume and archive. Archive keeps
conversation content and provides restore or separately confirmed permanent
deletion. Current sessions and active workers cannot be archived from this page.
Knowledge browses existing named libraries and provides local keyword search
without model/embedding calls. Learn source, Hybrid query and Managed sources
provide explicit TUI actions over the existing knowledge services. Learning and
refresh require a reviewed destination/source; hybrid queries use the configured
local embedding model. Owned tasks remain responsive, support Cancel/Ctrl+C,
and retain existing CLI commands. Documents and Media import private managed
copies (up to 32 MiB), with metadata search, type filters, sorting, manual tags,
bounded previews, desktop open and export to new workspace files. Archive →
Documents and Media supports restore and separately confirmed deletion. Import
and archive preserve originals and existing learned copies. Image previews show
header dimensions and an export/open fallback; no vision model is needed.
Research provides reviewed **Queue** and **Start** actions, bounded multi-round
web research, source receipts, cancellation and resume with fresh source reads.
Saved reports support preview, discussion, export, tags/archive and separately
reviewed learning into a named knowledge library. Discussion uses a bounded
private report excerpt; the public conversation shows the report name and your
question. Citation quotes are checked against fetched excerpts; review the
model's interpretation and coverage, especially with smaller local models.

Choose a Research endpoint/model in **Settings → Model Defaults**, or inherit the
session model. **Settings → Search → Deep Research** controls provider, report
output, extraction concurrency/timeouts, run deadline and advanced work budgets.
Defaults suit bounded local runs: 2 rounds, 6 queries, 8 sources, 8,192 context
tokens, 2,048 report tokens and a 300-second run deadline. These are adjustable;
research does not silently switch models or use Utility fallbacks.

For the CLI, use `klaude research run "QUESTION"`, add `--queue` to save a job
without starting research, inspect `klaude research list`, and continue with
`klaude research resume JOB_ID`. A completed run exits 0, a saved partial report
exits 2, an error exits 1, and Ctrl+C exits 130. Queued jobs start explicitly;
there is no unattended queue daemon. See the
[S4b validation and model limitations](docs/s4b-deep-research-validation.md).

Open **`/model-manager`**, or **Settings → Models → Model Manager**, to manage
downloaded models on an enabled native Ollama endpoint. Installed models has
Filter, Sort, Reload and Download controls above its inventory. Download and
deletion reviews show the exact server and model; Back is initially selected.
Downloads show live progress and support cancellation. Selected or loaded models
are protected from deletion. Connections, defaults and session history are retained.
Discover searches Hugging Face GGUF repositories through the existing credentials
owner. Service status checks Ollama; Hardware describes this machine, including
unknown measurements when unavailable. Downloading does not load or select a model.

CLI equivalents include `klaude model-manager list`, `status`, `hardware`,
`search "QUERY"`, `pull MODEL` and `delete MODEL`. Endpoint operations accept
`--endpoint ID`; mutations ask for confirmation unless `--yes` is supplied.
Failures exit 1 and Ctrl+C exits 130. Cancellation closes Klaude's request;
Ollama can retain server download data. See the
[S5a validation and remaining S5 scope](docs/s5a-model-manager-validation.md).
**Model Manager → Serve models** provides installed llama.cpp/vLLM engine tests,
local model paths, reviewed launch/adoption, server status, private log tails and
reviewed stop. Servers bind to loopback and stop when their owning Klaude client
exits. Ready endpoints appear in Added Models; choose one explicitly without
changing Default Chat automatically. CPU/GPU settings are engine-specific, and
unavailable GPU devices remain unavailable. Model downloads and engine installation
are separate actions; serving uses existing local weights.

For the CLI, inspect `klaude model-manager engines --executable PATH`, then
`klaude model-manager serve ABSOLUTE_MODEL_PATH --executable PATH --port 8080`.
Use `serve --help` for engine/context/CPU/GPU fields; it stays foreground until
Ctrl+C. `model-manager servers` lists retained records and `logs SERVER_ID` reads
a bounded tail. `model-manager adopt PID MODEL_ID --executable PATH --port N`
requires explicit review of an isolated existing server and takes responsibility
for stopping it on exit. See the
[S5b validation and limitations](docs/s5b-managed-serving-validation.md).
**Model Manager → Dependencies** inspects local build tools and selected engines.
It can build a CPU llama.cpp server from a trusted local checkout's committed
HEAD, with a Back-focused review and bounded compilation/cancellation. The new
private executable is separate from existing engines; Use in Serve models fills
its path without starting a server or changing defaults. Uncommitted source
edits are excluded and partial/failed builds are retained with private logs.

CLI equivalents are `klaude model-manager dependencies`, `klaude model-manager
builds` and `klaude model-manager build ABSOLUTE_SOURCE_PATH --jobs 2`.
Build instructions execute code from that commit; select trusted source. See
[S5c local dependency/build evidence](docs/s5c-dependencies-validation.md).

Dependencies also offers **Build llama.cpp CUDA engine** and **Install vLLM from
wheels**. CUDA checks installed NVCC and the selected host compiler using a small
fixed compilation probe. Enter numeric architectures such as `75;86`, or leave
them blank to discover available GPUs. A compatible host compiler can be chosen
explicitly; no compiler safety checks are bypassed. Jobs default to two, with
1–8 available. For example:

```bash
klaude model-manager build /absolute/llama.cpp --profile cuda --architectures 75 --host-compiler /usr/bin/g++-12 --jobs 2
klaude model-manager install-vllm /absolute/wheels --python /usr/bin/python3.12
```

The NVIDIA vLLM recipe requires a complete trusted local wheel set, including
CUDA PyTorch, for the selected Linux Python interpreter. It resolves compatibility
before copying, verifies hashes and installs offline into a new private
environment. Existing Python installations, model files and defaults are retained.
Review initially selects Back; cancellation retains partial files and waits for
owned worker cleanup. Help/backend checks certify the setup checks, not GPU model
fit or inference. Use in Serve models fills the correct engine/path without
launching or selecting a model. OS drivers/toolkits and online wheel downloading
remain explicit external setup. See [recipe evidence](docs/s5c-engine-recipes-validation.md).

**Dependencies → Built/installed engines → Review removal** reclaims one unused
setup after a review of its exact ID, directory and estimated storage. Back is
initially selected; long details support PageUp/PageDown. CLI: `klaude
model-manager remove-build ID [--yes]`; confirmation defaults to No. Removal
checks running workers/servers, current/default model selections, endpoint aliases
and accessible external process references again at acceptance. Linux-restricted
process checks are disclosed. Original source/wheel folders, external model
weights, defaults and server history remain independent. Cancelled/failed cleanup
may remove some files; Reload and review again to finish. Incomplete setups cannot
be served. [Removal evidence and limits](docs/s5c-setup-removal-validation.md).

**Model Manager → Servers** adds SSH definitions with existing key/known-hosts
references and an opt-in SSH agent. Save stores settings; Test connection and
Inspect server explicitly connect. Inspect shows bounded CPU/RAM/disk, model
directory and process metadata; GPU remains Not checked. Use as default controls
Inspect default server, independently of chat/default models. Serve model
reviews an installed remote llama.cpp executable, GGUF path and remote/tunnel
loopback ports. It registers an endpoint after owned listener/model/tunnel checks;
choose that model explicitly. Cancel loading and reviewed Stop wait for cleanup.
The server stops on owner exit or SSH lease loss. GPU layers default to 0 for
CPU. Set a positive layer count and choose GPU IDs from Test engine's remote
device mapping to request offload. Review and launch recheck that inventory;
missing/reordered devices fail, with no automatic CPU fallback. Reviews show exact
device names and layer requests. Existing model/default choices stay unchanged.
For example:

```bash
klaude model-manager serve /remote/model.gguf --ssh-server ID --executable /remote/llama-server --gpu-layers 99 --gpu 0
```

This uses an installed GPU-capable remote llama.cpp engine, not the client GPU.
Device availability does not guarantee model fit or offload. Long forms/reviews
support PageUp/PageDown; Cancel loading and reviewed Stop wait for owned cleanup.
[GPU evidence and limits](docs/s5c-remote-gpu-validation.md).

For an installed NVIDIA vLLM environment, choose **Engine → vllm** in the same
SSH form. Enter its absolute executable and a local safetensors model directory,
then test and review the remote UUID mapping, precision, context and memory fraction.
Eager execution starts ON in the TUI to avoid CUDA graphs; it can be changed.
The CLI enables it explicitly:

```bash
klaude model-manager serve /remote/models/model --engine vllm --executable /remote/env/bin/vllm --ssh-server ID --gpu 0 --memory 0.5 --dtype half --enforce-eager
```

Checks use CUDA in that environment, not the client's GPU. Missing CUDA, stale
weights/tokenizers/environments and unsupported precision fail before launch;
no installer, download, CPU fallback or default-model change is automatic.
The same owned SSH tunnel, cancellation and cleanup apply to frontend workers.
Upstream vLLM was exercised through the actual CLI/TUI on the local GTX 1650
using SmolLM2-135M-Instruct, context 512, half precision and eager execution.
This certifies that configuration over loopback SSH; other hosts/models/settings
need their own validation. [Remote vLLM evidence and limits](docs/s5c-remote-vllm-validation.md).

To take control of an already-running remote server, choose **Servers → saved
server → Adopt existing server**. Enter its installed executable, isolated PID,
exact model ID and loopback/tunnel ports. Inspect and Review leave it running;
Back/No is the review default. Accepted adoption keeps existing engine settings
and logs, registers a tunnel endpoint and stops that process group on Stop,
client exit or SSH lease loss. A failed takeover leaves the external server running.

```bash
klaude model-manager adopt PID MODEL_ID --engine llama_cpp --executable /remote/bin/llama-server --ssh-server ID --port 8080 --local-port 18080
```

Native llama.cpp and Python-console vLLM require same-account Linux ownership,
an isolated session and a healthy loopback listener. Diagnostics never authorize
adoption. [Real CLI/TUI evidence and limits](docs/s5c-remote-adoption-validation.md).


CLI equivalents are `klaude model-manager ssh list`, `add ID --host HOST --user
USER --identity-file PATH --known-hosts PATH`, `test ID`, `inspect ID`, `default
ID` and `remove ID`. Use existing verified known hosts; no password prompts or
automatic host-key trust are introduced. Checks use installed OpenSSH and remote
Python 3. See [S5c SSH evidence and limits](docs/s5c-ssh-validation.md).

**Servers → saved server → Key setup** discovers Ed25519 host fingerprints and
requires one independently verified from the server/admin before saving a private
host pin. Existing known-hosts files remain intact. Enroll public key reviews one
existing Ed25519 `.pub` file and the exact remote account/authorized-key path,
then appends through your current verified authentication. Existing entries and
restrictions are retained; identity selection and testing remain explicit.
No private-key generation, password or passphrase bootstrap is provided.

CLI equivalents are `klaude model-manager ssh host-key ID`, `trust ID
SHA256:VERIFIED_FINGERPRINT` and `enroll ID /absolute/key.pub`. Trust/enrollment
confirmations default to No; `--yes` accepts the reviewed effect explicitly.
Ctrl+C waits for local cleanup and exits 130; a completed remote append may remain.
See [key setup evidence and limits](docs/s5c-ssh-key-setup-validation.md).

To serve remote CPU weights, use `klaude model-manager serve /remote/model.gguf
--ssh-server ID --executable /remote/llama-server --port 8080 --local-port 18080`.
The command stays foreground until Ctrl+C; the model must be inside that SSH
definition's configured model directory. Long reviews use PageUp/PageDown. See
[real SSH serving/model evidence](docs/s5c-remote-serving-validation.md).

Artifact CLI includes `klaude library import PATH` for documents and
`klaude library import PATH --type media` for images. Use `klaude library list`,
`klaude library info ARTIFACT_ID`, `klaude library tags ARTIFACT_ID "tag, tag"`,
and `klaude library export ARTIFACT_ID NEW_FILE`; archive, restore and delete
subcommands each take an artifact ID. `library` manages stored copies; `libraries`
continues to list named knowledge libraries. Use an exported file with the
existing `klaude learn PATH -l NAME` command to learn explicitly.

Use `klaude sessions archive SESSION_ID`, `klaude sessions --archived`, and
`klaude sessions restore SESSION_ID` from the CLI. Archived sessions leave normal
session lists and `/resume`; restore one before continuing it. Archiving retains
existing memory-recall behavior. **Stored ≠ indexed; Imported ≠ learned;
Archived ≠ deleted.** Library browsing never learns content automatically.

**Image analysis:** Settings → Model Defaults → Vision selects an explicit
image-capable model and optional ordered fallbacks; Vision starts OFF.
Opening Model Defaults fills empty role choices from available verified models,
preferring local and already selected compatible models. Existing choices and
explicit inheritance/clears remain intact. No suitable model leaves the role
unselected. Selecting a default does not turn Vision on or switch the open chat.
The Ollama model list checks server metadata automatically and labels Vision,
text-only, Tools and Thinking support before selection. **Refresh capabilities**
rechecks without loading a model. Image generation is configured separately;
unknown metadata remains unverified rather than being guessed from model names.
Import a PNG/JPEG/static WebP/GIF into Library → Media, open its detail and choose **Analyze
image**. Edit the private question/budgets and review the exact image/model/
endpoint before sending. Results remain private to the panel, with no tools,
chat turns, indexing or automatic tags. CLI access shares the same reviewed flow:

```bash
klaude library analyze MEDIA_ID "Describe this screenshot" --context 4096 --output-tokens 512
```

Sources accept up to 32 MiB/40 megapixels. A bounded decoder prepares a working
copy to fit the request, normalizes orientation/transparency and strips metadata;
the private original is unchanged. Reviews show source and prepared dimensions.
Delivered PNG/JPEG is bounded to 4 megapixels and 7,500,000 bytes. Native Ollama,
Anthropic Messages, compatible HTTP endpoints and
OpenRouter require declared image support. Configured fallbacks are shown before
sending and run only on network/timeouts or temporary service failures. Context allocates
native Ollama's window; HTTP servers use it as Klaude's input estimate and retain
their own allocation. Results stay private and no tools run.
Native OpenAI Responses also supports the reviewed `gpt-4.1-mini` and
`gpt-4.1-mini-2025-04-14` IDs at `https://api.openai.com/v1`, using official
model documentation plus fresh authenticated availability checks. Other IDs,
fine-tunes and custom OpenAI URLs remain unknown. These models use Standard mode.
Native Gemini also supports the exact `gemini-2.5-flash` and
`gemini-2.5-flash-lite` IDs on Google's official endpoint, using documented
capabilities plus fresh model identity and token-limit checks. Requests use
inline pixels with a 20 MB total encoded-request ceiling and no file upload.
These legacy models may be unavailable to your account even when metadata is
visible; our live generation attempts returned HTTP 404. The current Gemini
models described below support chat, while Media keeps its thinking-off contract.
[Native Media analysis evidence](docs/s6a-local-vision-validation.md).
[Local Gemma E2B/E4B image and screenshot validation](docs/s6a-gemma-local-validation.md).
[HTTP Media analysis evidence and limits](docs/s6a3b-http-media-validation.md).
[OpenRouter live validation and limits](docs/s6a3c-openrouter-vision-validation.md).
[OpenAI protocol validation and account limits](docs/s6a3d-openai-vision-validation.md).
[Gemini protocol validation and account limits](docs/s6a3e-gemini-vision-validation.md).

**Local image generation:** Settings → Model Defaults → Image generation configures
an existing stable-diffusion.cpp native server. Generation starts OFF; Test checks
capabilities without generating, and Save pins its observed loaded model. Library
→ Media → Generate image reviews the prompt, endpoint/model, size, steps and seed
before submitting one job. Output and private provenance are saved in Media and
use its normal info/export/archive/delete controls. This first adapter requires
a server without authentication; it installs nothing and changes no Chat model.

```bash
klaude library image-service --endpoint http://localhost:8080 --enable
klaude library generate "A simple tool icon" --width 512 --height 512
klaude library generation-status JOB_ID
klaude library generation-status JOB_ID --recover
klaude library generation-jobs
klaude library generation-status JOB_ID --refresh
klaude library generation-status JOB_ID --forget
```

Reviews default to No/Back. Cancellation targets the accepted job only; lost
replies can leave its server outcome unconfirmed, without automatic resubmission.
The tested native server cancels queued jobs only: reviews warn that running
inference can continue after Cancel or the five-minute client deadline.
If the server completed before cancellation, Klaude reports that distinct state.
Explicit recovery reviews the original prompt, endpoint/model and budgets, then
retrieves the completed PNG without submitting generation again. The current
service binding must still match; recovery does not restore a deleted Media image.
Actual native CPU/CUDA generation, CLI/TUI reviews and exact export passed for
the tested profiles. Cancellation outcomes depend on the server's capabilities;
output quality and prompt fidelity depend on its model and reviewed budgets.
[S6b scope, validation and limits](docs/s6b-local-generation-validation.md).
[CUDA, image jobs and AI-tag validation](docs/s6-completion-validation.md).

**Optional AI tags:** Open a Media image and choose **Suggest AI tags**. Review
the Vision endpoint and budgets, then select which suggestions to save. AI tags
are kept separately from manual tags, with model provenance. Manual tags are
never overwritten; **Clear AI tags** retains manual tags and image bytes.
Importing, browsing and generating images never start tagging automatically.

```bash
klaude library suggest-tags MEDIA_ID
klaude library suggest-tags MEDIA_ID --save --select 1,3
klaude library clear-ai-tags MEDIA_ID
```

Image jobs can also be revisited through **Media → Image jobs** after the original
process closes. Lists contain local metadata only. Explicit server checks,
cancellation, output recovery and private receipt removal have separate effects;
removing a terminal receipt retains the image and sends no server cancellation.
[Tag and image-job evidence](docs/s6-completion-validation.md).

**Images in coding chat:** enable Vision and explicitly choose an image-capable
**Chat model** on native Ollama, Anthropic, OpenRouter, or a compatible HTTP
endpoint with declared image support, or a reviewed native OpenAI/Gemini model above.
Use `/attach screenshot.png` or inline
`@screenshot.png`; one-shot input also supports `klaude ask "Describe @screenshot.png"`.
PNG/JPEG/static WebP/GIF sources are prepared automatically within the limits above.
Use `/attach --detail detailed screenshot.png` for small text, or
`/attach --crop 100,200,800,600 screenshot.png` for a source-pixel crop. Coordinates
follow EXIF orientation. Animated sources require `/attach --frame 0 animation.gif`.
`--detail original` requests the largest permitted working copy; it still respects
provider/context limits. A saved `media:ID`, or its filename after source deletion,
can be explicitly attached again. After a failed image turn, `try again` reuses its
saved question and pixels; context failures get one smaller preparation, while
partial responses, credit/authentication failures and refusals require explicit retry.
[Attachment reliability validation and remaining limits](docs/image-attachment-reliability-validation.md).
Chat uses its active model and Runtime budgets, with no automatic model/fallback
switch. Up to two images are delivered per request. Explicitly sending an image
saves a private Media snapshot and small session references, enabling follow-ups
and resume after the original is removed. Pixels stay out of public transcript,
search and Markdown export. Changing endpoints/credentials requires reattachment
to authorize old pixels. Text-only/other providers receive an unavailable notice.
No indexing or AI tags start automatically. Anthropic images are capped at
7,500,000 raw bytes. Compatible catalogs must declare image input, or share an
already configured native Ollama endpoint that verifies it. Model rows show
Images as declared, documented, unsupported or unknown. Media analysis supports the same
HTTP adapters through its separate reviewed Vision model. OpenRouter must declare
both image input and text output; mandatory-reasoning models require an explicit
Thinking chat mode and cannot serve thinking-disabled Media analysis.
Resume restores the session model/mode without changing Default Chat; changed
connections require a new selection. Reviewed Gemini 2.5 models support Standard
or Thinking chat. Current `gemini-3.5-flash-lite` and `gemini-3.8-flash` models
support image chat with **Thinking required**, selected explicitly in the model
picker. Flash-Lite offers minimal/low/medium/high; Flash offers low/medium/high.
Minimal still permits thinking. One-shot explicit model selection uses the lowest
supported effort; runtime output limits include thinking tokens.
Private Media, Utility and Research use Standard mode and require a different
compatible role model. Signed Gemini continuation stays private and is never
reused across models or credentials. Other Gemini IDs and Codex account image
delivery remain outside these reviewed profiles.
[Current Gemini live tool/image/resume evidence](docs/s6a3f-current-gemini-validation.md).
[Chat image evidence, bounds and storage lifecycle](docs/s6a2-chat-images-validation.md).
[HTTP image adapter evidence and limits](docs/s6a3-http-chat-images-validation.md).

`/settings models` opens Added Models, Add Models and Session model. Add a
local Ollama/compatible server or a supported API endpoint using a private
draft, masked key and catalog-only Test. Test does not save or generate;
Add saves separately and retains the current chat model. Endpoint details
provide catalog reload/filter, manual model-ID selection, model visibility/pinning,
and endpoint enable/disable/reviewed removal. Probe checks enabled endpoints;
Clear offline reviews unreachable ones separately from authentication failures.
Affected startup choices require explicit replacement or unset. `/model` retains
the existing session selection flow; session choices no longer rewrite Default Chat. See
[the S2 validation record](docs/s2-model-settings-validation.md).

`/settings ai defaults` configures Default Chat for new sessions, an optional
Utility endpoint/model, ordered explicit Utility fallbacks and output limits.
Utility defaults to Same as chat. `/recap --ai` and `/rename --ai` explicitly
generate a bounded recap/title from recent public dialogue, without tools.
Ordinary chat, deterministic `/recap` and compaction make no extra Utility calls.
Default Chat applies to startup, `/new` and configured one-shot `ask`; explicit
CLI `--model` overrides it. Output-limit feedback points to Utility output;
Klaude never silently raises that budget or chooses an unconfigured fallback.
See [S2b evidence and provider limits](docs/s2b-ai-defaults-validation.md).

`/settings search` opens Web Search: enabled state, Auto/pinned provider, default
result count, provider management, a cancellable Test and fallback ordering.
Provider details contain masked keys and relevant options such as SearXNG URL
and Tavily depth. Existing Tools/Providers entries link to this owner.
Default agent results remain 12; choose 3/5/10/12/20 or Custom (1–50).
Explicit tool result counts still override the default. Reset restores routing
and result defaults while retaining keys, availability and provider options.
Test sends a query and respects billing, availability and health policies; its
footer reports the actual provider and result count. A catalog/configured key
is not proof of a working search. Availability also applies to `klaude ask`.
Search choices do not change URL Fetch routing. See
[Web Search evidence and limits](docs/s3a-web-search-validation.md).

Open **URL Fetch settings** from Search or Tools, or use `/settings fetch`.
Choose the local cascade or explicit Exa cloud extraction, configure Crawl4AI's
service root and optional masked key, and manage independent fetch availability.
Exa's key remains shared with Web Search. The cloud fallback is visible and
explicit; existing config behavior is retained until overridden. Test reads a
public URL in a cancellable worker and reports the actual extractor, without
learning or saving the page. Provider detail tests do not substitute a fallback.
Transport limits show current `[web.fetch]` values; private targets and unsafe
redirects remain blocked. Reset restores config routing without removing keys,
endpoints or availability. See [URL Fetch validation](docs/s3a-url-fetch-validation.md).

Maintainers can compare configured model behavior with the opt-in live harness:

```bash
uv run python scripts/evaluate_agent_behavior.py \
  --model ollama/qwen3-coder:30b \
  --model openai_codex/gpt-5.5 \
  --timeout 180 --yes
```

Each scenario runs read-only in a separate process with a hard timeout and a
private temporary Klaude data directory, so saved memory, sessions, and learned
libraries cannot contaminate results. The non-network `learned-document` scenario
seeds synthetic documentation in that directory and requires both the expected
claim and its exact source URL. Reports record tool, retry, permission, token,
timing, safety, finalization, retrieval, grounded-claim count, and grounding-score
metrics without saving answer text or raw provider errors. Schema-versioned reports
also aggregate pass rate, elapsed time, grounding, reported tokens, and unknown-token
counts by model and scenario. Web-retrieval evaluation
is excluded by default and requires both `--scenario web-retrieval` and
`--include-network`. Use `--output PATH` to write a new JSON report inside the
evaluated workspace; existing files are never overwritten.

The interactive terminal writes its transcript into ordinary terminal
scrollback, so normal wheel scrolling and drag-to-select work without Shift.
Completed lines stay above the live composer through refreshes and resizes;
Klaude does not trim session history. Your terminal's scrollback limit determines
how much history it retains.
Use `/resume` to pick any saved conversation from a list showing age, session ID,
and session name, or `/resume SESSION_ID` to continue one directly. The current
model and workspace stay selected. Finish active and queued turns before switching.
`/new` starts with a clean terminal view; `/resume` clears the previous view and
replays the selected session. Both clear terminal scrollback without deleting
saved conversations. `/rename NAME` names the session,
`/permission` opens persistent ask/allow/deny tool settings, `/plan` enables read-only
planning, `/compact` reduces stale model context, `/recap` summarizes recent
turns, `/status` shows runtime state and remaining context; with OpenAI Codex it
also shows the live five-hour, weekly, and Luna Reserve usage windows reported
by the official Codex app-server. `/memory` and `/skills` expose the local memory
and installed skill controls.
`/init` inspects the workspace and creates or carefully updates its root
`AGENTS.md` for future coding agents. `/fork` continues a copy. `/export [PATH]`
saves Markdown without overwriting
existing files (default: the data directory's `exports/` folder).
Use `/diff` for staged/unstaged patches and untracked filenames, or `/review`
for a model-assisted review with only read-only workspace tools enabled.
The input composer follows the transcript. Enter submits a turn; Alt+\ (or
`/steer TEXT`) prioritizes a correction at the next safe model/tool boundary.
`/restart` and `/stop` confirm before controlling the local Ollama service and
leave the chat session open. If administrator authentication is required, the
TUI offers a masked password field and uses it only for a narrow `sudo`
authentication step; it is not added to chat history or saved session data.
Up/down recall prior inputs, Tab completes slash commands, and Alt+Enter inserts
a newline when the terminal reports it distinctly. Ctrl+J is the compatibility
newline shortcut for terminals such as MobaXterm that collapse modified Enter
into plain Enter. `/model` and `/effort` use inline arrow-key pickers without leaving
the chat screen, displaying the available options and highlighted selection
inside the input frame rather than replacing the input with one option at a
time. All selection menus end with reset to default and cancel; cancelling the
effort step after choosing a model restores the original model. Model lists are
sorted alphabetically. Klaude remembers the last successfully selected chat model
across launches; an explicit `--model` overrides and updates that preference.
Typing `/` as the first input character immediately opens slash-command
suggestions with descriptions. `/keybinds` lists every keyboard control and
does not include slash commands or involve the model.
`/vim` toggles Vim composer controls; invoke it again to restore the standard
composer. The selected mode persists across chats.
`/settings` organizes appearance under Theme, Input Field, Divider, and Spinner,
alongside the other settings categories. Divider includes Custom and four built-in
patterns (`━`, `─`, `━ `, `─ `). Reset to default restores `━ ` and the divider defaults.
Spinner offers 90 bundled animations
from `cli-spinners`, preserving their frames and timing without runtime network
access, plus `claude` (· ✢ ✳ ✶ ✻ ✽, 100 ms). The page lists Custom,
then every built-in animation, with Reset to default at the bottom. Browse to preview an animation, then Enter to apply it.
Custom animations accept compact graphemes (`⠋⠙⠹`) or explicit quoted frames
(`"⢎⡰", "⢎⡡"`); the latter preserves spaces and multi-character frames.
Set a custom interval in milliseconds (blank defaults to 100), preview it, then
choose Apply spinner. `/settings spinner` opens this page directly.
**Tools** (`/settings tools` or `/settings agent tools`) starts with
Execution, Built-in Tools, Activity Updates, and links to MCPs and Skills. Execution configures
steps per message (default 20, custom 1–64), a finite Auto tool-call ceiling
(`max(4, steps × 2)`) or custom 1–256, and subagent workers. Advanced offers
an optional total-token budget (1–2,000,000) and provider-reported usage.
**No total-token cap** retains the finite step, time and non-progress limits;
token checks occur between calls and can overshoot, and missing provider usage
is explicitly unreported. Limits apply to new messages in chat and `klaude ask`.
Scoped resets preserve device/context choices, tool availability and permissions.
Runtime keeps device, threads, context and calibration, with an execution link.
Built-in Tools groups only tools in the live registry, with enabled/total counts.
Enter opens a group or a tool's purpose and permission link; Space switches a
selected tool. Group switches show ON, OFF, or MIXED and enable a mixed group
on the first press. Availability changes never grant permission. Disabled tools
stay absent from subsequent model schemas, recovered calls, and delegated workers.
MCPs and Skills keep their existing management pages. Settings now groups
Appearance, Models, Agent, and Advanced; `/settings providers` remains
available under Advanced as Provider credentials. Model Manager → Discover links
to that same Hugging Face credential owner. Search and URL Fetch link to the
availability owner.
[S3b validation](docs/s3b-agent-tools-validation.md).

Search owns web-result validation; Tools → Built-in Tools → Knowledge &
Sessions owns local-knowledge result validation.
Turning validation off exposes unvalidated discovery leads, but retains the normal transport,
provenance, and fetch safety limits. Activity Updates is enabled by default for
high-level live stages without private model scratchpad text. Chat output uses normal terminal
scrollback, so it has no Klaude-managed border or scrollbar; the rounded input border
defaults to on. Input Field → Height → Enter min/max accepts two whole numbers
(for example `2 10`). The composer grows between those limits; valid limits
satisfy `1 ≤ min ≤ max ≤ 12`, with defaults of 8 and 12. Enter saves, Escape or
Ctrl+C cancels, and typing `reset to default` restores both defaults.
Tools → Execution exposes Subagent workers: Auto uses one worker for
Ollama and compatible endpoints (including remote endpoints), or two for native
cloud providers, while an explicit 1–4 value is available for quota and hardware
tuning. Only audited independent read-only workspace inspections can overlap;
web, knowledge, shell, Git, and mutation work remains sequential.
Each category can be reset independently. Pastelle Azure is the
default interface theme, with Autumn, Crimson Red, Egg Yolk, Hacker Green, Neon Synth,
and rainbow-ordered Pastelle Red, Orange, Yellow, Lime, Green, Cyan, Azure,
Blue, Lavender, Purple, Magenta, and Pink also
included. Text/code colors remain independent: VS Code Dark, GitHub Dark,
Monokai, or Solarized Light. `/theme` opens Theme settings for both color choices.
Choices persist in `.klaude/data/appearance.json`. Non-interactive and piped
output remains plain.

Navigating interface themes previews the colors immediately. Text-theme pickers
show a temporary sample in the output. Enter saves the chosen colors; cancel
restores the previous colors and removes the sample. Picker lists follow the
selected row when scrolling; PageUp/PageDown navigate and Escape cancels.

Each session starts with a session divider after the logo and intro. Each user
message is followed by its timestamped user divider; streamed assistant output
is followed by a closing Klaude divider with elapsed duration.
`/help` category names are underlined
without adding separate underline rows.

Modified Enter keys use the terminal's distinct key sequences. While the TUI is
active, Klaude enables Kitty keyboard disambiguation and xterm modifyOtherKeys,
then restores both on every exit path. It accepts both protocols' sequences.
Terminals that implement neither protocol may collapse modified Enter into
ordinary Enter before any terminal application can inspect it; use Ctrl+J for a
newline and `/steer TEXT` for terminal-independent steering in that case.

Multiline clipboard pastes are submitted as one chat turn. Pastes of 1,000 or
more characters appear as a compact `[Pasted 1,234 chars]` marker in the
composer; Klaude still submits and saves the complete original text. Explicit
web or local-library search requests get one bounded compliance retry if a small
model tries to answer from memory instead of calling the requested retrieval tool.
When a prompt explicitly requests both discovery and page reading, Klaude
requires both model-directed operations and keeps query-relevant excerpts from
long fetched pages within the local model's context. Explicit no-search wording
never becomes focused help for the `klaude search` command.
Python and GDScript are mechanically checked before display and receive at most
two diagnostic-driven repair attempts when validation finds concrete defects.

`scripts/knowledge/install-online-docs.sh` writes timestamped logs under
`logs/knowledge/online-docs/` by default. Set `KLAUDE_LOG_DIR` to store logs
somewhere else. Failed `learn` commands are saved separately for retry.

Config examples live in `config/examples/`. Local editable config lives right
beside it in `config/config.toml`, `config/.env`, `config/searxng.env`,
and `config/online-docs.txt`.

## Architecture

```
terminal TUI ──► agent engine (loop · router · permission gate)
                    │
      ┌─────────────┼──────────────────┐
   Ollama        tool layer         knowledge layer
 coder/vision   fs·git·shell       LanceDB + FTS5 hybrid
 embeddings     SearXNG+fetch      docs cache · memory
                    │
              MCP plugin servers
```

Monorepo (`uv` workspace): `packages/core` (engine), `packages/knowledge`, `packages/web`, `packages/tools_local`, `apps/cli`. Source checkouts keep local editable config in visible `config/`: `config/config.toml`, `config/.env`, `config/searxng.env`, and `config/online-docs.txt`. Runtime data stays in gitignored `.klaude/data/`, including the learned name cache at `.klaude/data/entities.sqlite`. Set `KLAUDE_CONFIG_DIR` or `KLAUDE_DATA_DIR` to override those locations; set `KLAUDE_HOME` to relocate both under one custom home. Installed packages outside a source checkout fall back to `~/.config/klaude/` and `~/.local/share/klaude/`.

Search-query normalization preserves the original text, normalized text, and
per-correction provenance. The fast path is entirely local: stable structured
vocabulary, SQLite aliases, and RapidFuzz. To opt into the free online fallback
for unresolved probable names, use:

```toml
[entities.wikimedia]
enabled = true
```

Only the minimal candidate name is sent to Wikidata. Timeouts, outages, and
ambiguous results are ignored safely; ordinary search continues unchanged.

Ollama daemon settings stay with the Ollama launcher itself, such as systemd,
Docker Compose, or `ollama run` parameters. Klaude only owns request tuning for
the chat calls it sends: `config/config.toml` has `[ollama.options]`. For
example, `num_thread = 8` asks Ollama to use all 8 logical CPU threads for
Klaude chat requests, while GPU placement remains Ollama's automatic CUDA
behavior unless you explicitly set `num_gpu`. Self-contained code generation
uses a smaller prompt and streams output immediately. Machines with additional
capacity can tune code separately without changing ordinary chat:

```toml
[ollama]
code_think = "low"

[ollama.code_options]
num_ctx = 16384
num_predict = 4096
temperature = 0.15
```

Leave those overrides unset for bounded defaults: ordinary chat uses 2,048
output tokens, and code turns use at least 4,096 while honoring an explicitly
higher general limit. Klaude never silently switches the selected model based
on hardware.

Imported documentation and assistant skills are permanent user data, not repo
files:

```text
.klaude/data/docs-sources/<name>/
  manifest.json
  current/            # active llms.txt-linked docs or crawled pages
  snapshots/          # timestamped previous current/ trees

.klaude/data/skills/<name>/
  manifest.json
  source.zip          # when imported from a zip
  current/            # active SKILL.md, references, scripts, docs
  snapshots/          # timestamped previous current/ trees
```

`klaude import-skill` re-imports into the same skill name by replacing `current/`
and re-indexing text files into the selected library. `klaude docs update` does
the same for `llms.txt` and crawled documentation sources. If downloaded content is
unchanged, Klaude updates `checked_at` without creating a snapshot. By default it
keeps the last 3 snapshots. Searchable chunks live in the knowledge store;
original files stay in `docs-sources/` and `skills/`.

In chat, open `/settings skills` → **Manage installed** to review installed skills.
Both MCPs and Skills show enabled status beside each item's source and offer an
**All / Enabled / Disabled** filter. Open a skill to change its enabled state or
choose **Delete skill**. Deletion requires a separate
confirmation and removes only that skill's installed files and indexed content.
Pinned GitHub skills can be checked for a newer source revision with **Check for update**;
**Check for updates** opens a batch review. Its **Update all** confirmation applies
verified updates sequentially, up to ten at once.
Updates recheck the installed identity and do not execute skill scripts.

Choose **Import skills** from Skills settings to view the drop folder and detected
files, then explicitly start importing from that page. **Search catalog** opens
discovery in either category. Back retains the originating page and selection.

In `/settings mcps`, **Manage installed** lists configured servers with their source and
description. Open a server to enable or disable it, check for a newer verified
Registry package version, or choose **Remove server**. **Refresh list** reads server
metadata; **Refresh tools** reloads cached definitions without connecting.
Package updates are reviewed first, saved
disabled, and require a separate enable step that rediscovers tools. **Update all**
handles up to ten eligible servers in order. Custom and HTTP servers have no
automatic upstream update path.

**Discovery → Search** finds remote skills without installing them. Enter a query
or choose a local suggestion. SkillsMP is the default; Source can explicitly switch
to the provisional skills.sh catalog. Repository stars and Installs are separate
metrics, not trust ratings. Open a result for wrapped metadata and, where a GitHub
skill path is supplied, explicitly resolve its exact revision and available license.
Unknown licenses and compatibility stay unknown. Search uses cancellable background
jobs and a bounded in-process metadata cache; provider quota/offline errors are visible.
`/` filters the current results; PageUp/PageDown scroll long metadata. After resolving
a GitHub skill path, select **Install skill** and confirm the pinned source. Klaude
downloads that exact commit's folder, verifies file identities, and indexes it through
the existing skill import lane. It does not execute scripts, grant permissions, or
replace an installed skill. Catalog entries without a verified skill path cannot be
installed from Search.

Drop skill ZIPs or text files directly into `.klaude/data/skills/` (the exact
path is shown in Settings → Skills). Klaude detects settled new files and lists
pending filenames; select **Import skills** to import them. Detection alone does
not import anything. With no files, Import skills shows the folder to add them to.
Successful originals move into `skills/.imports/`; installed skill directories
are ignored. Failed files stay for review and explicit retry. Imports index text
without executing scripts and never silently replace an installed skill. The
configured embedding model must be available.
Use `klaude import-skill PATH --name NAME` for folders or explicit names.

## Memory

Klaude keeps two memory layers:

- `memory.md`: concise durable facts that load into every chat.
- `sessions.db`: searchable prior conversation turns, kept separate from durable
  memory.

Conservative auto-memory is on by default. It only saves clear, high-signal
preferences or project decisions, prints a small notice when it saves, skips
secrets, and can be turned off:

```bash
uv run klaude memory off
uv run klaude memory on
uv run klaude memory forget "old preference"
uv run klaude session-search "DanTDM"
```

## Runtime Context

At model startup Klaude collects a short, local runtime context block so the
model knows the current directory, Git root/branch/dirty state, OS, shell,
hardware summary, local time, timezone, and approximate country when it can be
inferred from local timezone data. Fastfetch is preferred for structured JSON,
Neofetch is fallback-only, and a native local collector is used when neither is
installed.

This is volatile runtime data, not durable memory, and it is not written to
`memory.md`. Network geolocation is off by default; Klaude does not contact an
IP location service unless explicitly configured. Inspect the normalized context
with `uv run klaude system-info` or disable it with:

```toml
[runtime_context]
enabled = false
```

## Use it inside VS Code today

The MCP servers work in Cline/Continue right now — add to your MCP config:

```json
{
  "mcpServers": {
    "klaude-knowledge": { "command": "uv", "args": ["run", "--directory", "/path/to/klaude-code", "klaude-knowledge-mcp"], "env": { "KLAUDE_MCP_ALLOW_WRITES": "1", "KLAUDE_MCP_WORKSPACE": "/path/to/allowed/workspace" } },
    "klaude-web":       { "command": "uv", "args": ["run", "--directory", "/path/to/klaude-code", "klaude-web-mcp"] }
  }
}
```

The knowledge MCP is read-only by default. Its learn, docs, crawl, and skill-import
tools require `KLAUDE_MCP_ALLOW_WRITES=1`. Local file and skill paths are jailed to
`KLAUDE_MCP_WORKSPACE` (the server working directory when unset).

And because klaude commits every edit on its own branch, VS Code's built-in diff/SCM views already show and review its work. A native extension (chat sidebar over `klaude serve`) is the phase-2 roadmap.

## Connect external MCP servers to Klaude

Klaude is both an MCP server and an MCP client. It supports local `stdio`
servers and remote Streamable HTTP servers. Search the official public MCP
Registry inside `/mcp` or **Settings → MCP Servers**. The in-chat page can also
collect required registry inputs securely, add a custom remote/local server,
import VS Code/OpenCode JSON, and review then enable it. The CLI remains useful
for scripts:

```bash
klaude mcp search context7
klaude mcp info io.github.upstash/context7
klaude mcp install io.github.upstash/context7
klaude mcp enable context7
```

Search is read-only and cached for one hour. Install accepts only supported
HTTPS Streamable HTTP definitions or exact-version npm/PyPI package definitions,
saves them disabled, and never connects to a server or downloads/executes a
package. Registry publication is metadata, not a security endorsement; inspect
the source and plan before separately enabling it. Registry definitions that
need credentials use the same masked in-chat secret composer as provider keys.

You can also add a known remote server or local command directly:

```bash
klaude mcp add context7  # guided transport/endpoint setup
klaude mcp add context7 --url https://mcp.context7.com/mcp
klaude mcp list
```

Existing VS Code and OpenCode JSON can be imported without executing anything:

```bash
klaude mcp import ~/.config/Code/User/mcp.json
klaude mcp enable context7
```

Every imported server starts disabled. Enabling a server asks for trust,
connects once to discover its tools, and caches only bounded public schemas so
chat startup stays fast. Each external tool has its own `ASK` permission by
default and keeps a persistent connection during the Klaude process so stateful
browser sessions work. Local `stdio` servers execute the configured program on
your machine; only enable software you trust.

Never put tokens directly in MCP JSON, command arguments, or URLs. Save a token
through the masked prompt and reference its environment variable:

```bash
klaude mcp secret CONTEXT7_API_KEY
klaude mcp add context7-auth \
  --url https://mcp.context7.com/mcp \
  --header 'Authorization=Bearer ${env:CONTEXT7_API_KEY}'
```

The value is stored in the private, gitignored `config/.env` with mode `0600`;
the MCP registry stores only `${env:...}` references.

Protected remote servers can instead use MCP OAuth. Klaude delegates protected
resource discovery, authorization-server discovery, PKCE, state validation,
dynamic client registration, and refresh to the official MCP Python SDK. Tokens
and issued client registration metadata are stored separately under the private
`.klaude/data/mcp-auth/` directory; neither appears in MCP configuration,
transcripts, logs, status output, or model context:

```bash
klaude mcp add github --url https://example.com/mcp --oauth --yes
klaude mcp auth login github
klaude mcp auth status github
klaude mcp auth logout github
```

Normal desktop login listens only on a loopback callback and opens the default
browser. Over SSH, WSL, or another headless environment, use
`klaude mcp auth login NAME --manual`: authorize in any browser, then paste the
complete final localhost callback URL into the masked prompt. If you publish a
standards-compliant Client ID Metadata Document, pass its HTTPS URL with
`--client-metadata-url`; otherwise the SDK falls back to dynamic registration
where the authorization server supports it. Logout removes local credentials
and disables the server; it does not claim to revoke an already issued token at
the authorization server.

## Secrets

All service secrets live in gitignored `config/.env` (generated by the installer from `config/examples/.env.example`, `chmod 600`). A root `.env` is still ignored as a legacy compatibility input, but new installs copy or generate secrets under `config/`. Tracked config files never contain credentials. Add future service tokens to `config/.env`, never to yaml/toml.

Container service env is kept narrow. SearXNG reads only `config/searxng.env`;
it should not receive search-provider API keys.

Do not put Ollama chat options such as `num_thread` or `num_ctx` in `.env`.
Those belong in `config/config.toml` under `[ollama.options]`. Ollama daemon
environment variables belong in Ollama's own service or container configuration.

Optional provider keys use the `PROVIDER_API_KEY` pattern:

```bash
OPENAI_API_KEY=...
OPENROUTER_API_KEY=...
GEMINI_API_KEY=...
BRAVE_SEARCH_API_KEY=...
PARALLEL_API_KEY=...
TAVILY_API_KEY=...
EXA_API_KEY=...
FIRECRAWL_API_KEY=...
HUGGINGFACE_API_KEY=...
CRAWL4AI_API_KEY=...
```

Cloud chat models are optional and do not replace local Ollama embeddings or
knowledge indexing. Install their SDKs with `uv sync --extra cloud`. For a
ChatGPT-backed Codex model, install the official `codex` CLI and run
`klaude auth login openai-codex`; Klaude delegates device login, secure storage,
refresh, and logout to that installation and never copies its tokens. OpenAI API
key access remains a separate provider configured with `OPENAI_API_KEY`.
OpenRouter uses `OPENROUTER_API_KEY` with its live, text-chat model catalog, and
Gemini API access uses `GEMINI_API_KEY`. API keys for every configured cloud
model, web-search, hosted-fetch/crawl, and Hugging Face provider can be pasted
through the masked **Settings → Providers** composer; Klaude atomically saves
them only in the private, gitignored `config/.env` with owner-only permissions
and never places them in transcript, session, input history, or preferences.
SearXNG's deployment secret remains separately managed in `config/searxng.env`.
In chat,
`/model` groups OpenAI Codex, OpenAI API, OpenRouter, and Gemini API under Cloud,
with Ollama under Local. Every Cloud provider page starts with Login (or Logout
when connected); API-key login is masked and Codex uses the official device
flow. Typing in any picker filters and ranks the closest matching choices.
`klaude models`
remains the local Ollama diagnostic. Saved selections use canonical references
such as `openai_codex/gpt-5.6-sol`, `openai_api/gpt-5`, or
`openrouter/anthropic/claude-sonnet-4`; older saved bare model names continue to
mean Ollama.

### Additional model connections

Register an Ollama server or a server exposing Chat Completions, such as a
configured llama.cpp or vLLM server:

```bash
klaude model-connections add lab --adapter openai_compatible --url http://192.168.1.20:8080/v1
klaude model-connections test lab
klaude chat --model openai_compatible@lab/MODEL_ID
klaude ask "Read README.md and summarize the project" --model openai_compatible@lab/MODEL_ID
```

Use `--adapter ollama` for the native Ollama API. `--key-env VARIABLE` references
a key in private `config/.env` or the process environment; it never accepts the
key itself as a command argument. `--cloud` requires HTTPS. Testing a connection
reads its catalog without loading a model; Ctrl+C cancels the owned worker.
A successful catalog check does not verify tool, vision, or reasoning support.

Connections live in private `config/model-connections.json`. The first Add or
Test migrates existing native choices once, retaining config roles and session
preferences. Qualified references distinguish identical model IDs on different
endpoints. Existing native aliases still work; chat remembers the qualified
selection across launches. Missing or disabled qualified connections fail
explicitly, preserving the saved selection.

The compatible runtime needs no cloud SDK. It sends portable temperature and
output-budget controls, streams text/tool calls, and retains native provider
runtimes separately. Context allocation and server-specific reasoning, GPU, and
thread controls remain server settings; Klaude uses a bounded conversation
budget without claiming it changed the server's allocation. Unknown compatible
servers default to one worker, with the existing explicit concurrency override.
Add/Added Models settings and Model Defaults are implemented. See the
[S1 validation](docs/s1-model-connections-validation.md),
[connection UI validation](docs/s2-model-settings-validation.md) and
[Model Defaults validation](docs/s2b-ai-defaults-validation.md) for evidence and limits.

DeepSeek is available under Add Models → Add API Models → Provider, or
`/model` → Cloud → DeepSeek → Add DeepSeek endpoint. Its key is entered through
the masked draft composer and saved only when Add is accepted. Scripted setup
can instead reference `DEEPSEEK_API_KEY` from private `config/.env`:

```bash
klaude model-connections add deepseek --adapter deepseek --url https://api.deepseek.com/v1
klaude model-connections test deepseek
klaude ask --model deepseek@deepseek/MODEL_ID "Your question"
```

Use a model ID returned by the catalog. Registration requires HTTPS and does not
generate text or change your default model. Registered models work with Session
model, Default Chat and Utility. Standard mode disables DeepSeek thinking;
thinking mode retains continuation privately without displaying it. Existing
provider connections remain unchanged. See the
[DeepSeek validation and live-cloud limits](docs/s2c-deepseek-validation.md).

Anthropic is also available in Add API Models or `/model` → Cloud → Anthropic →
Add Anthropic endpoint. The endpoint form uses a masked, connection-owned key.
Scripted registration references `ANTHROPIC_API_KEY` from private `config/.env`
or the environment:

```bash
klaude model-connections add anthropic --adapter anthropic --url https://api.anthropic.com/v1
klaude model-connections test anthropic
klaude ask --model anthropic@anthropic/MODEL_ID "Your question"
```

Use a model ID from the catalog. The native Messages adapter needs no cloud SDK
and keeps signed thinking blocks private. Mode and effort choices use declared
catalog capabilities. Models that require thinking show Thinking with the lowest
supported effort, retaining the configured output cap; they are unavailable for
the tool-free, thinking-disabled Utility role. Older catalogs with unknown
thinking support need updated metadata before Thinking can run. Manual thinking
also requires an output budget above 1,024 tokens; Klaude reports insufficient
budgets without increasing them. Local protocol checks passed; live paid
generation remains unverified. See the
[Anthropic validation](docs/s2c-anthropic-validation.md).

Klaude uses relevance-first provider routing for web search. Configured
providers are tried according to query intent, missing optional keys are skipped
quietly, and keyless Brave website search through the local DDGS adapter is the
default first provider. DDGS metasearch and local SearXNG are the next free
fallbacks. No API credential or per-query fee is required for those adapters,
but third-party websites can change access rules, throttle traffic, or present a
bot challenge at any time. The optional `brave_api` provider uses the official
Brave Search API when `BRAVE_SEARCH_API_KEY` is configured and may incur charges.
Tavily is an optional hosted Search provider: queries leave
your machine, free monthly credits are limited, and Klaude falls back to other
providers when Tavily is missing, invalid, rate-limited, unavailable, or out of
credits. Search/fetch evidence remains temporary and is not written to memory or
learned libraries.

In chat, ordinary browsing is a bounded model-directed loop: Klaude searches
for source leads, inspects snippets, selectively reads promising pages, and can
refine the query around the most important missing information. The runtime
prevents repeated equivalent searches and canonical duplicate fetches, keeps a
compact per-turn action/source trace, and enforces the configurable
`[web.search.behavior]` action, search, fetch, per-domain, and consecutive-failure
budgets. When a budget is exhausted, Klaude answers from the evidence already
gathered and identifies material uncertainty instead of discarding the work.

Browsing and learning are deliberately separate. `fetch_url` supplies temporary
evidence for the current turn, while an explicit request such as `Learn this
page into my react library: URL` exposes the permission-gated `learn_source`
tool. It accepts public HTTP(S) sources, rejects credentials embedded in URLs,
indexes a single page by default, and crawls only when the user explicitly asks
for a site, documentation set, or multiple pages. Site learning remains bounded
by the crawler's same-domain, robots, depth, page-count, and path constraints.

For explicit reachability, status-code, or redirect diagnostics, Klaude also
provides a restricted `http_probe` tool. It returns bounded response metadata
from public HTTP(S) endpoints without exposing request headers, credentials,
bodies, cookies, proxy settings, or page content to the model. Failed or
disabled web tools never silently fall back to `curl` or other shell networking.

Interactive chats show concise activity updates by default. The footer tracks
live states such as working, exploring, editing, running, learning, and waiting,
while the transcript retains completed `[EXPLORED]`, `[EDITED]`, `[RAN]`, and
`[LEARNED]` milestones.
These updates describe observable tool activity only—not private model
reasoning—and remain visible to clients following or resuming the session. They
can be disabled under `/settings` → Tools → Activity Updates.

Tavily integration status:

- Implemented: `web_search` can use Tavily Search through the provider router.
- Postponed: Tavily Extract, Crawl, Map, and Research are not exposed as Klaude
  tools. `fetch_url` keeps using Klaude's local direct/Crawl4AI/trafilatura
  cascade, and `crawl_site` keeps using Klaude's bounded same-domain crawler.
- Disable Tavily by leaving `TAVILY_API_KEY` empty or setting
  `[web.providers.tavily] enabled = false` in `config/config.toml`.
- Test Tavily without exposing secrets with
  `uv run klaude search "test query using Tavily" -n 3`.

Firecrawl integration status:

- Implemented: `web_search` can use Firecrawl Search through the provider
  router. Klaude uses Firecrawl's v2 Search API and does not request scraped
  page content for every result.
- Postponed: Firecrawl Scrape, Crawl, Map, Monitor, Parse, Interact, and
  Research are not exposed as Klaude tools. `fetch_url` keeps using Klaude's
  local direct/Crawl4AI/trafilatura cascade, and `crawl_site` keeps using
  Klaude's bounded same-domain crawler.
- Disable Firecrawl by leaving `FIRECRAWL_API_KEY` empty or setting
  `[web.providers.firecrawl] enabled = false` in
  `config/config.toml`.
- Test Firecrawl without exposing secrets with
  `uv run klaude search "test query using Firecrawl" -n 3`.

Codex MCP access to Tavily or Firecrawl is separate from Klaude-code native
integration. MCP tools configured for this Codex coding session do not
automatically make those providers available to Klaude's Ollama models.

Billing is conservative by default:

```toml
[web.billing]
mode = "prepaid_free_search_allowance"
allow_paid_overage = false
allow_auto_recharge = false
```

To prioritize one provider with compatibility fallbacks, set `[web] provider =
"local"` for SearXNG-only search, `provider = "brave"` for Brave-first search,
`provider = "brave_api"` for the official paid API, or `provider = "exa"` for
Exa-first search. A query can explicitly select keyless Brave with wording such
as `using Brave` or `provider: brave`.

Hugging Face Hub lookup is separate from web search and works against public
models, datasets, and Spaces by default. Add `HUGGINGFACE_API_KEY` to `config/.env`
when you want authenticated Hub access.

## Optional: JS-heavy scraping tier

```bash
docker compose --profile heavy up -d   # starts Crawl4AI
# then in config/config.toml:
# [services] crawl4ai_url = "http://localhost:11235"
```

Without it, fetching falls back to raw HTTP + trafilatura extraction (works for most docs sites). `klaude crawl` is intentionally conservative: same-domain only, robots.txt on by default, 50-page cap, depth 2, and a randomized 2-5 second delay between pages. Use `--sitemap` to seed URLs from robots.txt Sitemap entries and `/sitemap.xml`, `--include` / `--exclude` to constrain URL patterns, and tune defaults under `[crawler]` in config when you control the target site.

## License

MIT

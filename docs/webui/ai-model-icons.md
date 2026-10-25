# Local AI model logos

Assets live in apps/webhost/src/klaude_webhost/static/icons/ai. The existing
user-added cat SVG files in static/icons are untouched.

Source: https://github.com/lobehub/lobe-icons, npm package
@lobehub/icons-static-svg version 1.98.0, MIT licensed. LICENSE and manifest.json
record the attribution, exact archive URL/integrity and individual SVG hashes.
The gpt file aliases OpenAI, llama aliases Meta and phi aliases Microsoft;
these represent the model families' makers rather than invented family logos.
The generic model icon uses Klaude's existing layers artwork.

Available marks: GPT/OpenAI, Gemini/Google, Ollama, OpenRouter, Claude/Anthropic,
Kimi/Moonshot, Phi/Microsoft, Llama/Meta, Qwen, DeepSeek, Mistral, Gemma,
Grok/xAI, Cohere, NVIDIA, Hugging Face and Perplexity.

Chat's current model button and pending model selection label, plus the Models
catalog, render local alpha-mask SVGs in the surrounding theme's text color.
Model reference families take precedence over provider fallbacks, so an Ollama
Qwen model shows Qwen. Gemma's numeric-version names (`gemma2`, `gemma3`,
`gemma3n`), uppercase tags and namespaced/configured connection references also
use the Gemma mark. Unknown models use a known provider or the generic icon.
The native dropdown options remain text-only; their existing keyboard and
selection behavior is preserved. No runtime CDN or framework dependency added.

HTTP serves only fixed AI asset names with SVG MIME, CSP and nosniff headers.
No arbitrary static file publishing or upload handling is introduced.

Validation: test_webhost_ai_icons.py checks XML structure, asset hashes,
license, every icon response and unknown/traversal boundaries. The existing
webui_models_smoke.py checks family/provider/fallback selection, actual local
asset loading, responsive geometry and configured/legacy runtime behavior.
Package smoke now requires the requested logos, license and manifest in wheels.

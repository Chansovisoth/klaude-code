#!/usr/bin/env bash
# klaude-code bootstrap. Idempotent — safe to re-run.
#
# Flags (all optional; interactive menu covers everything):
#   --ollama=existing|system|docker|url:URL|skip   choose Ollama mode non-interactively
#   --no-models                                    skip model pulls
set -euo pipefail
cd "$(dirname "$0")/.."

say()  { printf '\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m==> %s\033[0m\n' "$*"; }

# --- parse flags ------------------------------------------------------------
OLLAMA_MODE=""
NO_MODELS=0
for arg in "$@"; do
  case "$arg" in
    --ollama=*) OLLAMA_MODE="${arg#--ollama=}" ;;
    --no-models) NO_MODELS=1 ;;
  esac
done

# 1. uv ------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  say "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# 2. ollama: detect, then let the user decide ---------------------------------
OLLAMA_URL="http://localhost:11434"
PULL_CMD="ollama pull"

DETECTED=""
if command -v ollama >/dev/null 2>&1; then
  DETECTED="cli"
elif curl -fsS --max-time 2 "http://localhost:11434/api/tags" >/dev/null 2>&1; then
  DETECTED="port"   # daemon answering but no CLI on PATH (e.g. dockerized)
fi

if [ -z "$OLLAMA_MODE" ]; then
  if [ -t 0 ]; then
    if [ -n "$DETECTED" ]; then
      N=$(curl -fsS --max-time 2 "http://localhost:11434/api/tags" 2>/dev/null \
          | grep -o '"name"' | wc -l | tr -d ' ')
      say "found existing Ollama at localhost:11434 (${N:-?} models installed)"
      DEFAULT=1
    else
      warn "no Ollama detected on this machine"
      DEFAULT=2
    fi
    echo "How do you want to run Ollama?"
    echo "  [1] Use the existing one at localhost:11434"
    echo "  [2] Install system-wide (official installer -- best GPU support)"
    echo "  [3] Run in Docker via klaude's compose file (self-contained;"
    echo "      CPU-only unless the NVIDIA container toolkit is installed)"
    echo "  [4] Use a remote Ollama -- enter its URL"
    echo "  [5] Skip -- configure later"
    read -r -p "choice [${DEFAULT}]: " CHOICE
    CHOICE="${CHOICE:-$DEFAULT}"
    case "$CHOICE" in
      1) OLLAMA_MODE="existing" ;;
      2) OLLAMA_MODE="system" ;;
      3) OLLAMA_MODE="docker" ;;
      4) OLLAMA_MODE="url" ;;
      5) OLLAMA_MODE="skip" ;;
      *) OLLAMA_MODE="existing" ;;
    esac
  else
    # non-interactive (curl | bash, CI): sane defaults, no questions
    if [ -n "$DETECTED" ]; then OLLAMA_MODE="existing"; else OLLAMA_MODE="system"; fi
  fi
fi

case "$OLLAMA_MODE" in
  existing)
    if [ -z "$DETECTED" ]; then
      warn "no local Ollama found -- falling back to system install"
      say "installing Ollama system-wide (official installer)"
      curl -fsSL https://ollama.com/install.sh | sh
    else
      say "using existing Ollama at ${OLLAMA_URL}"
    fi
    ;;
  system)
    say "installing Ollama system-wide (official installer)"
    curl -fsSL https://ollama.com/install.sh | sh
    ;;
  docker)
    say "Ollama will run in Docker (compose profile: selfhosted)"
    PULL_CMD="docker exec klaude-ollama ollama pull"
    ;;
  url|url:*)
    if [ "$OLLAMA_MODE" = "url" ]; then
      read -r -p "Ollama URL (e.g. http://192.168.1.50:11434): " OLLAMA_URL
    else
      OLLAMA_URL="${OLLAMA_MODE#url:}"
    fi
    say "using remote Ollama at ${OLLAMA_URL}"
    warn "model pulls will be skipped -- pull models on the remote host"
    NO_MODELS=1
    ;;
  skip)
    warn "skipping Ollama setup -- klaude will not work until it's configured"
    NO_MODELS=1
    ;;
  *)
    warn "unknown --ollama mode '${OLLAMA_MODE}'"; exit 1
    ;;
esac

# 3. docker services ------------------------------------------------------
# secrets live in .env (gitignored), generated from .env.example on first run
if [ ! -f .env ]; then
  say "generating .env with secrets"
  KEY=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
  sed "s/^SEARXNG_SECRET=.*/SEARXNG_SECRET=${KEY}/" .env.example > .env
  chmod 600 .env
fi
if command -v docker >/dev/null 2>&1; then
  if [ "$OLLAMA_MODE" = "docker" ]; then
    say "starting searxng + ollama (docker compose --profile selfhosted up -d)"
    docker compose --profile selfhosted up -d
    say "waiting for containerized ollama to answer"
    for _ in $(seq 1 30); do
      curl -fsS --max-time 2 "http://localhost:11434/api/tags" >/dev/null 2>&1 && break
      sleep 2
    done
  else
    say "starting searxng (docker compose up -d)"
    docker compose up -d
  fi
else
  if [ "$OLLAMA_MODE" = "docker" ]; then
    warn "ERROR: the Docker option requires Docker. Install Docker first."
    exit 1
  fi
  warn "docker not found -- web search will not work until you install it"
fi

# 4. python workspace ---------------------------------------------------------
say "syncing python workspace (uv sync)"
uv sync

# 5. models by hardware tier ---------------------------------------------------
if [ "$NO_MODELS" = "1" ]; then
  say "skipping model pulls"
else
  MEM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
  if   [ "$MEM_GB" -ge 28 ]; then TIER=full;     MODELS="qwen3-coder:30b qwen3:4b minicpm-v nomic-embed-text"
  elif [ "$MEM_GB" -ge 12 ]; then TIER=standard; MODELS="gpt-oss:20b qwen3:4b minicpm-v nomic-embed-text"
  else                            TIER=lite;     MODELS="qwen3:4b qwen3:1.7b nomic-embed-text"
  fi
  say "detected ${MEM_GB}GB RAM -> tier '${TIER}'"
  INSTALLED=$(curl -fsS --max-time 5 "${OLLAMA_URL}/api/tags" 2>/dev/null \
              | grep -o '"name":"[^"]*"' | cut -d'"' -f4 || true)
  for m in $MODELS; do
    if echo "$INSTALLED" | grep -q "^${m%%:*}"; then
      say "already have $m -- skipping"
    else
      say "pulling $m"
      $PULL_CMD "$m"
    fi
  done
fi

# 6. config + verify -----------------------------------------------------------
mkdir -p "$HOME/.config/klaude"
CFG="$HOME/.config/klaude/config.toml"
[ -f "$CFG" ] || cp config/config.example.toml "$CFG"
if [ "$OLLAMA_URL" != "http://localhost:11434" ]; then
  say "writing ollama_url = ${OLLAMA_URL} to ${CFG}"
  if grep -q '^\[services\]' "$CFG"; then
    sed -i "/^\[services\]/a ollama_url = \"${OLLAMA_URL}\"" "$CFG"
  else
    printf '\n[services]\nollama_url = "%s"\n' "$OLLAMA_URL" >> "$CFG"
  fi
fi

say "running klaude doctor"
uv run klaude doctor || true

say "done. try:  uv run klaude chat"
say "or add to PATH:  uv tool install --editable apps/cli"

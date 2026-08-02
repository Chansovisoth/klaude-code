#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -n "${KLAUDE_HOME:-}" ]]; then
    DEFAULT_CONFIG_DIR="$KLAUDE_HOME/config"
else
    KLAUDE_HOME="$PROJECT_ROOT/.klaude"
    DEFAULT_CONFIG_DIR="$PROJECT_ROOT/config"
fi
KLAUDE_CONFIG_DIR="${KLAUDE_CONFIG_DIR:-$DEFAULT_CONFIG_DIR}"
KLAUDE_DATA_DIR="${KLAUDE_DATA_DIR:-$KLAUDE_HOME/data}"
export KLAUDE_HOME KLAUDE_CONFIG_DIR KLAUDE_DATA_DIR

DEFAULT_DOCS_FILE="$KLAUDE_CONFIG_DIR/online-docs.txt"
if [[ ! -f "$DEFAULT_DOCS_FILE" ]]; then
    if [[ -f "$PROJECT_ROOT/online-docs.txt" ]]; then
        DEFAULT_DOCS_FILE="$PROJECT_ROOT/online-docs.txt"
    else
        DEFAULT_DOCS_FILE="$PROJECT_ROOT/config/examples/online-docs.txt"
    fi
fi
DOCS_FILE="${KLAUDE_ONLINE_DOCS_FILE:-$DEFAULT_DOCS_FILE}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_ROOT="${KLAUDE_LOG_DIR:-$PROJECT_ROOT/logs}"
LOG_DIR="$LOG_ROOT/knowledge/online-docs"
RUN_LOG="$LOG_DIR/$RUN_ID-run.log"

mkdir -p "$LOG_DIR"
: > "$RUN_LOG"

if [[ ! -f "$DOCS_FILE" ]]; then
    printf 'Error: documentation list not found:\n  %s\n' "$DOCS_FILE" >&2
    exit 1
fi

cd "$PROJECT_ROOT" || exit 1

{
    printf '\nKlaude Online Documentation Installer\n'
    printf 'Project root: %s\n' "$PROJECT_ROOT"
    printf 'Source file:  %s\n' "$DOCS_FILE"
    printf 'Run log:      %s\n\n' "$RUN_LOG"
    KLAUDE_ONLINE_DOCS_FILE="$DOCS_FILE" uv run klaude docs update --online
} 2>&1 | tee -a "$RUN_LOG"

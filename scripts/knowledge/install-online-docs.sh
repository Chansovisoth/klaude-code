#!/usr/bin/env bash

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCS_FILE="$PROJECT_ROOT/online-docs.txt"

if [[ ! -f "$DOCS_FILE" ]]; then
    printf 'Error: documentation list not found:\n  %s\n' "$DOCS_FILE" >&2
    exit 1
fi

cd "$PROJECT_ROOT" || exit 1

total=0
successful=0
failed=0
skipped=0

declare -a failed_commands=()

printf '\nKlaude Online Documentation Installer\n'
printf 'Project root: %s\n' "$PROJECT_ROOT"
printf 'Source file:  %s\n\n' "$DOCS_FILE"

while IFS= read -r line || [[ -n "$line" ]]; do
    # Support files saved with Windows CRLF line endings.
    line="${line%$'\r'}"

    # Trim leading whitespace.
    line="${line#"${line%%[![:space:]]*}"}"

    # Ignore comments and blank lines.
    if [[ -z "$line" || "$line" == \#* ]]; then
        continue
    fi

    # Only process:
    # uv run klaude learn <URL_OR_PATH> -c <COLLECTION>
    read -r -a parts <<< "$line"

    if [[ ${#parts[@]} -ne 7 ]] ||
       [[ "${parts[0]}" != "uv" ]] ||
       [[ "${parts[1]}" != "run" ]] ||
       [[ "${parts[2]}" != "klaude" ]] ||
       [[ "${parts[3]}" != "learn" ]] ||
       [[ "${parts[5]}" != "-c" ]]; then
        ((skipped += 1))

        printf 'Skipped unsupported line:\n'
        printf '  %s\n\n' "$line"
        continue
    fi

    source="${parts[4]}"
    collection="${parts[6]}"

    ((total += 1))

    printf '────────────────────────────────────────────────────────────\n'
    printf '[%d] %s\n' "$total" "$collection"
    printf 'Source: %s\n\n' "$source"

    if uv run klaude learn "$source" -c "$collection"; then
        ((successful += 1))
        printf '\nResult: SUCCESS\n\n'
    else
        exit_code=$?
        ((failed += 1))
        failed_commands+=("$line")

        printf '\nResult: FAILED (exit code %d)\n\n' "$exit_code"
    fi
done < "$DOCS_FILE"

printf '============================================================\n'
printf 'Installation summary\n'
printf '============================================================\n'
printf 'Processed:  %d\n' "$total"
printf 'Successful: %d\n' "$successful"
printf 'Failed:     %d\n' "$failed"
printf 'Skipped:    %d\n' "$skipped"

if ((failed > 0)); then
    printf '\nFailed commands:\n'

    for command in "${failed_commands[@]}"; do
        printf '  %s\n' "$command"
    done

    exit 1
fi

printf '\nAll online documentation sources installed successfully.\n'

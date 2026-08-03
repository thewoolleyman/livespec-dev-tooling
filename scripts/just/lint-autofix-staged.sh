#!/usr/bin/env bash
set -euo pipefail

staged=$(git diff --cached --name-only --diff-filter=AM | grep -E '\.py$' || true)
if [[ -z "$staged" ]]; then
    exit 0
fi

echo "$staged" | xargs uv run ruff check --fix --exit-zero
echo "$staged" | xargs uv run ruff format
echo "$staged" | xargs git add

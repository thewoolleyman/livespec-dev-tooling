#!/usr/bin/env bash
set -euo pipefail

upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || echo "origin/master")
changeset=$(git diff --name-only "${upstream}..HEAD")
py_changed=$(echo "$changeset" | grep -E '\.py$' || true)

if [[ -z "$py_changed" ]]; then
    echo ":: doc-only push detected (zero .py changes vs ${upstream}): running check-pre-commit-doc-only"
    just check-pre-commit-doc-only
    exit $?
fi

if uv run python -m livespec_dev_tooling.green_token check 2>&1; then
    echo ":: pre-push: green token matched - tree byte-identical to last green check; skipping full aggregate (CI is authoritative)"
    exit 0
fi

just check

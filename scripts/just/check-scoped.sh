#!/usr/bin/env bash
set -euo pipefail

upstream="origin/master"
changeset=$(git diff --name-only "${upstream}...HEAD")
if [[ -z "$changeset" ]]; then
    echo ":: check-scoped: no changes vs ${upstream}; nothing to gate"
    exit 0
fi

py_changed=$(echo "$changeset" | grep -E '\.py$' || true)
if [[ -z "$py_changed" ]]; then
    echo ":: check-scoped: no .py changes vs ${upstream} (change class: doc/config/deletion)"
    echo ":: running fast doc-only subset; CI runs the full matrix as the load-bearing gate"
    just check-pre-commit-doc-only
    exit $?
fi

echo ":: check-scoped: .py changes detected vs ${upstream}: running full check aggregate"
just check

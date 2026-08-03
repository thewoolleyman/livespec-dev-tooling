#!/usr/bin/env bash
set -euo pipefail

base=$(git merge-base HEAD origin/master 2>/dev/null || git merge-base HEAD master)
if git diff --quiet --name-only "$base"...HEAD -- .github/workflows; then
    exit 0
fi

echo "ERROR: factory branches must not modify .github/workflows/ files" >&2
git diff --name-only "$base"...HEAD -- .github/workflows >&2
exit 1

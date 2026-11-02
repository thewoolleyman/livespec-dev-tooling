#!/usr/bin/env bash
set -euo pipefail

# The gate Job's entry for a delegated pre-commit aggregate. The Job checks out
# the staged-tree commit the committing host published, so its index is clean
# and the hook's `git diff --cached` would be empty. Rewind HEAD to that
# commit's parent, keeping index and working tree, so the unchanged hook sees
# the staged files and the HEAD that the committing host saw.
gated_tree=$(git rev-parse 'HEAD^{tree}')
if [[ "$(git rev-list --parents -n 1 HEAD | wc -w)" -ne 2 ]]; then
    echo "FATAL: the gated staged-tree commit must have exactly one parent; no member was run, this gate is RED" >&2
    exit 1
fi
git reset --soft 'HEAD^'
if [[ "$(git write-tree)" != "$gated_tree" ]]; then
    echo "FATAL: rewinding to the staged commit's parent changed the gated tree; no member was run, this gate is RED" >&2
    exit 1
fi
exec scripts/just/check-pre-commit.sh

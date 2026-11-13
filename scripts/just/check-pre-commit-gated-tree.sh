#!/usr/bin/env bash
set -euo pipefail

# The gate Job's entry for a delegated pre-commit aggregate. The Job checks out
# the staged-tree commit the committing host published, so its index is clean
# and the hook's `git diff --cached` would be empty. Rewind HEAD to that
# commit's first parent, keeping index and working tree, so the unchanged hook
# the staged files and the HEAD that the committing host saw. A merge commit's
# remaining parents are restored as MERGE_HEAD so its checks receive the same
# merge state as the committing host.
gated_tree=$(git rev-parse 'HEAD^{tree}')
read -r -a parents <<< "$(git rev-list --parents -n 1 HEAD)"
if [[ ${#parents[@]} -lt 2 ]]; then
    echo "FATAL: the gated staged-tree commit must have a parent; no member was run, this gate is RED" >&2
    exit 1
fi
git reset --soft "${parents[1]}"
merge_head_file=$(git rev-parse --git-path MERGE_HEAD)
if [[ ${#parents[@]} -gt 2 ]]; then
    printf '%s\n' "${parents[@]:2}" > "$merge_head_file"
else
    rm -f "$merge_head_file"
fi
if [[ "$(git write-tree)" != "$gated_tree" ]]; then
    echo "FATAL: rewinding to the staged commit's parent changed the gated tree; no member was run, this gate is RED" >&2
    exit 1
fi
exec scripts/just/check-pre-commit.sh

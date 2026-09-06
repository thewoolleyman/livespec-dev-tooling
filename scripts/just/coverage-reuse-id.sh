#!/usr/bin/env bash
set -euo pipefail

# Coverage-reuse provenance id (work-item livespec-dev-tooling-sc0z).
#
# check-per-file-coverage (the PRODUCER) writes this id into
# .livespec-coverage-reuse-token beside the repo-root .coverage it produced;
# check-coverage (the CONSUMER) reuses that .coverage only when the id it
# resolves for itself is the same string. The id is a digest of the TRACKED
# tree state — HEAD plus every tracked change against it — so a marker binds
# the data file to the exact source it measured: a later edit, a commit, a
# rebase, or a checkout invalidates it, and a .coverage that never went
# through the producer (a focused `pytest --cov` run at the repo root) has no
# marker at all.
#
# Outside a git work tree (or before the first commit) there is no tree
# state to bind to: exit non-zero with nothing on stdout, and both callers
# treat that as "no reuse".
root="$(git rev-parse --show-toplevel)"
digest="$(
    {
        git -C "$root" rev-parse HEAD
        git -C "$root" diff --binary HEAD -- .
    } | sha256sum | awk '{ print $1 }'
)"
printf 'git-tree:%s\n' "$digest"

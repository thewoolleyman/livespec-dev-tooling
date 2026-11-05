#!/usr/bin/env bash
set -euo pipefail

# Coverage-reuse provenance id (work-items livespec-dev-tooling-sc0z and
# livespec-dev-tooling-ifhymw).
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
# The failure form deliberately binds only the suite outcome to the tracked
# tree: a failed pytest run has no coverage data that the consumer may read.
# Outside a git work tree (or before the first commit) there is no tree state
# to bind to: exit non-zero with nothing on stdout, and both callers treat that
# as "no reuse".
receipt_kind="${1:-success}"
case "$receipt_kind" in
    success|failure) ;;
    *)
        echo "usage: $0 [success|failure]" >&2
        exit 2
        ;;
esac
root="$(git rev-parse --show-toplevel)"
digest="$(
    {
        git -C "$root" rev-parse HEAD
        git -C "$root" diff --binary HEAD -- .
    } | sha256sum | awk '{ print $1 }'
)"
if [[ "$receipt_kind" == "failure" ]]; then
    printf 'git-tree:%s:normal:full-suite:pytest-failure\n' "$digest"
    exit 0
fi
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-xluwqj
# Bind the receipt to the measured bytes as well as the tree. A focused run
# can overwrite .coverage without changing any tracked source file.
coverage_file="${COVERAGE_FILE:-.coverage}"
coverage_digest="$(sha256sum "$coverage_file" | awk '{ print $1 }')"
printf 'git-tree:%s:normal:full-suite:coverage:%s\n' "$digest" "$coverage_digest"

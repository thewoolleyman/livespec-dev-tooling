#!/usr/bin/env bash
set -euo pipefail

# PR gate ≡ master gate (plan pr-gate-master-parity, livespec-citqsd R3):
# pre-push runs the FULL `just check` aggregate — the same set CI runs on a
# pull_request and on a push to master. The former zero-.py doc-only branch
# (delegating to check-pre-commit-doc-only) was RETIRED: it made a doc-only
# push run fewer checks than master, the exact PR-gate-weaker-than-master hole
# that reddened master on 2026-09-04. The green-token clean-tree skip below is
# KEPT — it is sound (a byte-identical tree provably yields an identical check
# result), not a `.py`-predicate that can rot.

if uv run python -m livespec_dev_tooling.green_token check 2>&1; then
    echo ":: pre-push: green token matched - tree byte-identical to last green check; skipping full aggregate (CI is authoritative)"
    exit 0
fi

# `hook_gate=1` omits the world-gate members enumerated in check.sh. The
# aggregate is otherwise unchanged, so PR gate ≡ master gate still holds for
# every member CI runs: the one omitted member is not in the CI matrix either,
# because the App installation token CI authenticates with deliberately lacks
# admin scope (work-item livespec-dev-tooling-mmqe, absorbing tkzf).
just hook_gate=1 check

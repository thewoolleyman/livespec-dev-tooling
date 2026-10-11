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

# The DELEGATED-GATE fall-through (R4.S7c of plan livespec
# `k3s-on-gmktec-for-vps-usage`; the contract is this repo's
# SPECIFICATION/contracts.md §"Delegated pre-push gate"). This repo HAS opted in
# — `delegated_gate = true` in its own `[tool.livespec_dev_tooling]` block — so
# which branch a push takes is decided by the host, not by this file. Only the
# FALL-THROUGH is ever replaced: the green-token skip above is untouched, because
# a delegated pass writes the SAME token through the SAME CLI a local aggregate
# does, so a byte-identical tree is skippable whichever path gated it.
#
# The probe's exit code is the whole answer, and it answers for THIS PUSH: the
# switch AND whether the pushing user can read the gates kubeconfig on this host.
# From the VPS, which holds the credential, that is 0 and the gate runs on the
# cluster; from a Fabro sandbox or a laptop it is non-zero and the probe itself
# prints that this push gated locally. Every doubt it can have — an absent key, a
# `false`, a malformed pyproject, a traceback, no credential — exits non-zero and
# lands here, on the strict local path, which is the only direction in which a
# mistake is merely expensive rather than an ungated push.
#
# Once delegation IS selected, this is the last local branch: a delegated run
# that reaches no verdict REFUSES the push rather than falling through to the
# aggregate below, because "we could not gate this" must never quietly become
# "we gated it some other way".
if uv run python -m livespec_dev_tooling.gate_remote_delegate enabled; then
    echo ":: pre-push: delegated gate is enabled for this repo; gating on the cluster"
    exec uv run python -m livespec_dev_tooling.gate_remote_delegate run
fi

# `hook_gate=1` omits the world-gate members enumerated in check.sh. The
# aggregate is otherwise unchanged, so PR gate ≡ master gate still holds for
# every member CI runs: the one omitted member is not in the CI matrix either,
# because the App installation token CI authenticates with deliberately lacks
# admin scope (work-item livespec-dev-tooling-mmqe, absorbing tkzf).
just hook_gate=1 check

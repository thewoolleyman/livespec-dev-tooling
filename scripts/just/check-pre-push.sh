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

# A DELETE-ONLY PUSH publishes no tree, so there is nothing for any gate below
# to judge (work-item livespec-dev-tooling-r4oj47). git feeds the pre-push hook
# one `<local ref> <local oid> <remote ref> <remote oid>` line per ref update on
# standard input and spells a deletion as an ALL-ZERO local oid. Read unread,
# those lines made `git push origin --delete <branch>` run the same aggregate a
# publish runs, against whatever happened to be checked out — a tree unrelated
# to the ref being removed. Measured 2026-10-12 on the VPS: a verifier session's
# remote-branch delete from a livespec-dev-tooling worktree held its pre-push
# hook about 272 s for that answer.
#
# This is NOT the retired doc-only subset the comment above convicts. That
# branch ran FEWER checks over a tree it was still PUBLISHING, and it failed by
# passing. Here nothing is published, so there is no weaker verdict to issue:
# the gate is not narrowed, it is inapplicable. And the discrimination is keyed
# on the refs git itself names, not on a change class read off the working tree,
# so there is no predicate that can rot into a subset.
#
# Fail-CLOSED on emptiness: no input is no EVIDENCE, not "nothing to publish".
# A hand-run `just check-pre-push`, a lefthook build that does not forward
# standard input, or any future transport that stops naming refs all arrive as
# emptiness, and reading that as a delete-only push would skip the gate on every
# push. Likewise a line whose oid field is missing or unparseable counts as a
# ref update, so a shape this loop does not understand still gates.
#
# The `-t 0` guard is load-bearing in the other direction: lefthook forwards the
# hook's standard input only to a command declaring `use_stdin: true` (the
# `01-check-pre-push` entry does, and `just` passes its own standard input
# through to this script), while a `just check-pre-push` run by hand from a
# terminal has no refs to read at all — reading it there would block on the tty
# forever rather than gate.
push_refs=""
if [ ! -t 0 ]; then
    push_refs="$(cat)"
fi

ref_updates=0
deleted_refs=0
while IFS=' ' read -r local_ref local_oid _; do
    [ -n "${local_ref}" ] || continue
    ref_updates=$((ref_updates + 1))
    case "${local_oid}" in
        "" | *[!0]*) ;;
        *) deleted_refs=$((deleted_refs + 1)) ;;
    esac
done <<<"${push_refs}"

if [ "${ref_updates}" -gt 0 ] && [ "${ref_updates}" -eq "${deleted_refs}" ]; then
    echo ":: pre-push: skipping the gate - this push only deletes refs (${deleted_refs}), and a deletion publishes no tree to check"
    exit 0
fi

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

diagnose_host_state_divergence() {
    local gate_output="$1"
    local gate_text
    local green_run
    local green_run_id
    local green_sha
    local checkout
    local rerun_output
    local rerun_status
    local node_id
    local -a failed_nodes
    local -a rerun_failures

    # Pytest's short summary is the one stable place the aggregate exposes the
    # individual node ids. A non-pytest check failure has no node to replay and
    # therefore no host-state comparison to make.
    gate_text="$(<"$gate_output")"
    gate_text="${gate_text//\\n/$'\n'}"
    mapfile -t failed_nodes < <(printf '%s\n' "$gate_text" | sed -n 's/^FAILED \([^[:space:]]*\) .*/\1/p')
    if [ "${#failed_nodes[@]}" -eq 0 ]; then
        return
    fi

    # `gh run list` is newest-first. Ask for the last 20 master runs before
    # selecting the first success, rather than asking GitHub for 20 successes:
    # the latter could silently reach arbitrarily far back through red runs.
    if ! green_run="$(gh run list --workflow CI --branch master --limit 20 \
        --json databaseId,headSha,conclusion \
        --jq '.[] | select(.conclusion == "success") | [.databaseId, .headSha] | @tsv' \
        2>/dev/null)"; then
        echo ":: pre-push: host-state divergence check skipped: unable to determine a green CI run"
        return
    fi
    green_run="$(printf '%s\n' "$green_run" | sed -n '1p')"
    if [ -z "$green_run" ]; then
        echo ":: pre-push: host-state divergence check skipped: no successful CI workflow run among the last 20 master runs"
        return
    fi
    # `gh --jq @tsv` writes a real tab. Accept an escaped tab too, because a
    # transport that preserves JSON-style escapes still names the same pair.
    green_run="${green_run//\\t/$'\t'}"
    IFS=$'\t' read -r green_run_id green_sha <<<"$green_run"
    if [ -z "$green_run_id" ] || [ -z "$green_sha" ]; then
        echo ":: pre-push: host-state divergence check skipped: green CI run did not identify its commit"
        return
    fi

    if ! git fetch --quiet origin master; then
        echo ":: pre-push: host-state divergence check skipped: could not fetch origin/master"
        return
    fi
    if ! checkout="$(mktemp -d)"; then
        echo ":: pre-push: host-state divergence check skipped: could not create a temporary checkout"
        return
    fi
    if ! git worktree add --detach "$checkout" "$green_sha"; then
        rm -rf "$checkout"
        echo ":: pre-push: host-state divergence check skipped: could not check out green CI commit"
        return
    fi

    rerun_output="$(mktemp)"
    set +e
    (
        cd "$checkout"
        uv run pytest "${failed_nodes[@]}"
    ) >"$rerun_output" 2>&1
    rerun_status=$?
    set -e
    cat "$rerun_output"
    mapfile -t rerun_failures < <(sed -n 's/^FAILED \([^[:space:]]*\) .*/\1/p' "$rerun_output")
    for node_id in "${failed_nodes[@]}"; do
        if printf '%s\n' "${rerun_failures[@]}" | grep -Fqx "$node_id"; then
            echo ":: pre-push: host-state divergence: ${node_id} also fails on green CI run ${green_run_id}"
        fi
    done
    rm -f "$rerun_output"
    git worktree remove --force "$checkout" || true
    rm -rf "$checkout"
    return "$rerun_status"
}

# `hook_gate=1` omits the world-gate members enumerated in check.sh. The
# aggregate is otherwise unchanged, so PR gate ≡ master gate still holds for
# every member CI runs: the one omitted member is not in the CI matrix either,
# because the App installation token CI authenticates with deliberately lacks
# admin scope (work-item livespec-dev-tooling-mmqe, absorbing tkzf).
gate_output="$(mktemp)"
trap 'rm -f "$gate_output"' EXIT
set +e
just hook_gate=1 check >"$gate_output" 2>&1
gate_status=$?
set -e
cat "$gate_output"
if [ "$gate_status" -ne 0 ]; then
    diagnose_host_state_divergence "$gate_output" || true
    exit "$gate_status"
fi

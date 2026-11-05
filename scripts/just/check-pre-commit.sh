#!/usr/bin/env bash
set -euo pipefail

# Resolve incident mode before any gate work (livespec-dev-tooling-6bmta2). The
# presence test is the installed hook's prefilter and decides nothing: unset, the
# body below runs unchanged; present, the shared boundary
# (livespec_dev_tooling/incident_gate_entry.py) parses and decides, and only its
# 75 continues. Every other status, including an unavailable boundary, refuses.
if [ -n "${EXPEDITED_INCIDENT_RESPONSE:-}${EXPEDITED_INCIDENT_RESPONSE_REVERT:-}${LIVESPEC_INCIDENT_CONTEXT:-}${LIVESPEC_INCIDENT_AUTHORITY_QUERY:-}" ]; then
    incident_status=0
    uv run --no-sync python -m livespec_dev_tooling.incident_gate_entry check-pre-commit || incident_status=$?
    [ "$incident_status" -eq 75 ] || exit $((incident_status == 0 ? 78 : incident_status))
fi

if [[ -z "$(git diff --cached --name-only)" ]]; then
    echo ":: empty commit detected (nothing staged at all): repo-state gates have nothing to gate; exit 0"
    exit 0
fi

staged=$(git diff --cached --name-only --diff-filter=AM)
py_staged=$(echo "$staged" | grep -E '\.py$' || true)
test_staged=$(echo "$staged" | grep -E '^tests/.*\.py$' || true)
impl_staged=$(echo "$staged" | grep -E '^livespec_dev_tooling/.*\.py$' || true)
test_count=0
impl_count=0
[[ -n "$test_staged" ]] && test_count=$(echo "$test_staged" | wc -l)
[[ -n "$impl_staged" ]] && impl_count=$(echo "$impl_staged" | wc -l)

# The staged-file pre-check and the delegation decision come BEFORE mode
# selection. Inside a gate Job (LIVESPEC_GATE_CONTEXT, set only by the Job
# template) neither runs: the committing host already ran the pre-check before
# it submitted the Job, and the Job must not delegate again.
if [[ -z "${LIVESPEC_GATE_CONTEXT:-}" ]]; then
    if [[ -n "$py_staged" ]]; then
        echo ":: staged-file pre-check: ruff + pyright on the staged Python files"
        uv run python -m livespec_dev_tooling.workflow_checks.staged_precheck
    fi

    set +e
    uv run python -m livespec_dev_tooling.pre_commit_delegate run
    delegate_status=$?
    set -e
    case "$delegate_status" in
        0)
            exit 0
            ;;
        75)
            ;;
        *)
            exit "$delegate_status"
            ;;
    esac
fi

if [[ -z "$py_staged" ]]; then
    echo ":: doc-only mode detected (zero .py files staged): running just check-pre-commit-doc-only"
    echo ":: pre-push + CI keep the full aggregate as the load-bearing safety net"
    just check-pre-commit-doc-only
    exit $?
fi

if [[ "$test_count" -eq 1 ]] && [[ "$impl_count" -eq 0 ]]; then
    echo ":: Red-mode shape detected: $test_staged"
    echo ":: scoping the Red gate by staged-path class (red_leg_scope): coverage gates skip"
    echo ":: (verified at the Green amend) + any orthogonal legs a staged unit test cannot affect"
    just red_staged="$test_staged" hook_gate=1 check
    exit $?
fi

# `hook_gate=1` omits the world-gate members enumerated in check.sh — today
# just check-fleet-conformance-admin, whose verdict is a fact about nine OTHER
# repositories' live admin state and so can refuse a commit that has nothing
# to do with it (work-item livespec-dev-tooling-mmqe, absorbing tkzf).
aggregate_log=$(mktemp "$(git rev-parse --git-path livespec-pre-commit-aggregate.XXXXXX)")
staged_tree=$(git write-tree)
set +e
just hook_gate=1 check 2>&1 | tee "$aggregate_log"
aggregate_status=${PIPESTATUS[0]}
set -e
# `just check` reads the working tree, so its verdict speaks for the staged
# tree only when the two are identical; with unstaged differences, or with
# untracked non-ignored files the suite may read, no token is recorded and
# commit-msg runs the full suite-green leg. The tree is captured BEFORE the
# aggregate and the token is written only if the index still names that tree
# afterwards, so a concurrent index change cannot certify a tree the suite
# never ran against.
if [[ "$aggregate_status" -eq 0 ]] && git diff --quiet \
    && [[ -z "$(git ls-files --others --exclude-standard)" ]] \
    && [[ "$(git write-tree)" == "$staged_tree" ]]; then
    run_id="pre-commit-aggregate:$(date -u +%Y%m%dT%H%M%SZ):${staged_tree}"
    output_checksum="sha256:$(sha256sum "$aggregate_log" | awk '{print $1}')"
    uv run python -m livespec_dev_tooling.green_token write-pre-commit "$run_id" "$output_checksum"
fi
rm -f "$aggregate_log"
exit "$aggregate_status"

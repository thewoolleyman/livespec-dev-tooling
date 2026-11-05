#!/usr/bin/env bash
set -euo pipefail

: "${test_nprocs:?}"

# Aggregate (total) `fail_under = 100` coverage gate, consume-once reuse
# (work-item livespec-dev-tooling-yilyxr.1). Inside `just check` the parallel
# dispatcher serializes this target after check-per-file-coverage, whose CLEAN
# suite run (COVERAGE_FILE unset for the tests) already produced this
# aggregate's data file, measured identically to this recipe's own clean run
# by construction — so reading it cannot reintroduce the lenient-measurement
# divergence that reverted the prior reuse optimization. The data file is the
# dispatcher's namespaced COVERAGE_FILE when one is exported and the repo-root
# `.coverage` otherwise (work-item livespec-dev-tooling-3wz453; see
# check-per-file-coverage.sh), so a second aggregate in the same worktree can
# neither supply nor consume it. The data file is deleted after the read
# (success or failure), so a later standalone invocation can never report from
# stale data.
#
# The reuse is gated on PROVENANCE (work-item livespec-dev-tooling-sc0z). A
# repo-root `.coverage` is not evidence of a full clean suite run: a focused
# `pytest <one test> --cov` leaves the same file behind, measuring only the
# modules that one test imported. Read as the suite's verdict, that file
# reports every imported-but-unexercised module as uncovered — the 49% total
# that killed a Green amend in a consuming repo (fabro run
# 01KZBJNKGQXM6XWZ06EC7T8KQR) — or, when the narrow set happens to be fully
# covered, a vacuous 100% pass. The file is reused only when:
#   - it carries the full-suite producer's mode/scope/tree/data receipt;
#   - that receipt matches both the current tracked tree and selected data bytes.
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-xluwqj
# GITHUB_ACTIONS alone is not provenance: focused artifacts can exist there too.
# A downloaded artifact without its receipt falls back to normal measurement.
coverage_file="${COVERAGE_FILE:-.coverage}"
reuse_stamp="$(dirname "$coverage_file")/.livespec-coverage-reuse-token"
failure_receipt="$(dirname "$coverage_file")/.livespec-coverage-failure-receipt"
failure_status=""
reuse_reason=""
if [[ -f "$failure_receipt" ]] \
    && failure_id="$(scripts/just/coverage-reuse-id.sh failure)"; then
    IFS=' ' read -r recorded_failure_id recorded_failure_status extra < "$failure_receipt" || true
    if [[ -z "$extra" ]] \
        && [[ "$recorded_failure_id" == "$failure_id" ]] \
        && [[ "$recorded_failure_status" =~ ^[1-9][0-9]*$ ]]; then
        failure_status="$recorded_failure_status"
    fi
fi
if [[ -n "$failure_status" ]]; then
    echo ":: check-coverage: check-per-file-coverage's clean suite already failed (pytest exit status ${failure_status}); refusing duplicate suite run"
    rm -f "$coverage_file" "$reuse_stamp" "$failure_receipt"
    exit "$failure_status"
fi
if [[ -f "$coverage_file" ]]; then
    if [[ -f "$reuse_stamp" ]] \
        && reuse_id="$(scripts/just/coverage-reuse-id.sh)" \
        && [[ "$(cat "$reuse_stamp")" == "$reuse_id" ]]; then
        reuse_reason="check-per-file-coverage's clean run, provenance marker matches the current tracked tree"
    fi
fi
if [[ -n "$reuse_reason" ]]; then
    echo ":: check-coverage: reading .coverage from ${reuse_reason} (no duplicate suite run)"
    status=0
    COVERAGE_FILE="$coverage_file" uv run coverage report --fail-under=100 || status=$?
    rm -f "$coverage_file" "$reuse_stamp" "$failure_receipt"
    exit "$status"
fi
if [[ -f "$coverage_file" ]]; then
    echo ":: check-coverage: ignoring existing .coverage without a matching provenance marker (a focused pytest --cov run leaves one behind); running the clean suite"
    rm -f "$coverage_file" "$reuse_stamp" "$failure_receipt"
else
    echo ":: check-coverage: no reusable .coverage data file; running the clean suite"
    rm -f "$failure_receipt"
fi
env -u COVERAGE_FILE LIVESPEC_COVERAGE_DATA_FILE="$coverage_file" \
    uv run pytest -n "${test_nprocs}" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing

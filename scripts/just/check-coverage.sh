#!/usr/bin/env bash
set -euo pipefail

: "${test_nprocs:?}"

# Aggregate (total) `fail_under = 100` coverage gate, consume-once reuse
# (work-item livespec-dev-tooling-yilyxr.1). Inside `just check` the parallel
# dispatcher serializes this target after check-per-file-coverage, whose CLEAN
# suite run (COVERAGE_FILE unset) already produced the repo-root `.coverage`,
# measured identically to this recipe's own clean run by construction — so
# reading it cannot reintroduce the lenient-measurement divergence that
# reverted the prior reuse optimization. The data file is deleted after the
# read (success or failure), so a later standalone invocation can never
# report from stale data.
#
# The reuse is gated on PROVENANCE (work-item livespec-dev-tooling-sc0z). A
# repo-root `.coverage` is not evidence of a full clean suite run: a focused
# `pytest <one test> --cov` leaves the same file behind, measuring only the
# modules that one test imported. Read as the suite's verdict, that file
# reports every imported-but-unexercised module as uncovered — the 49% total
# that killed a Green amend in a consuming repo (fabro run
# 01KZBJNKGQXM6XWZ06EC7T8KQR) — or, when the narrow set happens to be fully
# covered, a vacuous 100% pass. The file is reused only when:
#   - it carries the producer's marker and that marker equals the id this
#     run resolves for the same tracked tree (scripts/just/coverage-reuse-id.sh),
#     which is the local `just check` aggregate case; or
#   - this is a GitHub Actions job: the consumer job downloads the producer
#     job's artifact, and an actions artifact is scoped to the workflow run
#     that published it, so the file is this run's producer output by
#     construction (no marker crosses the job boundary today).
# Anything else is discarded, with its marker, and the clean suite runs here
# exactly as it does when no file is present at all.
reuse_stamp=.livespec-coverage-reuse-token
reuse_reason=""
if [[ -f .coverage ]]; then
    if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
        reuse_reason="this workflow run's producer artifact"
    elif [[ -f "$reuse_stamp" ]] \
        && reuse_id="$(scripts/just/coverage-reuse-id.sh)" \
        && [[ "$(cat "$reuse_stamp")" == "$reuse_id" ]]; then
        reuse_reason="check-per-file-coverage's clean run, provenance marker matches the current tracked tree"
    fi
fi
if [[ -n "$reuse_reason" ]]; then
    echo ":: check-coverage: reading .coverage from ${reuse_reason} (no duplicate suite run)"
    status=0
    env -u COVERAGE_FILE uv run coverage report --fail-under=100 || status=$?
    rm -f .coverage "$reuse_stamp"
    exit "$status"
fi
if [[ -f .coverage ]]; then
    echo ":: check-coverage: ignoring existing .coverage without a matching provenance marker (a focused pytest --cov run leaves one behind); running the clean suite"
    rm -f .coverage "$reuse_stamp"
else
    echo ":: check-coverage: no reusable .coverage data file; running the clean suite"
fi
env -u COVERAGE_FILE uv run pytest -n "${test_nprocs}" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing

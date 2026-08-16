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
# report from stale data: absent the file (CI's standalone matrix job, a
# manual `just check-coverage`), the clean suite runs here exactly as before.
if [[ -f .coverage ]]; then
    echo ":: check-coverage: reading .coverage from check-per-file-coverage's clean run (no duplicate suite run)"
    status=0
    env -u COVERAGE_FILE uv run coverage report --fail-under=100 || status=$?
    rm -f .coverage
    exit "$status"
fi
echo ":: check-coverage: no .coverage present (standalone run); running the clean suite"
env -u COVERAGE_FILE uv run pytest -n "${test_nprocs}" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing

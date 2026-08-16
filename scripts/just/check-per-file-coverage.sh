#!/usr/bin/env bash
set -euo pipefail

: "${test_nprocs:?}"

# Clean-env producer (work-item livespec-dev-tooling-yilyxr.1): COVERAGE_FILE
# is UNSET for both the suite run and the per-file read, so the measurement is
# IDENTICAL to CI's standalone clean jobs by construction — the lenient
# self-referential-branch divergence that reverted the previous reuse
# optimization cannot occur when the producer itself runs clean. The combined
# repo-root `.coverage` this produces is the single data file check-coverage
# then consumes instead of running the full suite a second time.
env -u COVERAGE_FILE uv run pytest -n "${test_nprocs}" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing
env -u COVERAGE_FILE uv run python -m livespec_dev_tooling.checks.per_file_coverage

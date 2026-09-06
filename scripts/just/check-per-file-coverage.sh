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
#
# Provenance marker (work-item livespec-dev-tooling-sc0z): the suite run is
# stamped with the tracked-tree id from scripts/just/coverage-reuse-id.sh so
# check-coverage can tell THIS data file from one a focused `pytest --cov`
# run left at the repo root. The stale marker is removed BEFORE the run and
# the new one written only AFTER pytest succeeds, so a marker never outlives
# the data it vouches for; per_file_coverage runs after the stamp so a
# per-file failure still leaves the consumer a reusable, current file.
reuse_stamp=.livespec-coverage-reuse-token
rm -f "$reuse_stamp"
env -u COVERAGE_FILE uv run pytest -n "${test_nprocs}" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing
if reuse_id="$(scripts/just/coverage-reuse-id.sh)"; then
    printf '%s\n' "$reuse_id" > "$reuse_stamp"
else
    echo ":: check-per-file-coverage: no coverage provenance id (not a git work tree); leaving no reuse marker"
fi
env -u COVERAGE_FILE uv run python -m livespec_dev_tooling.checks.per_file_coverage

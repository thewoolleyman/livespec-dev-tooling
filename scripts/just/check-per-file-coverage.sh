#!/usr/bin/env bash
set -euo pipefail

: "${test_nprocs:?}"

# Clean-env, NAMESPACED producer (work-items livespec-dev-tooling-yilyxr.1 and
# livespec-dev-tooling-3wz453).
#
# Clean env: COVERAGE_FILE is UNSET for the suite run, so every test sees the
# same environment as CI's standalone clean jobs — the lenient
# self-referential-branch divergence that reverted an earlier reuse
# optimization cannot occur. Namespaced: the data file is still this
# aggregate's own. The dispatcher's COVERAGE_FILE names it, and it reaches
# coverage.py through LIVESPEC_COVERAGE_DATA_FILE, which pyproject.toml's
# `[tool.coverage.run] data_file` expands (falling back to the repo-root
# `.coverage` when unset, as in CI and a manual run). Two aggregates in one
# worktree therefore never write, combine or read the same data file; the
# shared repo-root `.coverage` both used to write is what left the 0-byte,
# table-less files of livespec-dev-tooling-3wz453.
#
# Provenance marker (work-item livespec-dev-tooling-sc0z): the suite run is
# stamped with the tracked-tree id from scripts/just/coverage-reuse-id.sh so
# check-coverage can tell THIS data file from one a focused `pytest --cov`
# run left behind. The marker sits beside the data file it vouches for. The
# stale marker is removed BEFORE the run and the new one written only AFTER
# pytest succeeds, so a marker never outlives the data it vouches for;
# per_file_coverage runs after the stamp so a per-file failure still leaves
# the consumer a reusable, current file. The per-file read starts only after
# pytest has exited, so it reads the combined file of writers that are done.
coverage_file="${COVERAGE_FILE:-.coverage}"
reuse_stamp="$(dirname "$coverage_file")/.livespec-coverage-reuse-token"
rm -f "$reuse_stamp"
env -u COVERAGE_FILE LIVESPEC_COVERAGE_DATA_FILE="$coverage_file" \
    uv run pytest -n "${test_nprocs}" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing --durations=30
if reuse_id="$(scripts/just/coverage-reuse-id.sh)"; then
    printf '%s\n' "$reuse_id" > "$reuse_stamp"
else
    echo ":: check-per-file-coverage: no coverage provenance id (not a git work tree); leaving no reuse marker"
fi
COVERAGE_FILE="$coverage_file" uv run python -m livespec_dev_tooling.checks.per_file_coverage

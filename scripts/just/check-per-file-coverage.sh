#!/usr/bin/env bash
set -euo pipefail

# Resolve incident mode before any gate work (livespec-dev-tooling-wjmre6). The
# presence test is the installed hook's prefilter and decides nothing: unset, the
# body below runs unchanged; present, the shared boundary
# (livespec_dev_tooling/incident_gate_entry.py) parses and decides, and only its
# 75 continues. Every other status, including an unavailable boundary, refuses.
if [ -n "${EXPEDITED_INCIDENT_RESPONSE:-}${EXPEDITED_INCIDENT_RESPONSE_REVERT:-}${LIVESPEC_INCIDENT_CONTEXT:-}${LIVESPEC_INCIDENT_AUTHORITY_QUERY:-}" ]; then
    incident_status=0
    uv run --no-sync python -m livespec_dev_tooling.incident_gate_entry check-per-file-coverage || incident_status=$?
    [ "$incident_status" -eq 75 ] || exit $((incident_status == 0 ? 78 : incident_status))
fi

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
# stale success or failure receipt is removed BEFORE the run. A successful
# suite writes its data receipt only after pytest exits zero. A failed suite
# instead writes a tree-bound failure receipt, allowing check-coverage to
# preserve the first suite's nonzero verdict without starting another suite.
# The per-file read starts only after pytest has exited, so it reads the
# combined file of writers that are done.
coverage_file="${COVERAGE_FILE:-.coverage}"
reuse_stamp="$(dirname "$coverage_file")/.livespec-coverage-reuse-token"
failure_receipt="$(dirname "$coverage_file")/.livespec-coverage-failure-receipt"
rm -f "$reuse_stamp" "$failure_receipt"
status=0
env -u COVERAGE_FILE LIVESPEC_COVERAGE_DATA_FILE="$coverage_file" \
    uv run pytest -n "${test_nprocs}" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing --durations=30 \
    || status=$?
if [[ "$status" -ne 0 ]]; then
    if failure_id="$(scripts/just/coverage-reuse-id.sh failure)"; then
        printf '%s %s\n' "$failure_id" "$status" > "$failure_receipt"
    else
        echo ":: check-per-file-coverage: no failure provenance id (not a git work tree); leaving no failure receipt"
    fi
    exit "$status"
fi
# The per-file check runs BEFORE the receipt is stamped (work-item
# livespec-dev-tooling-x3lvve): its vanished-source rewrite
# (livespec-dev-tooling-5xh8) erases and rewrites the data file whenever a
# measured file has no source at report time, and the receipt binds the data
# bytes (livespec-dev-tooling-xluwqj). Stamped first, the receipt went stale
# on every such run and check-coverage re-ran the whole suite. The rewrite is
# this producer's own sanitisation of its own full-suite data, so the receipt
# still vouches for a clean full-suite run; it is written whatever the
# per-file verdict, as before, and the per-file status is the script's exit.
per_file_status=0
COVERAGE_FILE="$coverage_file" uv run python -m livespec_dev_tooling.checks.per_file_coverage \
    || per_file_status=$?
if reuse_id="$(scripts/just/coverage-reuse-id.sh)"; then
    printf '%s\n' "$reuse_id" > "$reuse_stamp"
else
    echo ":: check-per-file-coverage: no coverage provenance id (not a git work tree); leaving no reuse marker"
fi
exit "$per_file_status"

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
    unset EXPEDITED_INCIDENT_RESPONSE EXPEDITED_INCIDENT_RESPONSE_REVERT
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

# pytest-xdist's controller remains the process the shell launches; workers are
# its direct children.  pytest-cov's combine and session-finish work happens in
# that controller after those children exit.  Watch its CPU ticks during that
# phase so a controller blocked with no workers cannot hold this gate forever.
# Keep the production limit literal and unconfigurable: a caller must never be
# able to turn a failing gate back into an unbounded wait.
xdist_controller_idle_limit_seconds=600
xdist_controller_watchdog_poll_seconds=5

controller_cpu_ticks() {
    local controller_pid="$1"
    local controller_stat
    local -a stat_fields

    controller_stat="$(<"/proc/$controller_pid/stat")" || return 1
    controller_stat="${controller_stat##*) }"
    read -r -a stat_fields <<< "$controller_stat"
    printf '%s\n' "$((stat_fields[11] + stat_fields[12]))"
}

watch_xdist_controller() {
    local controller_pid="$1"
    local watchdog_failure_file="$2"
    local workers_seen=0
    local idle_since=''
    local last_cpu_ticks=''
    local current_cpu_ticks
    local now
    local elapsed

    while kill -0 "$controller_pid" 2>/dev/null; do
        current_cpu_ticks="$(controller_cpu_ticks "$controller_pid" || true)"
        if pgrep -P "$controller_pid" >/dev/null 2>&1; then
            workers_seen=1
            idle_since=''
            last_cpu_ticks="$current_cpu_ticks"
        elif [[ "$workers_seen" -eq 1 ]]; then
            now="$(date +%s)"
            if [[ -z "$idle_since" || "$current_cpu_ticks" != "$last_cpu_ticks" ]]; then
                idle_since="$now"
                last_cpu_ticks="$current_cpu_ticks"
            else
                elapsed=$((now - idle_since))
                if ((elapsed >= xdist_controller_idle_limit_seconds)); then
                    printf '%s\n' \
                        "::error::check-per-file-coverage: pytest controller pid $controller_pid stalled after xdist workers exited; idle for ${elapsed} seconds" \
                        > "$watchdog_failure_file"
                    kill "$controller_pid" 2>/dev/null || true
                    return
                fi
            fi
        fi
        sleep "$xdist_controller_watchdog_poll_seconds"
    done
}

watchdog_failure_file="$(mktemp "${TMPDIR:-/tmp}/check-per-file-coverage-watchdog.XXXXXX")"
status=0
env -u COVERAGE_FILE LIVESPEC_COVERAGE_DATA_FILE="$coverage_file" \
    uv run pytest -n "${test_nprocs}" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing --durations=30 \
    &
pytest_controller_pid=$!
watch_xdist_controller "$pytest_controller_pid" "$watchdog_failure_file" &
watchdog_pid=$!
wait "$pytest_controller_pid" || status=$?
kill "$watchdog_pid" 2>/dev/null || true
wait "$watchdog_pid" || true
if [[ -s "$watchdog_failure_file" ]]; then
    cat "$watchdog_failure_file" >&2
    status=1
fi
rm -f "$watchdog_failure_file"
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

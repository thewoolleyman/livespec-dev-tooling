#!/usr/bin/env bash
# livespec-dev-tooling-mxjbmi: run ONE shard of the per-file coverage suite.
#
# CI can split the suite's test files across parallel jobs, then
# check-per-file-coverage combines every shard's coverage data
# (LIVESPEC_COVERAGE_SHARDS_DIR) and runs the unchanged canonical per-file
# verifier over the combined `.coverage`. This script is the shard half. It
# only RECORDS coverage: a shard covers a fraction of the code, so it never
# judges coverage itself (fail-under 0, no report), and the per-file verdict
# stays the combine job's alone. The same names and the same assignment as
# livespec-orchestrator-beads-fabro's dev-tooling/just-coverage-shard.sh
# (bd-ib-m26pql, bd-ib-eq5ics), so one workflow shape serves both.
#
# Usage: coverage-shard.sh <shard-index 1..N> <shard-count N>
#
# The shard set is every tracked test file pytest would collect under
# `testpaths = ["tests"]` (pytest's default `test_*.py` / `*_test.py`
# patterns). The files are balanced by MEASURED duration, not dealt
# round-robin: the committed table scripts/just/coverage-shard-durations.tsv
# holds one `<test file path><TAB><seconds>` row per test file; the longest
# remaining file goes to the shard with the smallest running total (ties:
# lowest index, then path order). A tracked file the table does not list costs
# the table's mean, so it is still assigned, and a table row whose file is gone
# is ignored. Every shard computes the same plan from the same inputs, so the
# shards are disjoint and their union is the whole suite. `just
# coverage-shard-durations` regenerates the table from one pytest run.
#
# LIVESPEC_COVERAGE_SHARD_DURATIONS overrides the table path;
# LIVESPEC_COVERAGE_SHARD_LIST_ONLY=1 prints the shard's files, one per line,
# and stops before running pytest.
set -euo pipefail

if [[ $# -ne 2 || ! "$1" =~ ^[1-9][0-9]*$ || ! "$2" =~ ^[1-9][0-9]*$ || "$1" -gt "$2" ]]; then
    echo "usage: $0 <shard-index 1..N> <shard-count N>" >&2
    exit 2
fi
shard_index=$1
shard_count=$2

mapfile -t all_files < <(
    git ls-files 'tests/**' | grep -E '(^|/)(test_[^/]*|[^/]*_test)\.py$' | LC_ALL=C sort
)
if [[ ${#all_files[@]} -eq 0 ]]; then
    echo ":: coverage-shard: no tracked test files found" >&2
    exit 1
fi

durations_file=${LIVESPEC_COVERAGE_SHARD_DURATIONS:-$(dirname "${BASH_SOURCE[0]}")/coverage-shard-durations.tsv}
if [[ ! -r "$durations_file" ]]; then
    durations_file=/dev/null
fi
# awk #1 prices every tracked file (table value, else the table's mean, else 1);
# sort puts the longest first; awk #2 deals each file to the least-loaded shard.
mapfile -t shard_files < <(
    printf '%s\n' "${all_files[@]}" |
        awk -F '\t' -v table="$durations_file" '
            FILENAME == table {
                if ($0 ~ /^#/ || NF < 2) { next }
                seconds[$1] = $2 + 0
                total += $2
                rows += 1
                next
            }
            { files[++n] = $0 }
            END {
                fallback = (rows > 0) ? total / rows : 1
                for (i = 1; i <= n; i++) {
                    cost = (files[i] in seconds) ? seconds[files[i]] : fallback
                    printf "%.6f\t%s\n", cost, files[i]
                }
            }
        ' "$durations_file" - |
        LC_ALL=C sort -t $'\t' -k1,1nr -k2,2 |
        awk -F '\t' -v count="$shard_count" -v want="$shard_index" '
            BEGIN { for (s = 1; s <= count; s++) { load[s] = 0 } }
            {
                best = 1
                for (s = 2; s <= count; s++) { if (load[s] < load[best]) { best = s } }
                load[best] += $1
                if (best == want) { print $2 }
            }
        '
)

if [[ "${LIVESPEC_COVERAGE_SHARD_LIST_ONLY:-}" == "1" ]]; then
    printf '%s\n' "${shard_files[@]}"
    exit 0
fi

: "${test_nprocs:?}"
echo ":: coverage-shard ${shard_index}/${shard_count}: ${#shard_files[@]} of ${#all_files[@]} test files; pytest-xdist workers=${test_nprocs}"

mkdir -p .coverage-shards
# Same pytest flags as check-per-file-coverage.sh's suite run, with a
# shard-named data file (reaching coverage.py through
# LIVESPEC_COVERAGE_DATA_FILE, which pyproject.toml's data_file expands; the
# suite never sees COVERAGE_FILE) and fail-under 0 (pyproject's fail_under=100
# cannot hold for a fraction of the suite; the combined data is held to it
# downstream).
env -u COVERAGE_FILE LIVESPEC_COVERAGE_DATA_FILE=".coverage-shards/.coverage.shard-${shard_index}" \
    uv run pytest -n "${test_nprocs}" \
    --cov --cov-branch --cov-config=pyproject.toml --cov-report= --cov-fail-under=0 \
    --durations=30 \
    "${shard_files[@]}"

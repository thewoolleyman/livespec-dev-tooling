#!/usr/bin/env bash
# livespec-dev-tooling-mxjbmi: regenerate the committed per-test-file duration
# table that scripts/just/coverage-shard.sh balances the coverage shards with.
#
# Runs the whole suite once with per-test timings (`--durations=0
# --durations-min=0`), sums every setup / call / teardown phase by the test
# file it belongs to, and writes `<test file path><TAB><seconds>` rows, sorted
# by path, to scripts/just/coverage-shard-durations.tsv. Commit the result.
# Re-run it when the suite's shape changes enough that the shards drift apart; a
# file the table does not list is still assigned to a shard, at the table's mean
# cost.
#
# LIVESPEC_COVERAGE_SHARD_PYTEST_LOG names a saved pytest run to read instead of
# running one; LIVESPEC_COVERAGE_SHARD_DURATIONS_OUT overrides the table path.
# A run with no timings, or a failing suite, leaves the existing table alone.
set -euo pipefail

output=${LIVESPEC_COVERAGE_SHARD_DURATIONS_OUT:-$(dirname "${BASH_SOURCE[0]}")/coverage-shard-durations.tsv}
log=${LIVESPEC_COVERAGE_SHARD_PYTEST_LOG:-}

if [[ -z "$log" ]]; then
    : "${test_nprocs:?}"
    log=$(mktemp)
    trap 'rm -f "$log"' EXIT
    echo ":: coverage-shard-durations: running the suite once; pytest-xdist workers=${test_nprocs}"
    uv run pytest \
        -n "${test_nprocs}" \
        -p no:cacheprovider \
        --durations=0 --durations-min=0 \
        2>&1 | tee "$log"
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        echo ":: coverage-shard-durations: the suite failed; its timings are not trusted, table unchanged" >&2
        exit 1
    fi
fi

table=$(mktemp)
awk '
    $1 ~ /^[0-9]+(\.[0-9]+)?s$/ && $2 ~ /^(setup|call|teardown)$/ && $3 ~ /\.py::/ {
        file = $3
        sub(/::.*/, "", file)
        seconds = $1
        sub(/s$/, "", seconds)
        total[file] += seconds
    }
    END { for (file in total) { printf "%s\t%.3f\n", file, total[file] } }
' "$log" | LC_ALL=C sort > "$table"
if [[ ! -s "$table" ]]; then
    rm -f "$table"
    echo ":: coverage-shard-durations: no per-test timings found in the pytest output, table unchanged" >&2
    exit 1
fi
mv "$table" "$output"
echo ":: coverage-shard-durations: wrote $(wc -l < "$output") test files to $output"

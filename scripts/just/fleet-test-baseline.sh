#!/usr/bin/env bash
# fleet-test-baseline.sh — emit an on-demand JSON test baseline for sibling clones.
set -euo pipefail

exec uv run python -m livespec_dev_tooling.fleet_test_baseline "$@"

#!/usr/bin/env bash
# Export this CI run's per-job timings to Honeycomb as OTLP/HTTP-JSON spans,
# and FAIL the job if Honeycomb does not accept them.
#
# This is a CLOSED-LOOP self-verification, not an external monitor: a CI run
# deterministically knows its own telemetry should exist, so the run that
# produced the data confirms Honeycomb received it. If the ingest key is
# missing/revoked, the network is down, or the payload is rejected, this exits
# non-zero -> the job goes red -> the existing CI-failure notification fires.
# That makes a broken telemetry pipeline impossible to die silently.
#
# Wired to run on push(master)/merge_group only (never PRs), so it adds no
# latency to PR feedback. Emits one `ci.run` root span + one `ci.job.<name>`
# child per completed job. Span/trace ids are derived from the GitHub run/job
# integer ids (deterministic, unique, valid hex).
#
# The span building, the REST queue-time read and the POST live in the shared
# exporter, livespec_dev_tooling/ci_run_telemetry.py, so the check-coverage
# job's structured reuse outcome (livespec_dev_tooling/ci_coverage_reuse.py)
# reaches the export without a second, drifting implementation here. The
# exporter runs from this checkout on the runner's system python3; the one
# thing the vendored GitHub client imports that is not vendored with it is
# `typing_extensions`, which the export-telemetry job's bare checkout does not
# carry, so it is dropped beside the vendored packages when it is missing.
#
# Required environment:
#   REPO    - owner/name (e.g. thewoolleyman/livespec)
#   RUN_ID  - this workflow run's id (github.run_id)
#   GH_TOKEN - gh auth token with actions:read (the workflow's GITHUB_TOKEN)
#   HONEYCOMB_GITHUB_CI_INGEST_KEY_LIVESPEC - write-only Honeycomb ingest key
set -euo pipefail

: "${REPO:?REPO required}"
: "${RUN_ID:?RUN_ID required}"
: "${HONEYCOMB_GITHUB_CI_INGEST_KEY_LIVESPEC:?HONEYCOMB_GITHUB_CI_INGEST_KEY_LIVESPEC required}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# The checkout is this job's throwaway workspace, so installing next to the
# vendored packages leaves nothing behind. A failed install is only a warning:
# the exporter's own import error then names what is missing.
if ! python3 -c 'import typing_extensions' 2>/dev/null; then
  python3 -m pip install --quiet --disable-pip-version-check --no-deps \
    --target "$repo_root/livespec_dev_tooling/_vendor" 'typing-extensions>=4.0' \
    || echo "::warning::could not install typing_extensions for the CI telemetry exporter" >&2
fi

status=0
PYTHONPATH="$repo_root" python3 -m livespec_dev_tooling.ci_run_telemetry || status=$?
if [ "$status" -ne 0 ]; then
  echo "::error::CI telemetry export to Honeycomb FAILED (exporter exit status $status). The telemetry pipeline is broken; fix it rather than ignore this." >&2
  exit 1
fi
echo "CI telemetry exported and confirmed received by Honeycomb (run $RUN_ID)."

#!/usr/bin/env bash
# Export this CI run's telemetry to Honeycomb through the ONE shared exporter.
#
# non-functional-requirements.md "One CI run-telemetry exporter": the exporter
# that turns a CI run into a `ci.run` span and one `ci.job.<name>` span per
# completed job is one module shipped by livespec-dev-tooling,
# `livespec_dev_tooling.ci_run_telemetry`, with no copy of its logic in any
# member. This file carries none of that logic: it only runs the module, so the
# workflows that call it (ci.yml and ci-cache-negative-tests.yml) need no edit.
#
# The module reads the same environment this script always required (REPO,
# RUN_ID, GH_TOKEN, HONEYCOMB_GITHUB_CI_INGEST_KEY_LIVESPEC) and keeps its
# closed-loop contract: it exits non-zero when Honeycomb does not accept the
# spans, so the job goes red and a broken telemetry pipeline cannot die
# silently. livespec-dev-tooling-5ua57h.
set -euo pipefail

cd "$(dirname "$0")/../.."
exec python3 -m livespec_dev_tooling.ci_run_telemetry "$@"

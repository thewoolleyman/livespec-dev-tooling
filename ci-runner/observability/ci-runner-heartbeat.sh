#!/usr/bin/env bash
# ci-runner-heartbeat.sh — emit the local CI-runner fleet's liveness gauge.
#
# Counts ACTIVE `runner@*.service` units (the ephemeral JIT pool the
# supervisor maintains) and emits ONE OTLP/HTTP gauge datapoint,
# `livespec.ci_runners.active`, to the host otel-collector's loopback HTTP
# receiver (127.0.0.1:4319), which routes host metrics to the
# `livespec-host-metrics` Honeycomb dataset (agent-activity environment).
#
# The paired Honeycomb trigger alerts when the gauge stays below 1 — i.e.
# the runner fleet is gone while the collector still hears from us. The
# residual blind spot (this emitter or the collector itself dying stops the
# DATA, and a data-absence trigger is not expressible on a Honeycomb metrics
# dataset) is covered end-to-end by the CI sentinel job
# (`check-self-hosted-routing` pinned to the local lane): a dead lane leaves
# that job pending and blocks merges within hours.
#
# Credential-free by design: counting is a /proc read (pgrep) and the
# collector receiver is loopback-only. Runs from ci-runner-heartbeat.timer
# every 5 minutes as a dynamic (non-root) user. Deliberately NOT
# systemctl-based: D-Bus access proved flaky under DynamicUser ("Transport
# endpoint is not connected"), and counting Runner.Listener processes is
# also more truthful — an active unit whose listener crashed counts as dead.
#
# Fail-closed split: pgrep exit 1 means ZERO matches (a legitimate 0 — emit
# it so the trigger fires); any other nonzero exit means the READ failed —
# emit nothing and exit nonzero rather than reporting a false zero.
set -euo pipefail

OTLP_ENDPOINT="${CI_RUNNER_HEARTBEAT_OTLP:-http://127.0.0.1:4319/v1/metrics}"

if active_count="$(pgrep -c -u ci-runner -f 'Runner.Listener')"; then
  :
elif [ "$?" -eq 1 ]; then
  active_count=0
else
  echo "heartbeat: pgrep failed (not the zero-matches case); refusing to emit a false zero" >&2
  exit 1
fi
now_ns="$(date +%s%N)"

payload="$(cat <<JSON
{
  "resourceMetrics": [
    {
      "resource": {
        "attributes": [
          { "key": "service.name", "value": { "stringValue": "ci-runner-liveness" } }
        ]
      },
      "scopeMetrics": [
        {
          "scope": { "name": "ci-runner-heartbeat" },
          "metrics": [
            {
              "name": "livespec.ci_runners.active",
              "description": "ACTIVE runner@*.service units in the local JIT pool",
              "unit": "{runners}",
              "gauge": {
                "dataPoints": [
                  { "asInt": "${active_count}", "timeUnixNano": "${now_ns}" }
                ]
              }
            }
          ]
        }
      ]
    }
  ]
}
JSON
)"

curl --silent --show-error --fail --max-time 10 \
  -X POST "${OTLP_ENDPOINT}" \
  -H 'Content-Type: application/json' \
  -d "${payload}" > /dev/null

echo "heartbeat: livespec.ci_runners.active=${active_count} -> ${OTLP_ENDPOINT}"

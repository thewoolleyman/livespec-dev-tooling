#!/usr/bin/env bash
# ci-runner-heartbeat.sh — emit the CI-runner host's liveness gauges.
#
# Emits ONE OTLP/HTTP metrics POST carrying two gauges to the host
# otel-collector's loopback HTTP receiver (127.0.0.1:4319), which exports
# them to the `livespec` Honeycomb environment (they land in that env's
# `metrics` dataset, stamped host.name by the collector):
#
#   livespec.ci_listeners.active  — ARC scale-set LISTENERS (`ghalistener`
#                                   processes): one per registered scale set,
#                                   the thing that polls GitHub and takes
#                                   jobs. This is "the host is registered and
#                                   taking jobs"; 0 means ARC is down or has
#                                   no scale sets, even if the host is up.
#   livespec.ci_runners.active    — ephemeral runner pods currently executing
#                                   (`Runner.Listener run` processes). With
#                                   minRunners=0 on every scale set this is
#                                   legitimately 0 when idle — it is load, not
#                                   liveness, and must NOT be alarmed on < 1.
#
# The collector that receives this is the CI-runner-host shape of
# https://github.com/thewoolleyman/otel-collector (config.ci-runner-host.yaml,
# scripts/install-ci-runner-host.sh). It did not exist on the host from
# 2026-08-15 to 2026-08-23, so this script exited 7 on `curl: (7)` every five
# minutes for eight days and nothing noticed (livespec-s43svm.20).
#
# Two Honeycomb triggers pair with this, both in the `livespec` env on the
# `metrics` dataset, both filtered to host.name = <this host>:
#   - the DEAD-MAN: COUNT_DATAPOINTS(livespec.ci_listeners.active) < 1 over
#     a 20-minute window. Ungrouped-but-filtered is the only shape that fires
#     on SILENCE (a grouped query has no group to evaluate when the host is
#     silent). This is the mechanism the Availability clause of livespec
#     SPECIFICATION/non-functional-requirements.md § "Self-hosted CI runner
#     host requirements" requires: observe a dead host rather than infer it
#     from a growing queue.
#   - the value trigger: MAX(livespec.ci_listeners.active) < 1 — host and
#     collector alive, but no listener registered.
#
# Why processes rather than kubectl: this unit runs as a DynamicUser with no
# cluster credential; counting processes is a /proc read. The ARC listener and
# runner containers share the host PID namespace view from the host side, so
# pgrep sees them. Deliberately NOT filtered by uid (the retired rootless-
# podman pool ran as `ci-runner`; ARC pods do not), and deliberately NOT
# systemctl-based (D-Bus proved flaky under DynamicUser).
#
# Fail-closed split: pgrep exit 1 means ZERO matches (a legitimate 0 — emit
# it); any other nonzero exit means the READ failed — emit nothing and exit
# nonzero rather than reporting a false zero.
set -euo pipefail

OTLP_ENDPOINT="${CI_RUNNER_HEARTBEAT_OTLP:-http://127.0.0.1:4319/v1/metrics}"

count_procs() {
  # $1: pgrep -f pattern. Prints the count; exits nonzero only on a read error.
  local n
  if n="$(pgrep -c -f "$1")"; then
    printf '%s\n' "$n"
  elif [ "$?" -eq 1 ]; then
    printf '0\n'
  else
    echo "heartbeat: pgrep failed for '$1' (not the zero-matches case); refusing to emit a false zero" >&2
    return 1
  fi
}

listeners="$(count_procs '^/ghalistener')"
runners="$(count_procs 'Runner\.Listener run')"
host_name="$(hostname)"
now_ns="$(date +%s%N)"

payload="$(cat <<JSON
{
  "resourceMetrics": [
    {
      "resource": {
        "attributes": [
          { "key": "service.name", "value": { "stringValue": "ci-runner-liveness" } },
          { "key": "host.name", "value": { "stringValue": "${host_name}" } }
        ]
      },
      "scopeMetrics": [
        {
          "scope": { "name": "ci-runner-heartbeat" },
          "metrics": [
            {
              "name": "livespec.ci_listeners.active",
              "description": "ARC scale-set listener processes (ghalistener) registered on this host",
              "unit": "{listeners}",
              "gauge": {
                "dataPoints": [
                  { "asInt": "${listeners}", "timeUnixNano": "${now_ns}" }
                ]
              }
            },
            {
              "name": "livespec.ci_runners.active",
              "description": "Ephemeral ARC runner processes (Runner.Listener run) currently executing on this host",
              "unit": "{runners}",
              "gauge": {
                "dataPoints": [
                  { "asInt": "${runners}", "timeUnixNano": "${now_ns}" }
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

echo "heartbeat: livespec.ci_listeners.active=${listeners} livespec.ci_runners.active=${runners} host.name=${host_name} -> ${OTLP_ENDPOINT}"

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
#   livespec.ci_host.io_stall_pct — PSI `io full avg300` for the whole host:
#                                   the percent of the last 300s in which EVERY
#                                   runnable task was blocked on I/O, i.e. the
#                                   host accomplished nothing.
#   livespec.ci_kubepods.io_stall_pct
#                                 — the same, for kubepods.slice alone. The
#                                   pair is what separates "the host is busy"
#                                   from "CI is what is making it busy".
#                                   Omitted entirely (not zero) when k3s is not
#                                   running.
#
# WHAT READS THE io_stall_pct PAIR, AND WHEN — read this before assuming it is
# self-justifying telemetry. These two are DECISION INPUTS, not alarms, and
# they exist to answer one question that is currently open:
#
#   Is the array actually the constraint at CI's real concurrency, or was it
#   only ever the constraint in synthetic benchmarks?
#
# livespec plan/poweredge-raid-array-maintenance measured the array's random
# writes anywhere between ~1,400 and ~10,400 IOPS depending on working-set size
# and whether blocks were freshly allocated — a seven-fold spread that a
# synthetic benchmark cannot narrow, because the answer depends on what CI
# actually does. These gauges narrow it from real traffic. They are consulted:
#
#   - when choosing the node's churn-slot capacity C (kueue/DERIVATION.md calls
#     it "a measured ceiling, not a free parameter"), and
#   - when deciding whether to spend money on storage, or whether to trade RAM
#     away from pool size for tmpfs-backed runner volumes. Both trades are only
#     answerable against a real stall figure.
#
# ALARMING: deliberately none by default. A high io stall under heavy CI load is
# expected and correct, not an incident; a trigger on it would page on success.
# If one is ever added it must be for the PATHOLOGICAL case only — sustained
# high `full` stall while livespec.ci_runners.active is LOW, which means the
# host is thrashing on something that is not CI work.
#
# The precedent for why the consumer must be named up front: from 2026-08-15 to
# 2026-08-23 this script exited 7 on `curl: (7)` every five minutes for eight
# days and nothing noticed (livespec-s43svm.20). A metric with no named reader
# is indistinguishable from a metric that stopped being emitted.
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

psi_full_avg300() {
  # $1: a PSI file (/proc/pressure/io, or a cgroup's io.pressure).
  # Prints the `full` line's avg300 percentage. Same fail-closed split as
  # count_procs: a genuine 0.00 is a legitimate reading and is emitted, but an
  # unreadable or unparseable file emits NOTHING rather than a false zero —
  # 0% I/O stall is exactly what a healthy idle host looks like, so a false
  # zero here is indistinguishable from good news and would be believed.
  local f="$1" val
  if [ ! -r "$f" ]; then
    echo "heartbeat: ${f} unreadable; refusing to emit a false zero" >&2
    return 1
  fi
  # `full` = every runnable task stalled on I/O, i.e. the host accomplished
  # nothing. `some` (at least one task stalled) is the noisier signal; `full`
  # is the one that means capacity is actually lost. avg300 over avg10/avg60
  # because this unit fires every five minutes — a shorter window would alias.
  if ! val="$(awk '/^full /{for (i = 2; i <= NF; i++) { split($i, kv, "="); if (kv[1] == "avg300") { print kv[2]; found = 1 } }} END{exit !found}' "$f")"; then
    echo "heartbeat: no 'full ... avg300' field in ${f}; refusing to emit a false zero" >&2
    return 1
  fi
  printf '%s\n' "$val"
}

listeners="$(count_procs '^/ghalistener')"
runners="$(count_procs 'Runner\.Listener run')"
host_io_stall="$(psi_full_avg300 /proc/pressure/io)"
host_name="$(hostname)"
now_ns="$(date +%s%N)"

# The CI cgroup's own share of the host stall, which is what separates "this
# host is busy" from "CI is what is making it busy". Absent when k3s is not
# running, which is a legitimate state rather than a read error — so the metric
# is OMITTED entirely rather than emitted as 0. Both this and the host file are
# readable by an unprivileged user, which this unit needs (it runs DynamicUser).
kubepods_psi=/sys/fs/cgroup/kubepods.slice/io.pressure
kubepods_metric=""
if [ -r "${kubepods_psi}" ]; then
  kubepods_io_stall="$(psi_full_avg300 "${kubepods_psi}")"
  kubepods_metric="$(cat <<JSON
            ,{
              "name": "livespec.ci_kubepods.io_stall_pct",
              "description": "Percent of the last 300s in which every task in kubepods.slice was stalled on I/O (PSI io full avg300)",
              "unit": "%",
              "gauge": {
                "dataPoints": [
                  { "asDouble": ${kubepods_io_stall}, "timeUnixNano": "${now_ns}" }
                ]
              }
            }
JSON
)"
else
  kubepods_io_stall="(absent)"
fi

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
            },
            {
              "name": "livespec.ci_host.io_stall_pct",
              "description": "Percent of the last 300s in which every task on this host was stalled on I/O (PSI io full avg300)",
              "unit": "%",
              "gauge": {
                "dataPoints": [
                  { "asDouble": ${host_io_stall}, "timeUnixNano": "${now_ns}" }
                ]
              }
            }${kubepods_metric}
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

echo "heartbeat: livespec.ci_listeners.active=${listeners} livespec.ci_runners.active=${runners} livespec.ci_host.io_stall_pct=${host_io_stall} livespec.ci_kubepods.io_stall_pct=${kubepods_io_stall} host.name=${host_name} -> ${OTLP_ENDPOINT}"

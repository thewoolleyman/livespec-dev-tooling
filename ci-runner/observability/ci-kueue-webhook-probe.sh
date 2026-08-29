#!/usr/bin/env bash
# ci-kueue-webhook-probe.sh — emit the readiness of the Kueue mutating-admission
# webhook's endpoints on this single-node k3s host.
#
# Emits ONE OTLP/HTTP metrics POST carrying a single gauge to the host
# otel-collector's loopback HTTP receiver (127.0.0.1:4319), which exports it to
# the `livespec` Honeycomb environment (it lands in that env's `metrics`
# dataset, stamped host.name by the collector):
#
#   livespec.ci_kueue.webhook_ready_endpoints — the count of READY endpoint
#                                   addresses backing the `kueue-webhook-service`
#                                   Service in namespace `kueue-system`. In the
#                                   healthy single-replica state this is 1. ZERO
#                                   is the alarm condition: the Kueue
#                                   mutating-admission webhook has no backend, so
#                                   the apiserver's call to `mpod.kb.io` fails and
#                                   NO runner pod can be admitted.
#
# WHAT READS THIS METRIC, AND WHY IT IS NOT ORPHAN TELEMETRY — read this before
# assuming it is self-justifying. It exists to catch ONE specific, invisible
# outage class, and it is consumed by ONE Honeycomb value trigger:
#
#   MAX(livespec.ci_kueue.webhook_ready_endpoints) < 1, in the `livespec` env on
#   the `metrics` dataset, filtered to host.name = poweredge-xubuntu.
#
# The outage it catches (livespec-s43svm.46): on 2026-08-26 a livespec-runtime
# job died in `Initialize containers`, BEFORE running anything, with
#   Post "https://kueue-webhook-service.kueue-system.svc:443/mutate--v1-pod":
#   no endpoints available for service "kueue-webhook-service"
# The Kueue admission webhook had ZERO ready endpoints and the runner pod was
# never admitted. This host is a SINGLE NODE with no HA, so any eviction or
# restart of the webhook backend is a FULL admission outage for EVERY scale set
# at once, with nothing to absorb it. Worse, it presents as a CONTENT failure: the
# affected job showed `check-format: FAILURE`, reading as "your change is
# misformatted" for a check that never ran. Nothing at the cluster records that
# admission was down; absent this probe the only artifact is a red check on an
# unrelated PR whose name misdirects, and the next occurrence is diagnosed from
# scratch or absorbed as a flake. The precedent for naming the reader up front is
# livespec-s43svm.20, where the heartbeat exited 7 every five minutes for eight
# days and nothing noticed: a metric with no named reader is indistinguishable
# from a metric that stopped being emitted.
#
# Why a SEPARATE unit from ci-runner-heartbeat.sh, not an edit to it: the
# heartbeat runs as a systemd DynamicUser with NO cluster credential and counts
# /proc processes precisely because it cannot talk to the cluster (see its lines
# 79-84). Endpoint readiness needs cluster READ access it deliberately lacks. So
# this unit runs as root with a SCOPED read-only kubeconfig (a ServiceAccount
# granted get,list on endpoints in kueue-system ONLY — see the RBAC provisioned
# for livespec-s43svm.46). There is no kube-state-metrics and no in-cluster otel
# pod; the otel-collector's k8s_cluster receiver does not emit per-service
# endpoint-ready counts, so this gauge fills that specific gap.
#
# Why the endpoint count and NOT the sibling `kueue-controller-manager`
# k8s.deployment.available trigger: the controller Deployment can report
# available while the webhook Service momentarily has zero READY endpoints (a
# rolling restart, an eviction, a readiness-probe blip drops the address from the
# Endpoints object before the Deployment flips). The endpoint count is the signal
# the apiserver itself consults when it decides whether the webhook is callable —
# it is exactly what was zero in the observed outage.
#
# Fail-closed split, mirroring the heartbeat: a genuine 0 ready endpoints is a
# LEGITIMATE reading and IS emitted — that IS the alarm condition. A READ failure
# (apiserver unreachable, absent/expired credential, kubectl error, unparseable
# output) emits NOTHING and exits nonzero rather than reporting a false zero,
# because 0 is the alarm value and a false zero would page on a broken probe
# rather than a broken webhook.
set -euo pipefail

OTLP_ENDPOINT="${CI_RUNNER_HEARTBEAT_OTLP:-http://127.0.0.1:4319/v1/metrics}"
# Root-owned, mode 0600 kubeconfig for the scoped read-only ServiceAccount. The
# path is overridable for testing; the default is the host location the RBAC
# provisioning writes to (see install notes for livespec-s43svm.46).
KUBECONFIG_PATH="${CI_KUEUE_PROBE_KUBECONFIG:-/etc/ci-runner/kueue-webhook-probe.kubeconfig}"
# k3s exposes kubectl as `kubectl` (/usr/local/bin/kubectl) on this host; override
# to `k3s kubectl` or an absolute path if the binary moves.
KUBECTL_BIN="${CI_KUEUE_PROBE_KUBECTL:-kubectl}"

count_ready_endpoints() {
  # Prints the count of READY endpoint addresses for kueue-webhook-service in
  # kueue-system. Exits nonzero (emitting nothing to stdout) on any READ failure
  # so the caller can refuse to emit a false zero.
  local json n
  if ! json="$("${KUBECTL_BIN}" --kubeconfig "${KUBECONFIG_PATH}" \
      -n kueue-system get endpoints kueue-webhook-service -o json 2>/dev/null)"; then
    echo "kueue-webhook-probe: kubectl read of endpoints/kueue-webhook-service failed (apiserver unreachable, bad/absent credential, or object missing); refusing to emit a false zero" >&2
    return 1
  fi
  # Sum the lengths of every subset's `addresses` list — the READY addresses.
  # `notReadyAddresses` is deliberately excluded: a not-ready backend cannot serve
  # the webhook, so it does not count toward readiness. An Endpoints object with
  # no ready subsets yields a legitimate 0, which we DO emit. Unparseable output
  # (kubectl returned success but not the expected JSON) is a read failure.
  if ! n="$(printf '%s' "${json}" | python3 -c \
      'import sys, json; d = json.load(sys.stdin); print(sum(len(s.get("addresses") or []) for s in (d.get("subsets") or [])))' \
      2>/dev/null)"; then
    echo "kueue-webhook-probe: could not parse ready-endpoint count from kubectl JSON; refusing to emit a false zero" >&2
    return 1
  fi
  printf '%s\n' "${n}"
}

ready_endpoints="$(count_ready_endpoints)"
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
          "scope": { "name": "ci-kueue-webhook-probe" },
          "metrics": [
            {
              "name": "livespec.ci_kueue.webhook_ready_endpoints",
              "description": "Ready endpoint addresses backing kueue-webhook-service in kueue-system; 0 = Kueue admission webhook has no backend and no runner pod can be admitted",
              "unit": "{endpoints}",
              "gauge": {
                "dataPoints": [
                  { "asInt": "${ready_endpoints}", "timeUnixNano": "${now_ns}" }
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

echo "kueue-webhook-probe: livespec.ci_kueue.webhook_ready_endpoints=${ready_endpoints} host.name=${host_name} -> ${OTLP_ENDPOINT}"

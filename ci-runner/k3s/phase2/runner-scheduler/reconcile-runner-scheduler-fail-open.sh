#!/usr/bin/env bash
# reconcile-runner-scheduler-fail-open.sh: hand a runner pod stranded by a down
# `ci-runner-scheduler` to the default scheduler (livespec-dev-tooling-mtvxde).
#
# WHY THIS IS NEEDED. A pod that names a scheduler with no ready replica is never
# bound, so without this a scheduler outage would stall CI. Placement that ignores
# churn-slot use is safe for the length of an outage: each node's churn-slot
# capacity is still enforced by the default scheduler's fit filter.
#
# WHY IT WORKS RUNNER BY RUNNER. A pod's schedulerName is immutable, so a stranded
# pod has to be replaced. The EphemeralRunner carries the pod spec, and ARC 0.14.2
# recreates a missing pod from that spec under the same name, reusing the runner's
# unused JIT config and counting no failure (ephemeralrunner_controller.go,
# "Ephemeral runner pod does not exist"). So this patches the runner's spec and
# then deletes its pod, in that order. A failed delete is retried next cycle,
# because the pod still reads as stranded.
#
# It deliberately does NOT edit the AutoscalingRunnerSet template. That changes the
# set's spec hash, so ARC recreates the set's listener and EphemeralRunnerSet, once
# when the outage begins and again when it ends. It would also leave the live
# template disagreeing with the Helm values. The rescue touches only stranded pods
# and needs no revert: a recovered scheduler simply places every new runner again.
#
# WHAT COUNTS AS STRANDED, only while the scheduler has been at zero ready replicas
# for RUNNER_SCHEDULER_FAIL_OPEN_GRACE_SECONDS: a Pending pod in arc-runners that
# names the scheduler, has no node, and carries no scheduling gate. A gated pod is
# still waiting for Kueue, which no scheduler could change, and deleting it would
# only lose its place. A missing Deployment counts as zero ready. A failed READ
# changes nothing: an API error says nothing about the scheduler.
#
# NOT SILENT. A failed write exits non-zero so the unit shows failed, and the
# `k8s controllers` Honeycomb trigger alerts on the Deployment's zero availability.
#
# Flags: --dry-run prints the decision and changes nothing.
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

DRY_RUN=0
case "${1:-}" in
  --dry-run) DRY_RUN=1 ;;
  "") ;;
  *) die "usage: ${SCRIPT_NAME} [--dry-run]" ;;
esac

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
STATE_DIR="${RUNNER_SCHEDULER_FAIL_OPEN_STATE_DIR:-/var/lib/livespec/runner-scheduler-fail-open}"
GRACE="${RUNNER_SCHEDULER_FAIL_OPEN_GRACE_SECONDS:-60}"
NOW="${RUNNER_SCHEDULER_FAIL_OPEN_NOW:-$(date -u +%s)}"
SCHEDULER=ci-runner-scheduler
NAMESPACE=arc-runners
FIRST_ZERO_FILE="${STATE_DIR}/first-zero-ready-at"

mkdir -p "$STATE_DIR"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

ready=0
if ! kubectl -n kube-system get deployment "$SCHEDULER" -o json >"$work/deployment.json" 2>"$work/deployment.err"; then
  grep -q NotFound "$work/deployment.err" \
    || die "could not read the ${SCHEDULER} Deployment; changing nothing this cycle: $(cat "$work/deployment.err")"
else
  ready="$(python3 -c 'import json, sys; print(int(json.load(open(sys.argv[1])).get("status", {}).get("readyReplicas") or 0))' "$work/deployment.json")" \
    || die "could not parse the ${SCHEDULER} Deployment; changing nothing this cycle"
fi

if [ "$ready" -gt 0 ]; then
  rm -f "$FIRST_ZERO_FILE"
  echo "${SCRIPT_NAME}: UP ready=${ready}"
  exit 0
fi

if [ -f "$FIRST_ZERO_FILE" ]; then
  first_zero="$(cat "$FIRST_ZERO_FILE")"
else
  first_zero="$NOW"
  [ "$DRY_RUN" = 1 ] || printf '%s\n' "$first_zero" >"$FIRST_ZERO_FILE"
fi
elapsed=$((NOW - first_zero))
if [ "$elapsed" -lt "$GRACE" ]; then
  echo "${SCRIPT_NAME}: WAITING ready=0 for ${elapsed}s of a ${GRACE}s grace"
  exit 0
fi

kubectl -n "$NAMESPACE" get pods -o json >"$work/pods.json" \
  || die "could not list runner pods; changing nothing this cycle"
python3 - "$work/pods.json" "$SCHEDULER" >"$work/stranded" <<'PY'
import json, sys

with open(sys.argv[1]) as f:
    pods = json.load(f)["items"]
for pod in pods:
    spec = pod["spec"]
    if (
        spec.get("schedulerName") == sys.argv[2]
        and pod.get("status", {}).get("phase") == "Pending"
        and not spec.get("nodeName")
        and not spec.get("schedulingGates")
    ):
        print(pod["metadata"]["name"])
PY
mapfile -t stranded <"$work/stranded"
echo "${SCRIPT_NAME}: DOWN ready=0 for ${elapsed}s, ${#stranded[@]} stranded runner pod(s)"

failed=0
for name in "${stranded[@]}"; do
  if [ "$DRY_RUN" = 1 ]; then
    echo "${SCRIPT_NAME}: DRY RUN would rescue ${name}"
    continue
  fi
  if ! kubectl -n "$NAMESPACE" patch ephemeralrunner "$name" --type=merge \
    -p '{"spec":{"spec":{"schedulerName":"default-scheduler"}}}'; then
    echo "${SCRIPT_NAME}: FAILED to patch runner ${name}; its pod stays for the next cycle" >&2
    failed=1
    continue
  fi
  if ! kubectl -n "$NAMESPACE" delete pod "$name" --ignore-not-found --wait=false; then
    echo "${SCRIPT_NAME}: FAILED to delete pod ${name}; the next cycle retries" >&2
    failed=1
    continue
  fi
  echo "${SCRIPT_NAME}: RESCUED ${name} to default-scheduler"
done
exit "$failed"

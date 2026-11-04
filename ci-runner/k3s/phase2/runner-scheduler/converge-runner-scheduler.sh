#!/usr/bin/env bash
# converge-runner-scheduler.sh — apply the `ci-runner-scheduler` second
# kube-scheduler (./runner-scheduler.yaml) and wait, bounded, for its rollout.
# Run by ../reconstruct/converge-ci-stack.sh BEFORE the runner scale sets, so a
# scale set that names the scheduler never starts ahead of it.
# livespec-dev-tooling-mtvxde.
#
# FAIL-SOFT by design: a scheduler that is not Ready yet is a WARN, never a
# failure of the stack converge. The fail-open reconciler (mtvxde PR 2) returns
# runner templates to the default scheduler while it has no ready replica.
#
# --dry-run prints every kubectl call and touches nothing (the test suite runs
# it without a cluster).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="kube-system"
ROLLOUT_TIMEOUT="${RUNNER_SCHEDULER_ROLLOUT_TIMEOUT:-120s}"
DRY_RUN=0

usage() { printf 'usage: %s [--dry-run]\n' "$(basename "$0")"; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'FATAL: unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

log() { printf '\n== %s ==\n' "$*"; }
run() {
  if [ "${DRY_RUN}" -eq 1 ]; then printf '  would run: %s\n' "$*"; return 0; fi
  "$@"
}
run_quiet() {
  if [ "${DRY_RUN}" -eq 1 ]; then printf '  would run: %s\n' "$*"; return 0; fi
  "$@" >/dev/null
}

if [ "${DRY_RUN}" -eq 0 ]; then
  command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
  : "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../../provision-k3s.sh)}"
fi

log "runner-scheduler 1. Apply the ServiceAccount, RBAC, scheduler ConfigMap and Deployment"
run kubectl apply -f "${SCRIPT_DIR}/runner-scheduler.yaml"
# A config-only change does not roll a Deployment by itself; stamp the
# manifest's hash on the pod template so a changed scoring config restarts it.
conf_hash="$(sha256sum "${SCRIPT_DIR}/runner-scheduler.yaml" | cut -c1-16)"
run_quiet kubectl -n "${NAMESPACE}" patch deployment ci-runner-scheduler --type=merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ci-runner.io/config-hash\":\"${conf_hash}\"}}}}}"

log "runner-scheduler 2. Wait (bounded, ${ROLLOUT_TIMEOUT}) for the rollout"
if [ "${DRY_RUN}" -eq 1 ]; then
  run kubectl -n "${NAMESPACE}" rollout status deployment/ci-runner-scheduler --timeout="${ROLLOUT_TIMEOUT}"
  echo "DRY RUN: nothing was applied."
  exit 0
fi
if kubectl -n "${NAMESPACE}" rollout status deployment/ci-runner-scheduler --timeout="${ROLLOUT_TIMEOUT}"; then
  echo "ci-runner-scheduler ready"
else
  echo "WARN: ci-runner-scheduler rollout not complete after ${ROLLOUT_TIMEOUT}; runner pods that name it wait until it is Ready (kubectl -n ${NAMESPACE} get pods -l app.kubernetes.io/name=ci-runner-scheduler)"
fi

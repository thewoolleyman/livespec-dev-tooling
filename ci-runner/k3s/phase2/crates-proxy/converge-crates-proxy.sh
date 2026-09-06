#!/usr/bin/env bash
# converge-crates-proxy.sh — the one idempotent converge of the crates proxy's
# cluster objects (./crates-proxy.yaml: Namespace, nginx ConfigMap, Deployment,
# Service). Applies, waits briefly for the rollout, and exits.
#
# Called on every boot by the reconstruct converge
# (../reconstruct/converge-ci-stack.sh) — those objects live in the k3s
# datastore, which is tmpfs and EMPTY on every boot (../datastore-tmpfs/) —
# and by hand after editing crates-proxy.yaml. The on-disk cache under
# /var/cache/ci-runner/crates-proxy survives a reboot untouched.
#
# The rollout wait is bounded so a boot converge is never held hostage by an
# image pull; a proxy that is not yet Ready simply means the next jobs fetch
# from crates.io directly (the reader side probes before it opts in).
#
# --dry-run PRINTS every command this converge would run, in order, and
# executes NOTHING — no cluster write, no cluster read, not even the kubectl
# and KUBECONFIG preconditions — so it is safe to run from a checkout on a
# machine that is not the node (two-node precondition work; plan
# k3s-on-gmktec-for-vps-usage, carrier R3). Each printed line comes from the
# same `run` wrapper that would execute it, so the plan cannot drift from the
# body the way a hand-maintained second copy of it would.
#
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="ci-crates-proxy"
ROLLOUT_TIMEOUT="${CRATES_PROXY_ROLLOUT_TIMEOUT:-120s}"

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
# Print-or-execute: in dry-run the exact argv is shown and NOT run.
run() {
  if [ "${DRY_RUN}" -eq 1 ]; then printf '  would run: %s\n' "$*"; return 0; fi
  "$@"
}
# Same, for the calls whose stdout the converge deliberately discards.
run_quiet() {
  if [ "${DRY_RUN}" -eq 1 ]; then printf '  would run: %s\n' "$*"; return 0; fi
  "$@" >/dev/null
}

if [ "${DRY_RUN}" -eq 0 ]; then
  command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
  : "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"
fi

log "crates-proxy 1. Apply the Namespace, nginx ConfigMap, Deployment and Service"
run kubectl apply -f "${SCRIPT_DIR}/crates-proxy.yaml"
# A changed ConfigMap does not restart the Deployment by itself; stamp the
# config's hash onto the pod template so a config edit rolls the pod.
conf_hash="$(sha256sum "${SCRIPT_DIR}/crates-proxy.yaml" | cut -c1-16)"
run_quiet kubectl -n "${NAMESPACE}" patch deployment crates-proxy --type=merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ci-runner.io/config-hash\":\"${conf_hash}\"}}}}}"

log "crates-proxy 2. Wait (bounded, ${ROLLOUT_TIMEOUT}) for the rollout"
if [ "${DRY_RUN}" -eq 1 ]; then
  run kubectl -n "${NAMESPACE}" rollout status deployment/crates-proxy --timeout="${ROLLOUT_TIMEOUT}"
  echo "DRY RUN: nothing was applied."
  exit 0
fi
if kubectl -n "${NAMESPACE}" rollout status deployment/crates-proxy --timeout="${ROLLOUT_TIMEOUT}"; then
  echo "crates-proxy ready: crates-proxy.${NAMESPACE}.svc.cluster.local:3080 (pods), hostPort 3080 (node)"
else
  echo "WARN: crates-proxy rollout not complete after ${ROLLOUT_TIMEOUT}; jobs fetch from crates.io directly until it is Ready (kubectl -n ${NAMESPACE} get pods)"
fi

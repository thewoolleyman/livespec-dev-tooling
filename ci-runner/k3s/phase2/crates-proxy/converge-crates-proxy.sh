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
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="ci-crates-proxy"
ROLLOUT_TIMEOUT="${CRATES_PROXY_ROLLOUT_TIMEOUT:-120s}"

log() { printf '\n== %s ==\n' "$*"; }

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"

log "crates-proxy 1. Apply the Namespace, nginx ConfigMap, Deployment and Service"
kubectl apply -f "${SCRIPT_DIR}/crates-proxy.yaml"
# A changed ConfigMap does not restart the Deployment by itself; stamp the
# config's hash onto the pod template so a config edit rolls the pod.
conf_hash="$(sha256sum "${SCRIPT_DIR}/crates-proxy.yaml" | cut -c1-16)"
kubectl -n "${NAMESPACE}" patch deployment crates-proxy --type=merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ci-runner.io/config-hash\":\"${conf_hash}\"}}}}}" >/dev/null

log "crates-proxy 2. Wait (bounded, ${ROLLOUT_TIMEOUT}) for the rollout"
if kubectl -n "${NAMESPACE}" rollout status deployment/crates-proxy --timeout="${ROLLOUT_TIMEOUT}"; then
  echo "crates-proxy ready: crates-proxy.${NAMESPACE}.svc.cluster.local:3080 (pods), hostPort 3080 (node)"
else
  echo "WARN: crates-proxy rollout not complete after ${ROLLOUT_TIMEOUT}; jobs fetch from crates.io directly until it is Ready (kubectl -n ${NAMESPACE} get pods)"
fi

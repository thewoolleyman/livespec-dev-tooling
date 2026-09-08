#!/usr/bin/env bash
# converge-registry-mirror.sh — the one idempotent converge of the ghcr
# pull-through cache's cluster objects (./registry-mirror.yaml: Namespace,
# config ConfigMap, Deployment, Service). Applies, waits briefly for the
# rollout, and exits. Item `livespec-h96p`.
#
# Same shape and the same reasons as ../../crates-proxy/converge-crates-proxy.sh:
# these objects live in the k3s datastore, which is tmpfs and EMPTY on every
# boot (../../datastore-tmpfs/), so a converge belongs on the boot path
# (../../reconstruct/converge-ci-stack.sh) as well as in the operator's hand
# after editing the manifest. The store under
# /var/cache/ci-runner/registry-mirror survives a reboot untouched.
#
# NOT YET WIRED INTO THE BOOT CONVERGE. `livespec-h96p` is repository work: the
# mirror has never been applied to the cluster, so adding it to
# ../../reconstruct/converge-ci-stack.sh — which runs unattended on every boot —
# would put an unexercised Deployment on the boot path. Wiring it in is part of
# the maintainer-gated apply step, together with
# ../../reconstruct/install-converge-unit.sh so the boot copy under
# /usr/local/lib/ci-runner-k3s/ matches. ../README.md "Sandbox image hygiene"
# carries that sequence.
#
# THE ROLLOUT WAIT IS BOUNDED, and a mirror that is not Ready is not an outage:
# containerd's default endpoint is always tried last, so every pull simply goes
# to ghcr as it does today (./registries.yaml.template's header).
#
# --dry-run PRINTS every command this converge would run, in order, and
# executes NOTHING — no cluster write, no cluster read, not even the kubectl
# and KUBECONFIG preconditions — so it is safe to run from a checkout on a
# machine that is not the node. Each printed line comes from the same `run`
# wrapper that would execute it, so the plan cannot drift from the body.
#
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="ci-registry-mirror"
ROLLOUT_TIMEOUT="${REGISTRY_MIRROR_ROLLOUT_TIMEOUT:-120s}"

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
  : "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../../provision-k3s.sh)}"
fi

log "registry-mirror 1. Apply the Namespace, config ConfigMap, Deployment and Service"
run kubectl apply -f "${SCRIPT_DIR}/registry-mirror.yaml"
# A changed ConfigMap does not restart the Deployment by itself; stamp the
# config's hash onto the pod template so a config edit rolls the pod.
conf_hash="$(sha256sum "${SCRIPT_DIR}/registry-mirror.yaml" | cut -c1-16)"
run_quiet kubectl -n "${NAMESPACE}" patch deployment registry-mirror --type=merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ci-runner.io/config-hash\":\"${conf_hash}\"}}}}}"

log "registry-mirror 2. Wait (bounded, ${ROLLOUT_TIMEOUT}) for the rollout"
if [ "${DRY_RUN}" -eq 1 ]; then
  run kubectl -n "${NAMESPACE}" rollout status deployment/registry-mirror --timeout="${ROLLOUT_TIMEOUT}"
  echo "DRY RUN: nothing was applied."
  exit 0
fi
if kubectl -n "${NAMESPACE}" rollout status deployment/registry-mirror --timeout="${ROLLOUT_TIMEOUT}"; then
  echo "registry-mirror ready: hostPort 5001 on the cache-tier carrier node"
  echo "verify from that node: curl -fsS http://127.0.0.1:5001/v2/ && echo OK"
  echo "then install the node half on each node: ./install-registry-mirror.sh <profile>"
else
  echo "WARN: registry-mirror rollout not complete after ${ROLLOUT_TIMEOUT}; every image pull falls back to ghcr until it is Ready (kubectl -n ${NAMESPACE} get pods)"
fi

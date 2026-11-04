#!/usr/bin/env bash
# converge-hook-pod-template.sh — idempotently converge the
# `arc-hook-pod-template` ConfigMap in arc-runners from ./hook-pod-template.yaml.
#
# Called by ../apparmor/install-apparmor-profile.sh (which also loads the
# AppArmor profile the template names) and by
# ../warm-cache/install-warm-cache.sh (which owns the UV_CACHE_DIR the
# template carries). One converge, two callers, so the two installers cannot
# drift on how the ConfigMap is written. Runner pods mount this ConfigMap and
# point ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE at it — see
# ./values-livespec-overseer.yaml. A NEW workflow pod reads the converged
# template; existing runner pods keep the old ConfigMap content mounted until
# they are recycled (./recycle-scale-set-runners.sh).
#
# --dry-run (this SCRIPT's flag, not kubectl's) PRINTS the apply this converge
# would run and executes NOTHING — not even the kubectl and KUBECONFIG
# preconditions — so it is safe to run from a checkout on a machine that is
# not the node. Added with the two-node precondition work (plan
# k3s-on-gmktec-for-vps-usage, carrier R3), because this template is where the
# per-node cache-telemetry endpoint lives.
#
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_SRC="${SCRIPT_DIR}/hook-pod-template.yaml"
CONFIGMAP_NAME="arc-hook-pod-template"
RUNNERS_NAMESPACE="arc-runners"

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

if [ "${DRY_RUN}" -eq 0 ]; then
  command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
  : "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"
fi

# kubectl's OWN `--dry-run=client | apply` below is the idempotent
# create-or-update form; a bare `kubectl create configmap` fails on the second
# run. It is unrelated to this script's --dry-run, which suppresses the apply.
if [ "${DRY_RUN}" -eq 1 ]; then
  printf '  would run: kubectl create configmap %s --namespace %s --from-file=hook-pod-template.yaml=%s --dry-run=client -o yaml | kubectl apply -f -\n' \
    "${CONFIGMAP_NAME}" "${RUNNERS_NAMESPACE}" "${TEMPLATE_SRC}"
  echo "DRY RUN: nothing was applied."
  exit 0
fi
kubectl create configmap "${CONFIGMAP_NAME}" \
  --namespace "${RUNNERS_NAMESPACE}" \
  --from-file="hook-pod-template.yaml=${TEMPLATE_SRC}" \
  --dry-run=client -o yaml | kubectl apply -f -

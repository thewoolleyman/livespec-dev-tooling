#!/usr/bin/env bash
# converge-hook-pod-template.sh — idempotently converge the
# `arc-hook-pod-template` ConfigMap in arc-runners from ./hook-pod-template.yaml.
#
# Called by ../apparmor/install-apparmor-profile.sh (which also loads the
# AppArmor profile the template names) and by
# ../warm-cache/install-warm-cache.sh (which adds the warm-cache mount the
# template carries). One converge, two callers, so the two installers cannot
# drift on how the ConfigMap is written. Runner pods mount this ConfigMap and
# point ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE at it — see
# ./values-livespec-overseer.yaml. A NEW workflow pod reads the converged
# template; existing runner pods keep the old ConfigMap content mounted until
# they are recycled (./recycle-scale-set-runners.sh).
#
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_SRC="${SCRIPT_DIR}/hook-pod-template.yaml"
CONFIGMAP_NAME="arc-hook-pod-template"
RUNNERS_NAMESPACE="arc-runners"

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"

# --dry-run=client | apply is the idempotent create-or-update form; a bare
# `kubectl create configmap` fails on the second run.
kubectl create configmap "${CONFIGMAP_NAME}" \
  --namespace "${RUNNERS_NAMESPACE}" \
  --from-file="hook-pod-template.yaml=${TEMPLATE_SRC}" \
  --dry-run=client -o yaml | kubectl apply -f -

#!/usr/bin/env bash
# install-arc.sh — idempotently install Actions Runner Controller (ARC) on
# the k3s cluster provision-k3s.sh created. Two Helm releases: the
# controller itself, then two gha-runner-scale-set releases (shared pool
# label + host-unique label — see arc/values.yaml for why two releases).
#
# Pinned chart version: 0.14.2 for BOTH
# gha-runner-scale-set-controller and gha-runner-scale-set.
#
# Requires: helm on PATH, KUBECONFIG pointed at the k3s cluster
# (export KUBECONFIG=/etc/rancher/k3s/k3s.yaml, or provision-k3s.sh's
# default install location), and the secret named in arc/values.yaml
# (arc-github-app-installation) already created — see the "Credential
# separation" section of README.md for exactly what goes in it and why
# this script does NOT create it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARC_CHART_VERSION="0.14.2"
CONTROLLER_NAMESPACE="arc-systems"
RUNNERS_NAMESPACE="arc-runners"

log() { printf '\n== %s ==\n' "$*"; }

command -v helm >/dev/null || { echo "FATAL: helm not found on PATH"; exit 1; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see provision-k3s.sh)}"

# ---------------------------------------------------------------------------
log "0. Pre-gate: the credential secret must already exist (never created here)"
if ! kubectl get secret arc-github-app-installation -n "$CONTROLLER_NAMESPACE" >/dev/null 2>&1; then
  cat <<'EOF'
FATAL: secret arc-github-app-installation not found in arc-systems.
Create it from the fleet's least-privilege GitHub App installation token
BEFORE running this script (README.md "Credential separation" documents
the exact scope). This script never handles or persists that credential
itself — only the operator's own out-of-band step does.
EOF
  exit 1
fi

# ---------------------------------------------------------------------------
log "1. Install/upgrade the ARC controller (idempotent via helm upgrade --install)"
helm upgrade --install arc \
  --namespace "$CONTROLLER_NAMESPACE" --create-namespace \
  --version "$ARC_CHART_VERSION" \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller

kubectl -n "$CONTROLLER_NAMESPACE" rollout status deployment -l app.kubernetes.io/name=gha-rs-controller --timeout=120s

# ---------------------------------------------------------------------------
log "2. Install/upgrade BOTH runner scale sets (shared pool label + host-unique label)"
helm upgrade --install local-ci-k3s \
  --namespace "$RUNNERS_NAMESPACE" --create-namespace \
  --version "$ARC_CHART_VERSION" \
  -f "${SCRIPT_DIR}/arc/values.yaml" \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set

helm upgrade --install poweredge-xubuntu-k3s \
  --namespace "$RUNNERS_NAMESPACE" \
  --version "$ARC_CHART_VERSION" \
  -f "${SCRIPT_DIR}/arc/values-host-unique.yaml" \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set

# ---------------------------------------------------------------------------
log "3. Verify both scale sets are healthy (minRunners: 0 is expected — no idle pods yet)"
kubectl -n "$RUNNERS_NAMESPACE" get autoscalingrunnersets.actions.github.com

log "DONE. Next: install-kueue.sh, then run the proof job (test-job/proof-job.yml)."

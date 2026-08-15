#!/usr/bin/env bash
# install-kueue.sh — idempotently install Kueue v0.19.1 on the k3s cluster,
# then apply the minimal phase-1 ResourceFlavor/ClusterQueue/LocalQueue
# under kueue/resources.yaml so Kueue is provably healthy and admits a
# workload. Modeling this fleet's actual admission/fair-share formula
# (livespec-dev-tooling SPECIFICATION/non-functional-requirements.md
# section "Adaptive JIT runner admission budget") as Kueue Cohorts/Fair
# Sharing is explicitly PHASE 2 of the migration (see
# plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md in the
# livespec repo) — the resources here are the smallest shape that lets
# Kueue admit the phase-1 proof job, nothing more.
#
# Pinned version: v0.19.1 (the manifest release tag, applied directly —
# Kueue's own recommended install path for a single-cluster deployment,
# no Helm chart needed at this version for the core install).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUEUE_VERSION="v0.19.1"

log() { printf '\n== %s ==\n' "$*"; }

: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see provision-k3s.sh)}"

# ---------------------------------------------------------------------------
log "1. Install/upgrade Kueue core (idempotent — kubectl apply is a no-op on repeat)"
kubectl apply --server-side --force-conflicts -f \
  "https://github.com/kubernetes-sigs/kueue/releases/download/${KUEUE_VERSION}/manifests.yaml"

kubectl -n kueue-system rollout status deployment/kueue-controller-manager --timeout=180s

# ---------------------------------------------------------------------------
log "2. Apply the phase-1 ResourceFlavor / ClusterQueue / LocalQueue"
kubectl apply -f "${SCRIPT_DIR}/kueue/resources.yaml"

# ---------------------------------------------------------------------------
log "3. Verify healthy"
kubectl -n kueue-system get pods
kubectl get clusterqueue phase1-proof-cq
kubectl -n arc-runners get localqueue phase1-proof-lq

log "DONE. Kueue installed and admitting the phase-1 ClusterQueue. Next: run the proof job."

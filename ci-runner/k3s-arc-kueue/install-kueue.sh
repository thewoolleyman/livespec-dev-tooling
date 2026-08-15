#!/usr/bin/env bash
# install-kueue.sh — idempotently install Kueue onto the k3s cluster and apply a
# MINIMAL proof-of-life ResourceFlavor / ClusterQueue / LocalQueue set.
#
# Run with sudo, after install-k3s.sh and install-arc.sh:
#   sudo ci-runner/k3s-arc-kueue/install-kueue.sh
#
# Phase 1 of the k3s + ARC + Kueue migration (livespec work-item
# livespec-s43svm.14). Design record:
# livespec/plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md
#
# The fleet's actual admission/fair-share formula is NOT modelled here — that is
# work-item livespec-s43svm.15. See kueue-proof-of-life.yaml's own scope note.
set -euo pipefail

# Pinned deliberately — never float `latest`.
KUEUE_VERSION="${KUEUE_VERSION:-v0.19.1}"
# Referenced at the pinned URL rather than vendored: it is a large upstream
# bundle (CRDs + controller + webhooks) that would silently rot as a copy.
KUEUE_MANIFEST="https://github.com/kubernetes-sigs/kueue/releases/download/${KUEUE_VERSION}/manifests.yaml"

src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '%s\n' "install-kueue: $*" >&2; }

[ "$(id -u)" -eq 0 ] || { log "must run as root (use sudo)"; exit 1; }
[ -r /etc/rancher/k3s/k3s.yaml ] || { log "no k3s kubeconfig; run install-k3s.sh first"; exit 1; }

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# `--server-side` is upstream's documented install form and is what makes the
# apply idempotent across re-runs: the CRDs exceed the client-side
# last-applied-configuration annotation limit, so a plain `kubectl apply` fails
# on the second run.
log "applying Kueue ${KUEUE_VERSION}"
kubectl apply --server-side -f "${KUEUE_MANIFEST}"

log "waiting for the Kueue controller to become Available (up to 180s)"
if ! kubectl wait --for=condition=Available --timeout=180s \
    -n kueue-system deployment/kueue-controller-manager; then
  log "Kueue controller did not become Available; inspect:"
  log "  kubectl -n kueue-system logs deployment/kueue-controller-manager"
  exit 1
fi

# The webhook needs a moment past Deployment-Available before it will admit the
# queue objects; without this the first apply below can lose a race and fail
# with a connection-refused webhook error on an otherwise-healthy install.
kubectl wait --for=condition=Ready --timeout=120s \
  -n kueue-system pod -l control-plane=controller-manager

log "applying the minimal proof-of-life queue set"
kubectl apply -f "${src_dir}/kueue-proof-of-life.yaml"

kubectl get clusterqueue,resourceflavor
kubectl get localqueue -n arc-runners

log "Kueue ${KUEUE_VERSION} installed with a placeholder queue set."
log "Fair-share/cohort modelling is livespec-s43svm.15, not this phase."

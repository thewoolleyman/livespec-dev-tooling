#!/usr/bin/env bash
# install-k3s.sh — idempotently install a single-node k3s server on this host,
# ALONGSIDE the existing rootless-podman/dockershim runner pool. Nothing in the
# existing pool is stopped, disabled, reconfigured, or removed by this script.
#
# Run with sudo from the repo (or a worktree of it):
#   sudo ci-runner/k3s-arc-kueue/install-k3s.sh
#
# Phase 1 of the k3s + ARC + Kueue migration (livespec work-item
# livespec-s43svm.14). Design record:
# livespec/plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md
#
# WHY SINGLE-NODE, AND WHY ITS EMBEDDED SQLITE IS NOT THE PODMAN FAILURE MODE
# --------------------------------------------------------------------------
# k3s defaults its control-plane datastore to embedded SQLite, and the podman
# incident chain (livespec-s43svm.10/.11/.12/.13) was SQLite lock contention —
# so the resemblance deserves an explicit answer rather than silence.
#
# The migration research record (§"Why k3s, not a 'full' kubeadm-provisioned
# Kubernetes") states the distinction directly: the podman contention came from
# hundreds of INDEPENDENT short-lived CLI processes each opening and locking the
# shared libpod state file concurrently. k3s's datastore is opened by exactly ONE
# long-lived server process, which serialises its own access internally; there is
# no CLI-per-invocation fan-out against the file at all. Same storage engine,
# structurally different access pattern, so not the same failure mode.
#
# It is also not a one-way door: k3s supports embedded etcd (3+ server nodes) or
# an external datastore if the fleet's "multi-host, poweredge-xubuntu first"
# trajectory ever needs it. Multi-master HA is deliberately NOT provisioned here —
# this is one bare-metal homelab host with no cloud provider and a purely-outbound
# network posture, so the HA control plane and the cloud LoadBalancer/dynamic-
# storage integrations a kubeadm cluster brings are not load-bearing.
set -euo pipefail

# Pinned deliberately — never float `latest`. Bumping this is a reviewed change.
K3S_VERSION="${K3S_VERSION:-v1.36.2+k3s1}"

# The official installer is fetched, not vendored: upstream signs and maintains
# it, and vendoring a 1100-line third-party bootstrap script would be a copy that
# silently rots. What IS pinned is the version it installs.
K3S_INSTALL_URL="${K3S_INSTALL_URL:-https://get.k3s.io}"

log() { printf '%s\n' "install-k3s: $*" >&2; }

[ "$(id -u)" -eq 0 ] || { log "must run as root (use sudo)"; exit 1; }

# --- idempotence: converge, do not reinstall over a matching version ---
if command -v k3s >/dev/null 2>&1; then
  installed="$(k3s --version 2>/dev/null | awk '/^k3s version/ { print $3 }')"
  if [ "${installed}" = "${K3S_VERSION}" ]; then
    log "k3s ${K3S_VERSION} already installed; skipping installer"
  else
    log "k3s ${installed:-unknown} installed, want ${K3S_VERSION}; re-running installer"
    installed=""
  fi
else
  installed=""
fi

if [ -z "${installed}" ]; then
  log "installing k3s ${K3S_VERSION} (single-node server)"
  # --write-kubeconfig-mode 0644 so a non-root operator can read
  # /etc/rancher/k3s/k3s.yaml without sudo for `kubectl get nodes`.
  # No --disable flags: the default bundled containerd, flannel, CoreDNS,
  # local-path-provisioner and traefik-less service LB are what ARC needs.
  curl -sfL "${K3S_INSTALL_URL}" \
    | INSTALL_K3S_VERSION="${K3S_VERSION}" \
      INSTALL_K3S_EXEC="server --write-kubeconfig-mode 0644" \
      sh -
fi

systemctl enable --now k3s

# --- verification: the node must actually reach Ready ---
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

log "waiting for the node to report Ready (up to 180s)"
if ! k3s kubectl wait --for=condition=Ready node --all --timeout=180s; then
  log "node did not reach Ready; inspect: journalctl -u k3s -n 200 --no-pager"
  exit 1
fi

k3s kubectl get nodes -o wide
log "k3s ${K3S_VERSION} is up and Ready"
log "kubeconfig: /etc/rancher/k3s/k3s.yaml (export KUBECONFIG to use kubectl)"
log "next: ci-runner/k3s-arc-kueue/install-arc.sh"

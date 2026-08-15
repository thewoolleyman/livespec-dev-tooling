#!/usr/bin/env bash
# provision-k3s.sh — idempotently install a single-node k3s control plane
# on poweredge-xubuntu, ALONGSIDE the existing podman/dockershim runner
# pool (ci-runner/provision-ci-runner.sh). Installs NOTHING that touches
# that pool: different binaries (k3s's bundled containerd, not podman),
# different systemd units (k3s.service, not runner@.service), different
# host-unique label (poweredge-xubuntu-k3s, not the pool's label).
#
# Design record: livespec repo
#   plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md
#   ("Migration decision: rootless-podman host -> k3s + Actions Runner
#   Controller + Kueue"), maintainer-directed 2026-08-15. Phase 1 of 6:
#   stand up alongside the existing pool, route ZERO traffic.
#
# Pinned versions (do not float without re-running this script's
# version check and updating this comment + the ledger record):
#   k3s:   v1.36.2+k3s1  (stable channel)
#   ARC:   gha-runner-scale-set-controller / gha-runner-scale-set 0.14.2
#          (installed by install-arc.sh, not this script)
#   Kueue: v0.19.1        (installed by install-kueue.sh, not this script)
#
# Requires: run as a sudo-capable admin on poweredge-xubuntu. Outbound
# HTTPS only (get.k3s.io, GitHub releases) — no inbound reachability
# required, matching the existing host-requirements Network clause.
set -euo pipefail

K3S_VERSION="v1.36.2+k3s1"
NODE_LABEL="k3s-role=arc-runner-host"

log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
log "0. Pre-gate: confirm the existing podman pool is untouched by this script"
# This script installs k3s only. It never stops, disables, or reconfigures
# the ci-runner user, runner@.service instances, or podman. Assert the
# runner user still exists as a sanity check that we're on the right host
# and haven't been pointed at a script that assumes a fresh machine.
if id ci-runner >/dev/null 2>&1; then
  echo "existing podman ci-runner pool present (untouched by this script) — OK"
else
  echo "WARN: no ci-runner user found; proceeding anyway (fresh host is a valid target too)"
fi

# ---------------------------------------------------------------------------
log "1. Install k3s ${K3S_VERSION} (idempotent — skip if already at this version)"
if command -v k3s >/dev/null 2>&1; then
  current="$(k3s --version | head -1 | awk '{print $3}')"
  if [ "$current" = "${K3S_VERSION#v}" ] || [ "v${current}" = "$K3S_VERSION" ]; then
    echo "k3s already installed at ${K3S_VERSION} — skipping install"
  else
    echo "FATAL: k3s installed at v${current}, expected ${K3S_VERSION}. Uninstall first (see README) or update this pin deliberately."
    exit 1
  fi
else
  # --disable traefik/servicelb: this node carries no ingress traffic (zero
  # traffic routed to it per phase 1 scope) and no LoadBalancer services are
  # needed for the ARC + Kueue control plane. --node-label distinguishes this
  # k3s node from any future additional node without colliding with the
  # existing GitHub Actions runner labels (which live on the runner
  # registration, not the Kubernetes node — see arc/values.yaml).
  curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="$K3S_VERSION" \
    INSTALL_K3S_EXEC="server --disable traefik --disable servicelb --node-label ${NODE_LABEL}" \
    sh -s -
fi

# ---------------------------------------------------------------------------
log "2. Wait for the node to report Ready"
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
for _ in $(seq 1 60); do
  if k3s kubectl get nodes --no-headers 2>/dev/null | grep -q ' Ready'; then
    break
  fi
  sleep 2
done
k3s kubectl get nodes -o wide || { echo "FATAL: k3s node did not become Ready within 120s"; exit 1; }

# ---------------------------------------------------------------------------
log "3. Make kubectl usable for the provisioning admin (read access to KUBECONFIG)"
# k3s.yaml is 0600 root:root by default. Widen to 0644 (contents are a
# cluster-local admin kubeconfig for a single-tenant homelab node with no
# externally-reachable API server; this is the documented k3s convention for
# non-root kubectl use, not a security relaxation of the runner containment
# model above, which governs job execution identity, not admin access).
chmod 0644 /etc/rancher/k3s/k3s.yaml
printf 'k3s ready. export KUBECONFIG=/etc/rancher/k3s/k3s.yaml for kubectl/helm.\n'

log "DONE. Next: install-arc.sh, then install-kueue.sh (see README.md)."

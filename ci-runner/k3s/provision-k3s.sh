#!/usr/bin/env bash
# provision-k3s.sh — idempotently install a single-node k3s control plane
# on poweredge-xubuntu.
#
# Authored to install ALONGSIDE the then-live podman/dockershim runner
# pool, touching NOTHING that pool owned: different binaries (k3s's
# bundled containerd, not podman), different systemd units (k3s.service,
# not runner@.service), different host-unique label (poweredge-xubuntu-k3s,
# not the pool's label). That pool was decommissioned 2026-08-21 and its
# source deleted under livespec-s43svm.19; the isolation this script keeps
# is recorded because it is why the cutover was safe, not because there is
# still a second pool.
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_VERSION="v1.36.2+k3s1"
HELM_VERSION="v3.21.4"        # co-maintained with README.md "Pinned versions"
NODE_LABEL="k3s-role=arc-runner-host"
# The pool's hostPath singletons — the sccache redis, the crates proxy, the
# PyPI files proxy and the warm-cache CronJob — mount directories on THIS
# node's storage tiers, so they pin to this label and not to NODE_LABEL above.
# NODE_LABEL is the RUNNER role: every node that joins the pool to execute
# workflow pods carries it, including a second node that carries no tier, so it
# cannot express "the node whose disks these directories are on". Set below
# (step 2b) rather than via --node-label, because --node-label applies only on
# a FRESH install and this script must be re-runnable on a provisioned node.
TIER_CARRIER_LABEL="ci-runner.io/cache-tier-carrier=true"
# The tier whose presence PROVES this node is the carrier (phase2/
# storage-layout/): the label is only set when it is actually mounted here.
CACHE_TIER_MOUNT="${CI_CACHE_TIER_MOUNT:-/var/cache/ci-runner}"

log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
log "0. Install the fleet's k3s server config BEFORE the first k3s start"
# /etc/rancher/k3s/config.yaml (kubelet max-pods, the bundled local-storage
# disable) is read by k3s on every start; installing it first means a fresh
# node's very first start already carries it, and a rebuilt node cannot lose
# the hand-set values this replaced (livespec-a6lxuv, livespec-sernfh). The
# installer is idempotent and never restarts k3s.
"${SCRIPT_DIR}/phase2/k3s-config/install-k3s-config.sh"

# ---------------------------------------------------------------------------
log "1. Install k3s ${K3S_VERSION} (idempotent — skip if already at this version)"
if command -v k3s >/dev/null 2>&1; then
  # `k3s --version` prints `k3s version v1.36.2+k3s1 (01b6f04a)`: field 3
  # already carries the leading `v`. Compare with and without it, since the
  # original test only compared against a stripped form and a re-prefixed
  # form ("vv1.36…") and so REFUSED every re-run on an installed host — found
  # 2026-09-02 the first time this script was re-run live for idempotency.
  current="$(k3s --version | head -1 | awk '{print $3}')"
  if [ "$current" = "$K3S_VERSION" ] || [ "$current" = "${K3S_VERSION#v}" ] || [ "v${current}" = "$K3S_VERSION" ]; then
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
  # registration, not the Kubernetes node — see arc/values-host-unique.yaml).
  curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="$K3S_VERSION" \
    INSTALL_K3S_EXEC="server --disable traefik --disable servicelb --node-label ${NODE_LABEL}" \
    sh -s -
fi

# ---------------------------------------------------------------------------
log "1b. Install helm ${HELM_VERSION} (idempotent — skip if already at this version)"
# The reconstruct-on-boot converge (phase2/reconstruct/converge-ci-stack.sh)
# fails closed without helm on PATH, and until 2026-09-02 nothing in git
# installed it — the live /usr/local/bin/helm was hand-placed, so a rebuilt
# host would boot into a cluster the converge could not rebuild. Pinned and
# checksum-verified against the release's published .sha256sum.
if command -v helm >/dev/null 2>&1 && helm version --short 2>/dev/null | grep -q "^${HELM_VERSION}+"; then
  echo "helm already installed at ${HELM_VERSION} — skipping install"
else
  arch="$(uname -m)"
  case "$arch" in
    x86_64) helm_arch=amd64 ;;
    aarch64) helm_arch=arm64 ;;
    *) echo "FATAL: unsupported arch for helm: ${arch}"; exit 1 ;;
  esac
  tarball="helm-${HELM_VERSION}-linux-${helm_arch}.tar.gz"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL --retry 3 -o "${tmp}/${tarball}" "https://get.helm.sh/${tarball}"
  curl -fsSL --retry 3 -o "${tmp}/${tarball}.sha256sum" "https://get.helm.sh/${tarball}.sha256sum"
  (cd "$tmp" && sha256sum -c "${tarball}.sha256sum")
  tar -xzf "${tmp}/${tarball}" -C "$tmp" "linux-${helm_arch}/helm"
  install -o root -g root -m 0755 "${tmp}/linux-${helm_arch}/helm" /usr/local/bin/helm
fi
echo "helm: $(helm version --short)"

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
log "2b. Label this node as the cache-tier carrier (idempotent)"
# k3s defaults --node-name to the lowercased hostname; K3S_NODE_NAME overrides
# it for a host whose k3s node name was set otherwise.
node_name="${K3S_NODE_NAME:-$(hostname | tr '[:upper:]' '[:lower:]')}"
if findmnt -no TARGET "${CACHE_TIER_MOUNT}" >/dev/null 2>&1; then
  # `kubectl label --overwrite` IS the idempotent form: on a re-run it patches
  # the same value and reports "not labeled" instead of failing the way a bare
  # `kubectl label` does once the key exists.
  k3s kubectl label node "${node_name}" "${TIER_CARRIER_LABEL}" --overwrite
  echo "${node_name} carries ${CACHE_TIER_MOUNT}; labelled ${TIER_CARRIER_LABEL}"
else
  # Not fatal: a node may legitimately join the pool to run workflow pods
  # without carrying a tier. It simply must not attract the hostPath
  # singletons, and an absent label is exactly how it does not.
  echo "WARN: ${CACHE_TIER_MOUNT} is not a mountpoint on ${node_name} — NOT labelling it ${TIER_CARRIER_LABEL}; the hostPath singletons (sccache redis, crates proxy, PyPI proxy, warm-cache CronJob) will not schedule here"
fi

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

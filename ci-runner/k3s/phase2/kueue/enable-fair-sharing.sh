#!/usr/bin/env bash
# enable-fair-sharing.sh — idempotently turn on Kueue's cluster-wide Fair
# Sharing feature, which phase 1's install-kueue.sh deliberately did NOT
# do (it installed Kueue's released manifests.yaml with defaults —
# fairSharing is off by default at v0.19.1). Fair Sharing is what makes
# "repositories MAY fairly borrow unused shared capacity"
# (SPECIFICATION/non-functional-requirements.md section "Adaptive JIT
# runner admission budget") an enforced property of the Cohort rather
# than an aspiration: without it, Kueue still lets one ClusterQueue
# borrow unused quota from a cohort-mate, but admission order among
# COMPETING pending workloads is FIFO-by-queue-time rather than ordered
# by each repository's historical share of borrowed capacity — the
# "fair" half of fair borrowing.
#
# Run ONCE after install-kueue.sh, before applying resource-flavor.yaml
# or any cluster-queue-*.yaml (each sets spec.fairSharing.weight, which
# is inert until this is enabled cluster-wide).
#
# DELIBERATELY NOT a fully unattended patch: Kueue's Configuration
# object lives as opaque YAML text inside ONE key
# (controller_manager_config.yaml) of the kueue-manager-config
# ConfigMap, not as structured fields kubectl can strategic-merge — a
# scripted rewrite would need to parse and re-serialize that YAML,
# which this design-phase deliverable does not attempt to get right
# without a live cluster to verify it against (see
# ../VALIDATION_CHECKLIST.md item 1). `kubectl edit` on a single line
# is the correct-weight tool for a one-time, human-supervised install
# step; this script does everything AROUND that edit (dump the current
# config so the operator can see the exact starting point, wait for
# the edit, verify it landed, then restart).
set -euo pipefail

: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../provision-k3s.sh)}"

log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
log "1. Current kueue-manager-config (before edit)"
kubectl -n kueue-system get configmap kueue-manager-config \
  -o jsonpath='{.data.controller_manager_config\.yaml}'
printf '\n'

if kubectl -n kueue-system get configmap kueue-manager-config \
  -o jsonpath='{.data.controller_manager_config\.yaml}' | grep -q '^fairSharing:'; then
  echo "fairSharing already present — skipping the edit step (idempotent)"
else
  log "2. Opening \$EDITOR — add this top-level block, then save and quit:"
  cat <<'EOF'
fairSharing:
  enable: true
EOF
  read -r -p "Press Enter to open 'kubectl edit configmap kueue-manager-config -n kueue-system' now..."
  kubectl -n kueue-system edit configmap kueue-manager-config
fi

# ---------------------------------------------------------------------------
log "3. Verify the block landed"
if ! kubectl -n kueue-system get configmap kueue-manager-config \
  -o jsonpath='{.data.controller_manager_config\.yaml}' | grep -q '^fairSharing:'; then
  echo "FATAL: fairSharing block not found after edit — re-run this script." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
log "4. Restart the controller manager to pick up the new config (no live-reload)"
kubectl -n kueue-system rollout restart deployment/kueue-controller-manager
kubectl -n kueue-system rollout status deployment/kueue-controller-manager --timeout=180s

log "DONE. Fair Sharing enabled. Apply resource-flavor.yaml, cluster-queue-*.yaml next."

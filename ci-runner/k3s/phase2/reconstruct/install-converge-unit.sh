#!/usr/bin/env bash
# install-converge-unit.sh — install the boot-ordered CI-cluster-stack
# reconstruct on the k3s host: copy converge-ci-stack.sh AND every artifact it
# applies into /usr/local/lib/ci-runner-k3s/, then install and ENABLE (not
# start) converge-ci-stack.service so it converges on the NEXT boot.
#
# WHY COPY THE WHOLE ARTIFACT SET (not just the one script): converge-ci-stack.sh
# is boot-critical and, unlike the self-contained patch-node-churn-capacity.sh
# (../node-extended-resource/), it APPLIES a tree of repo YAML and scripts:
#   arc/            values-*.yaml, the hook template + its converge
#   kueue/          resource-flavor + cluster-queue-*
#   local-path-provisioner/   the fleet-owned provisioner manifest
#   warm-cache/     converge-warm-cache.sh + the CronJob + the populate script
#   observability/  the Kueue-webhook probe's RBAC (from ci-runner/observability)
#   render-sa-kubeconfig.sh   the probe-credential renderer
# The live host carries NO repo checkout, so a boot unit cannot read those
# from a working tree. Copying the set into /usr/local/lib/ci-runner-k3s/ (the
# same dir that already holds patch-node-churn-capacity.sh, archive-arc-logs.sh,
# scan-wedged-runners.sh) makes the converge self-contained and boot-durable
# with no git checkout present. The repository stays the source of truth;
# THIS installer is the copy/refresh step — re-run it after editing ANY of the
# artifacts above or the converge script itself.
#
# WHY ENABLE, NOT --now: `systemctl enable --now` would START the service, which
# APPLIES the stack live. This installer enables the unit (it runs on next boot,
# or when an operator runs `systemctl start converge-ci-stack.service`) without
# applying anything now.
#
# NODE-LOCAL, like ../node-extended-resource/install-reapply-unit.sh: systemd
# units + /usr/local/lib copies are machine state. Re-run on any node rebuild.
#
# Requires: root (writes /usr/local/lib and /etc/systemd/system), systemd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PHASE2_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARC_SRC="${PHASE2_DIR}/arc"
KUEUE_SRC="${PHASE2_DIR}/kueue"
PROVISIONER_SRC="${PHASE2_DIR}/local-path-provisioner"
WARM_CACHE_SRC="${PHASE2_DIR}/warm-cache"
OBSERVABILITY_SRC="$(cd "${PHASE2_DIR}/../../observability" && pwd)"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="converge-ci-stack.service"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes /usr/local/lib and /etc/systemd/system)"; exit 1; }
command -v systemctl >/dev/null || { echo "FATAL: systemctl not found on PATH"; exit 1; }

# ---------------------------------------------------------------------------
log "1. Create the self-contained artifact tree under ${LIB_DIR}"
install -d -m 0755 "${LIB_DIR}" "${LIB_DIR}/arc" "${LIB_DIR}/kueue" \
  "${LIB_DIR}/local-path-provisioner" "${LIB_DIR}/warm-cache" "${LIB_DIR}/observability"

# ---------------------------------------------------------------------------
log "2. Copy the converge script (the unit's ExecStart target) and its helper"
install -m 0755 "${SCRIPT_DIR}/converge-ci-stack.sh" "${LIB_DIR}/converge-ci-stack.sh"
install -m 0755 "${SCRIPT_DIR}/render-sa-kubeconfig.sh" "${LIB_DIR}/render-sa-kubeconfig.sh"

# ---------------------------------------------------------------------------
log "3. Copy the arc/ artifacts converge applies (hook converge + template + values)"
install -m 0755 "${ARC_SRC}/converge-hook-pod-template.sh" "${LIB_DIR}/arc/converge-hook-pod-template.sh"
install -m 0644 "${ARC_SRC}/hook-pod-template.yaml" "${LIB_DIR}/arc/hook-pod-template.yaml"
# Every live scale set's values file; the EXAMPLE template is not a live release.
for f in "${ARC_SRC}"/values-*.yaml; do
  case "$f" in
    *"/values-EXAMPLE-repo.yaml") continue ;;
  esac
  install -m 0644 "$f" "${LIB_DIR}/arc/$(basename "$f")"
done

# ---------------------------------------------------------------------------
log "4. Copy the kueue/ artifacts converge applies (flavor + per-repo queues)"
# DERIVATION.md is documentation, not an applyable object — deliberately skipped.
install -m 0644 "${KUEUE_SRC}/resource-flavor.yaml" "${LIB_DIR}/kueue/resource-flavor.yaml"
for f in "${KUEUE_SRC}"/cluster-queue-*.yaml; do
  install -m 0644 "$f" "${LIB_DIR}/kueue/$(basename "$f")"
done

# ---------------------------------------------------------------------------
log "5. Copy the fleet-owned local-path provisioner manifest"
install -m 0644 "${PROVISIONER_SRC}/local-path-provisioner.yaml" "${LIB_DIR}/local-path-provisioner/local-path-provisioner.yaml"

# ---------------------------------------------------------------------------
log "6. Copy the warm-cache converge and the artifacts it applies"
install -m 0755 "${WARM_CACHE_SRC}/converge-warm-cache.sh" "${LIB_DIR}/warm-cache/converge-warm-cache.sh"
install -m 0644 "${WARM_CACHE_SRC}/warm-cache-cronjob.yaml" "${LIB_DIR}/warm-cache/warm-cache-cronjob.yaml"
install -m 0644 "${WARM_CACHE_SRC}/warm-cache-populate.sh" "${LIB_DIR}/warm-cache/warm-cache-populate.sh"

# ---------------------------------------------------------------------------
log "7. Copy the Kueue-webhook probe's RBAC manifest"
install -m 0644 "${OBSERVABILITY_SRC}/kueue-webhook-probe-rbac.yaml" "${LIB_DIR}/observability/kueue-webhook-probe-rbac.yaml"

# ---------------------------------------------------------------------------
log "8. Install the systemd unit"
install -m 0644 "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"

# ---------------------------------------------------------------------------
log "9. Enable on next boot (NOT --now: starting it applies the stack live)"
systemctl daemon-reload
systemctl enable "${SERVICE}"

# ---------------------------------------------------------------------------
log "10. Verify the unit is enabled"
state="$(systemctl is-enabled "${SERVICE}" 2>/dev/null || true)"
[ "$state" = "enabled" ] || { echo "FATAL: ${SERVICE} is '${state}', expected 'enabled'"; exit 1; }

log "DONE. ${SERVICE} enabled; it converges the CI cluster stack on next boot."
log "To converge NOW (applies live): systemctl start ${SERVICE}"

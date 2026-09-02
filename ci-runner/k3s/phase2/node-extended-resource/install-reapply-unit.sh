#!/usr/bin/env bash
# install-reapply-unit.sh — install the ci-runner.io/churn-slot reapply
# insurance on a k3s runner NODE: the patch script into /usr/local/lib, then the
# oneshot service and its 5-minute timer into /etc/systemd/system, with
# CAPACITY_PLACEHOLDER substituted for the capacity this node is intended to
# carry.
#
# WHY A SCRIPT rather than three hand-run `install` commands: the unit file
# shipped in this tree is deliberately NOT runnable as-is — its ExecStart says
# `CAPACITY_PLACEHOLDER` so that an un-edited copy fails loudly instead of
# silently reapplying a wrong number (see reapply-node-extended-resource.service's
# own header). That design makes installation a substitution step, and a
# substitution step done by hand is a step that gets done differently twice. It
# also encodes the dependency the unit file cannot state: the ExecStart path
# /usr/local/lib/ci-runner-k3s/patch-node-churn-capacity.sh is a COPY of a script
# living in this repository, so installing the unit without copying the script
# yields a timer that fires every five minutes and fails every time.
#
# NODE-LOCAL, like install-apparmor-profile.sh: systemd units are machine state.
# Re-run on any node added to the pool and after any node rebuild.
#
# The capacity argument is REQUIRED and is not defaulted, for exactly the reason
# patch-node-churn-capacity.sh does not default it: the safe number was a
# measurement, not a constant (see that script's header and
# ../kueue/DERIVATION.md). This unit makes an ALREADY-DECIDED number durable
# across restarts; it does not decide it.
#
# BOTH the timer AND the service are enabled (2026-09-02): the service is
# WantedBy=multi-user.target and Before=converge-ci-stack.service so a boot
# applies the resource before the queues that are denominated in it; the
# timer keeps reconciling it every five minutes after that.
#
# Requires: root, systemd, and the same KUBECONFIG the service itself uses.
set -euo pipefail

USAGE="usage: install-reapply-unit.sh CAPACITY (the currently-intended ci-runner.io/churn-slot node capacity -- see this script's header)"
CAPACITY="${1:?$USAGE}"
[[ "$CAPACITY" =~ ^[0-9]+$ ]] || { echo "FATAL: CAPACITY must be a non-negative integer, got '${CAPACITY}'" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="reapply-node-extended-resource.service"
TIMER="reapply-node-extended-resource.timer"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes /usr/local/lib and /etc/systemd/system)"; exit 1; }
command -v systemctl >/dev/null || { echo "FATAL: systemctl not found on PATH"; exit 1; }

# ---------------------------------------------------------------------------
log "1. Install the patch script to ${LIB_DIR} (the unit's ExecStart path)"
install -d -m 0755 "${LIB_DIR}"
install -m 0755 "${SCRIPT_DIR}/patch-node-churn-capacity.sh" "${LIB_DIR}/patch-node-churn-capacity.sh"

# ---------------------------------------------------------------------------
log "2. Install the unit files, substituting capacity=${CAPACITY}"
sed "s|CAPACITY_PLACEHOLDER|${CAPACITY}|" "${SCRIPT_DIR}/${SERVICE}" > "${UNIT_DIR}/${SERVICE}"
chmod 0644 "${UNIT_DIR}/${SERVICE}"
install -m 0644 "${SCRIPT_DIR}/${TIMER}" "${UNIT_DIR}/${TIMER}"

# Fail loudly rather than installing a unit that would fail every five minutes.
if grep -q CAPACITY_PLACEHOLDER "${UNIT_DIR}/${SERVICE}"; then
  echo "FATAL: CAPACITY_PLACEHOLDER survived substitution in ${UNIT_DIR}/${SERVICE}"
  exit 1
fi

# ---------------------------------------------------------------------------
log "3. Enable the service at boot and enable + start the timer"
systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl enable --now "${TIMER}"

# ---------------------------------------------------------------------------
log "4. Verify: run the service once now and read the resulting capacity back"
systemctl start "${SERVICE}"
systemctl --no-pager status "${TIMER}" || true
KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}" \
  kubectl get nodes -l k3s-role=arc-runner-host \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.ci-runner\.io/churn-slot}{"\n"}{end}'

log "DONE. ${TIMER} armed; ${SERVICE} reapplies capacity=${CAPACITY} at boot (before the converge) and every 5 minutes."

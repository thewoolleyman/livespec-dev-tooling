#!/usr/bin/env bash
# install-host-thermal.sh — install the node's iDRAC cooling convergence:
# racadm (install-racadm.sh), the apply script into /usr/local/lib, the boot
# unit into /etc/systemd/system, then apply NOW so the live host matches git
# without waiting for a reboot.
#
# NODE-LOCAL, like node-extended-resource/install-reapply-unit.sh: this is
# machine (iDRAC) state. Re-run on any PowerEdge node added to the pool and
# after any node rebuild. Idempotent — re-running refreshes the installed
# copies and re-converges (a converged host makes no changes).
#
# /usr/local/lib/ci-runner-k3s/apply-idrac-thermal.sh is a COPY of the script
# beside this installer (the same copy-into-/usr/local pattern the other
# node-local units use, so the unit does not depend on a git checkout path).
#
# Requires: root; outbound HTTPS to linux.dell.com the first time (racadm).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="apply-idrac-thermal.service"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes /usr/local/lib and /etc/systemd/system)" >&2; exit 1; }

# ---------------------------------------------------------------------------
log "1. racadm (pinned Dell packages; no-op when already installed)"
"${SCRIPT_DIR}/install-racadm.sh"

# ---------------------------------------------------------------------------
log "2. Install the apply script and the boot unit"
install -d -m 0755 "$LIB_DIR"
install -m 0755 "${SCRIPT_DIR}/apply-idrac-thermal.sh" "${LIB_DIR}/apply-idrac-thermal.sh"
install -m 0644 "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"
systemctl daemon-reload
systemctl enable "$SERVICE"

# ---------------------------------------------------------------------------
log "3. Converge now"
"${LIB_DIR}/apply-idrac-thermal.sh"

log "DONE. ${SERVICE} enabled; iDRAC cooling configuration converged."

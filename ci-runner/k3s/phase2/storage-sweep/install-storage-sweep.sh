#!/usr/bin/env bash
# install-storage-sweep.sh — install the boot-ordered orphaned-scratch sweep
# on a k3s runner NODE: the script into /usr/local/lib/ci-runner-k3s/ and the
# oneshot unit into /etc/systemd/system, ENABLED for next boot and never
# started here.
#
# WHY NEVER --now: the sweep removes every local-path volume directory and is
# safe ONLY Before=k3s.service on an empty-datastore boot (see the unit and
# script headers). Starting it under a running k3s is refused by the script,
# but the installer does not try. The sweep runs on the next boot.
#
# PRECONDITION: this sweep only makes sense on a node whose datastore is
# volatile (../datastore-tmpfs/). It pre-gates on that mount unit being
# enabled and refuses otherwise — on a persistent-datastore node the
# condition never holds and the unit would be inert clutter.
#
# NODE-LOCAL, like the sibling installers: re-run after any node rebuild.
# Requires: root, systemd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="sweep-runner-scratch.service"
MOUNT_UNIT="var-lib-rancher-k3s-server-db.mount"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes ${LIB_DIR} and ${UNIT_DIR})"; exit 1; }
command -v systemctl >/dev/null || { echo "FATAL: systemctl not found on PATH"; exit 1; }

# ---------------------------------------------------------------------------
log "0. Pre-gate: the tmpfs datastore mount must be enabled"
if ! systemctl is-enabled --quiet "$MOUNT_UNIT" 2>/dev/null; then
  echo "FATAL: ${MOUNT_UNIT} is not enabled. The sweep is only meaningful on a volatile-datastore node"
  echo "       (../datastore-tmpfs/install-datastore-tmpfs.sh first)."
  exit 1
fi
echo "${MOUNT_UNIT}: enabled — OK"

# ---------------------------------------------------------------------------
log "1. Install the sweep script to ${LIB_DIR}"
install -d -m 0755 "${LIB_DIR}"
install -m 0755 "${SCRIPT_DIR}/sweep-runner-scratch.sh" "${LIB_DIR}/sweep-runner-scratch.sh"

# ---------------------------------------------------------------------------
log "2. Install the unit and enable it for next boot (NEVER --now)"
install -m 0644 "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"
systemctl daemon-reload
systemctl enable "${SERVICE}"

# ---------------------------------------------------------------------------
log "3. Verify enabled"
state="$(systemctl is-enabled "${SERVICE}" 2>/dev/null || true)"
[ "$state" = "enabled" ] || { echo "FATAL: ${SERVICE} is '${state}', expected 'enabled'"; exit 1; }

log "DONE. ${SERVICE} enabled; it sweeps orphaned runner scratch before k3s on the next empty-datastore boot."

#!/usr/bin/env bash
# install-datastore-tmpfs.sh — install the tmpfs mount unit for the k3s
# kine/SQLite datastore on a k3s NODE, ENABLED for next boot and NEVER
# started here.
#
# WHY NEVER --now: the mount goes OVER /var/lib/rancher/k3s/server/db.
# Starting it while k3s is RUNNING would hide the live datastore from under
# a running SQLite — data-loss-shaped and unrecoverable for that session.
# Activation is a reboot, or a deliberate cutover with k3s STOPPED (see the
# mount unit's header). This installer only enables.
#
# PRECONDITION — never install this on a host that cannot rebuild an empty
# cluster. inject-github-app-secret.service and converge-ci-stack.service
# MUST be installed, enabled and proven first (the mount unit's header says
# why). This script pre-gates on both being enabled and refuses otherwise.
#
# ROLLBACK: with k3s stopped, `systemctl disable --now` the mount; the
# on-disk datastore underneath it is intact.
#
# NODE-LOCAL, like the sibling installers: re-run after any node rebuild.
# Requires: root, systemd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="/etc/systemd/system"
MOUNT_UNIT="var-lib-rancher-k3s-server-db.mount"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes ${UNIT_DIR})"; exit 1; }
command -v systemctl >/dev/null || { echo "FATAL: systemctl not found on PATH"; exit 1; }

# ---------------------------------------------------------------------------
log "0. Pre-gate: both reconstruct-on-boot units must be installed and enabled"
# A volatile datastore is safe ONLY if the cluster rebuilds itself on boot.
for u in inject-github-app-secret.service converge-ci-stack.service; do
  if ! systemctl is-enabled --quiet "$u" 2>/dev/null; then
    echo "FATAL: ${u} is not enabled. Install and enable the reconstruct-on-boot units"
    echo "       (secret-reinjection/ and reconstruct/) BEFORE making the datastore volatile."
    exit 1
  fi
  echo "${u}: enabled — OK"
done

# ---------------------------------------------------------------------------
log "1. Install the mount unit to ${UNIT_DIR}"
install -m 0644 "${SCRIPT_DIR}/${MOUNT_UNIT}" "${UNIT_DIR}/${MOUNT_UNIT}"

# ---------------------------------------------------------------------------
log "2. Reload systemd and enable the mount for next boot (NEVER --now)"
systemctl daemon-reload
systemctl enable "${MOUNT_UNIT}"

# ---------------------------------------------------------------------------
log "3. Verify enabled, and report the mount's current state"
# State alone cannot tell the ONE dangerous case (this mount placed over a
# RUNNING k3s's live datastore) from the correct post-cutover case (k3s
# started ON TOP of this mount); the header's never-`--now` rule is what
# prevents the former. So report the state accurately rather than warning.
systemctl is-enabled "${MOUNT_UNIT}"
if systemctl is-active --quiet "${MOUNT_UNIT}"; then
  echo "${MOUNT_UNIT}: ACTIVE — the datastore is already on tmpfs (post-cutover: k3s was started on top of this mount). Enabled, so the next boot mounts a fresh tmpfs and the reconstruct units rebuild the cluster."
else
  echo "${MOUNT_UNIT}: not active — the datastore is still on disk (correct before the cutover; it activates on the next boot, or a deliberate k3s-stopped cutover)"
fi

log "DONE. ${MOUNT_UNIT} enabled for next boot."

#!/usr/bin/env bash
# install-k3s-config.sh — install the fleet's k3s server configuration
# (./config.yaml) to /etc/rancher/k3s/config.yaml on a CI runner pool NODE,
# and write the packaged-component skip marker for the bundled local-path
# provisioner.
#
# WHY THIS EXISTS: until 2026-09-02 the host's config.yaml was hand-written
# (kubelet max-pods=200, livespec-a6lxuv) and lived nowhere in git — durable
# across a reboot, lost on a rebuild. This installer makes ./config.yaml the
# source of truth and the live file its output (the recreatability rule every
# sibling installer follows: edit the source, re-run, never the live file).
#
# TWO ENFORCEMENT POINTS FOR ONE DISABLE: `disable: [local-storage]` in the
# config file tells k3s not to deploy its bundled provisioner; the
# `local-storage.yaml.skip` marker in the packaged-manifests directory is
# k3s's documented per-manifest opt-out and holds independently of how
# config-file and command-line `--disable` values are merged. Both are
# written so the fleet-owned provisioner (../local-path-provisioner/) can
# never be overwritten by the bundled copy. The marker directory is under
# /var/lib/rancher/k3s/server/ (on disk, NOT the tmpfs datastore), so it is
# reboot-durable.
#
# TAKES EFFECT ON THE NEXT k3s START. This installer never restarts k3s: a
# restart kills every running CI job on the pool, so it is done at zero
# active jobs, or by a reboot (the reconstruct-on-boot path re-applies the
# fleet-owned provisioner within the converge).
#
# NODE-LOCAL, like ../node-inotify-budget/install-inotify-sysctl.sh: re-run on
# any node added to the pool and after any node rebuild. Idempotent. Run it
# BEFORE ../../provision-k3s.sh on a fresh node so the first k3s start already
# reads it.
#
# Requires: root (writes /etc/rancher/k3s and /var/lib/rancher/k3s/server).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_SRC="${SCRIPT_DIR}/config.yaml"
CONFIG_DST="/etc/rancher/k3s/config.yaml"
MANIFESTS_DIR="/var/lib/rancher/k3s/server/manifests"
SKIP_MARKER="${MANIFESTS_DIR}/local-storage.yaml.skip"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes ${CONFIG_DST} and ${MANIFESTS_DIR})" >&2; exit 1; }
[ -f "$CONFIG_SRC" ] || { echo "FATAL: shipped config not found at ${CONFIG_SRC}" >&2; exit 1; }

# ---------------------------------------------------------------------------
log "1. Install ${CONFIG_DST} from the shipped copy"
if [ -f "$CONFIG_DST" ] && cmp -s "$CONFIG_SRC" "$CONFIG_DST"; then
  echo "${CONFIG_DST} already matches the shipped copy — unchanged"
else
  if [ -f "$CONFIG_DST" ]; then
    echo "replacing ${CONFIG_DST}; diff (live -> shipped):"
    diff "$CONFIG_DST" "$CONFIG_SRC" || true
  fi
  install -d -m 0755 "$(dirname "$CONFIG_DST")"
  install -m 0600 "$CONFIG_SRC" "$CONFIG_DST"
  echo "installed ${CONFIG_DST} (takes effect on the next k3s start)"
fi

# ---------------------------------------------------------------------------
log "2. Write the packaged-manifest skip marker ${SKIP_MARKER}"
install -d -m 0700 "$MANIFESTS_DIR"
if [ -e "$SKIP_MARKER" ]; then
  echo "${SKIP_MARKER} already present"
else
  : > "$SKIP_MARKER"
  chmod 0600 "$SKIP_MARKER"
  echo "wrote ${SKIP_MARKER}"
fi

# ---------------------------------------------------------------------------
log "3. Report the running k3s's view (informational)"
if [ -e "${MANIFESTS_DIR}/local-storage.yaml" ]; then
  echo "NOTE: the bundled ${MANIFESTS_DIR}/local-storage.yaml is still present — k3s removes it on its next start"
else
  echo "bundled local-storage.yaml absent — the disable is in effect"
fi
if systemctl is-active --quiet k3s.service 2>/dev/null; then
  echo "k3s.service is running: the new config applies on its NEXT start (do that at zero active CI jobs, or by reboot)"
fi

log "DONE. k3s config installed; local-storage disabled at two enforcement points."

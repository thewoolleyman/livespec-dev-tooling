#!/usr/bin/env bash
# install-keyring-sysctl.sh — install the per-user kernel keyring quota for
# the k3s CI-runner pool as a durable /etc/sysctl.d/ drop-in, then apply it
# now. Mirrors ../node-inotify-budget/install-inotify-sysctl.sh: a
# /etc/sysctl.d/*.conf file is applied by systemd-sysctl.service at every
# boot, so the values survive a reboot, a k3s restart, and a k3s upgrade
# with no reconciliation loop.
#
# NODE-LOCAL: this is machine kernel state. Re-run on any node added to the
# pool and after any node rebuild. Idempotent — re-running overwrites the
# drop-in with the shipped copy and re-applies it. The shipped drop-in is
# the single source of truth for the values; the verify step parses them
# FROM it so it cannot drift from what was installed.
#
# Requires: root (writes /etc/sysctl.d and calls sysctl) and systemd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DROPIN_SRC="${SCRIPT_DIR}/60-k3s-container-keyring.conf"
DROPIN_DST="/etc/sysctl.d/60-k3s-container-keyring.conf"
# The untracked drop-in this one replaces (same values, earlier lane's name);
# removed so two files cannot disagree later.
LEGACY_DROPIN="/etc/sysctl.d/60-ci-runner-keyring.conf"
KEYS="kernel.keys.maxkeys kernel.keys.maxbytes"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes /etc/sysctl.d and calls sysctl)" >&2; exit 1; }
command -v sysctl >/dev/null || { echo "FATAL: sysctl not found on PATH" >&2; exit 1; }
[ -f "$DROPIN_SRC" ] || { echo "FATAL: shipped drop-in not found at ${DROPIN_SRC}" >&2; exit 1; }

# ---------------------------------------------------------------------------
log "1. Install the drop-in to ${DROPIN_DST} (durable across reboot via systemd-sysctl)"
install -m 0644 "$DROPIN_SRC" "$DROPIN_DST"
if [ -e "$LEGACY_DROPIN" ]; then
  rm -f "$LEGACY_DROPIN"
  echo "removed the untracked predecessor ${LEGACY_DROPIN}"
fi

# ---------------------------------------------------------------------------
log "2. Apply it now (so the running kernel matches without waiting for a reboot)"
sysctl -p "$DROPIN_DST"

# ---------------------------------------------------------------------------
log "3. Verify every running value matches the shipped intent"
for key in $KEYS; do
  intended="$(sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*\([0-9]\{1,\}\).*/\1/p" "$DROPIN_SRC" | tail -1)"
  [ -n "$intended" ] || { echo "FATAL: ${DROPIN_SRC} declares no ${key} value" >&2; exit 1; }
  actual="$(sysctl -n "$key")"
  if [ "$actual" != "$intended" ]; then
    echo "FATAL: ${key} is ${actual} after apply, expected ${intended}" >&2
    exit 1
  fi
  echo "${key}=${actual} — OK"
done

log "DONE. Keyring quota applied and persisted in ${DROPIN_DST}; survives reboot."

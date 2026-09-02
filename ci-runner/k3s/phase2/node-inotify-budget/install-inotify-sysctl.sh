#!/usr/bin/env bash
# install-inotify-sysctl.sh — install the per-user inotify INSTANCE budget for
# the k3s CI-runner pool as a durable /etc/sysctl.d/ drop-in, then apply it now.
#
# WHY A sysctl.d DROP-IN AND NOT A REAPPLY TIMER (unlike
# node-extended-resource/): a /etc/sysctl.d/*.conf file is applied by
# systemd-sysctl.service at every boot, so the value survives a reboot, a k3s
# restart, and a k3s upgrade with no reconciliation loop. The
# node-extended-resource patch needs its 5-minute timer only because a
# `kubectl patch node --subresource=status` extended resource is NOT persisted
# by kubelet (see reapply-node-extended-resource.service's header); a kernel
# sysctl written under /etc/sysctl.d/ has no such gap, so shipping a timer here
# would be cargo-culted insurance the mechanism does not need.
#
# NODE-LOCAL, like node-extended-resource/install-reapply-unit.sh and
# apparmor/install-apparmor-profile.sh: this is machine kernel state. Re-run on
# any node added to the pool and after any node rebuild. It is idempotent —
# re-running overwrites the drop-in with the shipped copy and re-applies it.
#
# The interim, hand-applied /etc/sysctl.d/99-ci-runner-inotify.conf placed on
# poweredge-xubuntu on 2026-09-01 (livespec plan
# `ci-runner-pod-lifecycle-reliability`, research/002) is exactly what this
# installer makes reproducible; running it converges a new or rebuilt node to
# the same durable state. See ../kueue/DERIVATION.md (the kernel-side term
# beside the pod-capacity derivation) and the drop-in's own header for the
# value's derivation, and ../VALIDATION_CHECKLIST.md for confirming it survives
# a real reboot on the live host.
#
# Requires: root (writes /etc/sysctl.d and calls sysctl) and systemd (for the
# boot-time reapply guarantee).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DROPIN_SRC="${SCRIPT_DIR}/99-ci-runner-inotify.conf"
DROPIN_DST="/etc/sysctl.d/99-ci-runner-inotify.conf"
KEY="fs.inotify.max_user_instances"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes /etc/sysctl.d and calls sysctl)" >&2; exit 1; }
command -v sysctl >/dev/null || { echo "FATAL: sysctl not found on PATH" >&2; exit 1; }
[ -f "$DROPIN_SRC" ] || { echo "FATAL: shipped drop-in not found at ${DROPIN_SRC}" >&2; exit 1; }

# The shipped drop-in is the single source of truth for the value; parse the
# intended value FROM it so the verification below cannot drift from what was
# installed.
INTENDED="$(sed -n "s/^[[:space:]]*${KEY}[[:space:]]*=[[:space:]]*\([0-9]\{1,\}\).*/\1/p" "$DROPIN_SRC" | tail -1)"
[ -n "$INTENDED" ] || { echo "FATAL: ${DROPIN_SRC} declares no ${KEY} value" >&2; exit 1; }

# ---------------------------------------------------------------------------
log "1. Install the drop-in to ${DROPIN_DST} (durable across reboot via systemd-sysctl)"
install -m 0644 "$DROPIN_SRC" "$DROPIN_DST"

# ---------------------------------------------------------------------------
log "2. Apply it now (so the running kernel matches without waiting for a reboot)"
sysctl -p "$DROPIN_DST"

# ---------------------------------------------------------------------------
log "3. Verify the running value matches the shipped intent (${KEY}=${INTENDED})"
ACTUAL="$(sysctl -n "$KEY")"
if [ "$ACTUAL" != "$INTENDED" ]; then
  echo "FATAL: ${KEY} is ${ACTUAL} after apply, expected ${INTENDED}" >&2
  exit 1
fi

log "DONE. ${KEY}=${ACTUAL} applied and persisted in ${DROPIN_DST}; survives reboot."

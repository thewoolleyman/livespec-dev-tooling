#!/usr/bin/env bash
# install-storage-layout.sh — make the CI runner NODE's storage layout
# reproducible from git: the dedicated CI-churn volume mounted at
# /var/cache/ci-runner, and the two bind mounts that relocate containerd's
# store and the local-path PVC root onto it and off the root filesystem.
#
# WHY THIS EXISTS: the relocation was done by hand on 2026-08-28 (livespec
# plan poweredge-raid-array-maintenance, research/containerd-relocation-
# completed.md: rsync, rename the originals to *.premove, three fstab lines,
# `mount -a`) and the three /etc/fstab lines were its only record. They are
# reboot-durable, but a rebuilt host would boot with containerd and every
# runner's work volume back on `/` — silently, since every path still
# exists. The 2026-09-02 gitops audit (livespec plan
# ci-runner-pod-lifecycle-reliability) listed this as the one rebuild-
# critical piece of node state with no git source. This installer ENSURES
# the three lines are present, byte-exact, in /etc/fstab — it never rewrites
# lines that already match, and it never moves data.
#
# THE LAYOUT (what the three lines say):
#   UUID=<cache volume>   /var/cache/ci-runner                 ext4  defaults,noatime         0 2
#   /var/cache/ci-runner/k3s-containerd  /var/lib/rancher/k3s/agent/containerd  none bind,x-systemd.requires-mounts-for=/var/cache/ci-runner 0 0
#   /var/cache/ci-runner/k3s-storage     /var/lib/rancher/k3s/storage           none bind,x-systemd.requires-mounts-for=/var/cache/ci-runner 0 0
# Under /var/cache/ci-runner also live: warm/ (the warm uv cache lower,
# ../warm-cache/) and lost+found. The volume is the host's sda5 partition
# on poweredge-xubuntu; on another node it is whatever ext4 volume is
# dedicated to CI churn — hence the UUID is an ARGUMENT, not a constant.
#
# WHAT IT DOES NOT DO: it does not format a volume, does not rsync existing
# data into place, and does not run `mount -a` — on a fresh host, format
# the volume, run this, `mkdir -p` the two subdirectories on it, then
# `mount -a` BEFORE k3s is installed (../../provision-k3s.sh). On the live
# host it is a no-op that proves the lines are present.
#
# Usage: sudo install-storage-layout.sh [CACHE_VOLUME_UUID]
#   The UUID may be omitted when the volume is ALREADY mounted at
#   /var/cache/ci-runner (it is read from the live mount); on a fresh host
#   pass it (`blkid -s UUID -o value /dev/<partition>`).
#
# Requires: root (writes /etc/fstab).
set -euo pipefail

CACHE_MOUNT="/var/cache/ci-runner"
CONTAINERD_DIR="/var/lib/rancher/k3s/agent/containerd"
STORAGE_DIR="/var/lib/rancher/k3s/storage"
FSTAB="/etc/fstab"
CACHE_UUID="${1:-}"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes ${FSTAB})" >&2; exit 1; }

# ---------------------------------------------------------------------------
log "1. Resolve the CI-churn volume UUID"
if [ -z "$CACHE_UUID" ]; then
  src="$(findmnt -n -o SOURCE --target "$CACHE_MOUNT" 2>/dev/null || true)"
  if [ -n "$src" ] && [ "$(findmnt -n -o TARGET --target "$CACHE_MOUNT")" = "$CACHE_MOUNT" ]; then
    CACHE_UUID="$(blkid -s UUID -o value "${src%%[*}")"
    echo "read from the live mount: ${src%%[*} -> UUID=${CACHE_UUID}"
  else
    echo "FATAL: ${CACHE_MOUNT} is not mounted and no UUID was given." >&2
    echo "       usage: install-storage-layout.sh CACHE_VOLUME_UUID   (blkid -s UUID -o value /dev/<partition>)" >&2
    exit 1
  fi
fi
[[ "$CACHE_UUID" =~ ^[0-9a-fA-F-]{36}$ ]] || { echo "FATAL: '${CACHE_UUID}' is not a UUID" >&2; exit 1; }

# ---------------------------------------------------------------------------
log "2. Ensure the three fstab lines (byte-exact; never rewritten if present)"
ensure_line() {
  local line="$1" mountpoint="$2"
  if grep -qxF -- "$line" "$FSTAB"; then
    echo "present: ${mountpoint}"
  elif grep -qE "^[^#][^[:space:]]*[[:space:]]+${mountpoint}[[:space:]]" "$FSTAB"; then
    echo "FATAL: ${FSTAB} already carries a DIFFERENT line for ${mountpoint}; reconcile by hand:" >&2
    grep -nE "^[^#][^[:space:]]*[[:space:]]+${mountpoint}[[:space:]]" "$FSTAB" >&2
    exit 1
  else
    printf '%s\n' "$line" >> "$FSTAB"
    echo "added:   ${mountpoint}"
  fi
}
ensure_line "UUID=${CACHE_UUID} ${CACHE_MOUNT} ext4 defaults,noatime 0 2" "$CACHE_MOUNT"
ensure_line "${CACHE_MOUNT}/k3s-containerd ${CONTAINERD_DIR} none bind,x-systemd.requires-mounts-for=${CACHE_MOUNT} 0 0" "$CONTAINERD_DIR"
ensure_line "${CACHE_MOUNT}/k3s-storage ${STORAGE_DIR} none bind,x-systemd.requires-mounts-for=${CACHE_MOUNT} 0 0" "$STORAGE_DIR"

# ---------------------------------------------------------------------------
log "3. Report the live state (informational; nothing is mounted here)"
for m in "$CACHE_MOUNT" "$CONTAINERD_DIR" "$STORAGE_DIR"; do
  if findmnt -n -o SOURCE,FSTYPE --target "$m" >/dev/null 2>&1 && [ "$(findmnt -n -o TARGET --target "$m")" = "$m" ]; then
    printf '%-40s mounted: %s\n' "$m" "$(findmnt -n -o SOURCE,FSTYPE --target "$m")"
  else
    printf '%-40s NOT mounted (fresh host: mkdir -p the source dirs on the volume, then mount -a, before k3s starts)\n' "$m"
  fi
done

log "DONE. Storage layout recorded in ${FSTAB}."

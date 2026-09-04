#!/usr/bin/env bash
# install-storage-layout.sh — make the CI runner NODE's storage layout
# reproducible from git AND media-neutral: three CI tiers found by
# filesystem LABEL, two bind mounts that put containerd's store and the
# local-path PVC root on them, and the k3s drop-in that refuses to start
# k3s unless both binds are mounted.
#
# WHY LABELS (2026-09-04, livespec plan ci-runner-pod-lifecycle-reliability,
# item livespec-el5y): the node's tiers are moving media — array stand-in
# LVs today, one NVMe volume group per drive when the hardware lands
# (livespec-g52yrb). A filesystem UUID is minted by every mkfs, so a
# UUID-keyed fstab has to change on every media move and the git copy of
# the layout can never be byte-identical to the host's. A LABEL is chosen
# by us, is the same on any medium, and is what the maintainer's rule
# "the array uses the SAME volume names as the NVMe" means in fstab terms.
# The role names double as the LV names (VG-agnostic: poweredge/ci-workvols
# today, nvmeb/ci-workvols later). ext4 labels hold 16 bytes — the live
# label `standin-containe` was already silently truncated — so the names
# stay short.
#
# THE LAYOUT (the five lines this installer ensures, byte-exact):
#   LABEL=ci-cache       /var/cache/ci-runner                 ext4 defaults,noatime 0 2
#   LABEL=ci-containerd  /var/cache/ci-runner/k3s-containerd  ext4 defaults,noatime,x-systemd.requires-mounts-for=/var/cache/ci-runner 0 2
#   LABEL=ci-workvols    /var/cache/ci-runner/k3s-storage     ext4 defaults,noatime,x-systemd.requires-mounts-for=/var/cache/ci-runner 0 2
#   /var/cache/ci-runner/k3s-containerd /var/lib/rancher/k3s/agent/containerd none bind,x-systemd.requires-mounts-for=/var/cache/ci-runner/k3s-containerd 0 0
#   /var/cache/ci-runner/k3s-storage    /var/lib/rancher/k3s/storage          none bind,x-systemd.requires-mounts-for=/var/cache/ci-runner/k3s-storage 0 0
# Each bind requires ITS OWN SOURCE mount, not merely the cache volume:
# otherwise systemd may bind the empty mountpoint directory before the tier
# volume lands on it, and k3s would run on the cache volume — or on `/` —
# silently, since every path exists either way. The k3s drop-in
# (10-requires-storage-mounts.conf, installed here) closes the last gap:
# k3s does not start at all unless both bind targets are mounted.
#
# WHAT IT DOES: (1) refuses unless each label resolves to EXACTLY one block
# device (zero = format the volume first; two = a media swap is half done,
# relabel the old one first); (2) creates the mountpoint directories that
# can safely be created; (3) ensures the five lines — an existing DIFFERENT
# line for one of the five mountpoints is REPLACED, with /etc/fstab backed
# up first and old and new printed — then `findmnt --verify`; (4) installs
# the k3s drop-in and reloads systemd. It never formats, never moves data,
# never mounts, never restarts k3s. Re-running it on a conforming host is a
# byte-exact no-op.
#
# MEDIA SWAP (the whole point; README "Storage layout: media-neutral tier
# identity"): mkfs.ext4 -L <temporary label> on the new volume, rsync -aHAXS
# from the live tier, then in a quiet window with k3s stopped: tune2fs -L on
# both so ONLY the new volume carries the role label, mount -a. fstab is
# unchanged, and this installer stays a no-op throughout.
#
# Usage: sudo install-storage-layout.sh      (no arguments)
# Requires: root (writes /etc/fstab and /etc/systemd/system), util-linux.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_MOUNT="/var/cache/ci-runner"
CONTAINERD_SRC="${CACHE_MOUNT}/k3s-containerd"
STORAGE_SRC="${CACHE_MOUNT}/k3s-storage"
CONTAINERD_DIR="/var/lib/rancher/k3s/agent/containerd"
STORAGE_DIR="/var/lib/rancher/k3s/storage"
FSTAB="/etc/fstab"
DROPIN_NAME="10-requires-storage-mounts.conf"
DROPIN_DST="/etc/systemd/system/k3s.service.d/${DROPIN_NAME}"
LABEL_CACHE="ci-cache"
LABEL_CONTAINERD="ci-containerd"
LABEL_WORKVOLS="ci-workvols"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes ${FSTAB} and ${DROPIN_DST})" >&2; exit 1; }
for c in blkid lsblk findmnt systemctl; do
  command -v "$c" >/dev/null || { echo "FATAL: ${c} not on PATH" >&2; exit 1; }
done
[ -f "${SCRIPT_DIR}/${DROPIN_NAME}" ] || { echo "FATAL: ${SCRIPT_DIR}/${DROPIN_NAME} missing beside this script" >&2; exit 1; }

# ---------------------------------------------------------------------------
log "1. Each tier label must resolve to exactly one block device (fresh superblock probe, no blkid cache)"
# lsblk enumerates every partition and LVM volume; blkid -p probes the
# superblock directly, bypassing the cache that goes stale after tune2fs -L.
devices_with_label() {
  local label="$1" dev
  lsblk -rno PATH,TYPE | awk '$2=="part"||$2=="lvm"||$2=="crypt"||$2=="md"||$2=="disk"{print $1}' | while read -r dev; do
    if [ "$(blkid -p -s LABEL -o value "$dev" 2>/dev/null || true)" = "$label" ]; then
      printf '%s\n' "$dev"
    fi
  done
}
for label in "$LABEL_CACHE" "$LABEL_CONTAINERD" "$LABEL_WORKVOLS"; do
  devs="$(devices_with_label "$label")"
  n="$(printf '%s' "$devs" | grep -c . || true)"
  case "$n" in
    1) echo "LABEL=${label} -> ${devs}" ;;
    0) echo "FATAL: no block device carries LABEL=${label}." >&2
       echo "       Fresh host: mkfs.ext4 -L ${label} <volume>, and rsync the data in, BEFORE running this." >&2
       echo "       Live host with the volume under another name: tune2fs -L ${label} <device> (README 'Storage layout')." >&2
       exit 1 ;;
    *) echo "FATAL: ${n} block devices carry LABEL=${label}:" >&2
       printf '         %s\n' $devs >&2
       echo "       A media swap is half done. Relabel the OLD volume (tune2fs -L old-${label#ci-} <device>)" >&2
       echo "       so exactly one carries the role label, then re-run." >&2
       exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
log "2. Mountpoint directories (created only where that cannot hide data)"
# The bind targets and the cache mountpoint live on the root filesystem and
# are plain directories there. The two tier mountpoints live ON the cache
# volume: creating them while it is not mounted would put them on `/` where
# the mounted volume later hides them, so they are created only when the
# cache volume is live.
install -d -m 0755 "$CACHE_MOUNT" "$CONTAINERD_DIR" "$STORAGE_DIR"
if [ "$(findmnt -n -o TARGET --target "$CACHE_MOUNT" 2>/dev/null)" = "$CACHE_MOUNT" ]; then
  install -d -m 0755 "$CONTAINERD_SRC" "$STORAGE_SRC"
  echo "cache volume mounted at ${CACHE_MOUNT}; tier mountpoints present"
else
  echo "NOTE: ${CACHE_MOUNT} is not mounted. Fresh host: mount LABEL=${LABEL_CACHE} there, mkdir the"
  echo "      two tier mountpoints on it, then re-run this installer BEFORE k3s is installed."
fi

# ---------------------------------------------------------------------------
log "3. Ensure the five fstab lines (byte-exact; a differing line for the same mountpoint is replaced)"
BACKUP=""
ensure_line() {
  local line="$1" mountpoint="$2" existing lineno
  if grep -qxF -- "$line" "$FSTAB"; then
    echo "present: ${mountpoint}"
    return
  fi
  existing="$(grep -nE "^[^#][^[:space:]]*[[:space:]]+${mountpoint}[[:space:]]" "$FSTAB" || true)"
  if [ -n "$existing" ]; then
    if [ "$(printf '%s\n' "$existing" | wc -l)" -ne 1 ]; then
      echo "FATAL: ${FSTAB} carries more than one line for ${mountpoint}; reconcile by hand:" >&2
      printf '%s\n' "$existing" >&2
      exit 1
    fi
    if [ -z "$BACKUP" ]; then
      BACKUP="${FSTAB}.pre-storage-layout-$(date -u +%Y%m%dT%H%M%SZ)"
      cp -p "$FSTAB" "$BACKUP"
      echo "backup:  ${BACKUP}"
    fi
    lineno="${existing%%:*}"
    echo "replace: ${mountpoint}"
    echo "  old: ${existing#*:}"
    echo "  new: ${line}"
    # Spliced through a temp file: sed's replacement side would reinterpret
    # `&` and backslashes, and the line must land byte-exact.
    { head -n "$((lineno - 1))" "$FSTAB"; printf '%s\n' "$line"; tail -n "+$((lineno + 1))" "$FSTAB"; } > "${FSTAB}.tmp.$$"
    cat "${FSTAB}.tmp.$$" > "$FSTAB"
    rm -f "${FSTAB}.tmp.$$"
  else
    printf '%s\n' "$line" >> "$FSTAB"
    echo "added:   ${mountpoint}"
  fi
}
ensure_line "LABEL=${LABEL_CACHE} ${CACHE_MOUNT} ext4 defaults,noatime 0 2" "$CACHE_MOUNT"
ensure_line "LABEL=${LABEL_CONTAINERD} ${CONTAINERD_SRC} ext4 defaults,noatime,x-systemd.requires-mounts-for=${CACHE_MOUNT} 0 2" "$CONTAINERD_SRC"
ensure_line "LABEL=${LABEL_WORKVOLS} ${STORAGE_SRC} ext4 defaults,noatime,x-systemd.requires-mounts-for=${CACHE_MOUNT} 0 2" "$STORAGE_SRC"
ensure_line "${CONTAINERD_SRC} ${CONTAINERD_DIR} none bind,x-systemd.requires-mounts-for=${CONTAINERD_SRC} 0 0" "$CONTAINERD_DIR"
ensure_line "${STORAGE_SRC} ${STORAGE_DIR} none bind,x-systemd.requires-mounts-for=${STORAGE_SRC} 0 0" "$STORAGE_DIR"

echo
echo "findmnt --verify ${FSTAB}:"
if ! findmnt --verify --tab-file "$FSTAB"; then
  echo "FATAL: ${FSTAB} failed verification after the edit. Previous copy: ${BACKUP:-none (no line was replaced)}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
log "4. k3s drop-in ${DROPIN_DST} (k3s refuses to start unless both binds are mounted)"
if [ -f "$DROPIN_DST" ] && cmp -s "${SCRIPT_DIR}/${DROPIN_NAME}" "$DROPIN_DST"; then
  echo "present, byte-identical to git"
else
  install -D -m 0644 "${SCRIPT_DIR}/${DROPIN_NAME}" "$DROPIN_DST"
  systemctl daemon-reload
  echo "installed; takes effect on the next k3s start (this installer never restarts k3s)"
fi

# ---------------------------------------------------------------------------
log "5. Live state (informational; nothing is mounted here)"
for m in "$CACHE_MOUNT" "$CONTAINERD_SRC" "$STORAGE_SRC" "$CONTAINERD_DIR" "$STORAGE_DIR"; do
  if [ "$(findmnt -n -o TARGET --target "$m" 2>/dev/null)" = "$m" ]; then
    printf '%-40s mounted: %s\n' "$m" "$(findmnt -n -o SOURCE,FSTYPE --target "$m")"
  else
    printf '%-40s NOT mounted (fresh host: mount -a before k3s starts)\n' "$m"
  fi
done

log "DONE. Storage layout recorded in ${FSTAB} and ${DROPIN_DST}."

#!/usr/bin/env bash
# migrate-tier.sh — move a CI storage tier to new media by COPY + RELABEL,
# with /etc/fstab untouched and install-storage-layout.sh a no-op throughout.
#
# This is README "Storage layout: media-neutral tier identity" → "Moving a
# tier to new media" as code, generalised from the script that carried the
# containerd store and the runner work volumes from the RAID-5 array LVs onto
# the first NVMe on poweredge-xubuntu on 2026-09-04 (livespec plan
# `poweredge-raid-array-maintenance`, epic livespec-g52yrb, child
# livespec-e2vcqf). A tier is addressed by its ext4 LABEL; moving it means
# putting the bytes on a new volume and moving the label, never editing fstab.
#
# TWO PHASES, because the copy is long and the switch must be short:
#
#   prepare ROLE VG PV_BY_ID SIZE
#       Live, k3s running, CI may be on. Idempotent. Ensures the physical
#       volume (pvcreate only on a device with NO signature — a stale copy
#       from an earlier attempt must be wiped by hand first, deliberately:
#       `vgremove` + `wipefs -a`, never reused), the volume group, the LV
#       named ROLE in that VG, and an ext4 filesystem carrying the TEMPORARY
#       label `new-<suffix>` (ROLE minus its `ci-` prefix; two volumes must
#       never carry the role label at once). Then a bulk rsync of the live
#       tier onto it under a temporary mount. Re-run it to refresh the copy.
#
#   cutover ROLE [ROLE ...]
#       The quiet window. Refuses unless the pool is idle (zero
#       EphemeralRunners). Stops k3s (k3s-killall.sh leaves the bind mounts
#       alone), takes the final delta copy of each tier, verifies it (a
#       dry-run itemised pass must list nothing but directory timestamps, and
#       inode counts must match), unmounts the bind, the tier and the temp
#       mount, swaps the labels (old volume → `old-<suffix>`, new volume →
#       ROLE), refreshes /dev/disk/by-label WITHOUT a blanket udev trigger,
#       `mount -a`, proves every path resolves to the new device, starts k3s
#       and the After=k3s oneshots a manual start does not pull in, compares
#       the image count, and finally runs install-storage-layout.sh, which
#       must report every line present. Several roles in ONE window is the
#       normal case (one k3s stop).
#
# WHAT IT REFUSES, and why each is a rule (each cost real time on 2026-09-04):
#   - a PV on a device that already carries a signature: the SN8100 came back
#     from a failed attempt holding a VG with a copy of containerd that was
#     stale the moment CI ran again; reuse would have silently shipped old
#     layers.
#   - `ci-cache` in cutover: the two tier mounts live ON it, so moving the tier
#     root is a different, larger window (unmount everything); not this tool.
#   - a non-idle pool; a role whose `new-` volume is missing; a role label that
#     does not resolve to exactly one device before the switch.
#
# NEVER `udevadm trigger --subsystem-match=block` on this host: on 2026-09-04
# it marked the mounted device-mapper volumes not-ready, systemd stopped every
# tier mount, and the k3s RequiresMountsFor drop-in stopped k3s ahead of them
# (shims orphaned, every listener Unknown). `lvchange --refresh` emits a proper
# dm event; the fallback here is a `udevadm trigger --action=change` scoped to
# the four UNMOUNTED volumes only.
#
# Usage:  sudo migrate-tier.sh prepare ci-containerd nvmea /dev/disk/by-id/nvme-WD_BLACK_SN8100_4000GB_25384T801085 1.5T
#         sudo migrate-tier.sh prepare ci-workvols   nvmea /dev/disk/by-id/nvme-WD_BLACK_SN8100_4000GB_25384T801085 1.5T
#         sudo migrate-tier.sh cutover ci-containerd ci-workvols
# Requires: root, lvm2, e2fsprogs, rsync, util-linux, k3s. PV_BY_ID must be a
# /dev/disk/by-id/ path (enumeration order shifts across boots behind a switch).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_MOUNT="/var/cache/ci-runner"
TMP_ROOT="/mnt/migrate-tier"
export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

log() { printf '%s %s\n' "$(date -u '+%H:%M:%SZ')" "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 2; }

[ "$(id -u)" -eq 0 ] || die "must run as root"
for c in pvs vgs lvs lvcreate mkfs.ext4 tune2fs blkid findmnt rsync lvchange udevadm k3s; do
  command -v "$c" >/dev/null || die "${c} not on PATH"
done

# ROLE → its tier mountpoint and bind target. The tier root has no bind and
# is refused by cutover (see header).
tier_mount() {
  case "$1" in
    ci-cache)      echo "$CACHE_MOUNT" ;;
    ci-containerd) echo "${CACHE_MOUNT}/k3s-containerd" ;;
    ci-workvols)   echo "${CACHE_MOUNT}/k3s-storage" ;;
    *) die "unknown role '$1' (ci-cache | ci-containerd | ci-workvols)" ;;
  esac
}
bind_target() {
  case "$1" in
    ci-containerd) echo "/var/lib/rancher/k3s/agent/containerd" ;;
    ci-workvols)   echo "/var/lib/rancher/k3s/storage" ;;
    *) echo "" ;;
  esac
}
suffix() { printf '%s' "${1#ci-}"; }

# Fresh superblock probe (no blkid cache — it goes stale after tune2fs -L).
devices_with_label() {
  local label="$1" dev
  lsblk -rno PATH,TYPE | awk '$2=="part"||$2=="lvm"||$2=="crypt"||$2=="md"||$2=="disk"{print $1}' | while read -r dev; do
    if [ "$(blkid -p -s LABEL -o value "$dev" 2>/dev/null || true)" = "$label" ]; then
      printf '%s\n' "$dev"
    fi
  done
}
one_device_with_label() {
  local label="$1" devs n
  devs="$(devices_with_label "$label")"
  n="$(printf '%s' "$devs" | grep -c . || true)"
  [ "$n" -eq 1 ] || die "LABEL=${label} resolves to ${n} devices (need exactly one):$(printf ' %s' $devs)"
  printf '%s\n' "$devs"
}

rsync_tier() {  # rsync_tier SRC_DIR DST_DIR [extra rsync args]
  local src="$1" dst="$2"; shift 2
  rsync -aHAXS --numeric-ids --delete --one-file-system "$@" "${src}/" "${dst}/"
}

# ---------------------------------------------------------------------------
cmd_prepare() {
  [ $# -eq 4 ] || die "usage: prepare ROLE VG PV_BY_ID SIZE"
  local role="$1" vg="$2" pv="$3" size="$4" src lv dev newlabel tmp
  src="$(tier_mount "$role")"
  newlabel="new-$(suffix "$role")"
  [ "${#newlabel}" -le 16 ] || die "temporary label '${newlabel}' exceeds ext4's 16 bytes"
  case "$pv" in /dev/disk/by-id/*) ;; *) die "PV must be a /dev/disk/by-id/ path, got '${pv}'" ;; esac
  [ -b "$pv" ] || die "${pv} is not a block device (a missing by-id path is how fio once filled /dev with a regular file)"
  findmnt -n --target "$src" >/dev/null || die "${src} is not mounted; nothing to copy"

  log "prepare ${role}: PV ${pv} → VG ${vg} → LV ${role} (${size}) → ext4 LABEL=${newlabel} → bulk copy from ${src}"

  if pvs --noheadings -o pv_name "$pv" >/dev/null 2>&1; then
    log "PV present on ${pv}"
  else
    if [ -n "$(blkid -p -o value -s TYPE "$pv" 2>/dev/null || true)" ] || [ -n "$(blkid -p -o value -s PTTYPE "$pv" 2>/dev/null || true)" ]; then
      die "${pv} carries a signature ($(blkid -p "$pv" 2>/dev/null | tr -s ' ' | cut -c1-120)). Refusing to reuse it: wipe by hand (vgremove, pvremove, wipefs -a) after confirming nothing on it is wanted."
    fi
    pvcreate "$pv" >/dev/null || die "pvcreate ${pv}"
    log "PV created on ${pv}"
  fi

  if vgs --noheadings -o vg_name "$vg" >/dev/null 2>&1; then
    if ! pvs --noheadings -o vg_name "$pv" | grep -qx " *${vg} *"; then
      pvs --noheadings -o vg_name "$pv" | grep -q "$vg" || die "VG ${vg} exists but ${pv} is not one of its PVs"
    fi
    log "VG ${vg} present"
  else
    vgcreate "$vg" "$pv" >/dev/null || die "vgcreate ${vg} ${pv}"
    log "VG ${vg} created"
  fi

  lv="/dev/${vg}/${role}"
  if lvs --noheadings "${vg}/${role}" >/dev/null 2>&1; then
    log "LV ${vg}/${role} present"
  else
    lvcreate -L "$size" -n "$role" "$vg" >/dev/null || die "lvcreate ${vg}/${role} ${size}"
    log "LV ${vg}/${role} created (${size})"
  fi
  dev="$(readlink -f "$lv")"

  case "$(blkid -p -o value -s LABEL "$dev" 2>/dev/null || true)" in
    "$newlabel") log "filesystem present with LABEL=${newlabel}" ;;
    "")
      [ -z "$(blkid -p -o value -s TYPE "$dev" 2>/dev/null || true)" ] || die "${dev} has a filesystem with no label; refusing to guess"
      mkfs.ext4 -q -L "$newlabel" "$dev" || die "mkfs.ext4 ${dev}"
      log "ext4 created on ${dev} with LABEL=${newlabel}" ;;
    "$role") die "${dev} already carries the ROLE label ${role} — the cutover already happened, or two volumes carry it; run install-storage-layout.sh" ;;
    *) die "${dev} carries an unexpected label '$(blkid -p -o value -s LABEL "$dev")'" ;;
  esac

  tmp="${TMP_ROOT}/${role}"
  install -d -m 0755 "$tmp"
  findmnt -n --target "$tmp" | grep -q "^${tmp} " || mount "$dev" "$tmp" || die "mount ${dev} ${tmp}"
  log "bulk copy ${src} → ${tmp} (live; the cutover takes the final delta)"
  rsync_tier "$src" "$tmp" --info=progress2 ; rc=$?
  [ "$rc" -eq 0 ] || die "bulk rsync rc=${rc}"
  log "prepare ${role} done: $(df -h --output=used,size "$tmp" | tail -1 | tr -s ' ') used/size on ${dev}; left mounted at ${tmp} for the cutover"
}

# ---------------------------------------------------------------------------
cmd_cutover() {
  [ $# -ge 1 ] || die "usage: cutover ROLE [ROLE ...]"
  local roles=("$@") role src bind tmp old new n_old n_new diff_lines before after

  for role in "${roles[@]}"; do
    [ "$role" != "ci-cache" ] || die "ci-cache (the tier root) is not moved by this tool: the tier mounts live on it"
    src="$(tier_mount "$role")"
    tmp="${TMP_ROOT}/${role}"
    findmnt -n --target "$src" | grep -q "^${src} " || die "${src} is not mounted"
    findmnt -n --target "$tmp" | grep -q "^${tmp} " || die "${tmp} is not mounted — run prepare ${role} first"
    old="$(one_device_with_label "$role")"
    new="$(one_device_with_label "new-$(suffix "$role")")"
    [ "$(findmnt -n -o SOURCE "$src")" = "$old" ] || die "${src} is mounted from $(findmnt -n -o SOURCE "$src"), not from LABEL=${role} (${old})"
    [ "$(findmnt -n -o SOURCE "$tmp")" = "$new" ] || die "${tmp} is mounted from $(findmnt -n -o SOURCE "$tmp"), not from LABEL=new-$(suffix "$role") (${new})"
    log "cutover ${role}: ${old} → ${new}"
  done

  local runners
  runners="$(k3s kubectl get ephemeralrunners -A --no-headers 2>/dev/null | wc -l)"
  [ "$runners" -eq 0 ] || die "pool not idle: ${runners} EphemeralRunners present; route CI away and wait"

  before="$(mktemp)"; after="$(mktemp)"
  k3s crictl images -q 2>/dev/null | sort > "$before"
  log "baseline: $(wc -l < "$before") images, $(k3s kubectl get pods -A --no-headers 2>/dev/null | wc -l) pods; stopping k3s"
  systemctl stop k3s || die "systemctl stop k3s"
  [ -x /usr/local/bin/k3s-killall.sh ] && /usr/local/bin/k3s-killall.sh >/dev/null 2>&1
  sleep 3

  for role in "${roles[@]}"; do
    src="$(tier_mount "$role")"; tmp="${TMP_ROOT}/${role}"
    log "final delta copy ${role}"
    rsync_tier "$src" "$tmp"; rc=$?
    [ "$rc" -eq 0 ] || die "delta rsync ${role} rc=${rc}"
    diff_lines="$(rsync_tier "$src" "$tmp" -n -i | grep -v '^\.d' | wc -l)"
    n_old="$(find "$src" -xdev | wc -l)"; n_new="$(find "$tmp" -xdev | wc -l)"
    log "verify ${role}: non-directory differences=${diff_lines}, inodes old=${n_old} new=${n_new}"
    { [ "$diff_lines" -eq 0 ] && [ "$n_old" -eq "$n_new" ]; } || die "verification failed for ${role}"
  done

  for role in "${roles[@]}"; do
    src="$(tier_mount "$role")"; bind="$(bind_target "$role")"; tmp="${TMP_ROOT}/${role}"
    [ -z "$bind" ] || umount "$bind" || die "umount ${bind}"
    umount "$src" || die "umount ${src}"
    umount "$tmp" || die "umount ${tmp}"
    old="$(one_device_with_label "$role")"
    new="$(one_device_with_label "new-$(suffix "$role")")"
    tune2fs -L "old-$(suffix "$role")" "$old" >/dev/null || die "relabel ${old}"
    tune2fs -L "$role" "$new" >/dev/null || die "relabel ${new}"
    log "relabelled ${role}: ${old} → old-$(suffix "$role"), ${new} → ${role}"
    # Refresh by-label through proper dm events; scoped udev change as fallback.
    for d in "$old" "$new"; do
      if [ -n "$(lvs --noheadings -o lv_name --select "lv_path=$(readlink -f "$d")" 2>/dev/null)" ] || dmsetup info "$d" >/dev/null 2>&1; then
        lvchange --refresh "$(lvs --noheadings -o vg_name,lv_name --select "lv_path=$(readlink -f "$d")" 2>/dev/null | awk '{print $1"/"$2}')" 2>/dev/null || true
      fi
    done
    udevadm settle
    if [ "$(readlink -f "/dev/disk/by-label/${role}" 2>/dev/null)" != "$(readlink -f "$new")" ]; then
      log "by-label/${role} not yet refreshed; scoped udev change on the two unmounted volumes"
      udevadm trigger --action=change "$(readlink -f "$old")" "$(readlink -f "$new")"
      udevadm settle
      [ "$(readlink -f "/dev/disk/by-label/${role}")" = "$(readlink -f "$new")" ] || die "by-label/${role} still points at $(readlink -f "/dev/disk/by-label/${role}")"
    fi
  done

  systemctl daemon-reload
  mount -a || die "mount -a"
  for role in "${roles[@]}"; do
    src="$(tier_mount "$role")"; bind="$(bind_target "$role")"
    new="$(one_device_with_label "$role")"
    [ "$(findmnt -n -o SOURCE "$src")" = "$new" ] || die "${src} is not on ${new} after mount -a"
    [ -z "$bind" ] || [ "$(findmnt -n -o SOURCE "$bind")" = "$new" ] || die "${bind} is not on ${new} after mount -a"
    log "${role}: ${src} and ${bind:-'(no bind)'} on ${new}"
  done

  log "starting k3s"
  systemctl start k3s || die "systemctl start k3s"
  for _ in $(seq 1 30); do sleep 5; [ "$(k3s crictl images -q 2>/dev/null | wc -l)" -gt 0 ] && break; done
  k3s crictl images -q 2>/dev/null | sort > "$after"
  log "images before=$(wc -l < "$before") after=$(wc -l < "$after") diff-lines=$(diff "$before" "$after" | wc -l)"
  [ "$(diff "$before" "$after" | wc -l)" -eq 0 ] || log "WARN: image set changed across the cutover"
  # A manual k3s start does not pull in the boot chain's After=k3s oneshots.
  for u in inject-github-app-secret reapply-node-extended-resource otel-collector-identity; do
    systemctl list-unit-files "${u}.service" >/dev/null 2>&1 && systemctl start "${u}.service" 2>/dev/null && log "started ${u}"
  done
  sleep 20
  k3s kubectl get pods -A --no-headers 2>/dev/null | awk '{print $4}' | sort | uniq -c
  log "failed units: $(systemctl --failed --no-legend | wc -l)"
  rm -f "$before" "$after"

  log "install-storage-layout.sh must now be a no-op (every line present, drop-in byte-identical)"
  "${SCRIPT_DIR}/install-storage-layout.sh" | grep -E '^(present|replace|added|FATAL)' || true
  log "CUTOVER DONE for: ${roles[*]}. The old volumes keep their data under old-<suffix> until reclaimed."
}

case "${1:-}" in
  prepare) shift; cmd_prepare "$@" ;;
  cutover) shift; cmd_cutover "$@" ;;
  *) die "usage: migrate-tier.sh prepare ROLE VG PV_BY_ID SIZE | cutover ROLE [ROLE ...]" ;;
esac

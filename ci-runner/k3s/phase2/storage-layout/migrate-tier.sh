#!/usr/bin/env bash
# migrate-tier.sh — move a CI storage tier to new media, or replace its
# filesystem in place, by COPY + RELABEL, with /etc/fstab untouched and
# install-storage-layout.sh a no-op throughout.
#
# This is README "Storage layout: media-neutral tier identity" → "Moving a
# tier to new media" as code, generalised from the script that carried the
# containerd store and the runner work volumes from the RAID-5 array LVs onto
# the first NVMe on poweredge-xubuntu on 2026-09-04 (livespec plan
# `poweredge-raid-array-maintenance`, epic livespec-g52yrb, child
# livespec-e2vcqf), and extended on 2026-09-06 with the LIVE switch used to
# reformat `ci-workvols` as XFS (reflink) without stopping k3s
# (livespec-dev-tooling-hmv2bo). A tier is addressed by its filesystem
# LABEL; moving it means putting the bytes on a new volume and moving the
# label, never editing fstab.
#
# PER-ROLE FILESYSTEM TYPE — the one place it is decided (the installer's
# five fstab lines MUST agree; see role_fstype below):
#   ci-cache       ext4
#   ci-containerd  ext4   (overlayfs snapshotter; no copy-on-write need)
#   ci-workvols    xfs    (reflink=1: the warm uv-cache seed is `cp --reflink`,
#                          so every seeded inode is the job's own and a job's
#                          writes never reach the shared generation — livespec
#                          plan ci-runner-pod-lifecycle-reliability research/006
#                          option (a); an XFS label holds 12 bytes, ext4's 16)
#
# SUBCOMMANDS
#
#   prepare ROLE VG PV_BY_ID SIZE
#       Live, k3s running, CI may be on. Idempotent. Ensures the physical
#       volume (pvcreate only on a device with NO signature — a stale copy
#       from an earlier attempt must be wiped by hand first, deliberately:
#       `vgremove` + `wipefs -a`, never reused), the volume group, an LV for
#       the role in that VG (named ROLE, or `ROLE-new` when the VG already
#       holds an LV named ROLE — the in-place filesystem replacement case),
#       and a filesystem of the role's type carrying the TEMPORARY label
#       `new-<suffix>` (ROLE minus its `ci-` prefix; two volumes must never
#       carry the role label at once). Then a bulk rsync of the live tier onto
#       it under /mnt/migrate-tier/ROLE. Re-run it to refresh the copy.
#
#   cutover ROLE [ROLE ...]
#       The quiet-window switch (k3s stopped): refuses unless the pool is idle
#       (zero EphemeralRunners); stops k3s (k3s-killall.sh leaves the bind
#       mounts alone); final delta copy; verifies it (dry-run itemised pass
#       listing nothing but directory timestamps, matching inode counts);
#       unmounts bind, tier and temp mount; swaps labels (old → `old-<suffix>`,
#       new → ROLE); refreshes /dev/disk/by-label without a blanket udev
#       trigger; `mount -a`; proves every path resolves to the new device;
#       starts k3s and the After=k3s oneshots; compares the image count; runs
#       install-storage-layout.sh, which must report every line present.
#
#   switch-live ROLE
#       The NO-window switch, for a tier that holds only per-job data and a
#       regenerable root (ci-workvols): STACKS the prepared new filesystem on
#       top of the tier mountpoint and a fresh bind on top of the bind target,
#       never unmounting the old ones — so the mount units stay active and the
#       k3s RequiresMountsFor drop-in cannot fire. Pods already running keep
#       their references to the old filesystem and finish; every NEW work
#       volume lands on the new one. Prints the drain state.
#
#   drain-status ROLE
#       How many running pods still hold a work volume on the old filesystem
#       (kubelet's per-pod volume binds whose source is the old device).
#
#   finish-live ROLE
#       After drain reaches zero: relabels old → `old-<suffix>` and new → ROLE
#       ONLINE (tune2fs for ext4; `xfs_io label` for a mounted XFS), renames
#       the LVs when `ROLE-new` naming was used, runs install-storage-layout.sh
#       (which rewrites the fstab line's type if the role's type changed), and
#       records that the old volume stays mounted UNDERNEATH until the next
#       boot — fstab then mounts only the new one.
#
#   reclaim ROLE
#       After that next boot: removes the `ROLE-old` LV (refuses while it is
#       mounted anywhere), extends the role's LV over the freed extents, grows
#       the filesystem online.
#
# WHAT IT REFUSES, and why each is a rule (each cost real time on 2026-09-04):
#   - a PV on a device that already carries a signature (the SN8100 came back
#     from a failed attempt holding a stale containerd copy).
#   - `ci-cache` in cutover/switch-live: the two tier mounts live ON it.
#   - a non-idle pool for cutover; a role whose `new-` volume is missing; a
#     role label that does not resolve to exactly one device; a label longer
#     than the filesystem allows.
#
# NEVER `udevadm trigger --subsystem-match=block` on this host, and never
# unmount a tier mount under a running k3s: on 2026-09-04 the former marked the
# mounted device-mapper volumes not-ready, systemd stopped every tier mount,
# and the k3s RequiresMountsFor drop-in stopped k3s ahead of them (shims
# orphaned, every listener Unknown). switch-live only ever ADDS mounts.
#
# Usage:  sudo migrate-tier.sh prepare ci-workvols nvmea /dev/disk/by-id/nvme-WD_BLACK_SN8100_4000GB_25384T801085 600G
#         sudo migrate-tier.sh switch-live ci-workvols      # then wait: drain-status ci-workvols → 0
#         sudo migrate-tier.sh finish-live ci-workvols
#         (next boot)  sudo migrate-tier.sh reclaim ci-workvols
# Requires: root, lvm2, e2fsprogs, xfsprogs (for an xfs role), rsync,
# util-linux, k3s. PV_BY_ID must be a /dev/disk/by-id/ path (enumeration
# order shifts across boots behind a switch).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_MOUNT="/var/cache/ci-runner"
TMP_ROOT="/mnt/migrate-tier"
export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

log() { printf '%s %s\n' "$(date -u '+%H:%M:%SZ')" "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 2; }

[ "$(id -u)" -eq 0 ] || die "must run as root"
for c in pvs vgs lvs lvcreate lvrename blkid findmnt rsync lvchange udevadm k3s; do
  command -v "$c" >/dev/null || die "${c} not on PATH"
done

# ROLE → tier mountpoint, bind target, filesystem type, label limit.
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
role_fstype() {
  case "$1" in
    ci-workvols) echo "xfs" ;;
    *) echo "ext4" ;;
  esac
}
label_limit() { case "$1" in xfs) echo 12 ;; *) echo 16 ;; esac; }
suffix() { printf '%s' "${1#ci-}"; }
check_label() {  # check_label LABEL FSTYPE
  [ "${#1}" -le "$(label_limit "$2")" ] || die "label '$1' exceeds ${2}'s $(label_limit "$2")-byte limit"
}
require_fs_tools() {
  case "$1" in
    xfs)  for c in mkfs.xfs xfs_io xfs_admin xfs_growfs; do command -v "$c" >/dev/null || die "${c} not on PATH (apt install xfsprogs)"; done ;;
    ext4) for c in mkfs.ext4 tune2fs resize2fs; do command -v "$c" >/dev/null || die "${c} not on PATH"; done ;;
  esac
}

# Fresh superblock probe (no blkid cache — it goes stale after a relabel).
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
fstype_of() { blkid -p -s TYPE -o value "$1" 2>/dev/null || true; }

# set_label DEVICE LABEL — by filesystem type; works on a mounted filesystem
# for both ext4 (tune2fs) and xfs (xfs_io on the mountpoint, kernel ≥ 4.18).
set_label() {
  local dev="$1" label="$2" fstype mp
  fstype="$(fstype_of "$dev")"
  check_label "$label" "$fstype"
  case "$fstype" in
    ext4) tune2fs -L "$label" "$dev" >/dev/null || die "tune2fs -L ${label} ${dev}" ;;
    xfs)
      mp="$(findmnt -rn -S "$dev" -o TARGET | head -1)"
      if [ -n "$mp" ]; then
        xfs_io -c "label -s ${label}" "$mp" >/dev/null || die "xfs_io label ${label} on ${mp}"
      else
        xfs_admin -L "$label" "$dev" >/dev/null || die "xfs_admin -L ${label} ${dev}"
      fi ;;
    *) die "cannot relabel ${dev}: unsupported filesystem type '${fstype}'" ;;
  esac
}
make_fs() {  # make_fs DEVICE FSTYPE LABEL
  case "$2" in
    xfs)  mkfs.xfs -q -m reflink=1 -L "$3" "$1" || die "mkfs.xfs ${1}" ;;
    ext4) mkfs.ext4 -q -L "$3" "$1" || die "mkfs.ext4 ${1}" ;;
    *) die "unsupported filesystem type '$2'" ;;
  esac
}
rsync_tier() {  # rsync_tier SRC_DIR DST_DIR [extra rsync args]
  local src="$1" dst="$2"; shift 2
  rsync -aHAXS --numeric-ids --delete --one-file-system "$@" "${src}/" "${dst}/"
}
lv_of_device() {  # vg/lv for a dm device path, or empty
  lvs --noheadings -o vg_name,lv_name --select "lv_path=$(readlink -f "$1")" 2>/dev/null | awk '{print $1"/"$2}'
}

# ---------------------------------------------------------------------------
cmd_prepare() {
  [ $# -eq 4 ] || die "usage: prepare ROLE VG PV_BY_ID SIZE"
  local role="$1" vg="$2" pv="$3" size="$4" src lvname lv dev newlabel tmp fstype
  src="$(tier_mount "$role")"
  fstype="$(role_fstype "$role")"
  require_fs_tools "$fstype"
  newlabel="new-$(suffix "$role")"
  check_label "$newlabel" "$fstype"; check_label "$role" "$fstype"; check_label "old-$(suffix "$role")" "$(fstype_of "$(one_device_with_label "$role")")"
  case "$pv" in /dev/disk/by-id/*) ;; *) die "PV must be a /dev/disk/by-id/ path, got '${pv}'" ;; esac
  [ -b "$pv" ] || die "${pv} is not a block device (a missing by-id path is how fio once filled /dev with a regular file)"
  findmnt -n --target "$src" >/dev/null || die "${src} is not mounted; nothing to copy"

  log "prepare ${role}: PV ${pv} → VG ${vg} → LV (${size}) → ${fstype} LABEL=${newlabel} → bulk copy from ${src}"

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
    pvs --noheadings -o vg_name "$pv" | grep -q "$vg" || die "VG ${vg} exists but ${pv} is not one of its PVs"
    log "VG ${vg} present"
  else
    vgcreate "$vg" "$pv" >/dev/null || die "vgcreate ${vg} ${pv}"
    log "VG ${vg} created"
  fi

  # In-place filesystem replacement: the VG already holds the role's LV.
  lvname="$role"
  if lvs --noheadings "${vg}/${role}" >/dev/null 2>&1 && [ "$(readlink -f "/dev/${vg}/${role}")" = "$(readlink -f "$(one_device_with_label "$role")")" ]; then
    lvname="${role}-new"
    log "VG ${vg} already carries the live ${role}; the new LV is named ${lvname} (renamed at finish-live)"
  fi
  lv="/dev/${vg}/${lvname}"
  if lvs --noheadings "${vg}/${lvname}" >/dev/null 2>&1; then
    log "LV ${vg}/${lvname} present"
  else
    lvcreate -L "$size" -n "$lvname" "$vg" >/dev/null || die "lvcreate ${vg}/${lvname} ${size}"
    log "LV ${vg}/${lvname} created (${size})"
  fi
  dev="$(readlink -f "$lv")"

  case "$(blkid -p -o value -s LABEL "$dev" 2>/dev/null || true)" in
    "$newlabel")
      [ "$(fstype_of "$dev")" = "$fstype" ] || die "${dev} carries LABEL=${newlabel} but is $(fstype_of "$dev"), not ${fstype}; wipe it by hand"
      log "filesystem present: ${fstype} LABEL=${newlabel}" ;;
    "")
      [ -z "$(fstype_of "$dev")" ] || die "${dev} has a filesystem with no label; refusing to guess"
      make_fs "$dev" "$fstype" "$newlabel"
      log "${fstype} created on ${dev} with LABEL=${newlabel}" ;;
    "$role") die "${dev} already carries the ROLE label ${role} — the switch already happened, or two volumes carry it; run install-storage-layout.sh" ;;
    *) die "${dev} carries an unexpected label '$(blkid -p -o value -s LABEL "$dev")'" ;;
  esac

  tmp="${TMP_ROOT}/${role}"
  install -d -m 0755 "$tmp"
  findmnt -n --target "$tmp" | grep -q "^${tmp} " || mount "$dev" "$tmp" || die "mount ${dev} ${tmp}"
  log "bulk copy ${src} → ${tmp} (live; the switch takes the final delta)"
  rsync_tier "$src" "$tmp" --info=progress2 ; rc=$?
  [ "$rc" -eq 0 ] || die "bulk rsync rc=${rc}"
  log "prepare ${role} done: $(df -h --output=used,size "$tmp" | tail -1 | tr -s ' ') used/size on ${dev}; left mounted at ${tmp}"
}

# ---------------------------------------------------------------------------
# Common preconditions for a switch: the tier is mounted from the role label,
# the prepared volume is mounted at the temp path under the new- label.
switch_preconditions() {  # sets OLD NEW SRC BIND TMP
  local role="$1"
  [ "$role" != "ci-cache" ] || die "ci-cache (the tier root) is not moved by this tool: the tier mounts live on it"
  SRC="$(tier_mount "$role")"; BIND="$(bind_target "$role")"; TMP="${TMP_ROOT}/${role}"
  findmnt -n --target "$SRC" | grep -q "^${SRC} " || die "${SRC} is not mounted"
  findmnt -n --target "$TMP" | grep -q "^${TMP} " || die "${TMP} is not mounted — run prepare ${role} first"
  OLD="$(one_device_with_label "$role")"
  NEW="$(one_device_with_label "new-$(suffix "$role")")"
  [ "$(findmnt -n -o SOURCE "$SRC")" = "$OLD" ] || die "${SRC} is mounted from $(findmnt -n -o SOURCE "$SRC"), not from LABEL=${role} (${OLD})"
  [ "$(findmnt -n -o SOURCE "$TMP")" = "$NEW" ] || die "${TMP} is mounted from $(findmnt -n -o SOURCE "$TMP"), not from LABEL=new-$(suffix "$role") (${NEW})"
}

cmd_cutover() {
  [ $# -ge 1 ] || die "usage: cutover ROLE [ROLE ...]"
  local roles=("$@") role src bind tmp old new n_old n_new diff_lines before after

  for role in "${roles[@]}"; do
    switch_preconditions "$role"
    log "cutover ${role}: ${OLD} → ${NEW}"
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
    set_label "$old" "old-$(suffix "$role")"
    set_label "$new" "$role"
    log "relabelled ${role}: ${old} → old-$(suffix "$role"), ${new} → ${role}"
    for d in "$old" "$new"; do
      lvpath="$(lv_of_device "$d")"
      [ -z "$lvpath" ] || lvchange --refresh "$lvpath" 2>/dev/null || true
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

# ---------------------------------------------------------------------------
# Live switch: stack, never unmount. Old pods drain on their own.
old_device_pod_binds() {  # count kubelet per-pod volume binds sourced from DEVICE
  findmnt -rn -S "$1" -o TARGET 2>/dev/null | grep -c '^/var/lib/kubelet/pods/' || true
}

cmd_switch_live() {
  [ $# -eq 1 ] || die "usage: switch-live ROLE"
  local role="$1"
  switch_preconditions "$role"
  [ -n "$BIND" ] || die "${role} has no bind target; use cutover"
  log "switch-live ${role}: stacking ${NEW} over ${SRC} and a fresh bind over ${BIND} (old mounts stay underneath)"
  log "final delta copy of the regenerable root (per-job volumes are NOT copied: running pods keep theirs on ${OLD})"
  # Copy only what is not a per-job volume: everything except pvc-* directories.
  rsync -aHAXS --numeric-ids --one-file-system --exclude='/pvc-*' --exclude='/lost+found' "${SRC}/" "${TMP}/"; rc=$?
  [ "$rc" -eq 0 ] || die "delta rsync rc=${rc}"
  mount "$NEW" "$SRC" || die "stack-mount ${NEW} on ${SRC}"
  mount --bind "$SRC" "$BIND" || die "stack-bind ${SRC} on ${BIND}"
  [ "$(findmnt -n -o SOURCE "$SRC")" = "$NEW" ] || die "${SRC} top mount is not ${NEW}"
  [ "$(findmnt -n -o SOURCE "$BIND")" = "$NEW" ] || die "${BIND} top mount is not ${NEW}"
  # The old mounts must still be present underneath (units stay active).
  findmnt -rn -S "$OLD" -o TARGET | grep -qx "$SRC" || die "old tier mount vanished from under ${SRC} — unexpected"
  log "switched: new work volumes land on ${NEW}; $(old_device_pod_binds "$OLD") running pod(s) still hold a volume on ${OLD}"
  log "next: wait for 'drain-status ${role}' to report 0, then 'finish-live ${role}'"
}

cmd_drain_status() {
  [ $# -eq 1 ] || die "usage: drain-status ROLE"
  local role="$1" old n
  old="$(one_device_with_label "$role")"
  n="$(old_device_pod_binds "$old")"
  printf 'old=%s pods_holding_old_volume=%s\n' "$old" "$n"
  [ "$n" -eq 0 ]
}

cmd_finish_live() {
  [ $# -eq 1 ] || die "usage: finish-live ROLE"
  local role="$1" src bind old new n oldlv newlv vg fstype
  src="$(tier_mount "$role")"; bind="$(bind_target "$role")"
  old="$(one_device_with_label "$role")"
  new="$(one_device_with_label "new-$(suffix "$role")")"
  [ "$(findmnt -n -o SOURCE "$src")" = "$new" ] || die "${src} top mount is not the new volume; run switch-live first"
  n="$(old_device_pod_binds "$old")"
  [ "$n" -eq 0 ] || die "${n} running pod(s) still hold a volume on ${old}; wait for drain-status to reach 0"
  fstype="$(fstype_of "$new")"
  [ "$fstype" = "$(role_fstype "$role")" ] || die "${new} is ${fstype}, but ${role} is declared $(role_fstype "$role")"

  set_label "$old" "old-$(suffix "$role")"
  set_label "$new" "$role"
  log "relabelled online: ${old} → old-$(suffix "$role"), ${new} → ${role}"
  oldlv="$(lv_of_device "$old")"; newlv="$(lv_of_device "$new")"
  if [ -n "$newlv" ] && [ "${newlv##*/}" = "${role}-new" ]; then
    vg="${newlv%%/*}"
    [ "$oldlv" = "${vg}/${role}" ] || die "expected old LV ${vg}/${role}, found '${oldlv}'"
    lvrename "$vg" "$role" "${role}-old" >/dev/null || die "lvrename ${vg}/${role} → ${role}-old"
    lvrename "$vg" "${role}-new" "$role" >/dev/null || die "lvrename ${vg}/${role}-new → ${role}"
    log "renamed LVs: ${vg}/${role} → ${role}-old, ${vg}/${role}-new → ${role}"
  fi
  # The temp mount of the new volume is no longer needed; the tier mount is the live one.
  umount "${TMP_ROOT}/${role}" 2>/dev/null || true

  log "install-storage-layout.sh (rewrites the tier line's type if the role's filesystem changed; nothing is remounted)"
  "${SCRIPT_DIR}/install-storage-layout.sh" | grep -E '^(present|replace|added|backup|  old|  new|FATAL)' || true
  grep -E "^LABEL=${role} " /etc/fstab
  log "FINISH-LIVE DONE for ${role}. The old volume (${old}, LABEL=old-$(suffix "$role")) stays mounted UNDERNEATH ${src} until the next boot;"
  log "fstab then mounts only the new one. After that boot: 'migrate-tier.sh reclaim ${role}' removes the old LV and grows the new."
}

cmd_reclaim() {
  [ $# -eq 1 ] || die "usage: reclaim ROLE"
  local role="$1" old new oldlv newlv vg fstype mp
  new="$(one_device_with_label "$role")"
  old="$(devices_with_label "old-$(suffix "$role")" | head -1)"
  [ -n "$old" ] || die "no volume carries LABEL=old-$(suffix "$role"); nothing to reclaim"
  [ -z "$(findmnt -rn -S "$old" -o TARGET)" ] || die "${old} is still mounted ($(findmnt -rn -S "$old" -o TARGET | tr '\n' ' ')); reclaim only after the boot that drops it"
  oldlv="$(lv_of_device "$old")"; newlv="$(lv_of_device "$new")"
  [ -n "$oldlv" ] && [ -n "$newlv" ] || die "old (${oldlv:-none}) or new (${newlv:-none}) is not an LV"
  vg="${newlv%%/*}"
  [ "${oldlv%%/*}" = "$vg" ] || die "old LV ${oldlv} is in a different VG from ${newlv}; reclaim by hand"
  lvremove -y "$oldlv" >/dev/null || die "lvremove ${oldlv}"
  log "removed ${oldlv}"
  lvextend -l +100%FREE "$newlv" >/dev/null || die "lvextend ${newlv}"
  fstype="$(fstype_of "$new")"
  mp="$(findmnt -rn -S "$new" -o TARGET | head -1)"
  case "$fstype" in
    xfs)  [ -n "$mp" ] || die "xfs_growfs needs the filesystem mounted"; xfs_growfs "$mp" >/dev/null || die "xfs_growfs ${mp}" ;;
    ext4) resize2fs "$new" >/dev/null || die "resize2fs ${new}" ;;
  esac
  log "RECLAIM DONE: ${newlv} is now $(lvs --noheadings -o lv_size "$newlv" | tr -d ' ') ($(df -h --output=size "$mp" | tail -1 | tr -d ' ') ${fstype})"
}

case "${1:-}" in
  prepare)      shift; cmd_prepare "$@" ;;
  cutover)      shift; cmd_cutover "$@" ;;
  switch-live)  shift; cmd_switch_live "$@" ;;
  drain-status) shift; cmd_drain_status "$@" ;;
  finish-live)  shift; cmd_finish_live "$@" ;;
  reclaim)      shift; cmd_reclaim "$@" ;;
  *) die "usage: migrate-tier.sh prepare ROLE VG PV_BY_ID SIZE | cutover ROLE [ROLE ...] | switch-live ROLE | drain-status ROLE | finish-live ROLE | reclaim ROLE" ;;
esac

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
# PER-ROLE FILESYSTEM TYPE (decided in migrate-tier.sh role_fstype; these
# lines MUST agree with it): ci-cache and ci-containerd are ext4; ci-workvols
# is XFS with reflink=1 since 2026-09-06, so the warm uv-cache seed can be a
# `cp --reflink` that gives every job its own inodes (livespec plan
# ci-runner-pod-lifecycle-reliability research/006 option (a);
# livespec-dev-tooling-hmv2bo). An XFS label holds 12 bytes: `ci-workvols`,
# `new-workvols` and `old-workvols` all fit.
#
# THE LAYOUT (the five lines this installer ensures, byte-exact):
#   LABEL=ci-cache       /var/cache/ci-runner                 ext4 defaults,noatime 0 2
#   LABEL=ci-containerd  /var/cache/ci-runner/k3s-containerd  ext4 defaults,noatime,x-systemd.requires-mounts-for=/var/cache/ci-runner 0 2
#   LABEL=ci-workvols    /var/cache/ci-runner/k3s-storage     xfs  defaults,noatime,x-systemd.requires-mounts-for=/var/cache/ci-runner 0 2
#   /var/cache/ci-runner/k3s-containerd /var/lib/rancher/k3s/agent/containerd none bind,x-systemd.requires-mounts-for=/var/cache/ci-runner/k3s-containerd 0 0
#   /var/cache/ci-runner/k3s-storage    /var/lib/rancher/k3s/storage          none bind,x-systemd.requires-mounts-for=/var/cache/ci-runner/k3s-storage 0 0
# Each bind requires ITS OWN SOURCE mount, not merely the cache volume:
# otherwise systemd may bind the empty mountpoint directory before the tier
# volume lands on it, and k3s would run on the cache volume — or on `/` —
# silently, since every path exists either way. The k3s drop-in
# (10-requires-storage-mounts.conf, installed here) closes the last gap:
# k3s does not start at all unless both bind targets are mounted.
#
# WHAT IT DOES, in this order, printing every command as a `+ ` line:
#   1. refuses unless each label resolves to EXACTLY one block device (zero =
#      format the volume first; two = a media swap is half done, relabel the
#      old one first);
#   2. unmounts any FOREIGN mountpoint of a tier volume — a desktop's udisks
#      automount at /run/media/<user>/ci-cache holds the very volume the next
#      step is about to mount where it belongs;
#   3. creates the mountpoint directories and MOUNTS the cache tier, because
#      the two tier mountpoints live ON that volume: created while it is not
#      mounted they would land on `/` where the mounted volume then hides them;
#   4. ensures the five fstab lines — an existing DIFFERENT line for one of
#      the five mountpoints is REPLACED, with /etc/fstab backed up first and
#      old and new printed — and `systemctl daemon-reload` when it changed
#      anything, so the generated mount units match the file;
#   5. mounts every managed mountpoint that is not mounted yet. When k3s is
#      ALREADY RUNNING here and its containerd store or local-path root holds
#      content that is not on the tier yet, the k3s unit is stopped, the
#      content is rsynced onto the tier, the binds are mounted, and the unit is
#      started again — a bind laid over a live store would HIDE it, which is
#      the one thing this installer must never do;
#   6. `findmnt --verify`, whose errors are fatal only for those five
#      mountpoints (an unrelated line, e.g. an unplugged backup disk with
#      `nofail`, is reported and left alone), and then a hard check that all
#      five really are mounted;
#   7. installs the k3s drop-in and reloads systemd.
# It never formats and never destroys data. On a node whose tiers are already
# live it runs NO command at all: that no-op is its contract, and the reason
# migrate-tier.sh can end every procedure by running it.
#
# WHEN TO RUN IT: at any point after stage 1 of the rebuild
# (../../phase0-bare-metal/README.md) has produced the labelled filesystems —
# BEFORE or AFTER k3s is installed, and with k3s running or stopped. Step 5 is
# what makes the k3s-already-running case safe, so ../install-node.sh (stage 4,
# which runs after the k3s stage) can call it unattended.
#
# --dry-run PRINTS THE PLAN AND EXECUTES NOTHING: no mount, no fstab write, no
# root check. That is what makes every case above assertable off-host
# (./install-storage-layout-exit-tests.sh).
#
# MEDIA SWAP (the whole point; README "Storage layout: media-neutral tier
# identity"): mkfs.ext4 -L <temporary label> on the new volume, rsync -aHAXS
# from the live tier, then in a quiet window with k3s stopped: tune2fs -L on
# both so ONLY the new volume carries the role label, mount -a. fstab is
# unchanged, and this installer stays a no-op throughout.
#
# Usage: sudo install-storage-layout.sh [--dry-run]
# Requires: root (mounts the tiers, writes /etc/fstab and /etc/systemd/system),
# util-linux, rsync. `--dry-run` requires none of it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"

# TEST ROOT — empty on a node, and the ONLY way this script can be aimed at
# anything but the real host. Every absolute path below is resolved under it, so
# ./install-storage-layout-exit-tests.sh can build a fresh host, a foreign
# automount and a running k3s inside a scratch directory and assert the plan
# each one yields. It is never set on a node, and ../install-node.sh never sets
# it. Same shape as STORAGE_ROOT in ../storage-sweep/sweep-runner-scratch.sh.
ROOT="${STORAGE_LAYOUT_ROOT:-}"
ROOT="${ROOT%/}"

CACHE_MOUNT="${ROOT}/var/cache/ci-runner"
CONTAINERD_SRC="${CACHE_MOUNT}/k3s-containerd"
STORAGE_SRC="${CACHE_MOUNT}/k3s-storage"
CONTAINERD_DIR="${ROOT}/var/lib/rancher/k3s/agent/containerd"
STORAGE_DIR="${ROOT}/var/lib/rancher/k3s/storage"
FSTAB="${ROOT}/etc/fstab"
DROPIN_NAME="10-requires-storage-mounts.conf"
DROPIN_DST="${ROOT}/etc/systemd/system/k3s.service.d/${DROPIN_NAME}"
LABEL_CACHE="ci-cache"
LABEL_CONTAINERD="ci-containerd"
LABEL_WORKVOLS="ci-workvols"
# Both names, because the k3s unit an AGENT node runs is `k3s-agent.service`:
# a check naming only the server's would silently never fire on an agent, which
# is exactly the role the gmktec node joins as.
K3S_UNITS=(k3s.service k3s-agent.service)
MANAGED_MOUNTPOINTS=("$CACHE_MOUNT" "$CONTAINERD_SRC" "$STORAGE_SRC" "$CONTAINERD_DIR" "$STORAGE_DIR")

USAGE="usage: sudo ${SCRIPT_NAME} [--dry-run]"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    *) die "unknown argument '$1' -- ${USAGE}" ;;
  esac
  shift
done

# ONE call site per mutating command, printed as a `+ ` line in BOTH modes and
# executed only outside --dry-run, so the plan a dry run prints cannot describe
# a different run from the one that happens. A line WITHOUT the `+ ` marker is
# an observation and never changes anything — which is what lets the exit tests
# assert the no-op contract as "no `+ ` line at all".
run() {  # run CMD ARG...
  printf '+ %s\n' "$*"
  [ "$DRY_RUN" -eq 1 ] || "$@"
}

for c in blkid lsblk findmnt mount umount systemctl cmp find; do
  command -v "$c" >/dev/null || die "${c} not on PATH"
done
[ -f "${SCRIPT_DIR}/${DROPIN_NAME}" ] || die "${SCRIPT_DIR}/${DROPIN_NAME} missing beside this script"
[ -f "$FSTAB" ] || die "${FSTAB} does not exist"
if [ "$DRY_RUN" -eq 0 ]; then
  [ "$(id -u)" -eq 0 ] || die "must run as root (mounts the tiers and writes ${FSTAB} and ${DROPIN_DST})"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  MODE_NOTE='--dry-run (every step below is PRINTED and none is executed)'
else
  MODE_NOTE='execute (every step below is printed as it runs)'
fi
printf '== %s plan ==\n' "$SCRIPT_NAME"
printf 'mode:    %s\n' "$MODE_NOTE"
printf 'fstab:   %s\n' "$FSTAB"
printf 'drop-in: %s\n' "$DROPIN_DST"
if [ -n "$ROOT" ]; then
  printf 'root:    %s   (STORAGE_LAYOUT_ROOT -- TEST USE ONLY; never set on a node)\n' "$ROOT"
fi

# ---------------------------------------------------------------------------
# Mount bookkeeping. A dry run must plan as though its earlier steps HAD run —
# otherwise it would print `install -d` for tier mountpoints on a cache volume
# it has only planned to mount, and then plan to mount it a second time. Every
# step therefore asks `is_mounted_or_planned`, never the host alone.
# ---------------------------------------------------------------------------
MOUNT_PLANNED=""

is_mounted_now() {  # is_mounted_now TARGET — TARGET is a mountpoint on this host right now
  [ "$(findmnt -n -o TARGET --target "$1" 2>/dev/null)" = "$1" ]
}

mark_planned() { MOUNT_PLANNED="${MOUNT_PLANNED}${1}"$'\n'; }

is_mounted_or_planned() {  # is_mounted_or_planned TARGET
  if is_mounted_now "$1"; then
    return 0
  fi
  case $'\n'"$MOUNT_PLANNED" in
    *$'\n'"$1"$'\n'*) return 0 ;;
    *) return 1 ;;
  esac
}

is_managed_mountpoint() {  # is_managed_mountpoint TARGET
  local m
  for m in "${MANAGED_MOUNTPOINTS[@]}"; do
    if [ "$1" = "$m" ]; then
      return 0
    fi
  done
  return 1
}

ensure_dir() {  # ensure_dir DIR — created only when absent, so a conforming host runs no command
  if [ -d "$1" ]; then
    return 0
  fi
  run install -d -m 0755 "$1"
}

dir_has_content() {  # dir_has_content DIR — DIR exists and holds at least one entry
  [ -d "$1" ] || return 1
  local entry
  entry="$(find "$1" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null || true)"
  [ -n "$entry" ]
}

mount_managed() {  # mount_managed TARGET — mount it from fstab unless it is already up
  if is_mounted_or_planned "$1"; then
    printf 'mounted: %s\n' "$1"
    return 0
  fi
  run mount "$1"
  mark_planned "$1"
}

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
one_device_with_label() {  # one_device_with_label LABEL -> the device, or refuses
  local label="$1" devs n
  devs="$(devices_with_label "$label")"
  n="$(printf '%s' "$devs" | grep -c . || true)"
  case "$n" in
    1) printf '%s' "$devs" ;;
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
}
# `|| exit 1` on purpose: the refusals above run inside a command substitution,
# so their `exit 1` ends the SUBSHELL and would otherwise leave the assignment
# as the only thing that failed.
DEV_CACHE="$(one_device_with_label "$LABEL_CACHE")" || exit 1
DEV_CONTAINERD="$(one_device_with_label "$LABEL_CONTAINERD")" || exit 1
DEV_WORKVOLS="$(one_device_with_label "$LABEL_WORKVOLS")" || exit 1
printf 'LABEL=%-14s -> %s\n' "$LABEL_CACHE" "$DEV_CACHE"
printf 'LABEL=%-14s -> %s\n' "$LABEL_CONTAINERD" "$DEV_CONTAINERD"
printf 'LABEL=%-14s -> %s\n' "$LABEL_WORKVOLS" "$DEV_WORKVOLS"

# ---------------------------------------------------------------------------
log "2. A tier volume mounted anywhere but its own mountpoint is unmounted first"
# A desktop node runs udisks, which automounts a freshly formatted volume at
# /run/media/<user>/<label> the moment mkfs finishes — seen on gmktec-xubuntu
# 2026-09-07. Mounting the same volume where it belongs would then either fail
# or stack, so the foreign mountpoint goes first.
#
# NARROW ON PURPOSE: a tier already mounted where it belongs is SKIPPED
# ENTIRELY, whatever else its device carries. On a live node the workvols
# device carries one kubelet per-pod bind for every running runner
# (migrate-tier.sh drain-status counts exactly those), and the containerd
# device carries its own bind target; a rule that unmounted every non-managed
# mountpoint of a tier device would tear a running pool apart. A foreign
# mountpoint can only block us when the tier's own mountpoint is still free,
# and that is the only case this acts on.
FOREIGN=0
for pair in "${DEV_CACHE}|${CACHE_MOUNT}" "${DEV_CONTAINERD}|${CONTAINERD_SRC}" "${DEV_WORKVOLS}|${STORAGE_SRC}"; do
  dev="${pair%%|*}"; tier="${pair#*|}"
  if is_mounted_now "$tier"; then
    continue
  fi
  while IFS= read -r target; do
    [ -n "$target" ] || continue
    if is_managed_mountpoint "$target"; then
      continue
    fi
    run umount "$target"
    FOREIGN=1
  done < <(findmnt -rn -o TARGET --source "$dev" 2>/dev/null || true)
done
[ "$FOREIGN" -eq 1 ] || echo "no tier volume is mounted outside its own mountpoint"

# ---------------------------------------------------------------------------
log "3. Mountpoint directories, and the cache tier the other two live on"
# The bind targets and the cache mountpoint are plain directories on the root
# filesystem. The two TIER mountpoints live ON the cache volume, so creating
# them while it is not mounted would put them on `/` where the mounted volume
# later hides them: the cache volume is mounted first, and only then are they
# created. This is the fresh-host bootstrap that used to be a hand step whose
# omission left fstab written and nothing mounted.
ensure_dir "$CACHE_MOUNT"
ensure_dir "$CONTAINERD_DIR"
ensure_dir "$STORAGE_DIR"
if is_mounted_or_planned "$CACHE_MOUNT"; then
  printf 'mounted: %s\n' "$CACHE_MOUNT"
  ensure_dir "$CONTAINERD_SRC"
  ensure_dir "$STORAGE_SRC"
else
  # By LABEL and with the options spelled out, because this mount happens
  # BEFORE section 4 writes the fstab line: on a fresh host there is no line to
  # mount from yet. The options MUST stay equal to that line's — otherwise the
  # tier runs with the kernel's relatime until the next boot silently corrects
  # it, and the run that bootstrapped the node is the one node nobody rechecks.
  # ./install-storage-layout-exit-tests.sh §A asserts the two are the same.
  run mount -o defaults,noatime "LABEL=${LABEL_CACHE}" "$CACHE_MOUNT"
  mark_planned "$CACHE_MOUNT"
  # Unconditional, and `install -d` is idempotent: what is under these paths on
  # the root filesystem says nothing about what is on the volume just mounted.
  run install -d -m 0755 "$CONTAINERD_SRC"
  run install -d -m 0755 "$STORAGE_SRC"
fi

# ---------------------------------------------------------------------------
log "4. The five fstab lines (byte-exact; a differing line for the same mountpoint is replaced)"
BACKUP=""
CHANGED=0
fstab_backup() {
  [ -z "$BACKUP" ] || return 0
  BACKUP="${FSTAB}.pre-storage-layout-$(date -u +%Y%m%dT%H%M%SZ)"
  run cp -p "$FSTAB" "$BACKUP"
}
ensure_line() {
  local line="$1" mountpoint="$2" existing lineno
  if grep -qxF -- "$line" "$FSTAB"; then
    printf 'present: %s\n' "$mountpoint"
    return 0
  fi
  existing="$(grep -nE "^[^#][^[:space:]]*[[:space:]]+${mountpoint}[[:space:]]" "$FSTAB" || true)"
  if [ -n "$existing" ]; then
    if [ "$(printf '%s\n' "$existing" | wc -l)" -ne 1 ]; then
      printf '%s\n' "$existing" >&2
      die "${FSTAB} carries more than one line for ${mountpoint}; reconcile by hand (the lines are above)"
    fi
    fstab_backup
    lineno="${existing%%:*}"
    printf '+ fstab replace %s\n' "$mountpoint"
    printf '    old: %s\n' "${existing#*:}"
    printf '    new: %s\n' "$line"
    if [ "$DRY_RUN" -eq 0 ]; then
      # Spliced through a temp file: sed's replacement side would reinterpret
      # `&` and backslashes, and the line must land byte-exact.
      { head -n "$((lineno - 1))" "$FSTAB"; printf '%s\n' "$line"; tail -n "+$((lineno + 1))" "$FSTAB"; } > "${FSTAB}.tmp.$$"
      cat "${FSTAB}.tmp.$$" > "$FSTAB"
      rm -f "${FSTAB}.tmp.$$"
    fi
    CHANGED=1
  else
    printf '+ fstab append %s\n' "$mountpoint"
    printf '    new: %s\n' "$line"
    if [ "$DRY_RUN" -eq 0 ]; then
      printf '%s\n' "$line" >> "$FSTAB"
    fi
    CHANGED=1
  fi
}
ensure_line "LABEL=${LABEL_CACHE} ${CACHE_MOUNT} ext4 defaults,noatime 0 2" "$CACHE_MOUNT"
ensure_line "LABEL=${LABEL_CONTAINERD} ${CONTAINERD_SRC} ext4 defaults,noatime,x-systemd.requires-mounts-for=${CACHE_MOUNT} 0 2" "$CONTAINERD_SRC"
ensure_line "LABEL=${LABEL_WORKVOLS} ${STORAGE_SRC} xfs defaults,noatime,x-systemd.requires-mounts-for=${CACHE_MOUNT} 0 2" "$STORAGE_SRC"
ensure_line "${CONTAINERD_SRC} ${CONTAINERD_DIR} none bind,x-systemd.requires-mounts-for=${CONTAINERD_SRC} 0 0" "$CONTAINERD_DIR"
ensure_line "${STORAGE_SRC} ${STORAGE_DIR} none bind,x-systemd.requires-mounts-for=${STORAGE_SRC} 0 0" "$STORAGE_DIR"
if [ "$CHANGED" -eq 1 ]; then
  run systemctl daemon-reload
fi

# ---------------------------------------------------------------------------
log "5. Mount every managed mountpoint (a running k3s's store moves onto its tier first, it is never hidden)"
# The two tier volumes first: each bind's SOURCE has to be the tier itself, not
# the empty directory on the cache volume that stands in for it.
mount_managed "$CONTAINERD_SRC"
mount_managed "$STORAGE_SRC"

# A bind laid over a directory that already holds content HIDES it. On a node
# where k3s has been running — which is every node built in the README's stage
# order, since stage 3 installs k3s and stage 4 runs this — the containerd store
# under /var/lib/rancher/k3s/agent/containerd is exactly such a directory. The
# content is moved onto the tier first, with the k3s unit stopped for the copy.
# "Not yet on the tier" is read as "the tier source is EMPTY": a tier that
# already holds a store is the store, and re-copying over it would be wrong as
# well as slow — that is the state migrate-tier.sh hands this script.
MIGRATIONS=""
for pair in "${CONTAINERD_DIR}|${CONTAINERD_SRC}" "${STORAGE_DIR}|${STORAGE_SRC}"; do
  dir="${pair%%|*}"; src="${pair#*|}"
  if is_mounted_or_planned "$dir"; then
    continue
  fi
  if ! dir_has_content "$dir"; then
    continue
  fi
  if dir_has_content "$src"; then
    printf 'note:    %s already holds content, so %s is reported and NOT copied\n' "$src" "$dir"
    continue
  fi
  MIGRATIONS="${MIGRATIONS}${pair}"$'\n'
done

ACTIVE_UNIT=""
for unit in "${K3S_UNITS[@]}"; do
  if systemctl is-active --quiet "$unit" 2>/dev/null; then
    ACTIVE_UNIT="$unit"
    break
  fi
done

STOPPED=""
if [ -n "$MIGRATIONS" ]; then
  command -v rsync >/dev/null || die "rsync not on PATH, and a k3s store has to be copied onto its tier before the bind hides it"
fi
if [ -n "$MIGRATIONS" ] && [ -n "$ACTIVE_UNIT" ]; then
  printf 'note:    %s is active and holds content not on its tier; it is stopped for the copy and started again below\n' "$ACTIVE_UNIT"
  run systemctl stop "$ACTIVE_UNIT"
  STOPPED="$ACTIVE_UNIT"
fi
while IFS= read -r pair; do
  [ -n "$pair" ] || continue
  dir="${pair%%|*}"; src="${pair#*|}"
  run rsync -aHAX "${dir}/" "${src}/"
done <<< "$MIGRATIONS"

mount_managed "$CONTAINERD_DIR"
mount_managed "$STORAGE_DIR"

if [ -n "$STOPPED" ]; then
  run systemctl start "$STOPPED"
fi

# ---------------------------------------------------------------------------
log "6. findmnt --verify ${FSTAB} (errors are fatal only for the five managed mountpoints)"
if [ "$DRY_RUN" -eq 1 ]; then
  printf 'verify:  findmnt --verify --tab-file %s   (not run under --dry-run: the mounts above were printed, not made)\n' "$FSTAB"
else
  # findmnt --verify checks EVERY line and exits non-zero on any error, so an
  # unrelated entry — on 2026-09-04 the unplugged USB backup disk, harmless at
  # boot thanks to `nofail` — would otherwise abort this installer after it
  # had already written its lines. Only errors under the five managed
  # mountpoints, and parse errors (which poison the whole file), are fatal.
  verify_out="$(findmnt --verify --tab-file "$FSTAB" 2>&1 || true)"
  printf '%s\n' "$verify_out"
  managed_errors="$(printf '%s\n' "$verify_out" | awk -v managed="${CACHE_MOUNT} ${CONTAINERD_SRC} ${STORAGE_SRC} ${CONTAINERD_DIR} ${STORAGE_DIR}" '
    BEGIN { n = split(managed, m, " "); for (i = 1; i <= n; i++) is_managed[m[i]] = 1 }
    /^[^[:space:]]/ { current = $1; next }
    /^[[:space:]]+\[E\]/ && (current in is_managed) { print current ": " $0 }
  ')"
  if [ -n "$managed_errors" ] || printf '%s\n' "$verify_out" | grep -qE '^[1-9][0-9]* parse errors'; then
    printf '%s\n' "$managed_errors" >&2
    die "${FSTAB} failed verification for a managed line (or has parse errors). Previous copy: ${BACKUP:-none (no line was replaced)}"
  fi
  if printf '%s\n' "$verify_out" | grep -qE '^[[:space:]]+\[E\]'; then
    echo "NOTE: the error(s) above are on lines this installer does not manage; reported, not fixed here."
  fi
fi

# ---------------------------------------------------------------------------
log "7. k3s drop-in ${DROPIN_DST} (k3s refuses to start unless both binds are mounted)"
if [ -f "$DROPIN_DST" ] && cmp -s "${SCRIPT_DIR}/${DROPIN_NAME}" "$DROPIN_DST"; then
  echo "present, byte-identical to git"
else
  run install -D -m 0644 "${SCRIPT_DIR}/${DROPIN_NAME}" "$DROPIN_DST"
  run systemctl daemon-reload
fi

# ---------------------------------------------------------------------------
log "8. Live state"
for m in "${MANAGED_MOUNTPOINTS[@]}"; do
  if is_mounted_now "$m"; then
    printf '%-46s mounted: %s\n' "$m" "$(findmnt -n -o SOURCE,FSTYPE --target "$m")"
  elif is_mounted_or_planned "$m"; then
    printf '%-46s planned above (not made under --dry-run)\n' "$m"
  else
    printf '%-46s NOT mounted\n' "$m"
  fi
done

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the plan above was printed and NOTHING was executed --\n'
  exit 0
fi

# The half-applied state this installer was written to end: fstab carrying the
# five lines with nothing mounted, and an exit code that said it had worked.
for m in "${MANAGED_MOUNTPOINTS[@]}"; do
  is_mounted_now "$m" || die "${m} is still not mounted after this run; the layout is HALF APPLIED (fstab: ${FSTAB})"
done

log "DONE. Storage layout recorded in ${FSTAB} and ${DROPIN_DST}, and all five mountpoints are live."

#!/usr/bin/env bash
#
# usb-backup.sh — back up poweredge-xubuntu to the USB volume.
#
# Installed by the usb_backup Ansible role and triggered every 12h by
# usb-backup.timer -> usb-backup.service. Also runnable by hand:
#
#   sudo /usr/local/sbin/usb-backup
#   journalctl -u usb-backup.service -f      # when run via the timer/service
#
# Exits 0 only if EVERY pass succeeded. Any real failure exits non-zero and is
# named in the summary. Do not judge success by eyeballing the log.
#
# ---------------------------------------------------------------------------
# EXIT-CODE POLICY — carried verbatim from the proven poweredge run-backup.sh.
#
# An earlier ancestor of that script classified rsync's exit 23 as "tolerated".
# That was WRONG and it silently accepted an incomplete backup.
#
#   0  success.
#   24 "some files vanished before they could be transferred" — the file was
#      deleted between rsync's scan and its copy. Benign on a live system, and
#      the files in question no longer exist to be backed up. WARN.
#   23 "some files/attrs were NOT transferred" — rsync tried and FAILED.
#      The backup is INCOMPLETE. This is an ERROR, never tolerated.
#
# Anything other than 0 or 24 is an error.
# ---------------------------------------------------------------------------
#
# No `set -e`. Per BashFAQ/105 it is unreliable for this shape of script — it
# would abort on the first non-zero rc and skip the remaining passes, which is
# precisely how an earlier run lost passes without saying so. Exit status is
# checked explicitly instead. `pipefail` is set so that any pipeline added
# later cannot mask a failure.
set -uo pipefail

# MUST match usb_backup_dest and usb_backup_datastore_path in the role's
# defaults/main.yml — this static runner owns the operative values.
readonly DEST=/mnt/usb-backup
readonly DATASTORE=/var/lib/rancher/k3s/server/db/state.db

declare -i failures=0
declare -a summary=()

log() { printf '%s %s\n' "$(date -u '+%H:%M:%SZ')" "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 2; }

[[ $EUID -eq 0 ]]        || die "must run as root (needs to read all files and preserve ownership)"
mountpoint -q "$DEST"    || die "$DEST is not mounted — refusing to write into the underlying directory"

# Refuse to run concurrently with another copy of itself. A timer-launched job
# can overlap a careless manual relaunch, so a second `rsync --delete` run could
# land on one destination. `pgrep -x rsync` matches the executable name only, so
# it cannot match this script's own command line.
if pgrep -x rsync >/dev/null; then
    die "an rsync is already running — refusing to start a second writer against $DEST"
fi

# Shared options. An array, so no word-splitting surprises.
#   -a archive  -H hardlinks (containerd's overlay store depends on them)
#   -A ACLs     -X xattrs (overlayfs + security contexts)  -S sparse
#   --numeric-ids  never remap uid/gid via name lookup — essential when
#                  restoring onto a fresh install
#   --one-file-system  never cross a mount boundary, so a stray mount (the USB
#                  drive itself, or the k3s datastore tmpfs) is never swept in
#   --delete-excluded  ALSO delete excluded paths from the destination. Without
#                  it, --delete alone will not touch anything matching an
#                  --exclude, so a path that USED to be backed up and is now
#                  excluded stays stranded on the destination forever. rsync
#                  protects excluded paths from deletion by design; this opts
#                  out of that protection.
readonly -a RSYNC_OPTS=(
    -aHAXS
    --numeric-ids
    --delete
    --delete-excluded
    --info=progress2
    --one-file-system
)

# Volatile / futile paths, excluded because backing them up is both pointless
# and a source of spurious failures:
#   /var/cache/ci-runner  — the CI runner cache. ~59G of regenerable build
#                  cache the maintainer explicitly does NOT want backed up. This
#                  is the pass the old run-backup.sh had; here it is REPLACED by
#                  the exclude below plus the datastore snapshot pass.
#   /k3s-storage — local-path PVC scratch. A running CI job creates thousands of
#                  files here and deletes the whole tree when it finishes.
#                  Racing it produces rc=23. Nothing here survives a job.
#   *.premove    — rollback copies left by the containerd relocation.
#   /var/log/pods— transient per-pod logs, rotated away mid-copy.
#   /swap.img    — the swap file; large, volatile, meaningless to restore.
readonly -a EXCLUDE_COMMON=( --exclude='lost+found' )
readonly -a EXCLUDE_ROOT=(
    --exclude='/swap.img'
    --exclude='/var/log/pods/***'
    --exclude='/var/lib/rancher/k3s/agent/containerd.premove/***'
    --exclude='/var/lib/rancher/k3s/storage.premove/***'
    --exclude='/var/cache/ci-runner/***'
    --exclude='/k3s-storage/***'
)

# run_pass <label> <rsync args...>
# Runs rsync directly — NOT through a pipe — so $? is rsync's own status and
# cannot be masked by a downstream command in a pipeline.
run_pass() {
    local -r label=$1
    shift
    log "=== ${label} ==="
    rsync "$@"
    local -i rc=$?
    case $rc in
        0)
            log "    ${label}: OK (rc=0)"
            summary+=("OK      ${label}")
            ;;
        24)
            log "    ${label}: OK with warning (rc=24 — files vanished mid-copy; they no longer exist to back up)"
            summary+=("WARN    ${label} (rc=24 vanished)")
            ;;
        *)
            log "    ${label}: FAILED (rc=${rc}) — backup is INCOMPLETE"
            summary+=("FAILED  ${label} (rc=${rc})")
            failures+=1
            ;;
    esac
    return 0
}

# run_datastore_snapshot
# The k3s datastore is a LIVE SQLite database on a tmpfs mount, so the rsync
# passes (--one-file-system) never see it. `sqlite3 .backup` takes an
# online-consistent copy of it — including any WAL — safe to run against the
# open database. This pass REPLACES the old ci-runner-cache pass.
run_datastore_snapshot() {
    local -r label="k3s datastore snapshot"
    log "=== ${label} ==="

    if ! command -v sqlite3 >/dev/null 2>&1; then
        # The role installs sqlite3, so a missing binary means the host is
        # mis-provisioned. Fail loudly and name it rather than skip silently.
        log "    ${label}: FAILED — sqlite3 is not installed; cannot snapshot ${DATASTORE}"
        summary+=("FAILED  ${label} (sqlite3 missing)")
        failures+=1
        return 0
    fi

    if [[ ! -f $DATASTORE ]]; then
        # Absent datastore is expected when the k3s cluster is down (or this
        # node is an agent, not the server). Nothing to snapshot, but that is
        # not a backup failure — WARN, do not fail.
        log "    ${label}: WARNING — ${DATASTORE} is absent (cluster down?); skipping snapshot"
        summary+=("WARN    ${label} (datastore absent)")
        return 0
    fi

    mkdir -p "$DEST/k3s-datastore" || {
        log "    ${label}: FAILED — cannot create $DEST/k3s-datastore"
        summary+=("FAILED  ${label} (mkdir)")
        failures+=1
        return 0
    }

    sqlite3 "$DATASTORE" ".backup '$DEST/k3s-datastore/state.db'"
    local -i rc=$?
    if (( rc == 0 )); then
        log "    ${label}: OK (rc=0)"
        summary+=("OK      ${label}")
    else
        log "    ${label}: FAILED (rc=${rc}) — datastore snapshot is INCOMPLETE"
        summary+=("FAILED  ${label} (rc=${rc})")
        failures+=1
    fi
    return 0
}

mkdir -p "$DEST"/{rootfs,boot-efi,k3s-datastore,meta} || die "cannot create destination directories"

log "backup starting -> $DEST"

# Metadata first: a restore needs the map even if the data copy is interrupted.
{
    lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINT > "$DEST/meta/lsblk.txt"
    blkid                                                > "$DEST/meta/blkid.txt"
    cp -a /etc/fstab                                       "$DEST/meta/fstab.txt"
    sfdisk -d /dev/sda                                   > "$DEST/meta/sda-parttable.sfdisk"
    dpkg --get-selections                                > "$DEST/meta/dpkg-selections.txt"
    uname -a                                             > "$DEST/meta/uname.txt"
    systemctl list-unit-files --state=enabled --no-pager > "$DEST/meta/enabled-units.txt"
    k3s --version                                        > "$DEST/meta/k3s-version.txt"
} 2>/dev/null
log "metadata captured"

# Pass 1: the rootfs. --one-file-system keeps this on / alone; /boot/efi and
# the datastore tmpfs are handled by the two passes below.
run_pass "1/3 rootfs" \
    "${RSYNC_OPTS[@]}" "${EXCLUDE_COMMON[@]}" "${EXCLUDE_ROOT[@]}" \
    / "$DEST/rootfs/"

# Pass 2: the EFI system partition (vfat). vfat carries no ownership/perms/
# xattrs, so the full flag set is meaningless here; the ESP is regenerated by
# grub-install at restore anyway.
run_pass "2/3 boot/efi" \
    -rltD --delete --delete-excluded --info=progress2 \
    /boot/efi/ "$DEST/boot-efi/"

# Pass 3: the k3s embedded-SQLite datastore, via an online-consistent snapshot.
run_datastore_snapshot

sync

printf '\n=== SUMMARY ===\n'
printf '  %s\n' "${summary[@]}"
if (( failures > 0 )); then
    printf '\n*** BACKUP FAILED: %d pass(es) did not complete. The backup is NOT usable. ***\n' "$failures"
    exit 1
fi
printf '\n=== BACKUP COMPLETE — all passes succeeded ===\n'
exit 0

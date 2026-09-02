#!/usr/bin/env bash
# sweep-runner-scratch.sh — remove every local-path volume directory under
# /var/lib/rancher/k3s/storage BEFORE k3s starts on a boot whose datastore is
# empty, so no orphaned runner scratch survives a boot.
#
# WHY THIS EXISTS (livespec plan `ci-runner-pod-lifecycle-reliability`, child
# `livespec-psq5we`): two things leave directories here that nothing will
# ever reclaim. (a) The local-path provisioner leaks a directory whenever a
# claim vanishes under pod churn (research/001 logged 76 `claim ... in work
# queue no longer exists` in 20 minutes); it only deletes a directory when it
# deletes a PV it can still see. (b) The datastore is tmpfs
# (../datastore-tmpfs/), EMPTY on every boot, so every PVC directory that
# existed at reboot is orphaned by design, every time. Measured 2026-09-02:
# ~150 orphaned directories, ~50 GB, on the exact array research/004 showed
# is latency-bound at its cold-random-write ceiling.
#
# WHY THIS IS SAFE — and the two conditions it is safe under, both enforced:
#   1. EVERY PVC on this pool is a 5 Gi EPHEMERAL runner work volume; nothing
#      precious is ever placed here. If a non-ephemeral PVC is ever put on
#      this node, this unit MUST be revisited first (README "Storage sweep").
#   2. The datastore is EMPTY at the moment this runs, so no PV can reference
#      any directory. The unit's ConditionPathExists=!.../state.db is the
#      structural gate: on a boot where the tmpfs mount failed and k3s fell
#      back to the on-disk datastore, state.db exists and the sweep is
#      SKIPPED rather than run against a datastore that still holds PVs.
#      This script re-checks the same fact and refuses if k3s is running.
#
# Only directories named as the provisioner names them (pvc-<uid>_<ns>_<name>)
# are removed; anything else under the root is left alone and reported.
# Never runs under a live k3s; never crosses a mount point.
set -euo pipefail

STORAGE_ROOT="${STORAGE_ROOT:-/var/lib/rancher/k3s/storage}"
DATASTORE_DB="${DATASTORE_DB:-/var/lib/rancher/k3s/server/db/state.db}"

log() { printf '%s sweep-runner-scratch: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

[ "$(id -u)" -eq 0 ] || { log "FATAL: must run as root"; exit 1; }

# Gate 1: never under a running k3s — a live cluster may hold PVs here.
if systemctl is-active --quiet k3s.service 2>/dev/null; then
  log "REFUSED: k3s.service is active; this sweep runs only Before=k3s.service on an empty-datastore boot"
  exit 1
fi

# Gate 2: the datastore must be empty (mirrors the unit's ConditionPathExists).
if [ -e "$DATASTORE_DB" ]; then
  log "SKIPPED: ${DATASTORE_DB} exists (datastore not empty) — a PV may still reference a directory here"
  exit 0
fi

[ -d "$STORAGE_ROOT" ] || { log "nothing to do: ${STORAGE_ROOT} does not exist"; exit 0; }

# Gate 3: never cross a mount point under the root (a stray bind mount would
# turn rm -rf into a write somewhere else).
if findmnt -rn -o TARGET | grep -Fx -v "$STORAGE_ROOT" | grep -q "^${STORAGE_ROOT}/"; then
  log "REFUSED: a mount point exists below ${STORAGE_ROOT}"
  findmnt -rn -o TARGET | grep "^${STORAGE_ROOT}/" >&2
  exit 1
fi

removed=0
kept=0
bytes_before="$(du -sb "$STORAGE_ROOT" 2>/dev/null | cut -f1 || echo 0)"
shopt -s nullglob
for dir in "${STORAGE_ROOT}"/*/; do
  dir="${dir%/}"
  name="$(basename "$dir")"
  case "$name" in
    pvc-*)
      rm -rf --one-file-system -- "$dir"
      removed=$((removed + 1))
      ;;
    *)
      log "kept non-provisioner entry: ${name}"
      kept=$((kept + 1))
      ;;
  esac
done
bytes_after="$(du -sb "$STORAGE_ROOT" 2>/dev/null | cut -f1 || echo 0)"
log "removed ${removed} pvc-* directories under ${STORAGE_ROOT}; kept ${kept}; freed $(( (bytes_before - bytes_after) / 1048576 )) MiB"

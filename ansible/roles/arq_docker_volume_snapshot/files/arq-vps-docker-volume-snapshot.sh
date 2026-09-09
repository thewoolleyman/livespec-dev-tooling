#!/usr/bin/env bash
set -euo pipefail

SRC="/var/lib/docker/volumes/"
DEST_ROOT="/home/ubuntu/.local/state/arq-vps-docker-volume-snapshot"
DEST="${DEST_ROOT}/volumes"
LOCK="/run/lock/arq-vps-docker-volume-snapshot.lock"

mkdir -p "${DEST}"

exec 9>"${LOCK}"
if ! flock -n 9; then
    echo "Snapshot already running; exiting."
    exit 0
fi

if [[ ! -d "${SRC}" ]]; then
    echo "ERROR: Docker volumes path does not exist: ${SRC}" >&2
    exit 1
fi

set +e
rsync -aHAX --numeric-ids --delete --delete-delay --delete-excluded --one-file-system \
    --exclude='backingFsBlockDev' \
    --exclude='*/containerd/daemon/io.containerd.runtime.v2.task/**' \
    --exclude='*/containerd/daemon/io.containerd.snapshotter.v1.overlayfs/snapshots/**' \
    --exclude='*/containerd/tmpmounts/**' \
    --exclude='homelab-nix-store/***' \
    --exclude='homelab-nix-store-*/***' \
    --exclude='*/overlay2/**' \
    --exclude='*/tmp/**' \
    --partial-dir='.rsync-partial' \
    "${SRC}" "${DEST}/"
rsync_status=$?
set -e

if [[ ${rsync_status} -ne 0 && ${rsync_status} -ne 24 ]]; then
    echo "ERROR: rsync failed with status ${rsync_status}" >&2
    exit "${rsync_status}"
fi

{
    date --iso-8601=seconds
    echo "rsync_status=${rsync_status}"
    du -sh "${DEST_ROOT}"
} > "${DEST_ROOT}/last-success.txt"

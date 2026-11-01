#!/usr/bin/env bash
# Alert once per repeat interval when root or tmpfs capacity crosses its limit.
set -uo pipefail

ROOT_THRESHOLD=${LIVESPEC_DEV_HOST_ROOT_THRESHOLD_PERCENT:-85}
TMP_THRESHOLD=${LIVESPEC_DEV_HOST_TMP_THRESHOLD_PERCENT:-75}
REPEAT_SECONDS=${LIVESPEC_DEV_HOST_CAPACITY_REPEAT_SECONDS:-3600}
STATE_DIR=${LIVESPEC_DEV_HOST_CAPACITY_STATE_DIR:-/var/lib/livespec-dev-host-capacity}
TOPIC=${LIVESPEC_DEV_HOST_NTFY_TOPIC:-}
SERVER=${LIVESPEC_DEV_HOST_NTFY_SERVER:-https://ntfy.sh}

log() { printf '%s livespec-dev-host-capacity: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

filesystem_values() {
    df -P -k "$1" | awk 'NR == 2 {gsub(/%/, "", $5); print $5, $4}'
}

may_notify() {
    local marker=$1 now last=0
    now=$(date -u +%s)
    [[ -f $marker ]] && last=$(cat "$marker" 2>/dev/null || printf 0)
    ((now - last >= REPEAT_SECONDS))
}

check_filesystem() {
    local filesystem=$1 threshold=$2 key=$3 used available marker
    read -r used available < <(filesystem_values "$filesystem")
    [[ -n ${used:-} && -n ${available:-} ]] || { log "WARNING: cannot measure $filesystem"; return 0; }
    ((used >= threshold)) || return 0
    marker="$STATE_DIR/$key.last-notified"
    may_notify "$marker" || { log "$filesystem remains at ${used}%; repeat interval holds"; return 0; }
    if curl --fail --silent --show-error -H 'Title: Dev host capacity alert' \
        -d "$filesystem used ${used}%, ${available} KiB free" "$SERVER/$TOPIC"; then
        date -u +%s >"$marker"
        log "alerted for $filesystem: ${used}% used, ${available} KiB free"
    else
        log "WARNING: ntfy publication failed for $filesystem"
    fi
}

mkdir -p "$STATE_DIR"
if [[ -z $TOPIC ]]; then
    log "WARNING: no ntfy topic configured; capacity check cannot alert"
    exit 0
fi
check_filesystem / "$ROOT_THRESHOLD" root
check_filesystem /tmp "$TMP_THRESHOLD" tmp

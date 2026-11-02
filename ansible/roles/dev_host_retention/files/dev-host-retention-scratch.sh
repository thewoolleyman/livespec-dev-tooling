#!/usr/bin/env bash
# Scratch retention helpers sourced by dev-host-retention.sh.

declare -A LIVE_SESSION_IDS=()

scan_live_session_ids() {
    local proc_root=${LIVESPEC_DEV_HOST_RETENTION_PROC_ROOT:-/proc} process environment entry
    LIVE_SESSION_IDS=()
    for process in "$proc_root"/[0-9]*; do
        environment="$process/environ"
        [[ -r $environment ]] || continue
        while IFS= read -r entry; do
            case $entry in
                CLAUDE_CODE_SESSION_ID=*) LIVE_SESSION_IDS[${entry#CLAUDE_CODE_SESSION_ID=}]=1 ;;
            esac
        done < <(tr '\0' '\n' 2>/dev/null <"$environment")
    done
}

session_is_live() {
    local session_id=$1
    [[ -v "LIVE_SESSION_IDS[$session_id]" ]]
}

older_than() {
    local path=$1 seconds=$2 modified now
    modified=$(stat -c %Y -- "$path" 2>/dev/null) || return 1
    now=$(date -u +%s)
    ((modified < now - seconds))
}

remove_old_scratch() {
    local tmp_root=$1 seconds=$2 session
    scan_live_session_ids
    for session in "$tmp_root"/claude-*/*/*; do
        [[ -d $session ]] || continue
        older_than "$session" "$seconds" || continue
        if session_is_live "$(basename "$session")"; then
            continue
        fi
        rm -rf -- "$session" && log "removed dead session scratch $session"
    done
    for session in "$tmp_root"/pytest-of-*/*; do
        [[ -e $session ]] || continue
        older_than "$session" "$seconds" || continue
        rm -rf -- "$session" && log "removed aged pytest scratch $session"
    done
}

bulk_dump_is_root_filesystem() {
    local directory=$1 root_target dump_target dump_type
    command -v findmnt >/dev/null 2>&1 || return 0
    root_target=$(findmnt -no TARGET -T / 2>/dev/null) || return 1
    dump_target=$(findmnt -no TARGET -T "$directory" 2>/dev/null) || return 1
    dump_type=$(findmnt -no FSTYPE -T "$directory" 2>/dev/null) || return 1
    [[ $dump_target == "$root_target" && $dump_type != tmpfs ]]
}

cap_bulk_dumps() {
    local directory=$1 cap=$2 total line path
    [[ -d $directory ]] || return 0
    if ! bulk_dump_is_root_filesystem "$directory"; then
        log "REFUSE bulk-dump directory $directory: it is not on the root filesystem or is tmpfs"
        return 0
    fi
    total=$(du -sb -- "$directory" 2>/dev/null | awk '{print $1}') || return 0
    while ((total > cap)); do
        line=$(find "$directory" -type f -printf '%T@:%p\0' | sort -z -n | { IFS= read -r -d '' item || true; printf '%s' "$item"; })
        [[ -n $line ]] || break
        path=${line#*:}
        rm -f -- "$path" && log "removed bulk dump $path (oldest first)"
        total=$(du -sb -- "$directory" 2>/dev/null | awk '{print $1}') || break
    done
}

reclaim_scratch_and_bulk() {
    remove_old_scratch "$1" "$2"
    cap_bulk_dumps "$3" "$4"
}

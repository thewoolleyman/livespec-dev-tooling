#!/usr/bin/env bash
# Scratch retention helpers sourced by dev-host-retention.sh.

declare -A LIVE_SESSION_IDS=()
LIVE_SESSION_SCAN_FAILURE=

# One `grep` reads every process environment, so the scan starts the same
# number of child processes however many processes the host runs. The earlier
# loop forked a `tr` and a subshell per process: 34 s over 1,076 processes at
# load 46 on vmi3006760 (2026-11-10, livespec-dev-tooling-spva5x), against
# 0.38 s for one grep over the same environments. The paths reach grep through
# `xargs`, so a host with more processes than one argv can name still has
# every environment read instead of none. Its command buffer is sized from
# ARG_MAX (xargs lowers it to the real limit, silently here) because the
# 128 KiB default would split a few thousand paths across several greps.
# `-s` keeps an environment that cannot be read, or whose process exits
# mid-scan, silent. `-z` reads NUL-separated entries and writes each match
# NUL-terminated, so an id is read back whole.
#
# The scan FAILS CLOSED. An empty answer from a scan that did not run would
# make every session look dead, so only xargs's 0 (every grep matched) and
# 123 (some grep exited 1 for no match or 2 for an unreadable environment) are
# a completed scan. Anything else, including a missing ARG_MAX, returns
# non-zero with the reason in LIVE_SESSION_SCAN_FAILURE, and the caller
# removes no session directory and says so in the run's journal.
scan_live_session_ids() {
    local proc_root=${LIVESPEC_DEV_HOST_RETENTION_PROC_ROOT:-/proc} entry arg_max status
    local -a environments=("$proc_root"/[0-9]*/environ) matches=()
    LIVE_SESSION_IDS=()
    LIVE_SESSION_SCAN_FAILURE=
    [[ -e ${environments[0]} ]] || return 0
    if ! arg_max=$(getconf ARG_MAX 2>/dev/null) || [[ ! $arg_max =~ ^[0-9]+$ ]]; then
        LIVE_SESSION_SCAN_FAILURE="ARG_MAX unreadable"
        return 1
    fi
    mapfile -d '' -t matches < <(printf '%s\0' "${environments[@]}" |
        xargs -0 -s "$arg_max" grep -ahsz '^CLAUDE_CODE_SESSION_ID=.' -- 2>/dev/null)
    wait "$!"
    status=$?
    if [[ $status != 0 && $status != 123 ]]; then
        LIVE_SESSION_SCAN_FAILURE="status $status"
        return 1
    fi
    for entry in "${matches[@]}"; do
        LIVE_SESSION_IDS[${entry#CLAUDE_CODE_SESSION_ID=}]=1
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
    if scan_live_session_ids; then
        for session in "$tmp_root"/claude-*/*/*; do
            [[ -d $session ]] || continue
            older_than "$session" "$seconds" || continue
            if session_is_live "$(basename "$session")"; then
                continue
            fi
            rm -rf -- "$session" && log "removed dead session scratch $session"
        done
    else
        log "WARNING: session leg skipped: liveness scan failed ($LIVE_SESSION_SCAN_FAILURE); no session scratch directory is removed this run"
    fi
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

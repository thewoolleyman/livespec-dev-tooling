#!/usr/bin/env bash
# dev-host-retention.sh — the dev host's standing disk retention.
#
# WHAT BROKE. Measured 2026-10-21 on the maintainer's dev host: `/` at 94% —
# 637G of 678G, 39.4G free — with no standing retention of any kind. The
# reclaimable consumers were `~/.cache/uv` at 52G, the docker store at 21G
# (7.8G of it dangling sandbox images) and `tmp/gate-runs` at 1.1G over 4935
# run directories in four governed checkouts, with no retention period defined
# anywhere. Nothing swept any of them and nothing watched the disk, so the only
# control was a human noticing. Cargo build targets are deliberately NOT swept
# here: the two large ones belong to the fabro repository's owner, whose
# retention rule governs them.
#
# THE RUN NEVER ABORTS, AND THAT IS THE POINT. A hand `uv cache prune` on
# 2026-10-21 reclaimed ~6G and then exited non-zero on one path under
# `archive-v0` it was not permitted to remove. Under a timer that is worse than
# it sounds: everything after the prune would never run, so an unattended
# retention would reclaim nothing from docker and nothing from `tmp/gate-runs`
# either. Every leg below therefore logs its own failure and returns, and the
# script does not run under `errexit`.
#
# WHY `docker image prune -f` AND NEVER `-a`. The narrow spelling removes
# DANGLING images only. `-a` additionally removes every tagged image no
# container currently uses — which on this host is the warm sandbox image store
# that the `sandbox_image_warm` role exists to keep populated, and evicting it
# re-arms the first-pull race that role closes.
#
# WHY A GATE RUN'S TERMINAL STATE IS NOT RE-DERIVED HERE. `gate-run.sh` already
# owns that predicate — its `derive_state` is documented as "the single source
# of truth for every verdict word", and RUNNING is its only non-terminal state:
# no `exit_code`, a `pid` file, and `kill -0` against it succeeding. A run that
# never published a pid is terminal, because no verdict is coming. Re-deriving
# that here would be a second implementation of a rule whose whole value is
# having one, and the failure mode of drift is removing the evidence of a gate
# that is still running. So this script asks each checkout's own installed
# runner, once per checkout, via `gate-run.sh list`.
#
# Every value below is read from the environment the systemd unit sets from the
# role's variables; the defaults are the fleet's current ones so that running
# this script by hand on the dev host does the same thing the timer does.
set -uo pipefail

RETENTION_DAYS=${LIVESPEC_DEV_HOST_RETENTION_DAYS:-7}
CHECKOUT_ROOTS=${LIVESPEC_DEV_HOST_RETENTION_CHECKOUT_ROOTS:-/data/projects}
FILESYSTEM=${LIVESPEC_DEV_HOST_RETENTION_FILESYSTEM:-/}

log() {
    printf '%s livespec-dev-host-retention: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

# `df -P` is the POSIX output format: one record per filesystem on one line,
# whatever the length of the device name, so field 4 is always the available
# blocks. Without it a long device name wraps and the reading silently becomes
# the mount point.
report_free_space() {
    local when=$1 avail
    avail=$(df -P -k "$FILESYSTEM" | awk 'NR == 2 {print $4}')
    if [[ -z $avail ]]; then
        log "WARNING: could not measure free space on $FILESYSTEM"
        return 0
    fi
    log "free space $when: $avail KiB available on $FILESYSTEM"
}

prune_docker_images() {
    local output
    if ! command -v docker >/dev/null 2>&1; then
        log "docker is not on PATH; no image prune attempted"
        return 0
    fi
    # DANGLING ONLY — see the header for why `-a` is not an option here.
    if ! output=$(docker image prune -f 2>&1); then
        log "WARNING: the docker image prune failed and the run continues: $output"
        return 0
    fi
    log "docker image prune (dangling only): ${output//$'\n'/; }"
}

# The paths a failed prune names. uv reports the path it could not remove in
# its own error output, so the paths are read back out of that rather than
# guessed: anything that looks like an absolute path in the message is logged
# on a line of its own, and the message itself is logged verbatim beside it so
# a wording change can never silently drop the evidence.
unremovable_paths() {
    printf '%s\n' "$1" | grep -oE '(/[A-Za-z0-9._@+-]+)+' | sort -u
}

prune_uv_cache() {
    local output path
    if ! command -v uv >/dev/null 2>&1; then
        log "uv is not on PATH; no cache prune attempted"
        return 0
    fi
    if output=$(uv cache prune 2>&1); then
        log "uv cache prune: ${output//$'\n'/; }"
        return 0
    fi
    log "WARNING: the uv cache prune did not complete: ${output//$'\n'/; }"
    while IFS= read -r path; do
        [[ -n $path ]] || continue
        log "uv cache prune could not remove $path; continuing with the remaining steps"
    done < <(unremovable_paths "$output")
}

# Seconds since the epoch for a gate run's `started_at`, or nothing when the
# record cannot be read. "Older than the retention period" is anchored on
# `started_at` because it is the ONE timestamp every run directory carries: the
# gate writes it before the gate starts, so even a run that died before
# publishing a pid has one.
started_epoch() {
    local started
    started=$(cat "$1/started_at" 2>/dev/null) || return 0
    [[ -n $started ]] || return 0
    date -u -d "$started" +%s 2>/dev/null
}

remove_aged_gate_runs() {
    local checkout=$1 cutoff=$2
    local store="$checkout/tmp/gate-runs"
    [[ -d $store ]] || return 0
    local runner="$checkout/dev-tooling/gate-run.sh"
    if [[ ! -f $runner ]]; then
        log "SKIP $store: the checkout carries no dev-tooling/gate-run.sh, so the" \
            "terminal-state predicate this retention reuses is not available"
        return 0
    fi
    local listing
    if ! listing=$(cd "$checkout" && bash "$runner" list 2>&1); then
        log "SKIP $store: gate-run.sh list failed: ${listing//$'\n'/; }"
        return 0
    fi
    local run_id state dir epoch removed=0 kept=0
    while read -r run_id state _; do
        dir="$store/$run_id"
        [[ -n $run_id && -d $dir ]] || continue
        # RUNNING is gate-run.sh's only non-terminal state: the recorded process
        # is alive, so this run's evidence is still being written.
        if [[ $state == RUNNING ]]; then
            kept=$((kept + 1))
            continue
        fi
        epoch=$(started_epoch "$dir")
        if [[ -z $epoch ]]; then
            log "KEEP $dir: no readable started_at, so its age cannot be established"
            kept=$((kept + 1))
            continue
        fi
        if ((epoch > cutoff)); then
            kept=$((kept + 1))
            continue
        fi
        if rm -rf -- "$dir"; then
            log "removed gate run $dir (state $state, older than ${RETENTION_DAYS}d)"
            removed=$((removed + 1))
        else
            log "WARNING: could not remove gate run $dir"
            kept=$((kept + 1))
        fi
    done <<<"$listing"
    log "$store: removed $removed gate runs, kept $kept"
}

sweep_checkout_roots() {
    local cutoff candidate root
    cutoff=$(( $(date -u +%s) - RETENTION_DAYS * 86400 ))
    local roots
    read -r -a roots <<<"$CHECKOUT_ROOTS"
    for root in "${roots[@]}"; do
        if [[ ! -d $root ]]; then
            log "no such checkout root: $root"
            continue
        fi
        for candidate in "$root"/*/; do
            [[ -d "${candidate}.git" ]] || continue
            remove_aged_gate_runs "${candidate%/}" "$cutoff"
        done
    done
}

log "retention period: ${RETENTION_DAYS} days; checkout roots: ${CHECKOUT_ROOTS}"
report_free_space before
prune_docker_images
prune_uv_cache
sweep_checkout_roots
report_free_space after

#!/usr/bin/env bash
# Reclaim the CONTAINER layer on a Fabro factory host.
#
#   ./container-reclaim.sh hosts/vps.env            # DRY RUN (default)
#   ./container-reclaim.sh hosts/vps.env --apply    # actually prune
#
# WHY THIS EXISTS, AND WHY IT IS NOT "PRUNE UNUSED IMAGES". On 2026-08-22 the hp
# factory filled to zero bytes and an incident hotfix reclaimed ~390 GB with
# `docker image prune -a`. That worked for a reason that does not recur: 28
# unreferenced sandbox image TAGS had accumulated over two weeks. Measuring what
# the store actually holds, on BOTH hosts, by two DIFFERENT storage drivers:
#
#   hp   (containerd snapshotter)  49,935 M total | snapshots 49,432 M (99%)
#                                  images 2, content blobs 546 M
#                                  containers: 64 total, 3 running, 61 EXITED
#   vps  (overlay2)                43,041 M total | overlay2/ 43,041 M (99.97%)
#                                  image/ 13 M -- METADATA ONLY
#                                  containers: 21 total, 1 running, 20 EXITED
#
# THE STORE IS PER-CONTAINER WRITABLE LAYERS FROM EXITED CONTAINERS. A writable
# layer is released when its CONTAINER is removed, not when an image is pruned.
# So `container prune` is the PRIMARY lever and `image prune` the secondary one.
#
# THE FAILURE MODE THIS GUARDS AGAINST is a mechanism scoped to images: it would
# run clean, exit 0, report success, and leave 99% of the store untouched --
# indistinguishable from a working guard, and nothing downstream ever contradicts
# a guard that reports success.
#
# RESOLVE THE STORE FROM THE DAEMON, NEVER FROM A PATH LIST. The two hosts INVERT
# their layout: hp keeps 49 G in /var/lib/containerd with 3 M in /var/lib/docker;
# vps is the mirror image. A path-keyed mechanism measures a directory holding a
# few megabytes on the other host and reports success.
#
# `docker system df` IS NOT AVAILABLE TO US. It HANGS on both hosts -- measured
# on hp by the fix-hp-disk-space session and on vps here, where it had not
# returned after ten minutes. Per-subdirectory `du -xsm` on the resolved root is
# the substitute and takes seconds.
#
# Sourceable for testing: `main` runs only on direct execution.

set -euo pipefail

# Roots this script must never measure or treat as a store, even if a daemon
# reports one of them. A misconfigured or spoofed data-root must not turn a
# `du` loose on the whole filesystem.
readonly DENY_ROOTS=(/ /srv /tmp /var /usr /etc /boot /nix /opt /home /root /data /var/lib)

log()      { printf '%s\n' "$*"; }
warn()     { printf '%s\n' "$*" >&2; }
# Per-item narration on STDERR. Functions that RETURN a number put only that
# number on stdout, because the caller reads them through a command substitution
# and does arithmetic on the result. storage-reclaim.sh shipped this bug: a
# progress line on stdout landed in `$(( ))` and aborted the run at its SUMMARY,
# which under --apply is after every deletion has already happened.
progress() { printf '%s\n' "$*" >&2; }

# --- guards ---------------------------------------------------------------

path_is_denied() {
    local p="$1" deny
    for deny in "${DENY_ROOTS[@]}"; do
        [[ "${p}" == "${deny}" ]] && return 0
    done
    return 1
}

store_root_is_sane() {
    # A daemon-reported root must be an absolute path, must exist, and must not
    # be a deny-listed root. We never DELETE by path here -- the daemon does the
    # removal -- but we DO `du` it, and a root of "/" would walk the whole disk.
    local root="$1"
    [[ -n "${root}" ]]                || { warn "REFUSING empty store root"; return 1; }
    [[ "${root}" == /* ]]             || { warn "REFUSING non-absolute store root: ${root}"; return 1; }
    path_is_denied "${root}"          && { warn "REFUSING deny-listed store root: ${root}"; return 1; }
    [[ -d "${root}" ]]                || { warn "REFUSING non-existent store root: ${root}"; return 1; }
    return 0
}

# --- store discovery ------------------------------------------------------

docker_store_root() {
    # Ask the daemon. NOT a path list -- the two hosts invert their layout.
    docker info --format '{{.DockerRootDir}}' 2>/dev/null || true
}

containerd_store_root() {
    # `containerd config dump` prints `root = '/var/lib/containerd'`.
    containerd config dump 2>/dev/null | awk -F"'" '/^root[[:space:]]*=/{print $2; exit}' || true
}

store_root_is_readable() {
    # `du` SWALLOWS "Permission denied" AND RETURNS THE SMALL TOTAL IT REACHED,
    # so an unreadable store reports a plausible number instead of an error.
    #
    # Measured on vps 2026-08-22: as the non-root `ubuntu` user,
    # `du -xsm /var/lib/docker` returns 1 while the same command under sudo
    # returns 17163 -- a four-order-of-magnitude under-report, silent, because
    # `store_size_mb` sends stderr to /dev/null. That number feeds three things
    # at once: the printed store sizes, the dominant-store SELECTION (two
    # garbage values compared against each other), and the reclaimable total in
    # the SUMMARY.
    #
    # The service itself runs as root under systemd, so production numbers are
    # sound. This bites the HUMAN DRY RUN -- which is precisely the run an
    # operator makes to decide whether to arm the timer or pass --apply, and it
    # tells them the store is empty.
    local root="$1"
    [[ -n "${root}" ]] || return 0   # unresolved is handled by store_root_is_sane
    [[ -d "${root}" ]] || return 0   # absent is not the same as unreadable
    # Normalise to a 0/1 boolean: `ls` exits 2 on "Permission denied", and a
    # caller testing `rc == 1` would score that as readable.
    ls -- "${root}" >/dev/null 2>&1 || return 1
    return 0
}

store_size_mb() {
    # On-device size of the store root. `-x` IS DELIBERATE AND IS CORRECT HERE:
    # the question is "how many bytes does this occupy on THIS filesystem", not
    # "how large is this tree". Measured on hp, the same path reads 3 M with -x
    # and 2055 M without, and `df` confirms -x is the one answering the question
    # we are asking -- the difference is a subdirectory on a different device.
    local root="$1" s
    [[ -d "${root}" ]] || { echo 0; return 0; }
    s="$(timeout 300 du -xsm -- "${root}" 2>/dev/null | cut -f1)"
    [[ -n "${s}" ]] && echo "${s}" || echo 0
}

# --- inventory ------------------------------------------------------------

running_container_ids() {
    # RETURNS NON-ZERO WHEN THE DAEMON DOES NOT ANSWER, and callers must not
    # read that as "nothing is running".
    #
    # The previous form was `docker ps -q 2>/dev/null || true`, which collapsed
    # two different facts into one empty string: "the daemon answered and
    # nothing is running" and "the daemon did not answer at all". That is the
    # same silent-zero this file already documents for the `until` filter one
    # function below -- it is recorded there as a lesson, and it was still live
    # here, in the probe that protects running containers.
    local out
    out="$(docker ps -q 2>&1)" || { warn "ERROR: docker ps -q failed: ${out}"; return 1; }
    printf '%s' "${out}"
    [[ -n "${out}" ]] && printf '\n'
    return 0
}

# `docker ps` HAS NO `until` FILTER, THOUGH `docker container prune` DOES.
# Measured on vps 2026-08-22: `docker ps -aq --filter status=exited --filter
# until=48h` prints NOTHING to stdout and "Error response from daemon: invalid
# filter 'until'" to stderr, while `container prune --filter until=48h` accepts
# it. The first version of this file used the ps form with `2>/dev/null || true`,
# which converted that hard error into a SILENT ZERO: the report said "0 exited
# containers, ~0 MB" against a store holding 20 of them, while --apply would have
# pruned them correctly. A guard reporting nothing to do -- the exact failure
# this whole service exists to prevent, shipped inside the service itself.
#
# It was caught by an INDEPENDENT MEASUREMENT DISAGREEING (a plain `docker ps -as`
# count taken while deriving the horizon), never by the command announcing
# itself. So: enumerate with a filter the daemon actually supports, compute the
# age here, and FAIL LOUDLY if the daemon errors rather than swallowing it.
exited_containers_with_age() {
    # Emits "<id>\t<age_hours>\t<size>" per exited container. Returns non-zero
    # if the daemon call fails -- callers must not paper over that.
    local out now created age
    out="$(docker ps -a --filter status=exited \
             --format '{{.ID}}'$'\t''{{.CreatedAt}}'$'\t''{{.Size}}' 2>&1)" || {
        warn "ERROR: docker ps failed: ${out}"; return 1; }
    # A daemon error can also arrive on stdout with exit 0 in some versions.
    if grep -qi '^Error response from daemon' <<<"${out}"; then
        warn "ERROR: docker ps reported: ${out}"; return 1
    fi
    now="$(date +%s)"
    while IFS=$'\t' read -r id created size; do
        [[ -n "${id}" ]] || continue
        # CreatedAt renders as "2026-08-22 10:42:29 +0200 CEST"; the trailing
        # zone NAME confuses `date -d`, the numeric offset does not.
        created="$(sed -E 's/ [A-Z]{2,5}$//' <<<"${created}")"
        age="$(date -d "${created}" +%s 2>/dev/null)" || continue
        [[ -n "${age}" ]] || continue
        printf '%s\t%s\t%s\n' "${id}" "$(( (now - age) / 3600 ))" "${size}"
    done <<<"${out}"
}

exited_container_ids_older_than() {
    local hours="$1" id age size
    while IFS=$'\t' read -r id age size; do
        [[ -n "${id}" ]] || continue
        (( age >= hours )) && printf '%s\n' "${id}"
    done < <(exited_containers_with_age)
}

container_is_running() {
    # THE PROPERTY THAT MUST NEVER REGRESS. hp runs 3 live dispatches against 61
    # exited containers; vps 1 against 20. An over-broad prune kills live work.
    # We assert membership explicitly rather than trusting a filter's semantics,
    # because a filter that silently changes meaning is exactly the failure this
    # whole plan keeps meeting.
    # ID LENGTHS DIFFER AND THE MISMATCH FAILS TOWARD DELETION. `docker ps -q`
    # prints TRUNCATED 12-character ids, while `ps -aq`/inspect callers may hold
    # the full 64-character form. An exact-match test therefore fails to
    # recognise a container's own live short id, and the container it should
    # have protected becomes eligible. Compare by PREFIX IN BOTH DIRECTIONS: a
    # running short id that prefixes the queried long id, or the reverse. Over-
    # protecting is safe (a container is merely kept); under-protecting deletes
    # live work. Guarded by the long-id-against-short-live-form case in
    # container-reclaim.test.sh, which caught this.
    local id="$1" running r
    [[ -n "${id}" ]] || return 1
    if ! running="$(running_container_ids)"; then
        # FAIL CLOSED. A daemon that did not answer has not established that
        # this container is stopped; it has established nothing. Report RUNNING,
        # which by this function's own rule above is the safe direction -- the
        # container is merely kept, and the caller's report says so.
        #
        # WHAT THIS ACTUALLY PROTECTS, stated exactly so the next reader does
        # not over- or under-rate it. The single caller is the accounting pass
        # `reclaimable_container_mb`; the deletion itself is `docker container
        # prune`, executed by the daemon, which never removes a running
        # container. So the old behaviour could not delete live work. What it
        # DID do was silently drop every "skip (RUNNING)" line and fold running
        # containers' layers into the reported reclaimable total -- destroying
        # the operator's evidence that live containers were protected, which is
        # precisely the evidence this service's rollout was justified on.
        return 0
    fi
    [[ -z "${running}" ]] && return 1
    while IFS= read -r r; do
        [[ -n "${r}" ]] || continue
        [[ "${id}" == "${r}"* || "${r}" == "${id}"* ]] && return 0
    done <<<"${running}"
    return 1
}

reclaimable_container_mb() {
    # Sum of writable-layer sizes for the pruneable set. Returns MB on STDOUT
    # and NOTHING ELSE. `docker ps -as` renders human sizes ("563MB",
    # "5.67GB"), so they are normalised here rather than parsed downstream.
    local hours="$1" total=0 id age size unit n
    while IFS=$'\t' read -r id age size; do
        [[ -n "${id}" ]] || continue
        (( age >= hours )) || continue
        container_is_running "${id}" && { progress "  skip (RUNNING): ${id}"; continue; }
        # `docker ps` renders "563MB (virtual 2GB)"; take the FIRST field only --
        # the virtual size counts shared image layers that pruning does not free.
        size="${size%% *}"
        n="${size%%[A-Za-z]*}"; unit="${size##*[0-9. ]}"
        case "${unit}" in
            GB|gB) n="$(awk -v v="${n}" 'BEGIN{printf "%d", v*1024}')" ;;
            MB|mB) n="$(awk -v v="${n}" 'BEGIN{printf "%d", v}')" ;;
            kB|KB) n=0 ;;
            B|b)   n=0 ;;
            *)     n=0 ;;
        esac
        total=$(( total + n ))
    done < <(exited_containers_with_age_and_size "${hours}")
    echo "${total}"
}

exited_containers_with_age_and_size() {
    # Same enumeration as exited_containers_with_age, but through `ps -as` so the
    # writable-layer SIZE is populated. `-s` is materially slower (it stats every
    # container's layer), which is why the id-only path does not pay for it.
    local out now created age
    out="$(docker ps -as --filter status=exited \
             --format '{{.ID}}'$'\t''{{.CreatedAt}}'$'\t''{{.Size}}' 2>&1)" || {
        warn "ERROR: docker ps -as failed: ${out}"; return 1; }
    if grep -qi '^Error response from daemon' <<<"${out}"; then
        warn "ERROR: docker ps -as reported: ${out}"; return 1
    fi
    now="$(date +%s)"
    while IFS=$'\t' read -r id created size; do
        [[ -n "${id}" ]] || continue
        created="$(sed -E 's/ [A-Z]{2,5}$//' <<<"${created}")"
        age="$(date -d "${created}" +%s 2>/dev/null)" || continue
        [[ -n "${age}" ]] || continue
        printf '%s\t%s\t%s\n' "${id}" "$(( (now - age) / 3600 ))" "${size}"
    done <<<"${out}"
}

# --- legs -----------------------------------------------------------------

prune_containers() {
    # PRIMARY LEVER. Returns MB reclaimed (estimated pre-prune) on STDOUT.
    local hours="$1" apply="$2" ids n mb
    ids="$(exited_container_ids_older_than "${hours}")"
    n="$(grep -c . <<<"${ids}" || true)"; [[ -z "${ids}" ]] && n=0
    mb="$(reclaimable_container_mb "${hours}")"
    progress "  exited containers older than ${hours}h: ${n} (~${mb} MB of writable layers)"
    if [[ "${apply}" == "yes" && "${n}" -gt 0 ]]; then
        docker container prune -f --filter "until=${hours}h" >&2 2>/dev/null || \
            warn "  WARNING: container prune returned non-zero"
    fi
    echo "${mb}"
}

prune_images() {
    # SECONDARY LEVER, and it is the smaller half: on vps ~9 GB of image layers
    # against ~33.8 GB of exited-container writable layers. An image referenced
    # by a running container is never removed by `image prune -a`, which is the
    # property that let the hp hotfix reclaim 390 GB with eight dispatches live.
    local hours="$1" apply="$2" before after root="$3"
    before="$(store_size_mb "${root}")"
    if [[ "${apply}" == "yes" ]]; then
        docker image prune -af --filter "until=${hours}h" >&2 2>/dev/null || \
            warn "  WARNING: image prune returned non-zero"
        docker builder prune -af >&2 2>/dev/null || true
        after="$(store_size_mb "${root}")"
        echo $(( before > after ? before - after : 0 ))
    else
        progress "  (dry run: image/builder prune not executed; horizon ${hours}h)"
        echo 0
    fi
}

main() {
    local host_env="${1:?usage: container-reclaim.sh <hosts/NAME.env> [--apply]}"
    local apply=no
    [[ "${2:-}" == "--apply" ]] && apply=yes

    [[ -f "${host_env}" ]] || { warn "ERROR: no such host env file: ${host_env}"; exit 2; }
    set -a
    # shellcheck source=/dev/null
    source "${host_env}"
    set +a
    : "${RECLAIM_CANONICAL_HOST:?host env must set RECLAIM_CANONICAL_HOST}"
    : "${RECLAIM_SYSTEM_HOSTNAME:?host env must set RECLAIM_SYSTEM_HOSTNAME}"
    : "${RECLAIM_CONTAINER_IDLE_HOURS:?host env must set RECLAIM_CONTAINER_IDLE_HOURS}"
    : "${RECLAIM_IMAGE_IDLE_HOURS:?host env must set RECLAIM_IMAGE_IDLE_HOURS}"

    # Refuse to apply one host's configuration on another. Guard on the MEASURED
    # system hostname, never on a name derived from RECLAIM_CANONICAL_HOST: on
    # vps those differ (vmi3006760 vs vps), and deriving it would refuse to run
    # on the very host it targets. services/fabro-server/install.sh still
    # derives it and therefore cannot run on vps.
    local expected actual
    expected="${RECLAIM_SYSTEM_HOSTNAME}"
    actual="$(hostname -s)"
    [[ "${expected}" == "${actual}" ]] || {
        warn "ERROR: ${host_env} targets '${expected}' but this host is '${actual}'"
        exit 2
    }

    local droot croot before after freed_c freed_i running
    droot="$(docker_store_root)"
    croot="$(containerd_store_root)"

    log "container-reclaim on ${actual} ($( [[ ${apply} == yes ]] && echo APPLY || echo DRY-RUN ))"
    log "  docker root     : ${droot:-<unavailable>}"
    log "  containerd root : ${croot:-<unavailable>}"

    # Measure the LARGER of the two resolved roots. The hosts invert their
    # layout, so keying on one name is how a mechanism goes silently blind.
    local root="" dsz=0 csz=0
    # REFUSE TO REPORT SIZES WE CANNOT MEASURE. Checked before any `du` runs, so
    # the operator gets a refusal naming the cause instead of a store that looks
    # empty. See `store_root_is_readable` for the measurement.
    local sr
    for sr in "${droot}" "${croot}"; do
        store_root_is_readable "${sr}" || {
            warn "ERROR: cannot read container store root ${sr} (EUID ${EUID})."
            warn "       \`du\` would silently report the small total it could reach --"
            warn "       measured on vps: 1 MB as a non-root user against 17163 MB as root --"
            warn "       so every size, the dominant-store choice, and the reclaimable"
            warn "       total below would be wrong and would look plausible."
            warn "       Re-run as root; the systemd unit already does."
            exit 4
        }
    done

    if store_root_is_sane "${droot}"; then dsz="$(store_size_mb "${droot}")"; fi
    if store_root_is_sane "${croot}"; then csz="$(store_size_mb "${croot}")"; fi
    if (( dsz >= csz )); then root="${droot}"; else root="${croot}"; fi
    log "  docker root     : ${dsz} MB"
    log "  containerd root : ${csz} MB"
    log "  dominant store  : ${root} ($(( dsz > csz ? dsz : csz )) MB)"

    store_root_is_sane "${root}" || { warn "ERROR: no usable container store root"; exit 2; }

    # REPORT AN UNANSWERED PROBE AS UNANSWERED, NOT AS ZERO. Piping straight
    # into `grep -c .` discards the exit status, so a daemon that did not answer
    # printed "running containers (never pruned): 0" -- the most reassuring line
    # this service emits, produced by the case where it knows least.
    local running_ids
    if running_ids="$(running_container_ids)"; then
        running="$(grep -c . <<<"${running_ids}" || true)"
        [[ -z "${running_ids}" ]] && running=0
    else
        running="UNKNOWN (docker ps -q did not answer)"
    fi
    before="$(df -BM --output=avail / | tail -1 | tr -dc '0-9')"
    log "  running containers (never pruned): ${running}"
    log "  free before     : $(( before / 1024 )) GB"
    log ""

    log "LEG A (primary): exited containers older than ${RECLAIM_CONTAINER_IDLE_HOURS}h"
    freed_c="$(prune_containers "${RECLAIM_CONTAINER_IDLE_HOURS}" "${apply}")"
    log ""
    log "LEG B (secondary): images older than ${RECLAIM_IMAGE_IDLE_HOURS}h, then builder cache"
    freed_i="$(prune_images "${RECLAIM_IMAGE_IDLE_HOURS}" "${apply}" "${root}")"
    log ""

    after="$(df -BM --output=avail / | tail -1 | tr -dc '0-9')"
    log "SUMMARY"
    log "  container-layer bytes $( [[ ${apply} == yes ]] && echo reclaimed || echo reclaimable ): $(( freed_c / 1024 )) GB"
    log "  image/builder bytes reclaimed                  : $(( freed_i / 1024 )) GB"
    log "  running containers preserved                   : ${running}"
    log "  free before                                    : $(( before / 1024 )) GB"
    log "  free after                                     : $(( after / 1024 )) GB"
    [[ "${apply}" == "no" ]] && log "  (dry run -- pass --apply to act)"
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi

#!/usr/bin/env bash
# sandbox-image-warm.sh — pull the sandbox image tag this host's runs are about
# to need, before any of them needs it, and never more than once at a time.
#
# WHAT BROKE. On 2026-10-20 at 08:09:51-52Z two runs started within one second
# on a docker factory host and both needed
# ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.118.5, a tag the
# host did not hold. Each run's pull tore down the other's containerd leases and
# both died in sandbox init with "Failed to pull Docker image ... causes=[Docker
# stream error]" in 0.8 s and 3.3 s. The tag was in the registry the whole time;
# this was neither auth nor network. Nothing serialized the FIRST pull of a new
# tag, so every image bump re-armed the race and it fired hardest when the fleet
# was busiest.
#
# THE TWO PROPERTIES THAT CLOSE IT, both load-bearing:
#
#   1. The pull is SERIALIZED per reference, under flock. Two warms that start
#      together do not pull together.
#   2. The holder RE-CHECKS the local image store inside the lock. A lock
#      without the re-check serializes two pulls instead of preventing one, and
#      the second pull is exactly as able to tear down a lease as the first.
#
# WHICH TAG, AND WHY IT IS DERIVED RATHER THAN DECLARED. The tag a repository
# dispatches on is <layer>-v<version>, where the version is THIS repository's
# released version: the sandbox image layers are built and published from here,
# and the release fan-out is what rewrites every consumer's `docker =` pin to
# the new tag (livespec_dev_tooling/cross_repo/fabro_image_pin_rewrite.py, whose
# bump_pin preserves the layer prefix and moves only the version). So reading
# the version out of .release-please-manifest.json on this repository's master
# names the tag the fleet is about to dispatch on, and names it no later than
# the pin bump that makes a repository dispatch on it. A tag DECLARED in this
# host's inventory instead would lag the pin exactly as a hand-applied warm
# would, which is the ordering class work-item livespec-dev-tooling-vurvjl
# records.
#
# AN UNREADABLE PIN IS A FAILURE, NOT A QUIET NO-OP. A warm that could not read
# the pin has warmed nothing, and the next run on this host meets the very race
# this script exists to close. Exiting 0 would record that non-event in the
# journal as a healthy timer run, so it exits non-zero and pulls nothing.
#
# TWO IMAGE STORES, ONE MECHANISM (work-item bd-ib-kogktm, in the
# livespec-orchestrator-beads-fabro tenant). A docker factory host's runs pull
# from DOCKER's image store, but a Kubernetes factory pod is pulled by the k3s
# node's kubelet into K3S CONTAINERD's store (namespace k8s.io), which docker
# never touches. Measured 2026-10-26: gmktec-xubuntu's containerd held
# python-agent-v1.93.5 and not the python-agent-v1.114.1 its pods ran, so every
# factory pod landed on poweredge-xubuntu, the node that already held the image.
# LIVESPEC_SANDBOX_IMAGE_WARM_STORE=containerd points the same serialized,
# re-checked pull at that store through the CRI (`k3s crictl`), so the image is
# a kubelet-visible CRI image and not a bare ctr record.
#
# WHICH REFERENCES A CONTAINERD WARM PULLS. A Kubernetes sandbox is built from
# the `process_spec.image` of the registered provider in the Fabro server's
# host_vars, a tag that moves on its own schedule rather than with this
# repository's release (it read python-agent-v1.136.2 while master was
# v1.145.x). So when LIVESPEC_SANDBOX_IMAGE_WARM_PROCESS_SPEC_URLS names the
# committed host_vars files on master, the references are every
# `process_spec.image` those files declare, re-read on every tick: a pin bump
# merged to master is warmed on the next tick with nobody applying anything,
# exactly as the release-pin read does for docker. Only references inside
# LIVESPEC_SANDBOX_IMAGE_WARM_IMAGE are ever pulled.
#
# THE WARM KEEPS ONLY CURRENT TAGS (work-item livespec-dev-tooling-xknoqf; spec
# non-functional-requirements.md "The sandbox image warm keeps only current
# tags."). Every release bump pulls new tags, and nothing removed the old ones
# until a store crossed its own high-water mark. Measured 2026-11-02 on
# gmktec-xubuntu: about 135G of earlier sandbox tags in Docker's store before
# disk_guard's emergency prune. So once every reference of the current pinned
# set is present, each run makes a REMOVAL PASS over the tags this warm itself
# pulled (the RECORD, one reference per line, in a directory that survives a
# reboot). A tag is removed only when it is not in the pinned set, no
# container references its image, and no other protected reference shares that
# image. A tag the warm never pulled is never touched. A run that could not
# resolve and pull the whole pinned set removes nothing. Docker refuses to
# remove an image a container uses, so the warm never passes it a force flag.
# CRI RemoveImage does not refuse, so after each containerd removal the warm
# re-checks, and if a container now references the tag it pulls the tag back
# and fails the run, naming it.
#
# Every value below is read from the environment the systemd unit sets from the
# role's variables; the defaults are the fleet's current ones so that running
# this script by hand on a factory host does the same thing the timer does.
set -uo pipefail

IMAGE=${LIVESPEC_SANDBOX_IMAGE_WARM_IMAGE:-ghcr.io/thewoolleyman/livespec-fabro-sandbox}
TAG_PREFIXES=${LIVESPEC_SANDBOX_IMAGE_WARM_TAG_PREFIXES:-python-agent}
PIN_URL=${LIVESPEC_SANDBOX_IMAGE_WARM_PIN_URL:-https://raw.githubusercontent.com/thewoolleyman/livespec-dev-tooling/master/.release-please-manifest.json}
LOCK_DIR=${LIVESPEC_SANDBOX_IMAGE_WARM_LOCK_DIR:-/run/livespec-sandbox-image-warm}
LOCK_TIMEOUT_SECONDS=${LIVESPEC_SANDBOX_IMAGE_WARM_LOCK_TIMEOUT_SECONDS:-1800}
STORE=${LIVESPEC_SANDBOX_IMAGE_WARM_STORE:-docker}
CRICTL=${LIVESPEC_SANDBOX_IMAGE_WARM_CRICTL:-k3s crictl}
PROCESS_SPEC_URLS=${LIVESPEC_SANDBOX_IMAGE_WARM_PROCESS_SPEC_URLS:-}
NODE_ARCH=${LIVESPEC_SANDBOX_IMAGE_WARM_NODE_ARCH:-$(uname -m)}
# The record directory matches the role's unit name: the docker warm is
# livespec-sandbox-image-warm, every other store's carries a -<store> suffix.
if [[ $STORE == docker ]]; then _record_default=/var/lib/livespec-sandbox-image-warm; else _record_default=/var/lib/livespec-sandbox-image-warm-$STORE; fi
RECORD_DIR=${LIVESPEC_SANDBOX_IMAGE_WARM_RECORD_DIR:-$_record_default}
REMOVE_SUPERSEDED=${LIVESPEC_SANDBOX_IMAGE_WARM_REMOVE_SUPERSEDED:-true}
RECORD="$RECORD_DIR/pulled"

log() {
    printf '%s livespec-sandbox-image-warm: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

# The released version this repository's master carries. Extracted with sed
# rather than a JSON parser so the warm depends on nothing the host may not
# have: the manifest is release-please's, a flat object whose only quoted
# dotted-numeric value is the version. The second sed takes the first match
# without closing the pipe early, which `head` would, and which pipefail would
# then report as a failed read of a pin that was read perfectly well.
pin_version() {
    local body
    if ! body=$(curl --fail --silent --show-error --location --max-time 30 "$PIN_URL"); then
        return 1
    fi
    printf '%s' "$body" |
        sed -n 's/.*"\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)".*/\1/p' |
        sed -n '1p'
}

# One lock per REFERENCE, not one lock for the warm: two different tags have no
# reason to wait for each other, and a single lock would serialize a whole
# converge behind one slow layer download.
lock_path() {
    printf '%s/%s.lock' "$LOCK_DIR" "$(printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_')"
}

# The process_spec images one committed host_vars file declares. Read with awk
# rather than a YAML parser for the same reason the pin is read with sed: a
# factory node may have no YAML library. The shape is the fabro_server role's
# own schema: an `image:` key inside a `process_spec:` mapping. Comment lines
# are skipped, so a commented-out rollback image is never warmed.
process_spec_images() {
    awk '
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*$/ { next }
        {
            match($0, /^[[:space:]]*/)
            indent = RLENGTH
            if (inspec && indent <= specindent) inspec = 0
            if ($0 ~ /^[[:space:]]*process_spec:[[:space:]]*$/) {
                inspec = 1
                specindent = indent
                next
            }
            if (inspec && $0 ~ /^[[:space:]]*image:[[:space:]]*[^[:space:]]/) {
                value = $0
                sub(/^[[:space:]]*image:[[:space:]]*/, "", value)
                sub(/[[:space:]]+#.*$/, "", value)
                gsub(/["\047]/, "", value)
                print value
            }
        }
    '
}

# A tag suffixed `-arm64` names an arm64-only image, which a homelab worker's own
# Fabro instance pins. Every factory node reads that same committed file, and
# another architecture's node cannot pull it: the failed pull would fail the whole
# warm, so its real pins would stop being warmed. So only an arm64 node keeps one.
without_foreign_arch_tags() {
    case "$NODE_ARCH" in
    aarch64 | arm64) cat ;;
    *) awk '!/-arm64$/' ;;
    esac
}

# Every reference a containerd warm pulls: the process_spec images of every
# named file, inside IMAGE, de-duplicated. ANY file that cannot be read fails
# the whole read, because a partial read can silently omit the very pin that
# moved.
process_spec_references() {
    local url body found=""
    for url in "$@"; do
        if ! body=$(curl --fail --silent --show-error --location --max-time 30 "$url"); then
            return 1
        fi
        found+=$(printf '%s\n' "$body" | process_spec_images)$'\n'
    done
    # A prefix match on the literal repository, never a regex over it: awk exits
    # 0 when nothing matches, so an empty result reaches the caller's own
    # "no process_spec image" refusal instead of reading as a failed fetch.
    printf '%s' "$found" |
        awk -v image="$IMAGE" 'index($0, image ":") == 1 || index($0, image "@") == 1' |
        without_foreign_arch_tags |
        sort -u
}

# The store-specific halves of a warm: whether the store holds a reference, and
# the pull into it. Everything else — the lock, the re-check, the logging — is
# shared, so the two stores cannot drift apart on the properties that matter.
store_holds() {
    case "$STORE" in
        docker) docker image inspect "$1" >/dev/null 2>&1 ;;
        containerd) "${crictl[@]}" inspecti "$1" >/dev/null 2>&1 ;;
    esac
}

store_pull() {
    case "$STORE" in
        docker) docker pull "$1" ;;
        containerd) "${crictl[@]}" pull "$1" ;;
    esac
}

# Every tagged reference the store holds, as "<reference> <image-id>" lines.
# This is the alias map: two references sharing an image id are one image to
# the store, so removing one can delete the other's bytes (CRI) or must be
# refused when the other is protected.
store_images() {
    case "$STORE" in
        docker)
            docker images --no-trunc --format '{{.Repository}}:{{.Tag}} {{.ID}}' |
                awk '$1 !~ /:<none>$/ && NF == 2 { print $1, $2 }'
            ;;
        containerd)
            "${crictl[@]}" images --no-trunc |
                awk 'NR > 1 && $2 != "<none>" && NF >= 3 { print $1 ":" $2, $3 }'
            ;;
    esac
}

# The image id of every container on the host, in any state. A container
# references a tag when it uses that tag, its image id, or another tag of the
# same image, so in-use is decided by image id. A value that is not an id is a
# reference, and it is resolved to its id through the alias map.
store_in_use_ids() {
    local ids images
    case "$STORE" in
        docker)
            ids=$(docker ps --all --quiet --no-trunc) || return 1
            [[ -z $ids ]] && return 0
            # shellcheck disable=SC2086 # one container id per word
            docker container inspect --format '{{.Image}}' $ids || return 1
            ;;
        containerd)
            images=$(store_images) || return 1
            "${crictl[@]}" ps --all --no-trunc | awk 'NR > 1 && NF >= 2 { print $2 }' |
                while IFS= read -r value; do
                    if [[ $value == sha256:* ]]; then
                        printf '%s\n' "$value"
                    else
                        printf '%s\n' "$images" | awk -v ref="$value" '$1 == ref { print $2 }'
                    fi
                done
            ;;
    esac
}

# Remove ONE reference. Docker's `rmi` untags only the named reference and
# refuses an image a container uses; no force flag is ever passed, so that
# refusal closes the gap between the in-use check and the removal.
store_remove() {
    case "$STORE" in
        docker) docker rmi "$1" ;;
        containerd) "${crictl[@]}" rmi "$1" ;;
    esac
}

# The record: every reference this warm itself pulled, one per line. It lives in
# RECORD_DIR, a systemd StateDirectory that survives a reboot. A tag present
# before the record existed, or pulled by anyone else, is never in it.
record_init() {
    mkdir -p "$RECORD_DIR" && { [[ -f $RECORD ]] || : >"$RECORD"; }
}

record_add() {
    (
        flock --exclusive 8 || exit 1
        grep -qxF -- "$1" "$RECORD" || printf '%s\n' "$1" >>"$RECORD"
    ) 8>>"$RECORD.lock"
}

# Keep only the recorded references the store still holds: a tag removed here or
# by anyone else leaves the record, so a later pull by another party of the same
# tag is not mistaken for this warm's own.
record_prune() {
    local held=$1
    (
        flock --exclusive 8 || exit 1
        awk 'NR == FNR { held[$1] = 1; next } ($1 in held)' \
            <(printf '%s\n' "$held") "$RECORD" >"$RECORD.new" && mv "$RECORD.new" "$RECORD"
    ) 8>>"$RECORD.lock"
}

# The removal pass. Arguments: the current pinned set. Returns non-zero when a
# removal failed or a containerd removal had to be undone; a tag left in place
# because it is protected is not a failure.
remove_superseded() {
    local images in_use reference id status=0 began_referencing=0
    local -A pinned=() recorded=() id_of=() protected_ids=()
    for reference in "$@"; do pinned[$reference]=1; done
    while IFS= read -r reference; do
        [[ -n $reference ]] && recorded[$reference]=1
    done <"$RECORD"
    if ! images=$(store_images); then
        log "ERROR: could not list the $STORE image store; nothing removed"
        return 1
    fi
    if ! in_use=$(store_in_use_ids); then
        log "ERROR: could not list the containers on this host; nothing removed"
        return 1
    fi
    while read -r reference id; do
        [[ -n $reference ]] && id_of[$reference]=$id
    done <<<"$images"
    # An image id is PROTECTED when any reference of it is pinned, was not
    # pulled by this warm, or when a container uses it.
    while IFS= read -r id; do
        [[ -n $id ]] && protected_ids[$id]=1
    done <<<"$in_use"
    while read -r reference id; do
        [[ -z $reference ]] && continue
        if [[ -n ${pinned[$reference]:-} || -z ${recorded[$reference]:-} ]]; then
            protected_ids[$id]=1
        fi
    done <<<"$images"
    for reference in "${!recorded[@]}"; do
        [[ -n ${pinned[$reference]:-} ]] && continue
        id=${id_of[$reference]:-}
        [[ -z $id ]] && continue
        if [[ -n ${protected_ids[$id]:-} ]]; then
            log "kept: $reference (in use, or it shares an image with a protected reference)"
            continue
        fi
        log "removing superseded tag from $STORE: $reference"
        if ! store_remove "$reference"; then
            log "ERROR: the $STORE store refused or failed to remove $reference; it stays"
            status=1
            continue
        fi
        if [[ $STORE == containerd ]]; then
            if ! in_use=$(store_in_use_ids); then
                began_referencing=1
            else
                began_referencing=0
                while IFS= read -r in_use_id; do
                    if [[ $in_use_id == "$id" ]]; then
                        began_referencing=1
                        break
                    fi
                done <<<"$in_use"
            fi
            if [[ $began_referencing -eq 1 ]]; then
                log "ERROR: a container began referencing $reference during its removal;" \
                    "pulling it back"
                store_pull "$reference" || log "ERROR: could not pull $reference back"
                status=1
                continue
            fi
        fi
        log "removed: $reference"
    done
    if images=$(store_images); then
        record_prune "$(printf '%s\n' "$images" | awk '{ print $1 }')" || status=1
    fi
    return "$status"
}

warm_reference() {
    local reference=$1 lock
    if store_holds "$reference"; then
        log "already held: $reference"
        return 0
    fi
    lock=$(lock_path "$reference")
    (
        if ! flock --exclusive --timeout "$LOCK_TIMEOUT_SECONDS" 9; then
            log "ERROR: a concurrent warm held the lock for $reference longer than" \
                "${LOCK_TIMEOUT_SECONDS}s; not pulling, because pulling now is the race"
            exit 1
        fi
        if store_holds "$reference"; then
            log "pulled by a concurrent warm while this one waited: $reference"
            exit 0
        fi
        log "pulling into $STORE: $reference"
        if ! store_pull "$reference"; then
            log "ERROR: could not pull $reference"
            exit 1
        fi
        log "warmed: $reference"
        if ! record_add "$reference"; then
            log "ERROR: pulled $reference but could not record it in $RECORD"
            exit 1
        fi
    ) 9>"$lock"
}

case "$STORE" in
    docker | containerd) ;;
    *)
        log "ERROR: unknown image store '$STORE' (expected docker or containerd); nothing warmed"
        exit 1
        ;;
esac
read -r -a crictl <<<"$CRICTL"
if [[ $STORE == containerd && ${#crictl[@]} -eq 0 ]]; then
    log "ERROR: no crictl command declared for the containerd store; nothing warmed"
    exit 1
fi

if ! mkdir -p "$LOCK_DIR"; then
    log "ERROR: could not create the lock directory $LOCK_DIR; nothing warmed"
    exit 1
fi

references=()
read -r -a spec_urls <<<"$PROCESS_SPEC_URLS"
if [[ ${#spec_urls[@]} -gt 0 ]]; then
    if ! spec_refs=$(process_spec_references "${spec_urls[@]}"); then
        log "ERROR: could not read every process_spec source (${spec_urls[*]}); nothing warmed"
        exit 1
    fi
    while IFS= read -r reference; do
        [[ -n $reference ]] && references+=("$reference")
    done <<<"$spec_refs"
    if [[ ${#references[@]} -eq 0 ]]; then
        log "ERROR: no process_spec image inside $IMAGE in ${spec_urls[*]}; nothing warmed"
        exit 1
    fi
else
    version=$(pin_version)
    if [[ -z $version ]]; then
        log "ERROR: no version read from the pin at $PIN_URL; nothing warmed"
        exit 1
    fi

    read -r -a prefixes <<<"$TAG_PREFIXES"
    if [[ ${#prefixes[@]} -eq 0 ]]; then
        log "ERROR: no sandbox image tag prefixes declared; nothing warmed"
        exit 1
    fi
    for prefix in "${prefixes[@]}"; do
        references+=("$IMAGE:$prefix-v$version")
    done
fi

status=0
record_ready=1
if ! record_init; then
    log "ERROR: could not create the pull record $RECORD; no tag will be removed this run"
    status=1
    record_ready=0
fi
for reference in "${references[@]}"; do
    warm_reference "$reference" || status=1
done

# The removal pass runs only after a run that read every pinned-set source (a
# failed read already exited above) and pulled every reference, and only once
# the store is seen to hold the whole pinned set.
case "${REMOVE_SUPERSEDED,,}" in
    true | 1 | yes | on) remove_enabled=1 ;;
    *) remove_enabled=0 ;;
esac
if [[ $remove_enabled -eq 0 ]]; then
    log "removal pass disabled (LIVESPEC_SANDBOX_IMAGE_WARM_REMOVE_SUPERSEDED=$REMOVE_SUPERSEDED)"
elif [[ $status -ne 0 || $record_ready -eq 0 ]]; then
    log "not every reference of the pinned set was pulled; no tag removed this run"
else
    whole_set=1
    for reference in "${references[@]}"; do
        if ! store_holds "$reference"; then
            log "ERROR: $reference is absent from the $STORE store after the warm; no tag removed"
            whole_set=0
            status=1
        fi
    done
    if [[ $whole_set -eq 1 ]]; then
        remove_superseded "${references[@]}" || status=1
    fi
fi
exit "$status"

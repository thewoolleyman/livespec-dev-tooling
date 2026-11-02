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
for reference in "${references[@]}"; do
    warm_reference "$reference" || status=1
done
exit "$status"

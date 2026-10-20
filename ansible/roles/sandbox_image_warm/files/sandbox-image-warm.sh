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
# Every value below is read from the environment the systemd unit sets from the
# role's variables; the defaults are the fleet's current ones so that running
# this script by hand on a factory host does the same thing the timer does.
set -uo pipefail

IMAGE=${LIVESPEC_SANDBOX_IMAGE_WARM_IMAGE:-ghcr.io/thewoolleyman/livespec-fabro-sandbox}
TAG_PREFIXES=${LIVESPEC_SANDBOX_IMAGE_WARM_TAG_PREFIXES:-python-agent}
PIN_URL=${LIVESPEC_SANDBOX_IMAGE_WARM_PIN_URL:-https://raw.githubusercontent.com/thewoolleyman/livespec-dev-tooling/master/.release-please-manifest.json}
LOCK_DIR=${LIVESPEC_SANDBOX_IMAGE_WARM_LOCK_DIR:-/run/livespec-sandbox-image-warm}
LOCK_TIMEOUT_SECONDS=${LIVESPEC_SANDBOX_IMAGE_WARM_LOCK_TIMEOUT_SECONDS:-1800}

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

warm_reference() {
    local reference=$1 lock
    if docker image inspect "$reference" >/dev/null 2>&1; then
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
        if docker image inspect "$reference" >/dev/null 2>&1; then
            log "pulled by a concurrent warm while this one waited: $reference"
            exit 0
        fi
        log "pulling: $reference"
        if ! docker pull "$reference"; then
            log "ERROR: could not pull $reference"
            exit 1
        fi
        log "warmed: $reference"
    ) 9>"$lock"
}

if ! mkdir -p "$LOCK_DIR"; then
    log "ERROR: could not create the lock directory $LOCK_DIR; nothing warmed"
    exit 1
fi

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

status=0
for prefix in "${prefixes[@]}"; do
    warm_reference "$IMAGE:$prefix-v$version" || status=1
done
exit "$status"

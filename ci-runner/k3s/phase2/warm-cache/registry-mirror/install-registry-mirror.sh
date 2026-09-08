#!/usr/bin/env bash
# install-registry-mirror.sh — install the NODE-side half of the ghcr
# pull-through cache: render ./registries.yaml.template for this node's role
# and write it to /etc/rancher/k3s/registries.yaml. Item `livespec-h96p`.
#
# THE CLUSTER-SIDE HALF IS A DIFFERENT SCRIPT. ./converge-registry-mirror.sh
# applies ./registry-mirror.yaml (Namespace, config, Deployment, Service). The
# two are split because they are aimed at different things and fail differently
# — this one writes a file on one node and needs root, that one writes cluster
# objects and needs a kubeconfig — and because a node can carry this file
# safely before the mirror exists at all (see "SAFE TO INSTALL FIRST" below).
#
# NEVER RESTARTS k3s. k3s reads registries.yaml at START, so what this script
# writes takes effect at the next k3s start and not before. That restart kills
# every running job on the pool, so it is a maintenance-window decision and not
# an installer's — ../../k3s-config/config.yaml draws the same line for its own
# `tls-san` list. This script says so at the end and stops.
#
# SAFE TO INSTALL FIRST, in either order relative to the converge. Containerd
# keeps an implicit default endpoint that k3s documents as "always tried as a
# last resort, even if there are other endpoints listed for that registry in
# registries.yaml", so a node pointed at a mirror that does not exist yet loses
# one failed dial per pull and then fetches from ghcr exactly as today. That is
# also why this tree must never set the k3s node flag
# `--disable-default-registry-endpoint`: it removes precisely that safety net,
# and with it the property that makes this file harmless.
#
# ROLE-AWARE, and for a reason narrower than the sibling installers'. The
# artifact is the same on both roles; only the ENDPOINT differs, because the
# mirror's store is a hostPath on the node carrying the `ci-cache` tier:
#
#   server  http://127.0.0.1:5001 — the carrier is this node (the hostPort is
#           bound by CNI portmap and answers on loopback, the same way
#           ../../crates-proxy/'s 3080 does).
#   agent   http://<carrier>:5001, where <carrier> is the host of the profile's
#           CLUSTER_JOIN_ADDRESS — the server it joins, which is the node this
#           pool pins its cache tiers to. An agent given no profile therefore
#           cannot derive an endpoint and is refused unless --mirror-endpoint
#           says where the mirror is.
#
# IF THE CARRIER EVER MOVES off the server, that derivation is wrong and the
# node would point at an address serving nothing. Pass --mirror-endpoint
# explicitly in that case; the derivation is a default for the topology this
# pool has, not a claim about every topology it could have.
#
# IDEMPOTENT, and refuses rather than clobbers. A second run with the same
# inputs reports "unchanged" and writes nothing. An existing
# /etc/rancher/k3s/registries.yaml that this script did not write — no template
# marker line in it — is left alone and the run fails, naming the file: a
# hand-written registries.yaml is somebody's private-registry credentials or
# TLS configuration, and silently replacing it would break every pull on the
# node at the next k3s start.
#
# NODE-LOCAL, like the sibling installers: re-run after any node rebuild.
# Requires: root. `--dry-run` requires neither root nor a mirror; it prints the
# rendered file and the command sequence, and the only host state it touches is
# ONE READ of the installed file, so the plan can say whether this run would
# change anything.
#
# Usage: install-registry-mirror.sh [--dry-run] [--mirror-endpoint URL]
#                                   [--role server|agent] [PROFILE]
#   PROFILE            path to ../../../phase0-bare-metal/profiles/<node>.env,
#                      read for CLUSTER_ROLE and (on an agent)
#                      CLUSTER_JOIN_ADDRESS, and for nothing else. This is the
#                      form ../../install-node.sh passes.
#   --role             the same role choice made explicitly, for a hand run
#                      with no profile. Give either a PROFILE or --role.
#   --mirror-endpoint  the endpoint to write, overriding the derivation above.
#   Neither profile
#   nor --role         defaults to `server`, matching the sibling installers.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
TEMPLATE="${SCRIPT_DIR}/registries.yaml.template"
CONFIG_DIR="${K3S_CONFIG_ROOT:-/etc/rancher/k3s}"
TARGET="${CONFIG_DIR}/registries.yaml"
MIRROR_PORT=5001
PLACEHOLDER='@MIRROR_ENDPOINT@'
# The line every rendered copy carries. Used as the "we wrote this" marker, so
# a file that is somebody else's is recognised as such rather than overwritten.
MARKER='# registries.yaml — the NODE-side half of the ghcr pull-through cache'

USAGE="usage: ${SCRIPT_NAME} [--dry-run] [--mirror-endpoint URL] [--role server|agent] [PROFILE]"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
ROLE=""
ROLE_GIVEN=0
PROFILE_PATH=""
ENDPOINT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --role)
      [ $# -ge 2 ] || die "--role needs a value -- ${USAGE}"
      [ -n "$2" ] || die "--role needs a value -- ${USAGE}"
      [ "$ROLE_GIVEN" -eq 0 ] || die "--role given more than once -- ${USAGE}"
      ROLE_GIVEN=1
      ROLE="$2"; shift ;;
    --mirror-endpoint)
      [ $# -ge 2 ] || die "--mirror-endpoint needs a value -- ${USAGE}"
      [ -n "$2" ] || die "--mirror-endpoint needs a value -- ${USAGE}"
      [ -z "$ENDPOINT" ] || die "--mirror-endpoint given more than once -- ${USAGE}"
      ENDPOINT="$2"; shift ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    -*) die "unknown option '$1' -- ${USAGE}" ;;
    *)
      [ -z "$PROFILE_PATH" ] || die "unexpected extra argument '$1' -- ${USAGE}"
      PROFILE_PATH="$1" ;;
  esac
  shift
done

if [ "$ROLE_GIVEN" -eq 1 ] && [ -n "$PROFILE_PATH" ]; then
  die "give either --role or a PROFILE, not both -- ${USAGE}"
fi

# The profile is PARSED and never sourced, and only the keys this installer
# consumes are read out of it — the same restraint, and the same reason, as
# ../../storage-sweep/install-storage-sweep.sh's: ../../install-node.sh and
# ../../../phase0-bare-metal/storage-layout.sh already validate the whole file,
# and a third copy of that here would be a third thing to drift.
profile_key() {  # profile_key PATH KEY -> that key's value on stdout
  local path="$1" key="$2" line seen=0 value=""
  [ -f "$path" ] || die "profile not found: ${path}"
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in "${key}="*) ;; *) continue ;; esac
    [ "$seen" -eq 0 ] || die "${path}: profile key '${key}' given more than once"
    seen=1
    value="${line#*=}"
  done < "$path"
  [ "$seen" -eq 1 ] || die "${path}: missing required profile key '${key}'"
  printf '%s' "$value"
}

# host_of_join_address URL -> the host part of a k3s CLUSTER_JOIN_ADDRESS.
# `https://192.168.1.200:6443` -> `192.168.1.200`. Scheme and port are stripped
# because neither belongs in the mirror's endpoint: the mirror speaks plain
# HTTP on its own port on the same host.
host_of_join_address() {
  local address="$1" hostport
  hostport="${address#*://}"
  hostport="${hostport%%/*}"
  printf '%s' "${hostport%%:*}"
}

if [ -n "$PROFILE_PATH" ]; then
  # `|| exit 1` on purpose: `die` inside a command substitution exits the
  # SUBSHELL, so without this the assignment's failure would not stop the run.
  ROLE="$(profile_key "$PROFILE_PATH" CLUSTER_ROLE)" || exit 1
fi
ROLE="${ROLE:-server}"
case "$ROLE" in
  server|agent) ;;
  *) die "role must be 'server' or 'agent', got '${ROLE}'" ;;
esac

ENDPOINT_SOURCE="--mirror-endpoint"
if [ -z "$ENDPOINT" ]; then
  case "$ROLE" in
    server)
      ENDPOINT="http://127.0.0.1:${MIRROR_PORT}"
      ENDPOINT_SOURCE="derived [server]: the cache-tier carrier is this node" ;;
    agent)
      [ -n "$PROFILE_PATH" ] || die "an agent needs a PROFILE (for CLUSTER_JOIN_ADDRESS) or an explicit --mirror-endpoint: the mirror runs on the cache-tier carrier, not on this node -- ${USAGE}"
      join_address="$(profile_key "$PROFILE_PATH" CLUSTER_JOIN_ADDRESS)" || exit 1
      [ -n "$join_address" ] || die "${PROFILE_PATH}: CLUSTER_JOIN_ADDRESS is empty, so the cache-tier carrier's address cannot be derived; pass --mirror-endpoint"
      carrier_host="$(host_of_join_address "$join_address")"
      [ -n "$carrier_host" ] || die "${PROFILE_PATH}: no host could be read out of CLUSTER_JOIN_ADDRESS='${join_address}'; pass --mirror-endpoint"
      ENDPOINT="http://${carrier_host}:${MIRROR_PORT}"
      ENDPOINT_SOURCE="derived [agent]: the host of CLUSTER_JOIN_ADDRESS in ${PROFILE_PATH}" ;;
    *) die "unreachable role '${ROLE}'" ;;
  esac
fi

[ -f "$TEMPLATE" ] || die "template not found: ${TEMPLATE}"

# ---------------------------------------------------------------------------
# Render. Substituted with bash parameter expansion and not `sed`, so no part
# of the endpoint is ever read as a sed replacement metacharacter.
# ---------------------------------------------------------------------------
template_body="$(cat "$TEMPLATE")"
case "$template_body" in
  *"$PLACEHOLDER"*) ;;
  *) die "${TEMPLATE}: no '${PLACEHOLDER}' placeholder in the template" ;;
esac
rendered="${template_body//${PLACEHOLDER}/${ENDPOINT}}"
case "$rendered" in
  *"$MARKER"*) ;;
  *) die "${TEMPLATE}: the rendered file carries no marker line, so a later run could not tell its own file from somebody else's" ;;
esac

# ---------------------------------------------------------------------------
# ONE call site per command, printed under --dry-run and executed otherwise, so
# the plan a dry run prints cannot describe a different run from the one that
# happens.
# ---------------------------------------------------------------------------
run() {  # run CMD ARG...
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  %s\n' "$*"
  else
    "$@"
  fi
}

# The one host READ either mode makes: what is installed today, so both the
# plan and the run can say whether anything changes. Absent is a normal answer.
installed=""
installed_state="absent"
if [ -f "$TARGET" ]; then
  installed="$(cat "$TARGET")"
  case "$installed" in
    *"$MARKER"*) installed_state="ours" ;;
    *) installed_state="foreign" ;;
  esac
fi
if [ "$installed_state" = ours ] && [ "$installed" = "$rendered" ]; then
  installed_state="ours-unchanged"
fi

printf '== %s plan ==\n' "$SCRIPT_NAME"
printf 'role:      %s\n' "$ROLE"
printf 'endpoint:  %s   (%s)\n' "$ENDPOINT" "$ENDPOINT_SOURCE"
printf 'target:    %s   (currently: %s)\n' "$TARGET" "$installed_state"
printf '\nrendered file:\n'
printf '%s\n' "$rendered" | sed 's/^/  | /'

if [ "$installed_state" = foreign ]; then
  die "${TARGET} exists and was not written by this script (no marker line). Refusing to overwrite a hand-written registries.yaml — it may carry private-registry credentials or TLS configuration. Move it aside and re-run, or merge the 'mirrors: ghcr.io:' entry above into it by hand."
fi

if [ "$DRY_RUN" -eq 0 ]; then
  [ "$(id -u)" -eq 0 ] || die "must run as root (writes ${TARGET})"
fi

if [ "$installed_state" = ours-unchanged ]; then
  log "1. ${TARGET} is already exactly this — nothing to do"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\n-- --dry-run: the plan above was printed and NOTHING was executed --\n'
  fi
  exit 0
fi

log "1. Install ${TARGET}"
run install -d -m 0755 "${CONFIG_DIR}"
if [ "$DRY_RUN" -eq 1 ]; then
  printf '  install -m 0644 <rendered above> %s\n' "$TARGET"
else
  # Written through a temp file in the same directory and moved into place, so
  # a k3s start that races this run reads either the old file or the new one
  # and never a half-written one.
  tmp="$(mktemp "${CONFIG_DIR}/registries.yaml.XXXXXX")"
  printf '%s\n' "$rendered" > "$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$TARGET"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the plan above was printed and NOTHING was executed --\n'
  exit 0
fi

log "DONE. ${TARGET} written. k3s reads it at START, so it takes effect at the"
log "next k3s start — which this script deliberately does not perform, because"
log "restarting k3s kills every running job on the pool. Until then, and after,"
log "a mirror that is absent or down costs one failed dial and the pull falls"
log "back to ghcr (containerd's default endpoint is always tried last)."

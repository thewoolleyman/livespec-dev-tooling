#!/usr/bin/env bash
# install-apparmor-profile.sh — idempotently install and load the
# `ci-runner-workflow` AppArmor profile on a k3s runner NODE, and converge the
# `arc-hook-pod-template` ConfigMap that points workflow pods at it.
#
# Both halves are required, and they live in one script because either alone is
# a broken state: the ConfigMap without the profile makes every workflow pod
# fail admission, and the profile without the ConfigMap leaves workflow pods on
# containerd's default and reintroduces the defect. See
# ./ci-runner-workflow for the root cause and ../arc/hook-pod-template.yaml for
# how the profile reaches the hook-generated pod.
#
# NODE-LOCAL, and deliberately so: an AppArmor profile is kernel state on the
# machine that runs the pod, not a cluster object. Re-run this on any node added
# to the pool, and after any node rebuild. Dropping the file in
# /etc/apparmor.d/ is what makes the load survive a reboot — the distribution's
# apparmor unit parses that directory at boot.
#
# --profile-only INSTALLS THE KERNEL HALF ALONE, and it is not a convenience:
# the ConfigMap is a CLUSTER object, so on a node that joins the pool as an
# AGENT there is no admin kubeconfig to converge it with and no second copy of
# it to converge — the server owns it, for the whole cluster. The "either half
# alone is a broken state" rule above is a rule about the CLUSTER, and it still
# holds: the pool has one ConfigMap, written once by the server, and every
# node's kernel carries the profile it names. ../install-node.sh passes this
# flag for a profile whose CLUSTER_ROLE is `agent` and never for a `server`.
#
# Requires: root (apparmor_parser writes kernel state), apparmor_parser on
# PATH, and — unless --profile-only — kubectl with KUBECONFIG pointed at the
# k3s cluster.
#
# Usage: install-apparmor-profile.sh [--profile-only]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_NAME="ci-runner-workflow"
PROFILE_SRC="${SCRIPT_DIR}/${PROFILE_NAME}"
PROFILE_DEST="/etc/apparmor.d/${PROFILE_NAME}"
USAGE="usage: install-apparmor-profile.sh [--profile-only]"
PROFILE_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --profile-only) PROFILE_ONLY=1 ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    *) echo "FATAL: unknown argument '$1' -- ${USAGE}" >&2; exit 1 ;;
  esac
  shift
done

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (apparmor_parser writes kernel state)"; exit 1; }
command -v apparmor_parser >/dev/null || { echo "FATAL: apparmor_parser not found on PATH"; exit 1; }
if [ "$PROFILE_ONLY" -eq 0 ]; then
  command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
  : "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"
fi

# ---------------------------------------------------------------------------
log "1. Install and load the ${PROFILE_NAME} AppArmor profile on this node"
install -m 0644 "${PROFILE_SRC}" "${PROFILE_DEST}"
# -r replaces an already-loaded profile of the same name, so re-running is a
# no-op on an unchanged file and a live update on a changed one.
apparmor_parser -r -W "${PROFILE_DEST}"

# Fail loudly rather than leaving a half-installed node: a profile that parsed
# but did not reach ENFORCE mode would let pods start with weaker confinement
# than this tree claims they have.
#
# The consumer MUST read aa-status to EOF: this script runs under pipefail,
# and `grep -q` exits at the first match, so once the host carries more
# profiles than one write() of aa-status output holds, aa-status takes
# SIGPIPE (exit 141), the pipeline fails, and a correctly-enforced profile
# reads as FATAL. Measured on poweredge-xubuntu 2026-09-06 at 201 loaded
# profiles: `grep -qx` exit 141, `grep -Fx >/dev/null` exit 0, same input.
if ! aa-status 2>/dev/null | grep -Fx "   ${PROFILE_NAME}" >/dev/null; then
  echo "FATAL: ${PROFILE_NAME} is not loaded in enforce mode after parsing"
  exit 1
fi

# ---------------------------------------------------------------------------
if [ "$PROFILE_ONLY" -eq 1 ]; then
  log "2. SKIPPED (--profile-only): the arc-hook-pod-template ConfigMap is a"
  log "   cluster object the k3s server converges for the whole pool."
  log "Done. ${PROFILE_NAME} is loaded in enforce mode on this node."
  exit 0
fi

log "2. Converge the arc-hook-pod-template ConfigMap in arc-runners"
# Shared with ../warm-cache/install-warm-cache.sh, which converges the SAME
# ConfigMap for the warm-cache UV_CACHE_DIR the template also carries; one converge
# script so the two installers cannot drift on how it is written.
"${SCRIPT_DIR}/../arc/converge-hook-pod-template.sh"

log "Done. Scale sets mount this ConfigMap and set"
log "ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE — see ../arc/values-livespec-overseer.yaml."

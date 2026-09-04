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
# Requires: root (apparmor_parser writes kernel state), apparmor_parser on
# PATH, kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_NAME="ci-runner-workflow"
PROFILE_SRC="${SCRIPT_DIR}/${PROFILE_NAME}"
PROFILE_DEST="/etc/apparmor.d/${PROFILE_NAME}"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (apparmor_parser writes kernel state)"; exit 1; }
command -v apparmor_parser >/dev/null || { echo "FATAL: apparmor_parser not found on PATH"; exit 1; }
command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"

# ---------------------------------------------------------------------------
log "1. Install and load the ${PROFILE_NAME} AppArmor profile on this node"
install -m 0644 "${PROFILE_SRC}" "${PROFILE_DEST}"
# -r replaces an already-loaded profile of the same name, so re-running is a
# no-op on an unchanged file and a live update on a changed one.
apparmor_parser -r -W "${PROFILE_DEST}"

# Fail loudly rather than leaving a half-installed node: a profile that parsed
# but did not reach ENFORCE mode would let pods start with weaker confinement
# than this tree claims they have.
if ! aa-status 2>/dev/null | grep -qx "   ${PROFILE_NAME}"; then
  echo "FATAL: ${PROFILE_NAME} is not loaded in enforce mode after parsing"
  exit 1
fi

# ---------------------------------------------------------------------------
log "2. Converge the arc-hook-pod-template ConfigMap in arc-runners"
# Shared with ../warm-cache/install-warm-cache.sh, which converges the SAME
# ConfigMap for the warm-cache UV_CACHE_DIR the template also carries; one converge
# script so the two installers cannot drift on how it is written.
"${SCRIPT_DIR}/../arc/converge-hook-pod-template.sh"

log "Done. Scale sets mount this ConfigMap and set"
log "ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE — see ../arc/values-livespec-overseer.yaml."

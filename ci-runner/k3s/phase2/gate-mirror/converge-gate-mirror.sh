#!/usr/bin/env bash
# converge-gate-mirror.sh — the one idempotent converge of the gate mirror: the
# BARE MIRROR on the ci-cache tier (host state, survives a boot) and its
# CLUSTER objects (./gate-mirror.yaml: the `gates` Namespace, the gitconfig and
# sweep ConfigMaps, the read-only git daemon Deployment, its Service, and the
# `refs/gates/*` prune CronJob — all of which live in the k3s datastore, which
# is tmpfs and EMPTY on every boot, ../datastore-tmpfs/).
#
# It is the fourth hostPath singleton of the pool, and the first that also
# carries HOST state of its own: ../crates-proxy/, ../sccache/ and
# ../warm-cache/ each converge cluster objects over a directory something else
# created, while this one creates the directory too (./ensure-gate-mirror.sh).
# That is why the tier pre-gate below is fatal rather than a warning — a mirror
# created on an unmounted tier lands on the ROOT VOLUME and is then shadowed,
# invisibly, the moment the tier mounts.
#
# Called on every boot by the reconstruct converge
# (../reconstruct/converge-ci-stack.sh), and by hand after editing
# ./gate-mirror.yaml or ./prune-gate-refs.sh. THE SWEEP SCRIPT IS THE
# CONFIGMAP, not the copy on disk: editing ./prune-gate-refs.sh and re-running
# `install-converge-unit.sh` refreshes the disk copy and changes NOTHING the
# CronJob runs until this converge re-applies the ConfigMap from it
# (CLAUDE.md "Ordering — confirm the reader before you write").
#
# --dry-run PRINTS every command this converge would run, in order, and
# executes NOTHING — no host write (so no mirror is created), no cluster write,
# no cluster read, not even the kubectl and KUBECONFIG preconditions — so it is
# safe to run from a checkout on a machine that is not the node. Each printed
# line comes from the same `run` wrapper that would execute it, so the plan
# cannot drift from the body the way a hand-maintained second copy of it would.
#
# Requires: root (creates the mirror and chowns it to the receive account),
# git, and kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="gates"
# The ci-cache tier, live at /var/cache/ci-runner (../storage-layout/). NEVER
# /var/lib/git — that path belongs to the git package and sits on the root
# volume; ./ensure-gate-mirror.sh's header carries the whole correction, and it
# refuses that path outright.
MIRROR_TIER="${GATE_MIRROR_TIER:-/var/cache/ci-runner}"
MIRROR_DIR="${MIRROR_TIER}/gate-mirror.git"
# The account Tailscale SSH lands the driver host on, and therefore the account
# `git-receive-pack` runs as (./README.md "The receive path"). Overridable
# because it is a HOST fact this repository does not get to pin.
MIRROR_OWNER="${GATE_MIRROR_OWNER:-cwoolley}"
ROLLOUT_TIMEOUT="${GATE_MIRROR_ROLLOUT_TIMEOUT:-120s}"

DRY_RUN=0
usage() { printf 'usage: %s [--dry-run]\n' "$(basename "$0")"; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'FATAL: unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

log() { printf '\n== %s ==\n' "$*"; }
# Print-or-execute: in dry-run the exact argv is shown and NOT run.
run() {
  if [ "${DRY_RUN}" -eq 1 ]; then printf '  would run: %s\n' "$*"; return 0; fi
  "$@"
}
# Same, for the calls whose stdout the converge deliberately discards.
run_quiet() {
  if [ "${DRY_RUN}" -eq 1 ]; then printf '  would run: %s\n' "$*"; return 0; fi
  "$@" >/dev/null
}
# The create-then-apply pipeline is the idempotent create-or-update form; a
# bare `kubectl create` fails on the second run. It cannot go through `run` (a
# pipeline is not an argv), so it gets its own wrapper and prints the whole
# pipeline it would execute.
apply_created() {
  if [ "${DRY_RUN}" -eq 1 ]; then
    printf '  would run: kubectl %s --dry-run=client -o yaml | kubectl apply -f -\n' "$*"
    return 0
  fi
  kubectl "$@" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
}

if [ "${DRY_RUN}" -eq 0 ]; then
  command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
  command -v git >/dev/null || { echo "FATAL: git not found on PATH"; exit 1; }
  : "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"
  [ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (creates ${MIRROR_DIR} and chowns it to ${MIRROR_OWNER})"; exit 1; }
fi

log "gate-mirror 1. Ensure the bare mirror on the ci-cache tier ${MIRROR_DIR}"
# The mirror must land on the TIER, never on the root disk: refuse when the
# tier is not a mountpoint (.ai/ci-node-storage-tiers.md), exactly as
# ../sccache/converge-sccache-redis.sh refuses for its snapshot directory.
if [ "${DRY_RUN}" -eq 1 ]; then
  echo "  would require ${MIRROR_TIER} to be a mountpoint, then run: ensure-gate-mirror.sh --owner ${MIRROR_OWNER} ${MIRROR_DIR}"
else
  if ! findmnt -no TARGET "${MIRROR_TIER}" >/dev/null 2>&1; then
    echo "FATAL: ${MIRROR_TIER} is not a mountpoint; the ci-cache tier is not mounted, refusing to create ${MIRROR_DIR}"
    exit 1
  fi
  "${SCRIPT_DIR}/ensure-gate-mirror.sh" --owner "${MIRROR_OWNER}" "${MIRROR_DIR}"
fi

log "gate-mirror 2. Converge the sweep ConfigMap from ./prune-gate-refs.sh"
# The ConfigMap IS what the CronJob runs; the manifest carries only a refusing
# placeholder. Generated here rather than embedded in the YAML so the sweep is
# one file, shellcheck'd and covered by ./converge-gate-mirror-exit-tests.sh,
# instead of a second copy inside a manifest that drifts from it.
apply_created create namespace "${NAMESPACE}"
apply_created create configmap gate-mirror-prune \
  --namespace "${NAMESPACE}" \
  --from-file="prune-gate-refs.sh=${SCRIPT_DIR}/prune-gate-refs.sh"

log "gate-mirror 3. Apply the Namespace, gitconfig ConfigMap, daemon, Service and prune CronJob"
run kubectl apply -f "${SCRIPT_DIR}/gate-mirror.yaml"
# A changed ConfigMap does not restart the Deployment by itself; stamp the
# manifest's hash onto the pod template so an edit rolls the daemon.
if [ "${DRY_RUN}" -eq 1 ]; then
  echo "  would stamp ci-runner.io/config-hash (sha256 of gate-mirror.yaml, first 16 chars) on the daemon pod template"
else
  conf_hash="$(sha256sum "${SCRIPT_DIR}/gate-mirror.yaml" | cut -c1-16)"
  run_quiet kubectl -n "${NAMESPACE}" patch deployment gate-mirror-daemon --type=merge \
    -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ci-runner.io/config-hash\":\"${conf_hash}\"}}}}}"
fi

log "gate-mirror 4. Wait (bounded, ${ROLLOUT_TIMEOUT}) for the rollout"
if [ "${DRY_RUN}" -eq 1 ]; then
  run kubectl -n "${NAMESPACE}" rollout status deployment/gate-mirror-daemon --timeout="${ROLLOUT_TIMEOUT}"
  echo "DRY RUN: nothing was applied and no mirror was created."
  exit 0
fi
if kubectl -n "${NAMESPACE}" rollout status deployment/gate-mirror-daemon --timeout="${ROLLOUT_TIMEOUT}"; then
  echo "gate mirror served: git://gate-mirror.${NAMESPACE}.svc.cluster.local/gate-mirror.git (read-only)"
else
  echo "WARN: gate-mirror-daemon rollout not complete after ${ROLLOUT_TIMEOUT}; no gate can fetch its tree until it is Ready (kubectl -n ${NAMESPACE} get pods)"
fi

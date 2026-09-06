#!/usr/bin/env bash
# converge-sccache-redis.sh — the one idempotent converge of the shared
# compilation cache's CLUSTER objects: the writer credential (host-held),
# the ACL Secret, the `sccache-redis-writer` Secret the populator reads, and
# ./sccache-redis.yaml (Namespace, Deployment, Service). Applies, waits
# briefly for the rollout, and exits.
#
# Called on every boot by the reconstruct converge
# (../reconstruct/converge-ci-stack.sh) — the k3s datastore is tmpfs and EMPTY
# on every boot (../datastore-tmpfs/), and the cache itself is RAM-resident,
# so a boot brings back an empty redis that the next populate refills — and
# by hand after editing the manifest.
#
# THE WRITER CREDENTIAL lives on the host at $WRITER_PASS_FILE (root, 0600),
# generated here on first run. It is host-local machine state like the
# credstore, NOT a fleet secret: it authorizes writes into a regenerable cache
# on this one host, so rotating it is `rm` + re-converge + one populate. It is
# projected into exactly one place a workload can read: the
# `sccache-redis-writer` Secret in the populator's namespace. Nothing in
# arc-runners (where workflow pods live) can read it.
#
# --dry-run PRINTS every command this converge would run, in order, and
# executes NOTHING — no host write (so no credential is generated and no
# snapshot directory is created), no cluster write, no cluster read, and not
# even the root / kubectl / KUBECONFIG preconditions — so it is safe to run
# from a checkout on a machine that is not the node (two-node precondition
# work; plan k3s-on-gmktec-for-vps-usage, carrier R3). Each printed line comes
# from the same `run` wrapper that would execute it, so the plan cannot drift
# from the body the way a hand-maintained second copy of it would.
#
# Requires: root (the credential file), kubectl with KUBECONFIG set.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="ci-sccache"
POPULATOR_NAMESPACE="ci-warm-cache"
WRITER_USER="sccache-writer"
WRITER_PASS_FILE="${SCCACHE_WRITER_PASS_FILE:-/etc/ci-runner/sccache-redis-writer.pass}"
ROLLOUT_TIMEOUT="${SCCACHE_REDIS_ROLLOUT_TIMEOUT:-120s}"
SNAPSHOT_TIER="${SCCACHE_SNAPSHOT_TIER:-/var/cache/ci-runner}"
SNAPSHOT_DIR="${SNAPSHOT_TIER}/sccache-redis"

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
# bare `kubectl create` fails on the second run. It cannot go through `run`
# (a pipeline is not an argv), so it gets its own wrapper and prints the whole
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
  : "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"
  [ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (reads/creates ${WRITER_PASS_FILE})"; exit 1; }
fi

log "sccache-redis 1. Ensure the host-held writer credential ${WRITER_PASS_FILE}"
if [ "${DRY_RUN}" -eq 1 ]; then
  echo "  would ensure ${WRITER_PASS_FILE} (0600 root, generated from /dev/urandom on first run)"
  # A placeholder, never a read of the real credential: dry-run must not open
  # a root-only file, and the value is only used to render the ACL below.
  writer_pass="<the host-held writer credential>"
elif [ ! -s "${WRITER_PASS_FILE}" ]; then
  install -d -m 0755 "$(dirname "${WRITER_PASS_FILE}")"
  (umask 077; head -c 48 /dev/urandom | base64 | tr -d '\n=/+' | head -c 48 > "${WRITER_PASS_FILE}")
  chmod 0600 "${WRITER_PASS_FILE}"
  echo "generated a new writer credential (the cache is regenerable; nothing to migrate)"
  writer_pass="$(cat "${WRITER_PASS_FILE}")"
else
  echo "present"
  writer_pass="$(cat "${WRITER_PASS_FILE}")"
fi

log "sccache-redis 1b. Ensure the snapshot directory on the ci-cache tier ${SNAPSHOT_DIR}"
# The dump must land on the tier, never on the root disk: refuse when the
# tier is not a mountpoint (.ai/ci-node-storage-tiers.md). Owner 999:1000 is
# the pod's runAsUser/runAsGroup; hostPath ignores fsGroup.
if [ "${DRY_RUN}" -eq 1 ]; then
  echo "  would require ${SNAPSHOT_TIER} to be a mountpoint, then run: install -d -o 999 -g 1000 -m 0750 ${SNAPSHOT_DIR}"
else
  if ! findmnt -no TARGET "${SNAPSHOT_TIER}" >/dev/null 2>&1; then
    echo "FATAL: ${SNAPSHOT_TIER} is not a mountpoint; the ci-cache tier is not mounted, refusing to create ${SNAPSHOT_DIR}"
    exit 1
  fi
  install -d -o 999 -g 1000 -m 0750 "${SNAPSHOT_DIR}"
  if [ -s "${SNAPSHOT_DIR}/dump.rdb" ]; then
    echo "present; last snapshot $(stat -c '%y %s bytes' "${SNAPSHOT_DIR}/dump.rdb")"
  else
    echo "present; no snapshot yet (the first save lands within five minutes of the first write)"
  fi
fi

log "sccache-redis 2. Render the ACL file and converge both Secrets"
apply_created create namespace "${NAMESPACE}"
# default: unauthenticated = READ-ONLY (what every job pod connects as), plus
# INFO so the host gauges (livespec-dev-tooling-gjqw2i) can read hit/miss and
# memory counters without a credential — INFO is @dangerous only because it
# is @slow; it exposes no data. writer: the populator only. `-@all` first,
# then the allowed categories.
if [ "${DRY_RUN}" -eq 1 ]; then
  # No ACL is rendered: it embeds the writer credential, which dry-run never
  # read, so its hash would be a fabrication rather than the value the real
  # run stamps.
  acl_file="<the rendered ACL, in a 0600 mktemp>"
  acl_hash="<sha256 of the rendered ACL, first 16 chars>"
  echo "  would render ${acl_file}: default = nopass read-only + info, ${WRITER_USER} = read/write/keyspace/bgsave"
else
  acl_file="$(mktemp)"
  trap 'rm -f "${acl_file}"' EXIT
  (umask 077; cat > "${acl_file}" <<ACL
user default on nopass ~* &* -@all +@read +@connection +info
user ${WRITER_USER} on >${writer_pass} ~* &* -@all +@read +@write +@keyspace +@connection +bgsave
ACL
)
  acl_hash="$(sha256sum "${acl_file}" | cut -c1-16)"
fi
apply_created create secret generic sccache-redis-acl \
  --namespace "${NAMESPACE}" \
  --from-file="users.acl=${acl_file}"
apply_created create namespace "${POPULATOR_NAMESPACE}"
apply_created create secret generic sccache-redis-writer \
  --namespace "${POPULATOR_NAMESPACE}" \
  --from-literal="username=${WRITER_USER}" \
  --from-literal="password=${writer_pass}"
[ "${DRY_RUN}" -eq 1 ] || echo "secrets converged: ${NAMESPACE}/sccache-redis-acl, ${POPULATOR_NAMESPACE}/sccache-redis-writer"

log "sccache-redis 3. Apply the Namespace, Deployment and Service"
run kubectl apply -f "${SCRIPT_DIR}/sccache-redis.yaml"
# A changed ACL Secret does not restart the Deployment by itself; stamp the
# ACL's hash onto the pod template so a credential rotation rolls the pod.
run_quiet kubectl -n "${NAMESPACE}" patch deployment sccache-redis --type=merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ci-runner.io/acl-hash\":\"${acl_hash}\"}}}}}"

log "sccache-redis 4. Wait (bounded, ${ROLLOUT_TIMEOUT}) for the rollout"
if [ "${DRY_RUN}" -eq 1 ]; then
  run kubectl -n "${NAMESPACE}" rollout status deployment/sccache-redis --timeout="${ROLLOUT_TIMEOUT}"
  echo "DRY RUN: nothing was applied."
  exit 0
fi
if kubectl -n "${NAMESPACE}" rollout status deployment/sccache-redis --timeout="${ROLLOUT_TIMEOUT}"; then
  echo "sccache-redis ready: sccache-redis.${NAMESPACE}.svc.cluster.local:6379 (pods, read-only), hostPort 6379 (node)"
  pod="$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=sccache-redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
  if [ -n "${pod}" ]; then
    echo "persistence (INFO): $(kubectl -n "${NAMESPACE}" exec "${pod}" -- redis-cli INFO persistence 2>/dev/null | grep -E '^(rdb_last_save_time|rdb_changes_since_last_save|rdb_last_bgsave_status|loading):' | tr -d '\r' | paste -sd' ')"
    echo "keys restored from ${SNAPSHOT_DIR}/dump.rdb: $(kubectl -n "${NAMESPACE}" exec "${pod}" -- redis-cli DBSIZE 2>/dev/null | tr -d '\r')"
  fi
else
  echo "WARN: sccache-redis rollout not complete after ${ROLLOUT_TIMEOUT}; jobs compile without the cache until it is Ready (kubectl -n ${NAMESPACE} get pods)"
fi

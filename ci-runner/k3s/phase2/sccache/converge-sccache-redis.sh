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

log() { printf '\n== %s ==\n' "$*"; }

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"
[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (reads/creates ${WRITER_PASS_FILE})"; exit 1; }

log "sccache-redis 1. Ensure the host-held writer credential ${WRITER_PASS_FILE}"
if [ ! -s "${WRITER_PASS_FILE}" ]; then
  install -d -m 0755 "$(dirname "${WRITER_PASS_FILE}")"
  (umask 077; head -c 48 /dev/urandom | base64 | tr -d '\n=/+' | head -c 48 > "${WRITER_PASS_FILE}")
  chmod 0600 "${WRITER_PASS_FILE}"
  echo "generated a new writer credential (the cache is regenerable; nothing to migrate)"
else
  echo "present"
fi
writer_pass="$(cat "${WRITER_PASS_FILE}")"

log "sccache-redis 1b. Ensure the snapshot directory on the ci-cache tier ${SNAPSHOT_DIR}"
# The dump must land on the tier, never on the root disk: refuse when the
# tier is not a mountpoint (.ai/ci-node-storage-tiers.md). Owner 999:1000 is
# the pod's runAsUser/runAsGroup; hostPath ignores fsGroup.
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

log "sccache-redis 2. Render the ACL file and converge both Secrets"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
# default: unauthenticated = READ-ONLY (what every job pod connects as), plus
# INFO so the host gauges (livespec-dev-tooling-gjqw2i) can read hit/miss and
# memory counters without a credential — INFO is @dangerous only because it
# is @slow; it exposes no data. writer: the populator only. `-@all` first,
# then the allowed categories.
acl_file="$(mktemp)"
trap 'rm -f "${acl_file}"' EXIT
(umask 077; cat > "${acl_file}" <<ACL
user default on nopass ~* &* -@all +@read +@connection +info
user ${WRITER_USER} on >${writer_pass} ~* &* -@all +@read +@write +@keyspace +@connection +bgsave
ACL
)
kubectl create secret generic sccache-redis-acl \
  --namespace "${NAMESPACE}" \
  --from-file="users.acl=${acl_file}" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl create namespace "${POPULATOR_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl create secret generic sccache-redis-writer \
  --namespace "${POPULATOR_NAMESPACE}" \
  --from-literal="username=${WRITER_USER}" \
  --from-literal="password=${writer_pass}" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
echo "secrets converged: ${NAMESPACE}/sccache-redis-acl, ${POPULATOR_NAMESPACE}/sccache-redis-writer"

log "sccache-redis 3. Apply the Namespace, Deployment and Service"
kubectl apply -f "${SCRIPT_DIR}/sccache-redis.yaml"
# A changed ACL Secret does not restart the Deployment by itself; stamp the
# ACL's hash onto the pod template so a credential rotation rolls the pod.
acl_hash="$(sha256sum "${acl_file}" | cut -c1-16)"
kubectl -n "${NAMESPACE}" patch deployment sccache-redis --type=merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ci-runner.io/acl-hash\":\"${acl_hash}\"}}}}}" >/dev/null

log "sccache-redis 4. Wait (bounded, ${ROLLOUT_TIMEOUT}) for the rollout"
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

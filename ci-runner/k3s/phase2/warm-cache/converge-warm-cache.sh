#!/usr/bin/env bash
# converge-warm-cache.sh — the one idempotent converge of the warm uv cache's
# CLUSTER objects: the `ci-warm-cache` Namespace + CronJob
# (./warm-cache-cronjob.yaml), the `warm-cache-repos` ConfigMap derived from
# the ARC values files, and the `warm-cache-populate` script ConfigMap
# converged from ./warm-cache-populate.sh. Applies and exits; it runs NO
# populate Job and waits for nothing.
#
# WHY SPLIT OUT OF install-warm-cache.sh: those objects live in the k3s
# datastore, which is tmpfs and EMPTY on every boot (../datastore-tmpfs/).
# After the 2026-09-02 reboot the CronJob was simply gone — workflow pods
# kept reading the on-disk lower, but nothing refreshed it. The
# reconstruct-on-boot converge (../reconstruct/converge-ci-stack.sh) now
# calls THIS script on every boot; install-warm-cache.sh calls it too and
# then adds the attended parts (one immediate populate Job, waited for, and
# the hook-template converge) that a boot unit must not block on.
#
# Layout-agnostic like the converge: the ARC values files are read from
# WARM_CACHE_VALUES_DIR if set, else ../arc beside this directory (the repo
# layout and the /usr/local/lib/ci-runner-k3s installed layout both satisfy
# that).
#
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="ci-warm-cache"
VALUES_DIR="${WARM_CACHE_VALUES_DIR:-${SCRIPT_DIR}/../arc}"
WARM_CACHE_IMAGE="${WARM_CACHE_IMAGE:-}"

log() { printf '\n== %s ==\n' "$*"; }

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"
[ -d "$VALUES_DIR" ] || { echo "FATAL: ARC values dir not found: ${VALUES_DIR}"; exit 1; }

# ---------------------------------------------------------------------------
log "warm-cache 1. Derive the routed-repository list from ${VALUES_DIR}/values-*.yaml"
repos_file="$(mktemp)"
trap 'rm -f "${repos_file}"' EXIT
# values-EXAMPLE-repo.yaml is the template (its URL carries a <REPO>
# placeholder); everything else is a live scale set. The host-unique proof
# set (values-poweredge-xubuntu-k3s.yaml) points at livespec-dev-tooling,
# which its own per-repo file already names — hence the sort -u.
grep -h '^githubConfigUrl:' "${VALUES_DIR}"/values-*.yaml \
  | sed -E 's/^githubConfigUrl: *"?([^" ]+)"?.*/\1/' \
  | grep -v '<' \
  | sort -u > "${repos_file}"
repo_count="$(grep -c . "${repos_file}")"
[ "${repo_count}" -gt 0 ] || { echo "FATAL: no githubConfigUrl found under ${VALUES_DIR}"; exit 1; }
echo "${repo_count} repositories:"
sed 's/^/  /' "${repos_file}"

# ---------------------------------------------------------------------------
log "warm-cache 2. Apply the Namespace + CronJob and converge both ConfigMaps"
kubectl apply -f "${SCRIPT_DIR}/warm-cache-cronjob.yaml"
kubectl create configmap warm-cache-repos \
  --namespace "${NAMESPACE}" \
  --from-file="repos.txt=${repos_file}" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap warm-cache-populate \
  --namespace "${NAMESPACE}" \
  --from-file="warm-cache-populate.sh=${SCRIPT_DIR}/warm-cache-populate.sh" \
  --dry-run=client -o yaml | kubectl apply -f -
if [ -n "${WARM_CACHE_IMAGE}" ]; then
  kubectl -n "${NAMESPACE}" patch cronjob warm-cache-populate --type=json \
    -p "[{\"op\":\"replace\",\"path\":\"/spec/jobTemplate/spec/template/spec/containers/0/image\",\"value\":\"${WARM_CACHE_IMAGE}\"}]"
fi

log "warm-cache converged: namespace ${NAMESPACE}, CronJob warm-cache-populate, ${repo_count} repositories."

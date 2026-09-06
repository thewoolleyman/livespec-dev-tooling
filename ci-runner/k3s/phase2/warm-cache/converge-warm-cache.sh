#!/usr/bin/env bash
# converge-warm-cache.sh — the one idempotent converge of the warm uv cache's
# CLUSTER objects: the PyPI files proxy (./pypi-proxy/pypi-proxy.yaml —
# Deployment, Service, nginx ConfigMap; the populator builds every generation
# through it), the `ci-warm-cache` Namespace + budget ConfigMap + CronJob
# (./warm-cache-cronjob.yaml), the `warm-cache-repos` ConfigMap derived from
# the ARC values files, and the `warm-cache-populate` script ConfigMap
# converged from ./warm-cache-populate.sh AND ./verify-uv-cache.py (with its
# ./uv_cache_layout.py). Applies
# and exits; it runs NO populate Job and waits only (bounded) for the proxy's
# rollout, which a boot converge must not be held hostage by — a proxy that
# is not yet Ready only makes the next rebuild fetch from PyPI directly.
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
PYPI_PROXY_ROLLOUT_TIMEOUT="${PYPI_PROXY_ROLLOUT_TIMEOUT:-120s}"

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
log "warm-cache 2. Apply the PyPI files proxy (Namespace, nginx ConfigMap, Deployment, Service)"
# Before the CronJob: the populator's next rebuild fetches through it. A
# changed ConfigMap does not restart the Deployment by itself; stamp the
# manifest's hash onto the pod template so a config edit rolls the pod
# (../crates-proxy/converge-crates-proxy.sh does the same).
kubectl apply -f "${SCRIPT_DIR}/pypi-proxy/pypi-proxy.yaml"
proxy_hash="$(sha256sum "${SCRIPT_DIR}/pypi-proxy/pypi-proxy.yaml" | cut -c1-16)"
kubectl -n "${NAMESPACE}" patch deployment pypi-proxy --type=merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ci-runner.io/config-hash\":\"${proxy_hash}\"}}}}}" >/dev/null
if kubectl -n "${NAMESPACE}" rollout status deployment/pypi-proxy --timeout="${PYPI_PROXY_ROLLOUT_TIMEOUT}"; then
  echo "pypi-proxy ready: pypi-proxy.${NAMESPACE}.svc.cluster.local:8081"
else
  echo "WARN: pypi-proxy rollout not complete after ${PYPI_PROXY_ROLLOUT_TIMEOUT}; the populator builds direct from PyPI until it is Ready (kubectl -n ${NAMESPACE} get pods)"
fi

# ---------------------------------------------------------------------------
log "warm-cache 3. Apply the budget ConfigMap + CronJob and converge the repos and script ConfigMaps"
kubectl apply -f "${SCRIPT_DIR}/warm-cache-cronjob.yaml"
kubectl create configmap warm-cache-repos \
  --namespace "${NAMESPACE}" \
  --from-file="repos.txt=${repos_file}" \
  --dry-run=client -o yaml | kubectl apply -f -
# The populator AND its verifier (the CLI plus the layout module it imports
# from its own directory), one ConfigMap mounted at /scripts.
kubectl create configmap warm-cache-populate \
  --namespace "${NAMESPACE}" \
  --from-file="warm-cache-populate.sh=${SCRIPT_DIR}/warm-cache-populate.sh" \
  --from-file="verify-uv-cache.py=${SCRIPT_DIR}/verify-uv-cache.py" \
  --from-file="uv_cache_layout.py=${SCRIPT_DIR}/uv_cache_layout.py" \
  --dry-run=client -o yaml | kubectl apply -f -
if [ -n "${WARM_CACHE_IMAGE}" ]; then
  kubectl -n "${NAMESPACE}" patch cronjob warm-cache-populate --type=json \
    -p "[{\"op\":\"replace\",\"path\":\"/spec/jobTemplate/spec/template/spec/containers/0/image\",\"value\":\"${WARM_CACHE_IMAGE}\"}]"
fi

log "warm-cache converged: namespace ${NAMESPACE}, pypi-proxy, budget ConfigMap, CronJob warm-cache-populate (+ verifier), ${repo_count} repositories."

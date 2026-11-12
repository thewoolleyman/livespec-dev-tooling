#!/usr/bin/env bash
# converge-warm-cache.sh — the one idempotent converge of the warm uv cache's
# CLUSTER objects: the PyPI files proxy (./pypi-proxy/pypi-proxy.yaml —
# Deployment, Service, nginx ConfigMap; the populator builds every generation
# through it), the `ci-warm-cache` Namespace + budget ConfigMap + carrier
# CronJob + per-workvol uv DaemonSet (./warm-cache-cronjob.yaml), the
# `warm-cache-repos` ConfigMap derived from
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
# --dry-run PRINTS every command this converge would run, in order, and
# executes NOTHING against the cluster — no write, no read, and not even the
# kubectl and KUBECONFIG preconditions — so it is safe to run from a checkout
# on a machine that is not the node (two-node precondition work; plan
# k3s-on-gmktec-for-vps-usage, carrier R3). It DOES still derive the routed
# repository list, because that reads only the values files beside it and the
# list is the most useful thing a plan can show. Each printed line comes from
# the same `run` wrapper that would execute it, so the plan cannot drift from
# the body the way a hand-maintained second copy of it would.
#
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="ci-warm-cache"
VALUES_DIR="${WARM_CACHE_VALUES_DIR:-${SCRIPT_DIR}/../arc}"
WARM_CACHE_IMAGE="${WARM_CACHE_IMAGE:-}"
PYPI_PROXY_ROLLOUT_TIMEOUT="${PYPI_PROXY_ROLLOUT_TIMEOUT:-120s}"

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
  kubectl "$@" --dry-run=client -o yaml | kubectl apply -f -
}

if [ "${DRY_RUN}" -eq 0 ]; then
  command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
  : "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"
fi
[ -d "$VALUES_DIR" ] || { echo "FATAL: ARC values dir not found: ${VALUES_DIR}"; exit 1; }

# ---------------------------------------------------------------------------
log "warm-cache 1. Derive the routed-repository list from ${VALUES_DIR}/values-*.yaml"
repos_file="$(mktemp)"
trap 'rm -f "${repos_file}"' EXIT
# values-EXAMPLE-repo.yaml is the template (its URL carries a <REPO>
# placeholder); everything else is a live scale set. The host-unique proof
# set (values-poweredge-xubuntu-k3s.yaml) points at livespec-dev-tooling,
# which its own per-repo file already names — hence the sort -u.
#
# A values file carrying the line `# warm-cache: exclude` is NOT a populator
# target. values-fabro.yaml opts out (2026-11-05, bd-ib-dqxcsh): its cold
# Rust workspace build fills ~98 GiB and would run inside the populator's
# single 3600 s CronJob deadline ahead of the console's sccache refresh, so an
# overrun would starve every other repository's warm cache. Its own runner
# volume is the cache that lane relies on.
for values_file in "${VALUES_DIR}"/values-*.yaml; do
  grep -q '^# warm-cache: exclude$' "${values_file}" && continue
  grep -h '^githubConfigUrl:' "${values_file}"
done \
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
run kubectl apply -f "${SCRIPT_DIR}/pypi-proxy/pypi-proxy.yaml"
proxy_hash="$(sha256sum "${SCRIPT_DIR}/pypi-proxy/pypi-proxy.yaml" | cut -c1-16)"
run_quiet kubectl -n "${NAMESPACE}" patch deployment pypi-proxy --type=merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ci-runner.io/config-hash\":\"${proxy_hash}\"}}}}}"
if [ "${DRY_RUN}" -eq 1 ]; then
  run kubectl -n "${NAMESPACE}" rollout status deployment/pypi-proxy --timeout="${PYPI_PROXY_ROLLOUT_TIMEOUT}"
elif kubectl -n "${NAMESPACE}" rollout status deployment/pypi-proxy --timeout="${PYPI_PROXY_ROLLOUT_TIMEOUT}"; then
  echo "pypi-proxy ready: pypi-proxy.${NAMESPACE}.svc.cluster.local:8081"
else
  echo "WARN: pypi-proxy rollout not complete after ${PYPI_PROXY_ROLLOUT_TIMEOUT}; the populator builds direct from PyPI until it is Ready (kubectl -n ${NAMESPACE} get pods)"
fi

# ---------------------------------------------------------------------------
log "warm-cache 3. Apply the budget ConfigMap + CronJob and converge the repos and script ConfigMaps"
run kubectl apply -f "${SCRIPT_DIR}/warm-cache-cronjob.yaml"
run kubectl apply -f "${SCRIPT_DIR}/warm-cache-fabro-cronjob.yaml"
# The two warm uv DaemonSets (warm-uv-cache-populate, warm-uv-cache-populate-hp)
# read warm-cache-budget as configMapKeyRef env, which is fixed at pod start, and
# their while-sleep loop never restarts — so a budget raise in the ConfigMap
# reached neither of them (livespec-dev-tooling-gry6tq, 2026-11-11: both kept
# refusing on the old 20000-file budget while the carrier CronJob published on
# the new one). Stamp the hash of the LIVE ConfigMap's .data onto both pod
# templates so a budget change rolls them.
#
# The hash covers .data alone, not the manifest file: a comment-only or
# CronJob-only edit to warm-cache-cronjob.yaml must not roll both DaemonSets and
# start an immediate populate on every node. An unchanged hash is a no-op merge
# patch, so the roll is idempotent. It is deliberately NOT gated on apply's
# "configured" output either: a run that died between the apply and this patch
# would otherwise lose the roll for good. Killing a populate mid-generation is
# safe — a generation is published only by an atomic symlink rename, and an
# unpublished directory is pruned by the next run's KEEP_GENERATIONS sweep.
#
# kubectl prints a jsonpath map as JSON with sorted keys, so the hash is stable.
if [ "${DRY_RUN}" -eq 1 ]; then
  budget_hash="<sha256-16 of live warm-cache-budget .data>"
else
  budget_hash="$(kubectl -n "${NAMESPACE}" get configmap warm-cache-budget -o jsonpath='{.data}' | sha256sum | cut -c1-16)"
fi
for budget_ds in warm-uv-cache-populate warm-uv-cache-populate-hp; do
  run_quiet kubectl -n "${NAMESPACE}" patch daemonset "${budget_ds}" --type=merge \
    -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ci-runner.io/budget-hash\":\"${budget_hash}\"}}}}}"
done
apply_created create configmap warm-cache-repos \
  --namespace "${NAMESPACE}" \
  --from-file="repos.txt=${repos_file}"
# The populator AND its verifier (the CLI plus the layout module it imports
# from its own directory), one ConfigMap mounted at /scripts.
apply_created create configmap warm-cache-populate \
  --namespace "${NAMESPACE}" \
  --from-file="warm-cache-populate.sh=${SCRIPT_DIR}/warm-cache-populate.sh" \
  --from-file="sccache-warm-lag.py=${SCRIPT_DIR}/sccache-warm-lag.py" \
  --from-file=warm-cache-fabro-populate.sh=${SCRIPT_DIR}/warm-cache-fabro-populate.sh \
  --from-file="verify-uv-cache.py=${SCRIPT_DIR}/verify-uv-cache.py" \
  --from-file="uv_cache_layout.py=${SCRIPT_DIR}/uv_cache_layout.py"
if [ -n "${WARM_CACHE_IMAGE}" ]; then
  run kubectl -n "${NAMESPACE}" patch cronjob warm-cache-populate --type=json \
    -p "[{\"op\":\"replace\",\"path\":\"/spec/jobTemplate/spec/template/spec/containers/0/image\",\"value\":\"${WARM_CACHE_IMAGE}\"}]"
fi

if [ "${DRY_RUN}" -eq 1 ]; then
  echo "DRY RUN: nothing was applied."
  exit 0
fi
log "warm-cache converged: namespace ${NAMESPACE}, pypi-proxy, budget ConfigMap, CronJobs warm-cache-populate and warm-cache-populate-fabro, ${repo_count} regular repositories."

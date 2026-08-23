#!/usr/bin/env bash
# install-warm-cache.sh — idempotently install the warm uv cache tier (tier 1
# of the cache tiers in the livespec repo's
# plan/fleet-ci-runner-pool/research/design.md, re-scoped to the k3s/ARC lane
# under livespec-s43svm.2) on the k3s cluster, and converge the hook pod
# template that makes workflow pods read it.
#
# Three steps, all cluster objects (nothing node-local — the host path is
# created by the hostPath mounts' DirectoryOrCreate on first use):
#
#   1. Generate the `warm-cache-repos` ConfigMap from ../arc/values-*.yaml:
#      every `githubConfigUrl` of a per-repository scale set, de-duplicated.
#      That is the live set of repositories routed to this pool, so the
#      populator warms exactly the lockfiles this pool's jobs resolve and no
#      hand-maintained second list can drift from the routing.
#   2. Apply warm-cache-cronjob.yaml and converge its script ConfigMap from
#      ./warm-cache-populate.sh, then run ONE populate Job immediately and
#      wait for it, so the lower exists before the first workflow pod looks
#      for it rather than up to a schedule interval later.
#   3. Converge the arc-hook-pod-template ConfigMap (../arc/hook-pod-template.yaml
#      carries the read-only mount, the postStart copy, and UV_CACHE_DIR), via
#      the converge script shared with ../apparmor/install-apparmor-profile.sh.
#      Existing runner pods keep the previous template until recycled — run
#      ../arc/recycle-scale-set-runners.sh per scale set afterwards, exactly as
#      after any values change.
#
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="ci-warm-cache"
VALUES_DIR="${SCRIPT_DIR}/../arc"
WARM_CACHE_IMAGE="${WARM_CACHE_IMAGE:-}"
INITIAL_RUN_TIMEOUT="${INITIAL_RUN_TIMEOUT:-900s}"

log() { printf '\n== %s ==\n' "$*"; }

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"

# ---------------------------------------------------------------------------
log "1. Derive the routed-repository list from ${VALUES_DIR}/values-*.yaml"
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
log "2. Apply the CronJob, converge its ConfigMaps, run one populate now"
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

# One immediate run, named uniquely so re-running this installer never
# collides with a previous manual run still being retained by history.
job_name="warm-cache-populate-install-$(date -u +%Y%m%d%H%M%S)"
kubectl -n "${NAMESPACE}" create job "${job_name}" --from=cronjob/warm-cache-populate
echo "waiting up to ${INITIAL_RUN_TIMEOUT} for ${job_name} ..."
if ! kubectl -n "${NAMESPACE}" wait --for=condition=complete "job/${job_name}" --timeout="${INITIAL_RUN_TIMEOUT}"; then
  echo "FATAL: initial populate did not complete; its log:"
  kubectl -n "${NAMESPACE}" logs "job/${job_name}" --tail=100 || true
  exit 1
fi
kubectl -n "${NAMESPACE}" logs "job/${job_name}" | tail -5

# ---------------------------------------------------------------------------
log "3. Converge the arc-hook-pod-template ConfigMap (read-only mount + postStart copy)"
"${SCRIPT_DIR}/../arc/converge-hook-pod-template.sh"

log "Done. Recycle each scale set's idle runners (../arc/recycle-scale-set-runners.sh)"
log "so new workflow pods are created from the converged template."

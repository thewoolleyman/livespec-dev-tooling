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
#   1. Converge the CLUSTER objects via ./converge-warm-cache.sh — the PyPI
#      files proxy (./pypi-proxy/) the populator builds every generation
#      through, the `warm-cache-repos` ConfigMap derived from ../arc/values-*.yaml (every
#      `githubConfigUrl` of a per-repository scale set, de-duplicated: the
#      live set of repositories routed to this pool, so the populator warms
#      exactly the lockfiles this pool's jobs resolve and no hand-maintained
#      second list can drift from the routing), the Namespace + CronJob from
#      warm-cache-cronjob.yaml (with the `warm-cache-budget` ConfigMap), and
#      the script ConfigMap from ./warm-cache-populate.sh plus
#      ./verify-uv-cache.py. That converge is ALSO what the
#      reconstruct-on-boot path runs every boot (the datastore is tmpfs and
#      these objects are wiped with it); this installer is the attended
#      superset.
#   2. Run ONE populate Job immediately and wait for it, so the lower exists
#      before the first workflow pod looks for it rather than up to a
#      schedule interval later.
#   3. Converge the arc-hook-pod-template ConfigMap (../arc/hook-pod-template.yaml
#      carries UV_CACHE_DIR, pointing uv at the seed the local-path
#      provisioner's setup script makes at volume creation), via the converge
#      script shared with ../apparmor/install-apparmor-profile.sh. Existing
#      runner pods keep the previous template until recycled — run
#      ../arc/recycle-scale-set-runners.sh per scale set afterwards, exactly as
#      after any values change.
#
# The seed itself (the reader side of this tier) lives in
# ../local-path-provisioner/local-path-provisioner.yaml and is applied by
# ../reconstruct/converge-ci-stack.sh on every boot; this installer does not
# touch it. README.md "Where it lives, and why it moved".
#
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="ci-warm-cache"
INITIAL_RUN_TIMEOUT="${INITIAL_RUN_TIMEOUT:-900s}"

log() { printf '\n== %s ==\n' "$*"; }

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"

# ---------------------------------------------------------------------------
log "1. Converge the cluster objects (Namespace, CronJob, both ConfigMaps)"
# WARM_CACHE_IMAGE, if set, is honoured by the converge (it patches the
# CronJob's image); WARM_CACHE_VALUES_DIR defaults to ../arc there.
"${SCRIPT_DIR}/converge-warm-cache.sh"

# ---------------------------------------------------------------------------
log "2. Run one populate now and wait for it"
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
log "3. Converge the arc-hook-pod-template ConfigMap (UV_CACHE_DIR -> the provisioner-made seed)"
"${SCRIPT_DIR}/../arc/converge-hook-pod-template.sh"

log "Done. Recycle each scale set's idle runners (../arc/recycle-scale-set-runners.sh)"
log "so new workflow pods are created from the converged template."

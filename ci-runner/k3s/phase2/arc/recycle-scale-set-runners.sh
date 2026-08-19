#!/usr/bin/env bash
# recycle-scale-set-runners.sh — delete a scale set's IDLE runner pods after a
# `helm upgrade`, so no runner keeps serving the pre-upgrade configuration and
# no registration issued against the old listener survives into the new one.
#
# WHY THIS IS PART OF THE UPGRADE, not a separate chore: `helm upgrade` on a
# `gha-runner-scale-set` release replaces the LISTENER, but existing runner
# pods are not owned by the values you just changed — a runner that was already
# Running keeps running, still registered against the previous listener session
# and still configured from the previous pod template. Two consequences, one
# obvious and one not:
#
#   1. The obvious one: the upgrade you just applied is not actually in effect
#      on those pods. `livespec-s43svm.25`'s AppArmor rollout had to watch a
#      green run per release precisely because a values change reaches only
#      pods created after it.
#
#   2. The one that cost real time: a runner whose registration is invalidated
#      server-side does NOT exit. It loops on `Registration <uuid> was not
#      found` forever while staying `Running` and `ready=true`, which makes ARC
#      count it as live capacity and suppress the scale-up that would replace
#      it — see ../wedged-runner/scan-wedged-runners.sh. A re-cut is one of the
#      events that can strand a registration that way.
#
# SCOPE — READ THIS. This closes the re-cut path into the wedged state; it is
# NOT a fix for the wedged state generally. Both wedges observed on 2026-08-19
# were created roughly an hour AFTER the last re-cut, so a recycled upgrade
# would not have prevented them. The detector in ../wedged-runner/ is the
# load-bearing half; this script removes one known way in, and the trigger for
# the rest is still open (livespec-s43svm.30).
#
# IDLE ONLY, and deliberately so. A runner pod with a live `<pod>-workflow`
# companion is executing somebody's job; deleting it fails that job. This
# script skips those and reports them, so recycling after an upgrade is safe to
# run unconditionally — the skipped pods drain on their own, because scale-set
# runner pods are ephemeral and retire after one job.
#
# Requires: kubectl and a KUBECONFIG for the k3s cluster.
set -euo pipefail

USAGE="usage: recycle-scale-set-runners.sh SCALE_SET_NAME [--namespace NS]
  (SCALE_SET_NAME is the live Helm release / AutoscalingRunnerSet name, e.g.
   livespec-overseer-k3s -- see ../README.md 'Applying a scale set's values'
   for the release-to-values-file mapping)"

SCALE_SET="${1:?$USAGE}"
shift
NAMESPACE="arc-runners"
while [ $# -gt 0 ]; do
  case "$1" in
    --namespace) NAMESPACE="${2:?$USAGE}"; shift 2 ;;
    -h|--help)   echo "$USAGE"; exit 0 ;;
    *)           echo "FATAL: unknown argument '$1'"$'\n'"$USAGE" >&2; exit 2 ;;
  esac
done

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH" >&2; exit 2; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"

log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
log "1. Enumerate runner pods belonging to scale set ${SCALE_SET}"
PODS="$(kubectl get pods -n "$NAMESPACE" \
  -l "app.kubernetes.io/component=runner,actions.github.com/scale-set-name=${SCALE_SET}" \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')"

if [ -z "$PODS" ]; then
  log "No runner pods for ${SCALE_SET}. Nothing to recycle -- an idle scale set runs min-runners: 0, so this is the normal case."
  exit 0
fi
printf '%s\n' "$PODS" | sed 's/^/  /'

# ---------------------------------------------------------------------------
log "2. Delete the idle ones; skip any pod that is executing a job"
BUSY=0
while read -r name; do
  [ -n "$name" ] || continue
  if kubectl get pod -n "$NAMESPACE" "${name}-workflow" >/dev/null 2>&1; then
    echo "  SKIP ${name}: live ${name}-workflow companion -- it is running a job and will retire on its own"
    BUSY=$(( BUSY + 1 ))
    continue
  fi
  kubectl delete pod -n "$NAMESPACE" "$name" --wait=false
done <<< "$PODS"

# ---------------------------------------------------------------------------
# The deletes above are `--wait=false`, so a pod deleted a moment ago can still
# appear here while it terminates. What this listing establishes is which pods
# were LEFT ALONE, not that the deleted ones are already gone.
log "3. Verify what remains (a just-deleted pod may still show while terminating)"
kubectl get pods -n "$NAMESPACE" \
  -l "app.kubernetes.io/component=runner,actions.github.com/scale-set-name=${SCALE_SET}" \
  -o custom-columns=NAME:.metadata.name,PHASE:.status.phase,START:.status.startTime

if [ "$BUSY" -ne 0 ]; then
  log "DONE, with ${BUSY} busy pod(s) left in place. Re-run once they finish if the upgrade must reach every pod immediately."
  exit 0
fi

log "DONE. Every idle runner pod for ${SCALE_SET} recycled; ARC recreates from the upgraded template on the next queued job."

#!/usr/bin/env bash
# drill-runner-scheduler-fail-open.sh: prove the fail-open reconciler on the live
# cluster by holding ci-runner-scheduler at zero replicas, then restoring it
# (livespec-dev-tooling-mtvxde). Run it through
# ansible/runner-scheduler-fail-open-drill.yml, never by hand.
#
# WHAT IT PROVES. A runner pod stranded by the outage is replaced under the same
# name, naming the default scheduler, and reaches a node and Running. Three facts
# follow from one observed replacement:
#   - the old pod is gone, so its Kueue finalizer cleared: a new pod cannot take
#     the name until then;
#   - the new pod passed Kueue again: it carries no scheduling gate and has a node;
#   - the default scheduler placed it: it names no other scheduler.
#
# THE HOLD IS DELIBERATELY LONG. The zero-available trigger reads a 5-minute window
# every 5 minutes, so it can take up to 10 minutes to fire. A shorter hold could not
# prove the alert, so the run continues to MIN_POLLS even after the first rescue.
# A real alert reaches the trigger's recipients. Tell them first.
#
# IT NEEDS DEMAND. It creates no runner of its own: stranded pods come from real CI
# on the set that names the scheduler. With none by MAX_POLLS it exits 3, which is
# no evidence, not a pass.
#
# THE SCHEDULER IS RESTORED ON EVERY EXIT, by an EXIT trap, to the replica count read
# at the start. A failed restore exits non-zero and says so.
#
# Exit: 0 proven, 1 failed or refused, 3 ran but no pod was rescued.
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
SCHEDULER=ci-runner-scheduler
SCHEDULER_NS=kube-system
RUNNERS_NS=arc-runners
TIMER=reconcile-runner-scheduler-fail-open.timer
INTERVAL="${RUNNER_SCHEDULER_DRILL_INTERVAL_SECONDS:-10}"
MIN_POLLS="${RUNNER_SCHEDULER_DRILL_MIN_POLLS:-66}"
MAX_POLLS="${RUNNER_SCHEDULER_DRILL_MAX_POLLS:-120}"
RESTORE_TIMEOUT="${RUNNER_SCHEDULER_DRILL_RESTORE_TIMEOUT:-180s}"

work="$(mktemp -d)"
replicas=""
restore() {
  local status=$?
  trap - EXIT
  if [ -n "$replicas" ]; then
    echo "${SCRIPT_NAME}: RESTORE replicas=${replicas} at $(date -u +%FT%TZ)"
    if ! kubectl -n "$SCHEDULER_NS" scale deployment "$SCHEDULER" --replicas="$replicas" \
      || ! kubectl -n "$SCHEDULER_NS" rollout status deployment "$SCHEDULER" --timeout="$RESTORE_TIMEOUT"; then
      echo "${SCRIPT_NAME}: FAILED TO RESTORE ${SCHEDULER} to ${replicas} replicas; restore it through the CI stack converge" >&2
      status=1
    fi
  fi
  rm -rf "$work"
  exit "$status"
}
trap restore EXIT
trap 'exit 1' INT TERM

timer_state="$(systemctl is-active "$TIMER" || true)"
[ "$timer_state" = active ] || die "${TIMER} is ${timer_state:-unknown}; nothing would rescue a stranded pod, so the drill refuses"

kubectl -n "$SCHEDULER_NS" get deployment "$SCHEDULER" -o json >"$work/deployment.json" \
  || die "could not read the ${SCHEDULER} Deployment"
read -r desired ready < <(python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
print(d["spec"]["replicas"], d.get("status", {}).get("readyReplicas") or 0)
' "$work/deployment.json")
[ "$ready" -gt 0 ] || die "${SCHEDULER} already has no ready replica; the drill needs a healthy start"

echo "${SCRIPT_NAME}: START desired=${desired} ready=${ready} at $(date -u +%FT%TZ)"
replicas="$desired"
kubectl -n "$SCHEDULER_NS" scale deployment "$SCHEDULER" --replicas=0

echo '{}' >"$work/seen.json"
proven=0
poll=0
while [ "$poll" -lt "$MAX_POLLS" ]; do
  poll=$((poll + 1))
  if kubectl -n "$RUNNERS_NS" get pods -o json >"$work/pods.json"; then
    python3 - "$work/pods.json" "$work/seen.json" "$SCHEDULER" "$(date -u +%s)" <<'PY' >"$work/report"
import json, sys

pods_path, seen_path, scheduler, now = sys.argv[1:5]
now = int(now)
with open(pods_path) as f:
    pods = json.load(f)["items"]
with open(seen_path) as f:
    seen = json.load(f)
for pod in pods:
    meta, spec = pod["metadata"], pod["spec"]
    name, uid = meta["name"], meta["uid"]
    entry = seen.setdefault(name, {})
    if spec.get("schedulerName") == scheduler and pod.get("status", {}).get("phase") == "Pending":
        if not spec.get("nodeName") and "stranded_uid" not in entry:
            entry["stranded_uid"] = uid
            entry["stranded_at"] = now
            print(f"STRANDED {name} uid={uid}")
    elif (
        spec.get("schedulerName") == "default-scheduler"
        and "stranded_uid" in entry
        and uid != entry["stranded_uid"]
        and "proven" not in entry
    ):
        if "replaced_at" not in entry:
            entry["replaced_at"] = now
            print(f"REPLACED {name} old-uid={entry['stranded_uid']} new-uid={uid} after {now - entry['stranded_at']}s")
        if (
            spec.get("nodeName")
            and not spec.get("schedulingGates")
            and pod.get("status", {}).get("phase") == "Running"
        ):
            entry["proven"] = True
            print(
                f"PROVEN {name} node={spec['nodeName']} no-gate running "
                f"{now - entry['stranded_at']}s after it was first seen stranded"
            )
with open(seen_path, "w") as f:
    json.dump(seen, f)
print(f"COUNT {sum(1 for e in seen.values() if e.get('proven'))}")
PY
    grep -v '^COUNT ' "$work/report" | sed "s/^/${SCRIPT_NAME}: /" || true
    proven="$(sed -n 's/^COUNT //p' "$work/report")"
  else
    echo "${SCRIPT_NAME}: could not list runner pods on poll ${poll}; continuing" >&2
  fi
  [ "$poll" -ge "$MIN_POLLS" ] && [ "${proven:-0}" -gt 0 ] && break
  sleep "$INTERVAL"
done

template_scheduler="$(kubectl -n "$RUNNERS_NS" get autoscalingrunnerset livespec-dev-tooling-k3s \
  -o jsonpath='{.spec.template.spec.schedulerName}')" \
  || die "could not read the canary scale set's template"
[ "$template_scheduler" = "$SCHEDULER" ] \
  || die "the canary scale set's template names '${template_scheduler}'; the rescue must leave it unchanged"

echo "${SCRIPT_NAME}: END polls=${poll} proven=${proven:-0} at $(date -u +%FT%TZ)"
if [ "${proven:-0}" -gt 0 ]; then
  exit 0
fi
echo "${SCRIPT_NAME}: NO EVIDENCE: no runner pod was rescued to Running in ${poll} polls" >&2
exit 3

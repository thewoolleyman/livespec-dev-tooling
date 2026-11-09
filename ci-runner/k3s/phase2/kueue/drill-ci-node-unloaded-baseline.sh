#!/usr/bin/env bash
# drill-ci-node-unloaded-baseline.sh: measure each named CI node's UNLOADED
# CPU benchmark, the normalizer of livespec-dev-tooling-6e5pyj's
# hardware-normalized starvation ratio (Stage B, phase 1). Run it through
# ansible/ci-node-unloaded-baseline.yml, never by hand.
#
# WHAT IT MEASURES. For each node, in the order named, ONE Kueue-admitted Job
# pinned to that node runs `sysbench cpu` at 1 and 3 threads, REPS repetitions
# each, and prints events per second. That is COMPUTE ONLY: sysbench cpu is a
# prime-compute loop, while the coverage suites are partly memory- and
# IO-bound, so agreement with the coverage-job baselines validates sysbench as
# the normalizer for the measured nodes only (coordinator condition, recorded
# on 6e5pyj).
#
# IT TAKES ONE CHURN SLOT AND CHANGES NOTHING ELSE. The Job requests
# ci-runner.io/churn-slot 1 through livespec-dev-tooling-lq, exactly as a
# runner pod does, so admission meters it. No cordon, no cap change, no
# scheduler change.
#
# A BUSY NODE IS SKIPPED, NOT MEASURED. Before a node's Job is created, the
# node is ABORTED (and the drill moves on) when it runs more than MAX_RUNNERS
# churn-slot runner pods or more than MAX_FACTORY factory pods, or does not
# carry the churn-slot flavor's node label. Inside the Job, a CPU PSI some
# avg60 at or above PSI_MAX aborts before measuring. A run whose node CPU,
# excluding the Job's own usage, reached BUSY_MAX of the node's cores, or whose
# end PSI reached PSI_MAX, is reported LOADED: it is a record, not a baseline.
#
# EVERY JOB IS DELETED ON EVERY EXIT, by an EXIT trap.
#
# Exit: 0 every named node yielded an UNLOADED result; 3 the drill ran but at
# least one node was aborted or loaded (no baseline for it; repeat it in the
# next quiet window); 1 failed or refused.
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
NS=arc-runners
LOCAL_QUEUE=livespec-dev-tooling-lq
FLAVOR_LABEL=k3s-role=arc-runner-host
FACTORY_NAMESPACES="${CI_NODE_BASELINE_FACTORY_NAMESPACES:-factory factory-mi-homelab}"
IMAGE="${CI_NODE_BASELINE_IMAGE:-ubuntu:24.04}"
MAX_RUNNERS="${CI_NODE_BASELINE_MAX_RUNNERS:-2}"
MAX_FACTORY="${CI_NODE_BASELINE_MAX_FACTORY:-2}"
PSI_MAX="${CI_NODE_BASELINE_PSI_MAX:-10}"
BUSY_MAX="${CI_NODE_BASELINE_BUSY_MAX:-0.35}"
REPS="${CI_NODE_BASELINE_REPS:-3}"
SECONDS_PER_RUN="${CI_NODE_BASELINE_SECONDS_PER_RUN:-20}"
INTERVAL="${CI_NODE_BASELINE_INTERVAL_SECONDS:-10}"
MAX_POLLS="${CI_NODE_BASELINE_MAX_POLLS:-90}"

[ "$#" -gt 0 ] || die "name at least one node to measure"
case "$REPS$SECONDS_PER_RUN$MAX_RUNNERS$MAX_FACTORY" in
  *[!0-9]*) die "REPS, SECONDS_PER_RUN, MAX_RUNNERS and MAX_FACTORY must be whole numbers" ;;
esac

jobs_created=()
cleanup() {
  local status=$?
  trap - EXIT
  local job
  for job in "${jobs_created[@]+"${jobs_created[@]}"}"; do
    kubectl -n "$NS" delete job "$job" --ignore-not-found --wait=false \
      || echo "${SCRIPT_NAME}: could not delete job ${job}; delete it through the CI stack converge" >&2
  done
  exit "$status"
}
trap cleanup EXIT
trap 'exit 1' INT TERM

# The measurement, run inside the Job. Reads are host-wide where they must be:
# /proc/stat and /proc/pressure are not namespaced, the cgroup's cpu.stat is.
POD_SCRIPT="$(cat <<'POD'
set -eu
psi() { awk '/^some/{for(i=1;i<=NF;i++) if($i ~ /^avg60=/){sub("avg60=","",$i); print $i}}' /proc/pressure/cpu; }
cpu_now() { awk '/^cpu /{b=$2+$3+$4+$7+$8+$9; print b, b+$5+$6}' /proc/stat; }
self_usec() { awk '/^usage_usec/{print $2}' /sys/fs/cgroup/cpu.stat 2>/dev/null || echo 0; }
below() { awk -v a="$1" -v b="$2" 'BEGIN{exit !(a < b)}'; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null && apt-get install -y -qq sysbench >/dev/null
echo "SYSBENCH $(sysbench --version)"
p0="$(psi)"; echo "PSI_PRE avg60=$p0"
below "$p0" "$PSI_MAX" || { echo "ABORT psi_avg60=$p0 at or above $PSI_MAX"; exit 3; }
ncpu="$(grep -c "^cpu[0-9]" /proc/stat)"
read -r b0 t0 <<EOF
$(cpu_now)
EOF
s0="$(self_usec)"
for th in 1 3; do
  r=1
  while [ "$r" -le "$REPS" ]; do
    eps="$(sysbench cpu --threads="$th" --time="$SECONDS_PER_RUN" --cpu-max-prime=20000 run | awk '/events per second/{print $4}')"
    echo "RESULT threads=$th rep=$r events_per_second=$eps"
    r=$((r + 1))
  done
  echo "PSI_AFTER_THREADS_$th avg60=$(psi)"
done
p1="$(psi)"
read -r b1 t1 <<EOF
$(cpu_now)
EOF
s1="$(self_usec)"
# /proc/stat counts USER_HZ (100) ticks; cpu.stat counts microseconds.
awk -v b="$((b1 - b0))" -v t="$((t1 - t0))" -v s="$((s1 - s0))" -v n="$ncpu" -v m="$BUSY_MAX" -v p="$p1" -v pm="$PSI_MAX" 'BEGIN{
  own = s / 10000; f = (t > 0) ? (b - own) / t : 1; if (f < 0) f = 0
  printf "LOAD ncpu=%d node_busy_excl_self=%.3f psi_end_avg60=%s\n", n, f, p
  print "VERDICT " ((f < m && p < pm) ? "unloaded" : "loaded")
}'
POD
)"

count_runner_pods() {
  # Running pods on the node that request a churn slot: the runner pods.
  kubectl -n "$NS" get pods --field-selector "spec.nodeName=$1,status.phase=Running" -o json \
    | python3 -c 'import json,sys
pods = json.load(sys.stdin)["items"]
print(sum(1 for p in pods if any("ci-runner.io/churn-slot" in (c.get("resources", {}).get("requests") or {}) for c in p["spec"]["containers"])))'
}

count_factory_pods() {
  local node="$1" total=0 ns n
  for ns in $FACTORY_NAMESPACES; do
    n="$(kubectl -n "$ns" get pods --field-selector "spec.nodeName=$node,status.phase=Running" -o json \
      | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["items"]))')"
    total=$((total + n))
  done
  echo "$total"
}

job_manifest() {
  local job="$1" node="$2"
  python3 - "$job" "$node" "$NS" "$LOCAL_QUEUE" "$IMAGE" <<'PY'
import json, os, sys
job, node, ns, queue, image = sys.argv[1:6]
env = [{"name": k, "value": os.environ[k]} for k in ("PSI_MAX", "BUSY_MAX", "REPS", "SECONDS_PER_RUN")]
print(json.dumps({
    "apiVersion": "batch/v1", "kind": "Job",
    "metadata": {"name": job, "namespace": ns,
                 "labels": {"kueue.x-k8s.io/queue-name": queue, "app.kubernetes.io/name": "ci-node-unloaded-baseline"}},
    "spec": {
        "suspend": True, "backoffLimit": 0, "activeDeadlineSeconds": 1200,
        "template": {"spec": {
            "restartPolicy": "Never", "automountServiceAccountToken": False,
            "terminationGracePeriodSeconds": 0,
            "nodeSelector": {"kubernetes.io/hostname": node},
            "tolerations": [{"key": "livespec.io/factory-pressure", "operator": "Exists", "effect": "PreferNoSchedule"}],
            "containers": [{
                "name": "baseline", "image": image, "command": ["sh", "-c", os.environ["POD_SCRIPT"]], "env": env,
                "resources": {"requests": {"ci-runner.io/churn-slot": "1"}, "limits": {"ci-runner.io/churn-slot": "1"}},
            }],
        }},
    },
}))
PY
}

job_state() {
  kubectl -n "$NS" get job "$1" -o json | python3 -c 'import json,sys
conds = {c["type"]: c["status"] for c in json.load(sys.stdin).get("status", {}).get("conditions") or []}
print("complete" if conds.get("Complete") == "True" else "failed" if conds.get("Failed") == "True" else "running")'
}

export PSI_MAX BUSY_MAX REPS SECONDS_PER_RUN POD_SCRIPT
any_short=0
for node in "$@"; do
  stamp="$(date -u +%Y%m%dt%H%M%Sz)"
  echo "${SCRIPT_NAME}: NODE ${node} at $(date -u +%FT%TZ)"
  flavor_node="$(kubectl get node "$node" -l "$FLAVOR_LABEL" -o name || true)"
  if [ -z "$flavor_node" ]; then
    echo "ABORT node=${node} reason=no-node-carrying-${FLAVOR_LABEL}"; any_short=1; continue
  fi
  runners="$(count_runner_pods "$node")"
  factory="$(count_factory_pods "$node")"
  echo "PRECONDITION node=${node} runner_pods=${runners} factory_pods=${factory}"
  if [ "$runners" -gt "$MAX_RUNNERS" ] || [ "$factory" -gt "$MAX_FACTORY" ]; then
    echo "ABORT node=${node} reason=busy runner_pods=${runners}>${MAX_RUNNERS}-or-factory_pods=${factory}>${MAX_FACTORY}"
    any_short=1; continue
  fi
  job="unloaded-baseline-${node%%.*}-${stamp}"
  job_manifest "$job" "$node" | kubectl create -f -
  jobs_created+=("$job")
  state=running; polls=0
  while [ "$state" = running ] && [ "$polls" -lt "$MAX_POLLS" ]; do
    sleep "$INTERVAL"; polls=$((polls + 1)); state="$(job_state "$job")"
  done
  kubectl -n "$NS" logs "job/${job}" 2>&1 | sed "s/^/  ${node}: /" || true
  if [ "$state" != complete ]; then
    echo "ABORT node=${node} reason=job-${state}-after-${polls}-polls"; any_short=1; continue
  fi
  job_log="$(kubectl -n "$NS" logs "job/${job}" || true)"
  if ! grep -q '^VERDICT unloaded$' <<<"$job_log"; then
    echo "LOADED node=${node}: recorded, not a baseline"; any_short=1; continue
  fi
  echo "BASELINE node=${node}"
done

if [ "$any_short" -ne 0 ]; then
  echo "${SCRIPT_NAME}: at least one node has no unloaded baseline; repeat it in the next quiet window" >&2
  exit 3
fi

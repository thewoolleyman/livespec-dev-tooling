#!/usr/bin/env bash
# converge-worker-queues.sh — render and apply the container-worker Kueue
# queues (./worker/cluster-queue-*.yaml) with a quota equal to the sum of the
# enrolled workers' derived ci-runner.io/churn-slot capacity, and the gates-cq
# worker flavors (./worker/gates-worker-flavor.yaml, one per architecture)
# with a quota of whole gates from the enrolled workers' gate shares
# (livespec-dev-tooling-ko26ez.7). converge-ci-stack.sh runs it after the
# committed queues; homelab-worker/enroll-workload-classes.sh runs it after
# enrolling or un-enrolling a worker, so the cohort quota is reconciled in the
# same operation. Each template names its architecture in its file name
# (…-<arch>.yaml) and sums only workers of that architecture.
#
# Requires kubectl with KUBECONFIG pointed at the cluster. --dry-run prints the
# rendered manifests and applies nothing.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dir="${WORKER_QUEUE_DIR:-$here/worker}"
dry_run=0
[ "${1:-}" = --dry-run ] && dry_run=1

for template in "$dir"/cluster-queue-*.yaml; do
  [ -e "$template" ] || continue
  base="${template##*/}"
  arch="${base%.yaml}"
  arch="${arch##*-}"
  slots="$(kubectl get nodes -l "homelab-worker.livespec.dev/class=worker,kubernetes.io/arch=$arch" \
    -o jsonpath='{range .items[*]}{.status.capacity.ci-runner\.io/churn-slot}{"\n"}{end}' |
    awk '/^[0-9]+$/ { s += $1 } END { print s + 0 }')"
  rendered="$(sed "s|@WORKER_CHURN_SLOTS@|$slots|" "$template")"
  echo "converge-worker-queues: $base -> $slots churn slots from enrolled $arch workers"
  if [ "$dry_run" -eq 1 ]; then
    printf '%s\n' "$rendered"
  else
    printf '%s\n' "$rendered" | kubectl apply -f - >/dev/null
  fi
done

# --- gates: one worker flavor per architecture, appended LAST to gates-cq ----
# One gate is the size gates-cq's committed quotas count in: 5 CPU and 8 Gi
# (../kueue/cluster-queue-gates.yaml: 15 cpu / 24Gi is three gates on gmktec,
# 10 / 16Gi two on hp and poweredge; the renderer requests 5 cpu per gate). A
# worker's gate share (enroll-workload-classes.sh) holds max(1, share / 5 CPU)
# whole gates, the same at-least-one rule its churn slots follow.
gate_millicores=5000
gate_memory_gi=8
gates_template="$dir/gates-worker-flavor.yaml"
[ -e "$gates_template" ] || exit 0
shares="$(kubectl get nodes -l 'homelab-worker.livespec.dev/class=worker,homelab-worker.livespec.dev/gate-share-millicores' \
  -o jsonpath='{range .items[*]}{.metadata.labels.kubernetes\.io/arch} {.metadata.labels.homelab-worker\.livespec\.dev/gate-share-millicores}{"\n"}{end}')"
gates="$(printf '%s\n' "$shares" | awk -v g="$gate_millicores" '
  NF == 2 && $2 ~ /^[0-9]+$/ { n = int($2 / g); if (n < 1) n = 1; s[$1] += n }
  END { for (a in s) print a, s[a] }' | sort)"
flavors_json="[]"
while read -r arch count; do
  [ -n "$arch" ] || continue
  rendered="$(sed "s|@ARCH@|$arch|g" "$gates_template")"
  echo "converge-worker-queues: gates-worker-$arch-flavor -> $count gates from enrolled $arch workers"
  if [ "$dry_run" -eq 1 ]; then
    printf '%s\n' "$rendered"
  else
    printf '%s\n' "$rendered" | kubectl apply -f - >/dev/null
  fi
  flavors_json="$(printf '%s' "$flavors_json" | ARCH="$arch" CPU="$((count * gate_millicores / 1000))" \
    MEM="$((count * gate_memory_gi))Gi" python3 -c '
import json, os, sys
f = json.load(sys.stdin)
f.append({"name": "gates-worker-%s-flavor" % os.environ["ARCH"], "resources": [
    {"name": "cpu", "nominalQuota": int(os.environ["CPU"])},
    {"name": "memory", "nominalQuota": os.environ["MEM"]}]})
print(json.dumps(f))')"
done <<<"$gates"

# Replace ONLY gates-cq's flavor list: every fleet flavor stays as committed, in
# its order, and the worker flavors follow. A worker no longer enrolled drops out.
if ! queue="$(kubectl get clusterqueue gates-cq -o json)"; then
  echo "converge-worker-queues: gates-cq is not present; no worker gate flavor added" >&2
  exit 0
fi
patch="$(printf '%s' "$queue" | WORKER_FLAVORS="$flavors_json" python3 -c '
import json, os, sys
queue = json.load(sys.stdin)
worker = json.loads(os.environ["WORKER_FLAVORS"])
groups = queue["spec"]["resourceGroups"]
index = next(i for i, g in enumerate(groups) if "cpu" in g.get("coveredResources", []))
kept = [f for f in groups[index]["flavors"]
        if not (f["name"].startswith("gates-worker-") and f["name"].endswith("-flavor"))]
print(json.dumps([{"op": "replace", "path": "/spec/resourceGroups/%d/flavors" % index,
                   "value": kept + worker}]))')"
echo "converge-worker-queues: gates-cq flavors -> fleet flavors, then $(printf '%s' "$flavors_json" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))') worker flavor(s)"
if [ "$dry_run" -eq 1 ]; then
  printf '%s\n' "$patch"
else
  kubectl patch clusterqueue gates-cq --type=json -p "$patch" >/dev/null
fi

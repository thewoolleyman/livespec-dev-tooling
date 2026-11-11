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

# --- gates: one worker flavor per architecture, placed FIRST in gates-cq ----
# One gate is the GATE UNIT that gates-cq itself declares, in its
# ci-runner.io/gate-unit-cpu and ci-runner.io/gate-unit-memory annotations
# (../kueue/cluster-queue-gates.yaml). That file's fleet flavor quotas are whole
# multiples of the same unit, which tests/spec/test_gates_queue_gate_unit.py
# holds, so this script and the fleet lanes count gates in one committed value
# rather than three (plan gate-job-resources, livespec-dev-tooling-brggiu). It is
# read off the LIVE queue, which converge-ci-stack.sh applies from that file just
# before this script runs. A worker's gate share (enroll-workload-classes.sh)
# holds max(1, share / unit cpu) whole gates, the same at-least-one rule its
# churn slots follow.
gates_template="$dir/gates-worker-flavor.yaml"
[ -e "$gates_template" ] || exit 0
if ! queue="$(kubectl get clusterqueue gates-cq -o json)"; then
  echo "converge-worker-queues: gates-cq is not present; no worker gate flavor added" >&2
  exit 0
fi
if ! unit="$(printf '%s' "$queue" | python3 -c '
import json, re, sys
annotations = json.load(sys.stdin).get("metadata", {}).get("annotations") or {}
cpu = annotations.get("ci-runner.io/gate-unit-cpu", "")
memory = annotations.get("ci-runner.io/gate-unit-memory", "")
if not re.fullmatch(r"[1-9][0-9]*", cpu) or not re.fullmatch(r"[1-9][0-9]*Gi", memory):
    sys.exit("gates-cq must carry ci-runner.io/gate-unit-cpu (a positive integer) and "
             "ci-runner.io/gate-unit-memory (a positive integer of Gi); read cpu=%r memory=%r"
             % (cpu, memory))
print(cpu, memory[:-2])')"; then
  echo "converge-worker-queues: FATAL: no gate unit on gates-cq; no worker gate flavor added" >&2
  exit 1
fi
read -r gate_cpu gate_memory_gi <<<"$unit"
gate_millicores=$((gate_cpu * 1000))
shares="$(kubectl get nodes -l 'homelab-worker.livespec.dev/class=worker,homelab-worker.livespec.dev/gate-share-millicores' \
  -o jsonpath='{range .items[*]}{.metadata.labels.kubernetes\.io/arch} {.metadata.labels.homelab-worker\.livespec\.dev/gate-share-millicores}{"\n"}{end}')"
gates="$(printf '%s\n' "$shares" | awk -v g="$gate_millicores" '
  NF == 2 && $2 ~ /^[0-9]+$/ { n = int($2 / g); if (n < 1) n = 1; s[$1] += n }
  END { for (a in s) print a, s[a] }' | sort)"
flavors_json="[]"
while read -r arch count; do
  [ -n "$arch" ] || continue
  rendered="$(sed "s|@ARCH@|$arch|g" "$gates_template")"
  echo "converge-worker-queues: gates-worker-taint-$arch-flavor -> $count gates from enrolled $arch workers"
  if [ "$dry_run" -eq 1 ]; then
    printf '%s\n' "$rendered"
  else
    printf '%s\n' "$rendered" | kubectl apply -f - >/dev/null
  fi
  flavors_json="$(printf '%s' "$flavors_json" | ARCH="$arch" CPU="$((count * gate_millicores / 1000))" \
    MEM="$((count * gate_memory_gi))Gi" python3 -c '
import json, os, sys
f = json.load(sys.stdin)
f.append({"name": "gates-worker-taint-%s-flavor" % os.environ["ARCH"], "resources": [
    {"name": "cpu", "nominalQuota": int(os.environ["CPU"])},
    {"name": "memory", "nominalQuota": os.environ["MEM"]}]})
print(json.dumps(f))')"
done <<<"$gates"

# Replace ONLY gates-cq's flavor list: the worker flavors come FIRST, then every
# fleet flavor as committed, in its order. First, so an enrolled worker takes its
# own share of the gates its architecture can run rather than only the overflow
# the fleet's nodes have no quota left for (maintainer direction 2026-11-09, plan
# homelab-k8s-worker-nodes: the worker serves live load). Kueue never assigns a
# worker flavor to a gate whose required kubernetes.io/arch affinity excludes
# that architecture, so the order moves no amd64-only gate onto an arm64 worker.
# A worker no longer enrolled drops out.
patch="$(printf '%s' "$queue" | WORKER_FLAVORS="$flavors_json" python3 -c '
import json, os, sys
queue = json.load(sys.stdin)
worker = json.loads(os.environ["WORKER_FLAVORS"])
groups = queue["spec"]["resourceGroups"]
index = next(i for i, g in enumerate(groups) if "cpu" in g.get("coveredResources", []))
kept = [f for f in groups[index]["flavors"]
        if not (f["name"].startswith("gates-worker-") and f["name"].endswith("-flavor"))]
print(json.dumps([{"op": "replace", "path": "/spec/resourceGroups/%d/flavors" % index,
                   "value": worker + kept}]))')"
echo "converge-worker-queues: gates-cq flavors -> $(printf '%s' "$flavors_json" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))') worker flavor(s), then fleet flavors"
if [ "$dry_run" -eq 1 ]; then
  printf '%s\n' "$patch"
else
  kubectl patch clusterqueue gates-cq --type=json -p "$patch" >/dev/null
fi

# --- retired worker flavors -------------------------------------------------
# A worker flavor renamed out of gates-cq is left behind as an unused
# ResourceFlavor: apply never deletes. Each name here was replaced by the
# flavor above (gates-worker-<arch>-flavor -> gates-worker-taint-<arch>-flavor,
# livespec-dev-tooling#3926), and the gates-cq patch just above has removed
# every gates-worker-*-flavor entry, so nothing references it here. Kueue's
# resource-in-use finalizer still refuses to drop a flavor some queue names, so
# --wait=false keeps a converge from blocking on that guard. Plan
# homelab-k8s-worker-nodes, cleanup follow-up.
retired_flavors=(gates-worker-arm64-flavor)
for flavor in "${retired_flavors[@]}"; do
  echo "converge-worker-queues: deleting retired ResourceFlavor $flavor"
  if [ "$dry_run" -eq 0 ]; then
    kubectl delete resourceflavor "$flavor" --ignore-not-found --wait=false >/dev/null
  fi
done

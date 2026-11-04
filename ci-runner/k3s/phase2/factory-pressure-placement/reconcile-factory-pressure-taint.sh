#!/usr/bin/env bash
# reconcile-factory-pressure-taint.sh: steer NEW factory sandbox pods away from a
# CPU-pressured factory node, with no plugin change and no change to the factory
# credential. Orchestrator work-item bd-ib-plon2p, route accepted by the
# coordinator under R301.
#
# WHAT IT DOES, once per run (the timer runs it every ~30 s, on the server):
#   1. Reads every node labelled ci-runner.io/factory=true and its
#      `LivespecCPUPressure` condition, which each node publishes about itself
#      (publish-node-cpu-pressure.sh). A heartbeat older than
#      FACTORY_PRESSURE_STALE_SECONDS, or no condition at all, is UNKNOWN.
#   2. Finds the lowest-pressure node and asks whether it fits one more sandbox:
#        fit = allocatable cpu - requested cpu (Pending/Running pods)
#              - gates_reserve
#      gates_reserve is the gates-cq cpu nominalQuota of the flavor whose
#      ResourceFlavor .spec.nodeLabels select that node (mapped by labels, never
#      by flavor name), minus the cpu its Pending/Running gate pods already request.
#      This reconciler OWNS NO CPU: it never steers a sandbox into the gates'
#      unused quota. The rule was agreed with dev-host-test-gate-load (owner of
#      livespec-dev-tooling-cikd6m) and recorded on bd-ib-plon2p.
#   3. When the fit is at least FACTORY_PRESSURE_SANDBOX_MILLICPU and a node is at
#      least FACTORY_PRESSURE_GAP points above the lowest, it puts
#      livespec.io/factory-pressure=high:PreferNoSchedule on THAT node.
#      Otherwise (no gap, no fit, any reading unknown, no quota read ever) it
#      removes the taint from every factory node, so placement falls back to the
#      sandbox pods' own hostname topology spread.
#   4. Annotates each factory sandbox pod that lacks it with
#      livespec.io/placement-pressure: the readings, fit and taint state of the
#      cycle that first saw it.
#
# PreferNoSchedule ONLY SCORES. It never filters, so a pod is never left Pending
# because of it. The scheduler weights TaintToleration (3) above
# PodTopologySpread (2). That ordering was proven on a two-worker kind cluster in
# thewoolleyman/sandbox-driver-kubernetes PR #11 (tests/placement_scoring.rs).
# Every non-factory pool workload tolerates the key: the ARC runner and hook pod
# templates and the gate Job template carry a toleration for it. So the taint
# steers factory pods ONLY.
#
# THE QUOTA FAIL-SAFE LADDER. A successful gates-cq read is cached in
# ${STATE_DIR}/gates-quota.json. If a later read fails, the cached FULL
# nominalQuota is reserved, with no subtraction for running gates. If no read
# has ever succeeded, no taint is applied.
#
# Nothing else in this tree writes this taint key: ansible/roles/node_taints
# reconciles only node-role/ci, k3s_config renders only the profile's
# --node-taint, and converge-ci-stack.sh writes no taint.
#
# Flags: --dry-run prints the decision and changes nothing.
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

DRY_RUN=0
case "${1:-}" in
  --dry-run) DRY_RUN=1 ;;
  "") ;;
  *) die "usage: ${SCRIPT_NAME} [--dry-run]" ;;
esac

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
STATE_DIR="${FACTORY_PRESSURE_STATE_DIR:-/var/lib/livespec/factory-pressure-placement}"
export FACTORY_PRESSURE_GAP="${FACTORY_PRESSURE_GAP:-20}"
export FACTORY_PRESSURE_SANDBOX_MILLICPU="${FACTORY_PRESSURE_SANDBOX_MILLICPU:-4000}"
export FACTORY_PRESSURE_STALE_SECONDS="${FACTORY_PRESSURE_STALE_SECONDS:-90}"
export FACTORY_PRESSURE_NOW="${FACTORY_PRESSURE_NOW:-$(date -u +%s)}"
TAINT_KEY=livespec.io/factory-pressure
ANNOTATION_KEY=livespec.io/placement-pressure

mkdir -p "$STATE_DIR"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

kubectl get nodes -l ci-runner.io/factory=true -o json >"$work/nodes.json" \
  || die "could not list the factory nodes; changing nothing this cycle"
kubectl get pods --all-namespaces -o json >"$work/pods.json" \
  || die "could not list pods; changing nothing this cycle"
quota_ok=1
kubectl get clusterqueue gates-cq -o json >"$work/cq.json" 2>"$work/cq.err" || quota_ok=0
kubectl get resourceflavors -o json >"$work/flavors.json" 2>>"$work/cq.err" || quota_ok=0
[ "$quota_ok" = 1 ] || { echo "${SCRIPT_NAME}: gates-cq quota read FAILED:" >&2; cat "$work/cq.err" >&2; }
export FACTORY_PRESSURE_QUOTA_OK="$quota_ok"

python3 - "$work" "$STATE_DIR" >"$work/decision" <<'PY'
import json, os, sys
from datetime import datetime, timezone

work, state_dir = sys.argv[1], sys.argv[2]
gap = float(os.environ["FACTORY_PRESSURE_GAP"])
need = int(os.environ["FACTORY_PRESSURE_SANDBOX_MILLICPU"])
stale = int(os.environ["FACTORY_PRESSURE_STALE_SECONDS"])
now = int(os.environ["FACTORY_PRESSURE_NOW"])
quota_ok = os.environ["FACTORY_PRESSURE_QUOTA_OK"] == "1"
TAINT_KEY = "livespec.io/factory-pressure"
GATE_LABEL = ("app.kubernetes.io/part-of", "livespec-ci-gates")


def load(name):
    with open(os.path.join(work, name)) as f:
        return json.load(f)


def millicpu(q):
    q = str(q)
    if q.endswith("m"):
        return int(float(q[:-1]))
    return int(round(float(q) * 1000))


def pod_cpu(pod):
    spec = pod.get("spec", {})
    def req(c):
        return millicpu(((c.get("resources") or {}).get("requests") or {}).get("cpu", "0"))
    main = sum(req(c) for c in spec.get("containers", []))
    init = max([req(c) for c in spec.get("initContainers", [])] or [0])
    return max(main, init)


nodes = load("nodes.json")["items"]
pods = [p for p in load("pods.json")["items"]
        if p.get("status", {}).get("phase") in ("Pending", "Running")]

readings = {}
for n in nodes:
    name = n["metadata"]["name"]
    value = None
    for c in n.get("status", {}).get("conditions", []):
        if c.get("type") != "LivespecCPUPressure":
            continue
        beat = c.get("lastHeartbeatTime", "")
        msg = c.get("message", "")
        try:
            at = datetime.strptime(beat, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            if now - at <= stale and msg.startswith("cpu.some.avg60="):
                value = float(msg.split("=", 1)[1])
        except ValueError:
            value = None
    readings[name] = value

# The gates reserve per node, from a live read or the cached last good read.
cache = os.path.join(state_dir, "gates-quota.json")
quota = None        # node -> nominal millicpu
quota_source = "none"
if quota_ok:
    flavors = {f["metadata"]["name"]: (f.get("spec", {}).get("nodeLabels") or {})
               for f in load("flavors.json")["items"]}
    quota = {}
    groups = load("cq.json").get("spec", {}).get("resourceGroups", [])
    for fl in (groups[0].get("flavors", []) if groups else []):
        labels = flavors.get(fl.get("name"))
        if not labels:
            continue
        cpu = [r for r in fl.get("resources", []) if r.get("name") == "cpu"]
        if not cpu:
            continue
        for n in nodes:
            nl = n["metadata"].get("labels", {})
            if all(nl.get(k) == v for k, v in labels.items()):
                quota[n["metadata"]["name"]] = quota.get(n["metadata"]["name"], 0) + millicpu(cpu[0]["nominalQuota"])
    quota_source = "live"
    with open(cache + ".tmp", "w") as f:
        json.dump({"quota": quota, "at": now}, f)
    os.replace(cache + ".tmp", cache)
elif os.path.exists(cache):
    with open(cache) as f:
        quota = json.load(f)["quota"]
    quota_source = "cached"


def gates_reserve(node):
    nominal = (quota or {}).get(node, 0)
    if quota_source != "live":
        return nominal  # the cached FULL nominal quota: the fail-safe ladder
    used = sum(pod_cpu(p) for p in pods
               if p.get("spec", {}).get("nodeName") == node
               and p["metadata"].get("namespace") == "gates"
               and p["metadata"].get("labels", {}).get(GATE_LABEL[0]) == GATE_LABEL[1])
    return max(0, nominal - used)


def fit(node):
    n = next(x for x in nodes if x["metadata"]["name"] == node)
    alloc = millicpu(n.get("status", {}).get("allocatable", {}).get("cpu", "0"))
    requested = sum(pod_cpu(p) for p in pods if p.get("spec", {}).get("nodeName") == node)
    return alloc - requested - gates_reserve(node)


tainted_now = {n["metadata"]["name"] for n in nodes
               if any(t.get("key") == TAINT_KEY for t in (n.get("spec", {}).get("taints") or []))}
want = set()
reason = ""
fit_low = None
if not nodes:
    reason = "no-factory-nodes"
elif any(v is None for v in readings.values()):
    reason = "reading-unknown:" + ",".join(sorted(k for k, v in readings.items() if v is None))
elif quota is None:
    reason = "no-gates-quota-read-ever"
else:
    low = min(readings, key=lambda k: readings[k])
    fit_low = fit(low)
    high = {k for k, v in readings.items() if v - readings[low] >= gap}
    if not high:
        reason = f"no-gap:lowest={low}"
    elif fit_low < need:
        reason = f"lowest-does-not-fit:{low}:fit={fit_low}m<{need}m"
    else:
        want = high
        reason = f"steer-to:{low}:fit={fit_low}m"

summary = " ".join(f"{k}={'unknown' if v is None else v}" for k, v in sorted(readings.items()))
print(f"DECISION {reason} readings[{summary}] quota={quota_source} taint={','.join(sorted(want)) or 'none'}")
for n in sorted(want - tainted_now):
    print(f"TAINT {n}")
for n in sorted(tainted_now - want):
    print(f"UNTAINT {n}")
annotation = f"cycle={now} {reason} readings[{summary}] taint={','.join(sorted(want)) or 'none'}"
for p in pods:
    md = p["metadata"]
    if md.get("namespace") not in ("factory", "factory-mi-homelab"):
        continue
    if md.get("labels", {}).get("app.kubernetes.io/managed-by") != "sandbox-driver-kubernetes":
        continue
    if "livespec.io/placement-pressure" in (md.get("annotations") or {}):
        continue
    print(f"ANNOTATE {md['namespace']} {md['name']} {annotation}")
PY

grep '^DECISION' "$work/decision" | sed "s/^/${SCRIPT_NAME}: /"
[ "$DRY_RUN" = 0 ] || { grep -v '^DECISION' "$work/decision" | sed "s/^/${SCRIPT_NAME}: dry-run: /"; exit 0; }

status=0
while read -r verb a b rest; do
  case "$verb" in
    TAINT)
      echo "${SCRIPT_NAME}: tainting ${a} ${TAINT_KEY}=high:PreferNoSchedule"
      kubectl taint nodes "$a" "${TAINT_KEY}=high:PreferNoSchedule" --overwrite || status=1 ;;
    UNTAINT)
      echo "${SCRIPT_NAME}: removing ${TAINT_KEY} from ${a}"
      kubectl taint nodes "$a" "${TAINT_KEY}:PreferNoSchedule-" || status=1 ;;
    ANNOTATE)
      kubectl annotate pod -n "$a" "$b" "${ANNOTATION_KEY}=${rest}" >/dev/null || status=1 ;;
  esac
done <"$work/decision"
exit "$status"

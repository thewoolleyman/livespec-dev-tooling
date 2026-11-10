#!/usr/bin/env bash
# reconcile-gate-lane-order.sh: steer which gate lane of the `gates-cq`
# ClusterQueue admits a NEWLY SUBMITTED gate Job, from measured node CPU
# readings. Work item livespec-dev-tooling-gvo7fa; contract: SPECIFICATION/
# contracts.md "Delegated pre-push gate", the "Placement by node pressure" bullet.
#
# WHY. gates-cq admits by requests, and CI runner pods request no CPU, so a node
# that runners saturate reads as free and a 5-CPU gate then takes CPU from those
# runners. The committed flavor order is static and cannot follow load.
#
# THE LEVER is the flavor ORDER of gates-cq. Kueue tries flavors in list order
# and admits on the first whose node has room, so a saturated lane moved behind
# the unsaturated ones stops receiving new gates while any other lane has room.
# It is never a quota change (the pool's lane-size derivation owns quota: every
# flavor object is written back byte-for-byte as read) and never a new
# WorkloadPriorityClass.
#
# WHAT IT DOES, once per run (the timer runs it every ~30 s, on the k3s server):
#   1. Lanes are DERIVED from the live gates-cq: a flavor whose ResourceFlavor
#      .spec.nodeLabels names kubernetes.io/hostname is a node lane. No node is
#      listed here, so a node that joins ci_pool and gets its lane (the gates test
#      requires exactly one per member) is covered with no edit to this script.
#      Any other flavor (the container-worker flavors) stays in front, in place.
#   2. Reads each lane node's `LivespecGateLaneCPU` condition (published by
#      publish-gate-lane-readings.sh on every pool node): cpu.idle60 and
#      ci.slice.some.avg60. A node is SATURATED when idle < 5 AND the CI slice's
#      pressure avg60 > 30 (.ai/ci-node-capacity-reads.md).
#   3. The STATIC LANE ORDER is the order the converge composes: the container-
#      worker flavors first, then the order committed in kueue/cluster-queue-
#      gates.yaml (installed beside this script by ci_converge_unit). The desired
#      order is the unsaturated lanes in static order, then the saturated lanes in
#      static order. When EVERY lane is saturated that is the static order itself,
#      so saturation alone never leaves the queue without a lane.
#   4. A lane whose node cannot run the gate Job's architecture (the `gate gate`
#      line of workload-arch.conf) is neither unsaturated nor a lane with room: it
#      is not read, and it sorts after both groups.
#   5. A reading it cannot take (condition absent, heartbeat older than
#      GATE_LANE_STALE_SECONDS, a field `unreadable` or malformed, node absent)
#      is logged by node and reading and is NEVER treated as saturated or free:
#      the whole queue falls back to the static order.
#   6. If the live order differs from the desired order, it patches ONLY
#      /spec/resourceGroups/<i>/flavors, guarded by a `test` of the queue's
#      resourceVersion, and logs the change with every lane node's readings.
#
# It never writes the committed files: a converge run restores the static order
# and the next pass re-applies the choice. It sets no CPU request on runner pods
# and neither reads nor writes ci-runner.io/factory-admit.
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
LIB_DIR="${GATE_LANE_LIB_DIR:-/usr/local/lib/ci-runner-k3s}"
export GATE_LANE_STATIC_QUEUE_FILE="${GATE_LANE_STATIC_QUEUE_FILE:-${LIB_DIR}/kueue/cluster-queue-gates.yaml}"
export GATE_LANE_ARCH_CONF="${GATE_LANE_ARCH_CONF:-${LIB_DIR}/workload-arch.conf}"
export GATE_LANE_IDLE_MAX="${GATE_LANE_IDLE_MAX:-5}"
export GATE_LANE_SLICE_MIN="${GATE_LANE_SLICE_MIN:-30}"
export GATE_LANE_STALE_SECONDS="${GATE_LANE_STALE_SECONDS:-90}"
export GATE_LANE_NOW="${GATE_LANE_NOW:-$(date -u +%s)}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

kubectl get nodes -o json >"$work/nodes.json" || die "could not list the nodes; changing nothing this cycle"
kubectl get clusterqueue gates-cq -o json >"$work/cq.json" || die "could not read clusterqueue gates-cq; changing nothing this cycle"
kubectl get resourceflavors -o json >"$work/flavors.json" || die "could not list resourceflavors; changing nothing this cycle"

status=0
python3 - "$work" >"$work/decision" <<'PY' || status=$?
import json, os, re, sys
from datetime import datetime, timezone

work = sys.argv[1]
idle_max = float(os.environ["GATE_LANE_IDLE_MAX"])
slice_min = float(os.environ["GATE_LANE_SLICE_MIN"])
stale = int(os.environ["GATE_LANE_STALE_SECONDS"])
now = int(os.environ["GATE_LANE_NOW"])
CONDITION = "LivespecGateLaneCPU"
HOST = "kubernetes.io/hostname"


def load(name):
    with open(os.path.join(work, name)) as f:
        return json.load(f)


def static_names(path):
    # The flavor names under the gates-cq ClusterQueue's `flavors:` key, in file
    # order. A flavor line is `- name: <unquoted>` at the flavor indent; the
    # resources under it are quoted (`- name: "cpu"`) and deeper.
    with open(path) as f:
        documents = re.split(r"(?m)^---\s*$", f.read())
    for document in documents:
        if re.search(r"(?m)^kind: ClusterQueue\s*$", document) and re.search(r"(?m)^  name: gates-cq\s*$", document):
            body = document.split("\n      flavors:\n", 1)
            if len(body) == 2:
                return re.findall(r"(?m)^        - name: ([A-Za-z0-9][A-Za-z0-9.-]*)\s*$", body[1])
    raise ValueError("no gates-cq flavor list found in " + path)


def gate_arches(path):
    with open(path) as f:
        for line in f:
            fields = line.split()
            if fields[:2] == ["gate", "gate"] and len(fields) >= 3:
                return set(fields[2].split(","))
    raise ValueError("no `gate gate` line in " + path)


cq = load("cq.json")
nodes = load("nodes.json")["items"]
flavor_labels = {f["metadata"]["name"]: (f.get("spec", {}).get("nodeLabels") or {})
                 for f in load("flavors.json")["items"]}
groups = cq.get("spec", {}).get("resourceGroups", [])
index = next((i for i, g in enumerate(groups) if "cpu" in g.get("coveredResources", [])), None)
if index is None:
    print("FATAL gates-cq has no resource group covering cpu")
    sys.exit(1)
live = groups[index]["flavors"]
live_names = [f["name"] for f in live]
by_name = {f["name"]: f for f in live}
lane_node = {n: flavor_labels[n][HOST] for n in live_names if HOST in flavor_labels.get(n, {})}
front = [n for n in live_names if n not in lane_node]

try:
    committed = static_names(os.environ["GATE_LANE_STATIC_QUEUE_FILE"])
    arches = gate_arches(os.environ["GATE_LANE_ARCH_CONF"])
except (OSError, ValueError) as error:
    print(f"FATAL cannot read the static lane order or the gate architectures ({error}); changing nothing")
    sys.exit(1)
static_lanes = [n for n in committed if n in lane_node] + [n for n in live_names if n in lane_node and n not in committed]


def node_for(hostname):
    for n in nodes:
        if n["metadata"].get("labels", {}).get(HOST, n["metadata"]["name"]) == hostname:
            return n
    return None


def parse(message):
    fields = dict(part.split("=", 1) for part in message.split() if "=" in part)
    return fields.get("cpu.idle60"), fields.get("ci.slice.some.avg60")


readings = {}      # lane -> (idle, slice) when both are read
unread = []        # (node, reading, why)
ineligible = []
for lane in static_lanes:
    host = lane_node[lane]
    node = node_for(host)
    if node is None:
        unread += [(host, "cpu.idle60", "node not found"), (host, "ci.slice.some.avg60", "node not found")]
        continue
    arch = node["metadata"].get("labels", {}).get("kubernetes.io/arch")
    if arch not in arches:
        ineligible.append(lane)
        continue
    condition = next((c for c in node.get("status", {}).get("conditions", []) if c.get("type") == CONDITION), None)
    if condition is None:
        unread += [(host, "cpu.idle60", f"no {CONDITION} condition"), (host, "ci.slice.some.avg60", f"no {CONDITION} condition")]
        continue
    try:
        at = datetime.strptime(condition.get("lastHeartbeatTime", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        age = now - at
    except ValueError:
        age = None
    if age is None or age > stale:
        why = "heartbeat missing" if age is None else f"heartbeat {int(age)}s old"
        unread += [(host, "cpu.idle60", why), (host, "ci.slice.some.avg60", why)]
        continue
    idle_raw, slice_raw = parse(condition.get("message", ""))
    values = []
    for name, raw in (("cpu.idle60", idle_raw), ("ci.slice.some.avg60", slice_raw)):
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            unread.append((host, name, f"reading is {raw if raw is not None else 'absent'}"))
            values.append(None)
    if None not in values:
        readings[lane] = tuple(values)


def saturated(lane):
    idle, pressure = readings[lane]
    return idle < idle_max and pressure > slice_min


summary = " ".join(
    f"{lane_node[l]}(idle60={readings[l][0]},ci.slice.some.avg60={readings[l][1]},{'saturated' if saturated(l) else 'not-saturated'})"
    for l in static_lanes if l in readings)
summary += "".join(f" {lane_node[l]}(ineligible-architecture)" for l in ineligible)

for host, name, why in unread:
    print(f"UNREAD node={host} reading={name} why={why}")
if unread:
    desired_lanes, reason = static_lanes, "reading-unread:static-order"
else:
    free = [l for l in static_lanes if l in readings and not saturated(l)]
    full = [l for l in static_lanes if l in readings and saturated(l)]
    desired_lanes = free + full + ineligible
    reason = ("all-lanes-saturated:static-order" if not free and full else
              "steer-to-unsaturated" if free and full else "none-saturated:static-order")
desired = front + desired_lanes
print(f"DECISION {reason} readings[{summary.strip()}] live={','.join(live_names)} desired={','.join(desired)}")
if desired != live_names:
    patch = [
        {"op": "test", "path": "/metadata/resourceVersion", "value": cq["metadata"]["resourceVersion"]},
        {"op": "replace", "path": f"/spec/resourceGroups/{index}/flavors", "value": [by_name[n] for n in desired]},
    ]
    print(f"CHANGE gates-cq flavor order {','.join(live_names)} -> {','.join(desired)} because {reason} readings[{summary.strip()}]")
    print("PATCH " + json.dumps(patch))
PY

grep -E '^(UNREAD|DECISION|CHANGE|FATAL)' "$work/decision" | sed "s/^/${SCRIPT_NAME}: /" || true
[ "$status" = 0 ] || exit "$status"
[ "$DRY_RUN" = 0 ] || exit 0
patch="$(sed -n 's/^PATCH //p' "$work/decision")"
[ -n "$patch" ] || exit 0
kubectl patch clusterqueue gates-cq --type=json -p "$patch" >/dev/null \
  || { echo "${SCRIPT_NAME}: patching gates-cq failed; the next pass re-applies" >&2; exit 1; }
echo "${SCRIPT_NAME}: patched gates-cq flavor order"

#!/usr/bin/env bash
# reconcile-factory-budget-admit.sh: hold each factory node to a fixed number of
# factory sandbox pods. This is the TEMPORARY fixed factory-vs-CI CPU share
# (maintainer ruling 2026-11-08 ~14:3xZ: "OK, go with fixed CPU share, as a
# temporary workaround to a better solution"; mechanism approved by
# legacy-coordinator-agent, plan gmktec-factory-placement, research note 003).
# END CONDITION: replaced by the better solution, which stays a maintainer design
# item. Remove this reconciler, its role and the selector entry then.
#
# WHAT IT DOES, once per run (the timer runs it every ~30 s, on the server):
#   1. Reads the per-node budgets from FACTORY_BUDGET_FILE: one `<node> <budget>`
#      per line, rendered by the factory_budget_reconciler Ansible role from each
#      ci_pool host's `factory_pod_budget`. That host_vars value is the ONE source
#      of truth. A factory node with no line gets budget 0.
#   2. Counts, per node, the factory sandbox pods bound to it: label
#      app.kubernetes.io/managed-by=sandbox-driver-kubernetes, in any namespace
#      (so the fleet, candidate and mi-homelab instances all count), excluding the
#      driver's cleanup pods (label sandbox-driver-kubernetes/cleanup-of) and pods
#      that have ended (phase Succeeded or Failed). A terminating pod still counts:
#      it still holds its CPU.
#   3. Sets the node label ci-runner.io/factory-admit=true on every factory node
#      whose count is below its budget, and false on the rest. The sandbox driver's
#      node selector includes that label, so a NEW sandbox is placed only on an
#      admitted node.
#
# ONLY FIRST PLACEMENT IS GATED. sandbox-driver-kubernetes pins a sandbox's later
# pods (resume, recreate) and its cleanup pod to the node it already uses, with
# no node selector (src/pod.rs, v0.8.2). The gate never strands a running run.
#
# FAIL OPEN, NEVER A PENDING SANDBOX. A first-placement pod that no node admits
# waits for the driver's start timeout (600 s) and then fails sandbox start, which
# counts as an infrastructure failure. So when EVERY factory node is at or over
# its budget, the node with the most headroom (budget minus count, then the most
# allocatable cpu, then the name) stays admitted, and the cycle logs OVERFLOW.
# An OVERFLOW line means the launch cap exceeds the sum of the budgets, or pods
# the launcher does not count are running. Keep the launch cap at or below the sum.
#
# KILL SWITCH. FACTORY_BUDGET_GATE=off (committed in the .service unit) sets
# admit=true on every factory node: the gate opens with no Fabro restart.
#
# FAIL SAFE. If the budget file is missing or unreadable, or a node or pod read
# fails, the cycle changes nothing and exits non-zero.
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
export FACTORY_BUDGET_FILE="${FACTORY_BUDGET_FILE:-/etc/livespec/factory-pod-budgets.conf}"
export FACTORY_BUDGET_GATE="${FACTORY_BUDGET_GATE:-on}"
ADMIT_LABEL=ci-runner.io/factory-admit

case "$FACTORY_BUDGET_GATE" in
  on|off) ;;
  *) die "FACTORY_BUDGET_GATE must be on or off, not '${FACTORY_BUDGET_GATE}'; changing nothing" ;;
esac
if [ "$FACTORY_BUDGET_GATE" = on ]; then
  [ -r "$FACTORY_BUDGET_FILE" ] \
    || die "cannot read the budget file ${FACTORY_BUDGET_FILE}; changing nothing this cycle"
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

kubectl get nodes -l ci-runner.io/factory=true -o json >"$work/nodes.json" \
  || die "could not list the factory nodes; changing nothing this cycle"
kubectl get pods --all-namespaces -l app.kubernetes.io/managed-by=sandbox-driver-kubernetes -o json \
  >"$work/pods.json" || die "could not list the sandbox pods; changing nothing this cycle"

python3 - "$work" >"$work/decision" <<'PY'
import json, os, sys

work = sys.argv[1]
gate = os.environ["FACTORY_BUDGET_GATE"]
ADMIT = "ci-runner.io/factory-admit"
CLEANUP = "sandbox-driver-kubernetes/cleanup-of"


def load(name):
    with open(os.path.join(work, name)) as f:
        return json.load(f)


def cpu_millis(value):
    value = str(value)
    if value.endswith("m"):
        return int(value[:-1])
    return int(float(value) * 1000)


# A container worker (homelab-worker.livespec.dev/class=worker) has no host_vars
# file, so it takes the class-wide budget the `@container-worker <n>` line names
# unless a per-node line names it (plan homelab-k8s-worker-nodes, ko26ez.7).
WORKER_CLASS = "homelab-worker.livespec.dev/class"
CLASS_LINE = "@container-worker"
budgets = {}
worker_budget = 0
if gate == "on":
    with open(os.environ["FACTORY_BUDGET_FILE"]) as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            name, value = line.split()
            if name == CLASS_LINE:
                worker_budget = int(value)
            else:
                budgets[name] = int(value)

nodes = load("nodes.json")["items"]
counts = {n["metadata"]["name"]: 0 for n in nodes}
for pod in load("pods.json")["items"]:
    labels = pod["metadata"].get("labels") or {}
    if CLEANUP in labels:
        continue
    if (pod.get("status") or {}).get("phase") in ("Succeeded", "Failed"):
        continue
    node = (pod.get("spec") or {}).get("nodeName")
    if node in counts:
        counts[node] += 1

rows = []
for n in nodes:
    name = n["metadata"]["name"]
    node_labels = n["metadata"].get("labels") or {}
    current = node_labels.get(ADMIT)
    default = worker_budget if node_labels.get(WORKER_CLASS) == "worker" else 0
    budget = budgets.get(name, default)
    alloc = cpu_millis(n["status"]["allocatable"]["cpu"])
    arch = node_labels.get("kubernetes.io/arch", "")
    rows.append({"name": name, "count": counts[name], "budget": budget, "alloc": alloc,
                 "current": current, "arch": arch})

if gate == "off":
    for r in rows:
        r["admit"] = "true"
    print("GATE off: every factory node admitted (kill switch)")
else:
    for r in rows:
        r["admit"] = "true" if r["count"] < r["budget"] else "false"
    # A sandbox selects one architecture, so the fail-open overflow is judged per
    # architecture: a full amd64 fleet is never relieved by an arm64 worker.
    for arch in sorted({r["arch"] for r in rows}):
        group = [r for r in rows if r["arch"] == arch]
        if all(r["admit"] == "false" for r in group):
            best = max(group, key=lambda r: (r["budget"] - r["count"], r["alloc"], r["name"]))
            best["admit"] = "true"
            print(
                "OVERFLOW every %s factory node is at or over budget; keeping %s admitted "
                "(count=%d budget=%d) so no sandbox waits out its start timeout"
                % (arch or "unlabelled", best["name"], best["count"], best["budget"])
            )

for r in sorted(rows, key=lambda r: r["name"]):
    print("ADMIT node=%s count=%d budget=%d admit=%s was=%s"
          % (r["name"], r["count"], r["budget"], r["admit"], r["current"]))
    if r["admit"] != r["current"]:
        print("LABEL %s %s" % (r["name"], r["admit"]))
PY

grep -v '^LABEL ' "$work/decision" | sed "s/^/${SCRIPT_NAME}: /"
while read -r verb node value; do
  [ "$verb" = LABEL ] || continue
  if [ "$DRY_RUN" = 1 ]; then
    echo "${SCRIPT_NAME}: dry-run: would set ${ADMIT_LABEL}=${value} on ${node}"
  else
    kubectl label node "$node" "${ADMIT_LABEL}=${value}" --overwrite >/dev/null
    echo "${SCRIPT_NAME}: set ${ADMIT_LABEL}=${value} on ${node}"
  fi
done <"$work/decision"

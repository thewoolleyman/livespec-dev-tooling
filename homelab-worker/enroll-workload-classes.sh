#!/usr/bin/env bash
# enroll-workload-classes.sh <node> — enroll a joined container worker in every
# workload class whose images publish its architecture, the way the fleet's
# existing nodes are enrolled, with no per-host file (SPECIFICATION/
# non-functional-requirements.md, "Homelab worker nodes": automatic enrollment
# by workload class, derived per-class capacity; livespec-dev-tooling-ko26ez.7).
# join-worker.sh calls it once the Node is registered; a rerun converges.
#
# Reads the Node's kubernetes.io/arch label and allocatable CPU with the
# caller's kubectl, and the one declared per-class architecture list
# (ci-runner/k3s/phase2/workload-arch.conf; WORKLOAD_ARCH_CONF overrides):
# Each class the node is enrolled in gets an equal share of its allocatable
# CPU: one third when all three classes declare its architecture, and a class
# that does not declare it lends its share to the enrolled ones rather than
# leaving it idle (one half each for two classes, all of it for one).
#   - CI: when any scale-set release declares the node's architecture, the node
#     gets k3s-role=arc-runner-host (the label the churn-slot ResourceFlavor
#     selects) and a ci-runner.io/churn-slot capacity derived from its CI
#     share at about 2.73 CPUs per slot (the fleet's sizing rule,
#     ci-runner/k3s/phase2/kueue/DERIVATION.md), at least one.
#   - factory: when the factory class declares it, ci-runner.io/factory=true.
#   - gate: when any gate line declares it (the default or a repository's own),
#     the node gets homelab-worker.livespec.dev/gate-share-millicores, its
#     gate share; ci-runner/k3s/phase2/kueue/converge-worker-queues.sh turns
#     that into whole gates on the worker flavor it adds to gates-cq.
# A class that does not declare the node's architecture is NOT enrolled, its
# enrollment is removed if present, and it is named with what it lacks.
# Only a node carrying homelab-worker.livespec.dev/class=worker is touched.
set -euo pipefail

prog="enroll-workload-classes"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
conf="${WORKLOAD_ARCH_CONF:-$here/../ci-runner/k3s/phase2/workload-arch.conf}"
worker_queues="${WORKER_QUEUES_CONVERGE:-$here/../ci-runner/k3s/phase2/kueue/converge-worker-queues.sh}"
# The fleet sizes one churn slot at about 2.73 CPUs (DERIVATION.md); millicores.
slot_millicores=2730

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}
say() { printf '%s: %s\n' "$prog" "$*"; }

[ "$#" -eq 1 ] || die "usage: enroll-workload-classes.sh <node>"
node="$1"
[ -s "$conf" ] || die "the workload architecture list $conf is missing"

# node_field <jsonpath>: one field of the Node, or die naming the read. A bare
# `$(kubectl ...)` under set -e exits silently when kubectl fails (measured
# 2026-11-08: a dropped tailscale ssh hop ended the first live run with no
# message), so every read goes through here.
node_field() {
  kubectl get node "$node" -o "jsonpath=$1" ||
    die "could not read $1 of Node $node through kubectl; the cluster was not reached, nothing was changed"
}

class="$(node_field '{.metadata.labels.homelab-worker\.livespec\.dev/class}')"
[ "$class" = worker ] || die "Node $node is not a container worker (no homelab-worker.livespec.dev/class=worker label); refusing to change its enrollment"
arch="$(node_field '{.metadata.labels.kubernetes\.io/arch}')"
[ -n "$arch" ] || die "Node $node reports no kubernetes.io/arch label"
cpu="$(node_field '{.status.allocatable.cpu}')"
case "$cpu" in
  *m) millicores="${cpu%m}" ;;
  '' | *[!0-9]*) die "Node $node reports allocatable cpu '$cpu', which is not a CPU quantity" ;;
  *) millicores=$((cpu * 1000)) ;;
esac

# declares <kind> [<name>]: 0 when a matching line lists $arch among its arches.
declares() {
  awk -v k="$1" -v n="${2:-}" -v a="$arch" '
    $1 == k && (n == "" || $2 == n) { split($3, xs, ","); for (i in xs) if (xs[i] == a) found = 1 }
    END { exit !found }' "$conf"
}
# lacks <kind> <name>: what the line says the other architectures lack.
lacks() {
  awk -v k="$1" -v n="$2" '$1 == k && $2 == n { $1 = $2 = $3 = ""; sub(/^ +/, ""); print; exit }' "$conf"
}

# The enrolled classes, decided before any write so each one's share is known.
ci=0 gate=0 factory=0
declares release && ci=1
declares gate && gate=1
declares factory python-agent && factory=1
enrolled=$((ci + gate + factory))
share=$((millicores / (enrolled > 0 ? enrolled : 1)))
slots=$((share / slot_millicores))
[ "$slots" -ge 1 ] || slots=1

if [ "$ci" -eq 1 ]; then
  kubectl label node "$node" k3s-role=arc-runner-host --overwrite >/dev/null
  kubectl patch node "$node" --subresource=status --type=merge \
    -p "{\"status\":{\"capacity\":{\"ci-runner.io/churn-slot\":\"$slots\"}}}" >/dev/null
  say "CI: enrolled with $slots churn slots (share ${share}m of ${millicores}m allocatable CPU across $enrolled enrolled classes)"
else
  kubectl label node "$node" k3s-role- >/dev/null 2>&1 || true
  say "CI: NOT enrolled: no scale set in $(basename "$conf") declares $arch"
fi

if [ "$gate" -eq 1 ]; then
  kubectl label node "$node" "homelab-worker.livespec.dev/gate-share-millicores=$share" --overwrite >/dev/null
  say "gate: enrolled (share ${share}m CPU)"
else
  kubectl label node "$node" homelab-worker.livespec.dev/gate-share-millicores- >/dev/null 2>&1 || true
  say "gate: NOT enrolled: $(lacks gate gate)"
fi

# The worker queues' quota is the enrolled workers' churn slots and gate shares,
# so enrolling or un-enrolling reconciles it in the same operation (v154).
"$worker_queues"

if [ "$factory" -eq 1 ]; then
  kubectl label node "$node" ci-runner.io/factory=true --overwrite >/dev/null
  say "factory: enrolled (share ${share}m CPU)"
else
  kubectl label node "$node" ci-runner.io/factory- >/dev/null 2>&1 || true
  say "factory: NOT enrolled: $(lacks factory python-agent)"
fi

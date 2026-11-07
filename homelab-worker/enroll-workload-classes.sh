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
#   - CI: when any scale-set release declares the node's architecture, the node
#     gets k3s-role=arc-runner-host (the label the churn-slot ResourceFlavor
#     selects) and a ci-runner.io/churn-slot capacity derived from its
#     allocatable CPU: one third of it, at about 2.73 CPUs per slot (the fleet's
#     sizing rule, ci-runner/k3s/phase2/kueue/DERIVATION.md), at least one.
#   - factory: when the factory class declares it, ci-runner.io/factory=true.
#   - gate: when the gate class declares it, the class label the gates worker
#     flavor selects is already on every worker; eligibility is reported.
# A class that does not declare the node's architecture is NOT enrolled, its
# enrollment is removed if present, and it is named with what it lacks.
# Only a node carrying homelab-worker.livespec.dev/class=worker is touched.
set -euo pipefail

prog="enroll-workload-classes"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
conf="${WORKLOAD_ARCH_CONF:-$here/../ci-runner/k3s/phase2/workload-arch.conf}"
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

class="$(kubectl get node "$node" -o jsonpath='{.metadata.labels.homelab-worker\.livespec\.dev/class}')"
[ "$class" = worker ] || die "Node $node is not a container worker (no homelab-worker.livespec.dev/class=worker label); refusing to change its enrollment"
arch="$(kubectl get node "$node" -o jsonpath='{.metadata.labels.kubernetes\.io/arch}')"
[ -n "$arch" ] || die "Node $node reports no kubernetes.io/arch label"
cpu="$(kubectl get node "$node" -o jsonpath='{.status.allocatable.cpu}')"
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

share=$((millicores / 3))
slots=$((share / slot_millicores))
[ "$slots" -ge 1 ] || slots=1

if declares release; then
  kubectl label node "$node" k3s-role=arc-runner-host --overwrite >/dev/null
  kubectl patch node "$node" --subresource=status --type=merge \
    -p "{\"status\":{\"capacity\":{\"ci-runner.io/churn-slot\":\"$slots\"}}}" >/dev/null
  say "CI: enrolled with $slots churn slots (one third of ${millicores}m allocatable CPU)"
else
  kubectl label node "$node" k3s-role- >/dev/null 2>&1 || true
  say "CI: NOT enrolled: no scale set in $(basename "$conf") declares $arch"
fi

if declares factory python-agent; then
  kubectl label node "$node" ci-runner.io/factory=true --overwrite >/dev/null
  say "factory: enrolled (share ${share}m CPU)"
else
  kubectl label node "$node" ci-runner.io/factory- >/dev/null 2>&1 || true
  say "factory: NOT enrolled: $(lacks factory python-agent)"
fi

if declares gate gate; then
  say "gate: eligible (share ${share}m CPU)"
else
  say "gate: NOT enrolled: $(lacks gate gate)"
fi

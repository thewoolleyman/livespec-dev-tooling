#!/usr/bin/env bash
# lift-admission-hold.sh <host>
# — lift the admission hold from <host>'s joined homelab worker, in the
# cluster the caller's `kubectl` reaches. This is the separate, explicit
# operator action of SPECIFICATION/non-functional-requirements.md, "Homelab
# worker nodes", "Standard bootstrap under an admission hold": the worker's
# kubelet registers its Node with the taint
# homelab-worker.livespec.dev/admission=hold:NoSchedule
# (image/systemd/kubelet.service, --register-with-taints), and neither the
# start task nor join-worker.sh lifts it. It needs kubectl only, no limactl.
#
#   1. Nothing is changed unless the Node exists, carries the label
#      homelab-worker.livespec.dev/class=worker, reports Ready=True and is not
#      cordoned. A cordon is a different hold with its own committed lift
#      (ansible/k3s-window-drain.yml, action `uncordon`); this script lifts
#      one hold and must not look as though it lifted both.
#   2. Exactly the admission hold taint is removed. The permanent class taint
#      homelab-worker.livespec.dev/class=worker:NoSchedule is never touched.
#      A Node that does not carry the hold is reported and left alone.
#   3. The taints are read back: the hold must be gone and the class taint
#      still there.
#
# Enrollment and the worker queues are not converged here: join-worker.sh
# already enrolled the worker, and that enrollment takes effect once this
# hold is lifted.
set -euo pipefail

prog="lift-admission-hold"
hw="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
hold="homelab-worker.livespec.dev/admission=hold:NoSchedule"
class_taint="homelab-worker.livespec.dev/class=worker:NoSchedule"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

say() {
  printf '%s: %s\n' "$prog" "$*"
}

usage="usage: $prog <host>"
[ "$#" -eq 1 ] || die "$usage"
host="$1"
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
worker="$host-homelab-worker"

# read_taints <when>: the Node's taints, one <key>=<value>:<effect> per line,
# or die naming the read. A bare `$(kubectl ...)` under set -e exits silently
# when kubectl fails, so every read is checked.
read_taints() {
  kubectl get node "$worker" \
    -o 'jsonpath={range .spec.taints[*]}{.key}={.value}:{.effect}{"\n"}{end}' ||
    die "could not read the taints of Node $worker through kubectl; $1"
}

# --ignore-not-found makes an absent Node an empty answer rather than a failure.
node="$(kubectl get node "$worker" --ignore-not-found \
  -o 'jsonpath={.metadata.name}|{.metadata.labels.homelab-worker\.livespec\.dev/class}|{.status.conditions[?(@.type=="Ready")].status}|{.spec.unschedulable}')" ||
  die "could not read Node $worker through kubectl; the cluster was not reached, nothing was changed"
IFS='|' read -r name class ready unschedulable <<<"$node"
[ "$name" = "$worker" ] ||
  die "Node $worker is not registered; join it first (homelab-worker/join-worker.sh $host ...). Nothing was changed"
[ "$class" = worker ] ||
  die "Node $worker is not a container worker (no homelab-worker.livespec.dev/class=worker label); refusing to change its taints. Nothing was changed"
[ "$ready" = True ] ||
  die "Node $worker is not Ready (its Ready condition is '${ready:-absent}'); the hold stays until the node is healthy. Nothing was changed"
[ "$unschedulable" != true ] ||
  die "Node $worker is cordoned; a cordon is a separate hold, lifted by ansible/k3s-window-drain.yml action uncordon. Lift that first, so this run lifts one hold only. Nothing was changed"

taints="$(read_taints "nothing was changed")"
if ! grep -qxF "$hold" <<<"$taints"; then
  say "Node $worker does not carry the admission hold ($hold); nothing to lift"
  exit 0
fi

kubectl taint node "$worker" "$hold-" >/dev/null ||
  die "could not remove $hold from Node $worker"

taints="$(read_taints "the hold's removal was requested but could not be verified")"
! grep -qxF "$hold" <<<"$taints" ||
  die "Node $worker still carries $hold after its removal was requested"
grep -qxF "$class_taint" <<<"$taints" ||
  die "Node $worker no longer carries its permanent class taint $class_taint after the hold was lifted; this script does not remove it, restore it before the node takes work"
say "admission hold lifted from Node $worker ($hold removed); the class taint $class_taint is kept"
say "the worker's workload-class enrollment now takes effect"

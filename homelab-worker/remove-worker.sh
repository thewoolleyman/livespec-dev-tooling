#!/usr/bin/env bash
# remove-worker.sh <host> [--state-root <dir>]
# — remove <host>'s homelab worker from the cluster the caller's `kubectl`
# reaches, so that the next join-worker.sh run is a fresh enrollment. The
# counterpart of join-worker.sh: run it on the worker's macOS host, from a
# clone of this repository, with the same kubectl and limactl.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes".
#
# Deleting the Node object alone is not a removal: the worker's kubelet keeps
# its node credentials under <state-root>/kubelet and registers the Node again
# at once, after which join-worker.sh takes its "already registered" path (no
# token mint, no serving-CSR wait). So, in this order:
#
#   1. Nothing is changed unless the Node, when it exists, is cordoned, and no
#      pod other than a DaemonSet's is running or pending on it. Cordoning is
#      a separate committed step (ansible/k3s-window-drain.yml, action
#      `cordon`); this script never evicts, drains or strands running work.
#      The VM must answer too, so a removal never deletes a Node whose kubelet
#      it could not stop.
#   2. The kubelet is stopped inside the worker container. An absent or
#      stopped container has no kubelet to stop.
#   3. The Node object is deleted, if present.
#   4. In the VM, under --state-root (default /mnt/lima-hwdata/worker), only
#      what makes a rejoin take the fresh path is cleared:
#        kubelet/kubeconfig              the node kubeconfig (kubelet.service,
#                                        --kubeconfig=/var/lib/kubelet/kubeconfig)
#        kubelet/pki                     the kubelet's client and serving
#                                        certificates (kubelet.service sets no
#                                        --cert-dir, so the kubelet's default,
#                                        /var/lib/kubelet/pki)
#        enrollment/bootstrap-kubeconfig the delivered enrollment
#        enrollment/client-ca.crt
#      containerd/, the rest of kubelet/, tailscale/, telemetry/, ci/,
#      factory/, enrollment/kubelet-config.yaml and enrollment/kubelet.env are
#      kept. Without client-ca.crt the next converge does not start the
#      kubelet, and a kubelet that systemd starts on a container restart finds
#      no credentials to register with.
#   5. The worker queues are converged again, so the quota derived from
#      enrolled worker Nodes drops with the worker.
#
# Every step is idempotent: a rerun after a partial failure converges, and a
# rerun for a worker already removed clears and converges again.
set -euo pipefail

prog="remove-worker"
hw="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
worker_queues="${WORKER_QUEUES_CONVERGE:-$hw/../ci-runner/k3s/phase2/kueue/converge-worker-queues.sh}"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

say() {
  printf '%s: %s\n' "$prog" "$*"
}

usage="usage: $prog <host> [--state-root <dir>]"
[ "$#" -ge 1 ] || die "$usage"
host="$1"
shift
state_root="/mnt/lima-hwdata/worker"
state_root_given=0
while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] || die "$1 needs a value; $usage"
  case "$1" in
    --state-root)
      state_root="$2"
      state_root_given=1
      ;;
    *) die "unknown argument '$1'; $usage" ;;
  esac
  shift 2
done
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
case "$state_root" in
  /?*) ;;
  *) die "state root '$state_root' is not an absolute directory path" ;;
esac
state_root="${state_root%/}"
worker="$host-homelab-worker"

in_vm() {
  limactl shell --workdir / "$worker" sudo "$@"
}

# --- reads: every one is checked, and nothing is changed before they pass ---
# A bare `$(kubectl ...)` under set -e exits silently when kubectl fails, so
# each read dies naming itself. --ignore-not-found makes an absent Node an
# empty answer rather than a failure.
node="$(kubectl get node "$worker" --ignore-not-found \
  -o 'jsonpath={.metadata.name} {.spec.unschedulable}')" ||
  die "could not read Node $worker through kubectl; the cluster was not reached, nothing was changed"
node_present=0
case "$node" in
  "$worker "*)
    node_present=1
    [ "${node#* }" = true ] ||
      die "Node $worker is not cordoned; cordon it first (ansible/k3s-window-drain.yml, action cordon) and let its work finish. Nothing was changed"
    ;;
esac

pods="$(kubectl get pods --all-namespaces --field-selector "spec.nodeName=$worker" \
  -o 'jsonpath={range .items[*]}{.metadata.namespace}/{.metadata.name} {.status.phase} {.metadata.ownerReferences[*].kind}{"\n"}{end}')" ||
  die "could not read the pods on Node $worker through kubectl; the cluster was not reached, nothing was changed"
busy="$(printf '%s\n' "$pods" | awk '
  $2 == "Running" || $2 == "Pending" {
    ds = 0
    for (i = 3; i <= NF; i++) if ($i == "DaemonSet") ds = 1
    if (!ds) printf "%s%s", (n++ ? " " : ""), $1
  }')"
[ -z "$busy" ] ||
  die "Node $worker still has running or pending pods that no DaemonSet owns: $busy. Let them finish or move them first. Nothing was changed"

in_vm true ||
  die "could not reach VM $worker through limactl, so its kubelet cannot be stopped; nothing was changed"

# --- writes ------------------------------------------------------------------
if running="$(in_vm docker inspect -f '{{.State.Running}}' "$worker" 2>/dev/null)" && [ "$running" = true ]; then
  in_vm docker exec "$worker" systemctl stop kubelet ||
    die "could not stop the kubelet in container $worker; the Node was not deleted and no credential was cleared"
  say "kubelet stopped in container $worker"
else
  say "container $worker is absent or stopped; no kubelet to stop"
fi

if [ "$node_present" = 1 ]; then
  kubectl delete node "$worker" --wait --ignore-not-found >/dev/null ||
    die "could not delete Node $worker; no credential was cleared"
  say "Node $worker deleted"
else
  say "Node $worker is not registered; nothing to delete"
fi

in_vm rm -rf -- \
  "$state_root/kubelet/kubeconfig" \
  "$state_root/kubelet/pki" \
  "$state_root/enrollment/bootstrap-kubeconfig" \
  "$state_root/enrollment/client-ca.crt" ||
  die "could not clear the node credentials under $state_root in VM $worker; run $prog again"
say "cleared the kubelet's node credentials (kubelet/kubeconfig, kubelet/pki) and the delivered enrollment (enrollment/bootstrap-kubeconfig, enrollment/client-ca.crt) under $state_root in VM $worker; all other worker state is kept"

"$worker_queues" ||
  die "the worker-queue converge ($worker_queues) failed; the worker is removed, run $prog again to reconcile the queues"
say "worker queues converged without $worker"

rejoin="homelab-worker/join-worker.sh $host --api-server <url> --server-ca <file>"
[ "$state_root_given" = 0 ] || rejoin="$rejoin --state-root $state_root"
say "worker $worker is removed. To rejoin it as a fresh enrollment:"
say "  $rejoin"
say "The rejoined worker registers under the admission hold; homelab-worker/lift-admission-hold.sh $host lifts it."

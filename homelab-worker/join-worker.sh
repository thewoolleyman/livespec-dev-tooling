#!/usr/bin/env bash
# join-worker.sh <host> --api-server <url> --server-ca <file>
#                [--cluster-config <file>] [--state-root <dir>] [--worker-network <net>]
# — enroll <host>'s homelab worker into the cluster the caller's `kubectl`
# reaches, the production join sequence. Run it on the worker's macOS host,
# from a clone of this repository, after the start task has converged the VM.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes". Design: plan/homelab-k8s-worker-nodes/research/008 §4.
#
#   1. enrollment/rbac.yaml, the worker networking agents and the per-cluster
#      ConfigMap (--cluster-config, default networking/cluster.yaml) are
#      applied with the caller's kubectl.
#   2. A bootstrap token is minted against --api-server, pinned to
#      --server-ca, and the enrollment is delivered into the VM on stdin,
#      never in an argument, under --state-root (default
#      /mnt/lima-hwdata/worker).
#   3. The worker container converges (on --worker-network when given, else
#      as a home-LAN node at the host's declared WORKER_LAN_ADDRESS),
#      registers its Node, and its serving CSR is approved by
#      approve-serving-csr.sh.
#
# A rerun for a worker whose Node is already registered mints and delivers
# nothing: it reconciles the container and approves any pending serving CSR
# once, without waiting for one.
#
# WAIT_SECONDS (default 300) bounds each wait for the Node and its CSR.
set -euo pipefail

prog="join-worker"
hw="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
wait_seconds="${WAIT_SECONDS:-300}"
poll="${POLL_SECONDS:-5}"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

say() {
  printf '%s: %s\n' "$prog" "$*"
}

usage="usage: $prog <host> --api-server <url> --server-ca <file> [--cluster-config <file>] [--state-root <dir>] [--worker-network <net>]"
[ "$#" -ge 1 ] || die "$usage"
host="$1"
shift
api_server=""
server_ca=""
cluster_config="$hw/networking/cluster.yaml"
state_root="/mnt/lima-hwdata/worker"
worker_network=""
worker_network_given=0
while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] || die "$1 needs a value; $usage"
  case "$1" in
    --api-server) api_server="$2" ;;
    --server-ca) server_ca="$2" ;;
    --cluster-config) cluster_config="$2" ;;
    --state-root) state_root="$2" ;;
    --worker-network)
      worker_network="$2"
      worker_network_given=1
      ;;
    *) die "unknown argument '$1'; $usage" ;;
  esac
  shift 2
done
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
[ -n "$api_server" ] || die "--api-server is required; $usage"
[ -n "$server_ca" ] || die "--server-ca is required; $usage"
[ -f "$server_ca" ] || die "server CA '$server_ca' is not a file"
[ -f "$cluster_config" ] || die "cluster config '$cluster_config' is not a file"
# Without --worker-network the worker converges as a home-LAN node at its
# host's declared static address, as the start task does (spec v143).
if [ "$worker_network_given" = 0 ]; then
  lan="$(sed -n 's/^WORKER_LAN_ADDRESS=//p' "$hosts_dir/$host.env" | tail -n 1)"
  [ -z "$lan" ] || worker_network="host:${lan%/*}"
fi
worker="$host-homelab-worker"
image="$(grep -v '^#' "$hw/image/ref" | sed -n 1p)"

in_vm() {
  limactl shell --workdir / "$worker" sudo "$@"
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
chmod 0700 "$tmp"

say "applying enrollment RBAC, the worker networking agents and the cluster config"
kubectl apply -f - <"$hw/enrollment/rbac.yaml" >/dev/null
for f in flannel kube-proxy kube-router; do
  kubectl apply -f - <"$hw/networking/$f.yaml" >/dev/null
done
kubectl apply -f - <"$cluster_config" >/dev/null

converge() {
  # shellcheck disable=SC2086 # an empty worker_network adds no argument
  in_vm bash -s -- "$worker" "$host" "$image" "$state_root" $worker_network <"$hw/vm/converge-worker-container.sh"
}

if kubectl get node "$worker" >/dev/null 2>&1; then
  say "Node $worker is already registered; reconciling its container without a new enrollment"
  converge
  "$hw/enrollment/approve-serving-csr.sh" "$host"
  kubectl get nodes -o wide
  exit 0
fi

"$hw/enrollment/mint-bootstrap-token.sh" "$host" "$api_server" "$server_ca" "$tmp/enrollment"

converge
for f in bootstrap-kubeconfig client-ca.crt; do
  in_vm install -m 0600 /dev/stdin "$state_root/enrollment/$f" <"$tmp/enrollment/$f"
done
say "enrollment delivered to $state_root/enrollment in VM $worker"
converge

waited=0
until kubectl get node "$worker" >/dev/null 2>&1; do
  [ "$waited" -lt "$wait_seconds" ] || die "Node $worker did not register within ${wait_seconds}s"
  sleep "$poll"
  waited=$((waited + poll))
done
say "Node $worker registered"

waited=0
until "$hw/enrollment/approve-serving-csr.sh" "$host" | grep '^approve-serving-csr: approved ' >/dev/null; do
  [ "$waited" -lt "$wait_seconds" ] || die "no serving CSR from $worker was approved within ${wait_seconds}s"
  sleep "$poll"
  waited=$((waited + poll))
done
say "serving certificate approved for $worker"
kubectl get nodes -o wide

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
#   4. The worker is enrolled in every workload class whose images publish its
#      architecture, by enroll-workload-classes.sh (livespec-dev-tooling-ko26ez.7);
#      a class that does not is named. It takes effect once the admission hold
#      is lifted, because the hold keeps every workload off the node until then.
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
enroll="${HOMELAB_WORKER_ENROLL:-$hw/enroll-workload-classes.sh}"

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

worker_pods() {
  kubectl get pods --all-namespaces --field-selector "spec.nodeName=$worker" \
    -o 'jsonpath={range .items[*]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}'
}

node_pod_cidr() {
  kubectl get node "$worker" -o 'jsonpath={.spec.podCIDR}'
}

flannel_subnet() {
  in_vm docker exec "$worker" awk -F= \
    '$1 == "FLANNEL_SUBNET" { print $2; exit }' /run/flannel/subnet.env
}

cidr_network() {
  local cidr="$1" address prefix a b c d bits mask octet network
  case "$cidr" in
    *.*.*.*/*) ;;
    *) return 1 ;;
  esac
  address="${cidr%/*}"
  prefix="${cidr##*/}"
  IFS=. read -r a b c d <<<"$address"
  for octet in "$a" "$b" "$c" "$d"; do
    [[ "$octet" =~ ^[0-9]+$ ]] || return 1
    [ "$octet" -le 255 ] || return 1
  done
  [[ "$prefix" =~ ^[0-9]+$ ]] || return 1
  [ "$prefix" -le 32 ] || return 1
  bits="$prefix"
  network=""
  for octet in "$a" "$b" "$c" "$d"; do
    if [ "$bits" -ge 8 ]; then
      mask=255
    elif [ "$bits" -le 0 ]; then
      mask=0
    else
      mask=$((256 - (1 << (8 - bits))))
    fi
    network="${network}${network:+.}$((10#$octet & mask))"
    bits=$((bits - 8))
  done
  printf '%s/%s\n' "$network" "$prefix"
}

wait_for_matching_pod_subnet() {
  local waited=0 node_cidr flannel_cidr node_network flannel_network
  while :; do
    node_cidr="$(node_pod_cidr)" ||
      die "could not read pod CIDR from Node $worker through kubectl"
    flannel_cidr="$(flannel_subnet)" ||
      die "could not read the flannel subnet from worker $worker"
    node_network="$(cidr_network "$node_cidr" || true)"
    flannel_network="$(cidr_network "$flannel_cidr" || true)"
    if [ -n "$node_network" ] && [ "$node_network" = "$flannel_network" ]; then
      say "Node $worker pod CIDR $node_cidr matches flannel subnet $flannel_cidr"
      return
    fi
    if [ "$waited" -ge "$wait_seconds" ]; then
      die "Node $worker pod CIDR ${node_cidr:-<empty>} and flannel subnet ${flannel_cidr:-<empty>} still differ after ${wait_seconds}s"
    fi
    sleep "$poll"
    waited=$((waited + poll))
  done
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

bridge_address() {
  in_vm docker exec "$worker" ip -4 -o addr show dev cni0 2>/dev/null |
    awk '{print $4}' | cut -d / -f 1 | sed -n 1p || true
}

refresh_pod_span_endpoint() {
  local bridge waited
  waited=0
  bridge="$(bridge_address)"
  until [ -n "$bridge" ]; do
    if [ "$waited" -ge "$wait_seconds" ]; then
      say "pod-span endpoint is not yet set: cni0 received no address within ${wait_seconds}s after Node registration"
      return
    fi
    sleep "$poll"
    waited=$((waited + poll))
    bridge="$(bridge_address)"
  done
  converge
  say "pod-span endpoint now uses cni0 at $bridge:4319"
}

if kubectl get node "$worker" >/dev/null 2>&1; then
  say "Node $worker is already registered; reconciling its container without a new enrollment"
  converge
  "$hw/enrollment/approve-serving-csr.sh" "$host"
  "$enroll" "$worker"
  kubectl get nodes -o wide
  exit 0
fi

stale_pods="$(worker_pods)" ||
  die "could not read pods bound to absent Node $worker through kubectl; no bootstrap credential was issued"
[ -z "$stale_pods" ] ||
  die "pods are still bound to absent Node $worker; no bootstrap credential was issued: $stale_pods"

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
wait_for_matching_pod_subnet
refresh_pod_span_endpoint

waited=0
until "$hw/enrollment/approve-serving-csr.sh" "$host" | grep '^approve-serving-csr: approved ' >/dev/null; do
  [ "$waited" -lt "$wait_seconds" ] || die "no serving CSR from $worker was approved within ${wait_seconds}s"
  sleep "$poll"
  waited=$((waited + poll))
done
say "serving certificate approved for $worker"
"$enroll" "$worker"
kubectl get nodes -o wide

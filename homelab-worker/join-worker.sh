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

# refresh_pod_span_endpoint: a final converge records the pod-span endpoint as
# the first usable address of the worker's flannel subnet (converge-worker-
# container.sh), with no wait for cni0 and no operator command; the join names
# the endpoint it recorded.
refresh_pod_span_endpoint() {
  local endpoint
  converge
  endpoint="$(in_vm cat "$state_root/telemetry/node.env" 2>/dev/null |
    sed -n 's/^OTLP_PODS_ENDPOINT=//p' | sed -n 1p || true)"
  if [ -n "$endpoint" ]; then
    say "pod-span endpoint recorded: $endpoint (the first usable address of the worker's flannel subnet)"
  else
    say "pod-span endpoint is not yet set: the worker has no flannel subnet or no delivered telemetry"
  fi
}

if kubectl get node "$worker" >/dev/null 2>&1; then
  say "Node $worker is already registered; reconciling its container without a new enrollment"
  converge
  "$hw/enrollment/approve-serving-csr.sh" "$host"
  "$enroll" "$worker"
  kubectl get nodes -o wide
  exit 0
fi

# A Node that does not exist yet must not find pods already bound to its name:
# they would keep the removed Node's pod subnet when the name registers again.
leftover="$(kubectl get pods --all-namespaces --field-selector "spec.nodeName=$worker" \
  -o 'jsonpath={range .items[*]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}' |
  awk 'NF { print $1 }')" ||
  die "could not read the pods bound to Node name $worker through kubectl; no token was minted"
[ -z "$leftover" ] ||
  die "Node $worker is not registered but pods bound to that name still exist: $(printf '%s' "$leftover" | tr '\n' ' '). Run homelab-worker/remove-worker.sh $host and wait for them to be gone; no token was minted"

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
refresh_pod_span_endpoint

# network_of: read "a.b.c.d/len" on stdin, print its network "a.b.c.0/len".
network_of() {
  awk -F'[./]' 'NF == 5 {
    ip = $1 * 16777216 + $2 * 65536 + $3 * 256 + $4
    block = 2 ^ (32 - $5)
    n = int(ip / block) * block
    printf "%d.%d.%d.%d/%d\n", int(n / 16777216) % 256, int(n / 65536) % 256, int(n / 256) % 256, n % 256, $5
  }'
}

# The pod CIDR the cluster assigned the Node must be the subnet the worker's
# flannel agent holds; a rejoined Node that kept an older subnet leaves the
# pod network split.
verify_pod_subnet() {
  local waited=0 cidr flannel subnet
  while :; do
    cidr="$(kubectl get node "$worker" -o 'jsonpath={.spec.podCIDR}' 2>/dev/null || true)"
    flannel="$(in_vm docker exec "$worker" cat /run/flannel/subnet.env 2>/dev/null |
      sed -n 's/^FLANNEL_SUBNET=//p' | sed -n 1p || true)"
    subnet=""
    [ -z "$flannel" ] || subnet="$(printf '%s\n' "$flannel" | network_of)"
    if [ -n "$cidr" ] && [ "$cidr" = "$subnet" ]; then
      say "pod CIDR $cidr of Node $worker matches the worker's flannel subnet"
      return
    fi
    [ "$waited" -lt "$wait_seconds" ] ||
      die "Node $worker's pod CIDR (${cidr:-unset}) and the worker's flannel subnet (${subnet:-${flannel:-unset}}) still differ after ${wait_seconds}s"
    sleep "$poll"
    waited=$((waited + poll))
  done
}
verify_pod_subnet

waited=0
until "$hw/enrollment/approve-serving-csr.sh" "$host" | grep '^approve-serving-csr: approved ' >/dev/null; do
  [ "$waited" -lt "$wait_seconds" ] || die "no serving CSR from $worker was approved within ${wait_seconds}s"
  sleep "$poll"
  waited=$((waited + poll))
done
say "serving certificate approved for $worker"
"$enroll" "$worker"
kubectl get nodes -o wide

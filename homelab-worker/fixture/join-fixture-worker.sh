#!/usr/bin/env bash
# join-fixture-worker.sh <host> [tailnet] — enroll <host>'s homelab worker into the
# isolated K3s fixture (k3s-fixture.sh) running in the same worker VM, through
# the same RBAC, token mint, networking agents, container step and serving-CSR
# approval production uses. Run it on the worker's macOS host, from a clone of
# this repository, after `k3s-fixture.sh up <mode>`.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes": "Reviewed cluster changes". Design:
# plan/homelab-k8s-worker-nodes/research/006 §3 (fixture stage one: the
# worker on the fixture's Docker network, no tailnet underlay).
#
#   1. kubectl is a shim that runs kubectl inside the fixture's server
#      container, so the host needs no kubectl and no kubeconfig.
#   2. enrollment/rbac.yaml and the networking agents are applied to the
#      fixture, with ConfigMap homelab-worker-cluster pointing them at the
#      fixture's server and flannel at the worker's eth0.
#   3. A bootstrap token is minted and the enrollment is delivered into the
#      VM on stdin, never in an argument. The worker's fixture state lives
#      under /mnt/lima-hwdata/fixture-worker, apart from its production state.
#   4. The worker container converges on the fixture network, registers its
#      Node, and its serving CSR is approved by approve-serving-csr.sh.
#
# A rerun for a worker whose Node is already registered mints and delivers
# nothing: it reconciles the container and approves any pending serving CSR
# once, without waiting for one.
#
# With `tailnet`, fixture stage two (research 007): the fixture's K3s nodes
# are on the tailnet advertising their own /32 (underlay-fixture.sh up), and
# the worker runs in production mode instead of on the fixture network. It
# logs in to the tailnet as <host>-homelab-worker under its production
# identity (the fixture root's tailscale/ is a link to the production one),
# accepts the nodes' routes, reaches the API server at the server node's
# fixture IP, and runs flannel over tailscale0. Start stage two from a fresh
# fixture (k3s-fixture.sh down, then up), so no stage-one worker remains.
#
# WAIT_SECONDS (default 300) bounds each wait for the Node and its CSR.
set -euo pipefail

prog="join-fixture-worker"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hw="$here/.."
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
network="k3d-hw-fixture"
server="k3d-hw-fixture-server-0"
state_root="/mnt/lima-hwdata/fixture-worker"
wait_seconds="${WAIT_SECONDS:-300}"
poll="${POLL_SECONDS:-5}"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

say() {
  printf '%s: %s\n' "$prog" "$*"
}

usage="usage: $prog <host> [tailnet]"
[ "$#" -eq 1 ] || [ "$#" -eq 2 ] || die "$usage"
host="$1"
mode="${2:-network}"
case "$mode" in
  network | tailnet) ;;
  *) die "mode '$mode' is not tailnet; $usage" ;;
esac
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
worker="$host-homelab-worker"
image="$(grep -v '^#' "$hw/image/ref" | head -n 1)"

in_vm() {
  limactl shell --workdir / "$worker" sudo "$@"
}

in_vm docker inspect -f '{{.State.Running}}' "$server" 2>/dev/null | grep -qx true ||
  die "fixture server $server is not running in VM $worker; run k3s-fixture.sh up first"

if [ "$mode" = "tailnet" ]; then
  api_host="$(in_vm docker inspect -f "{{(index .NetworkSettings.Networks \"$network\").IPAddress}}" "$server")"
  [ -n "$api_host" ] || die "fixture server $server has no address on network $network"
  flannel_iface="tailscale0"
  worker_network=""
else
  api_host="$server"
  flannel_iface="eth0"
  worker_network="$network"
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
chmod 0700 "$tmp"
mkdir "$tmp/bin"
cat >"$tmp/bin/kubectl" <<EOF
#!/usr/bin/env bash
exec limactl shell --workdir / "$worker" sudo docker exec -i "$server" kubectl "\$@"
EOF
chmod 0755 "$tmp/bin/kubectl"
PATH="$tmp/bin:$PATH"
export PATH

say "applying enrollment RBAC and the worker networking agents to the fixture"
kubectl apply -f - <"$hw/enrollment/rbac.yaml" >/dev/null
for f in flannel kube-proxy kube-router; do
  kubectl apply -f - <"$hw/networking/$f.yaml" >/dev/null
done
kubectl apply -f - >/dev/null <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: homelab-worker-cluster
  namespace: kube-system
  labels:
    homelab-worker.livespec.dev/networking: "true"
data:
  api-server-host: $api_host
  api-server-port: "6443"
  flannel-iface: $flannel_iface
EOF

converge() {
  # shellcheck disable=SC2086 # an empty worker_network adds no argument
  in_vm bash -s -- "$worker" "$host" "$image" "$state_root" $worker_network <"$hw/vm/converge-worker-container.sh"
}

if [ "$mode" = "tailnet" ]; then
  # The worker's tailnet identity is the production one; only kubelet,
  # containerd and enrollment state are the fixture's.
  in_vm sh -c "mkdir -p /mnt/lima-hwdata/worker/tailscale $state_root && { [ -L $state_root/tailscale ] || { [ ! -e $state_root/tailscale ] && ln -s /mnt/lima-hwdata/worker/tailscale $state_root/tailscale; }; }" ||
    die "$state_root/tailscale exists and is not the link to the production identity; run k3s-fixture.sh down first"
fi

if kubectl get node "$worker" >/dev/null 2>&1; then
  say "Node $worker is already registered; reconciling its container without a new enrollment"
  converge
  "$hw/enrollment/approve-serving-csr.sh" "$host"
  kubectl get nodes -o wide
  exit 0
fi

in_vm docker exec "$server" cat /var/lib/rancher/k3s/server/tls/server-ca.crt >"$tmp/server-ca.crt"
"$hw/enrollment/mint-bootstrap-token.sh" "$host" "https://$api_host:6443" "$tmp/server-ca.crt" "$tmp/enrollment"

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
until "$hw/enrollment/approve-serving-csr.sh" "$host" | grep -q '^approve-serving-csr: approved '; do
  [ "$waited" -lt "$wait_seconds" ] || die "no serving CSR from $worker was approved within ${wait_seconds}s"
  sleep "$poll"
  waited=$((waited + poll))
done
say "serving certificate approved for $worker"
kubectl get nodes -o wide

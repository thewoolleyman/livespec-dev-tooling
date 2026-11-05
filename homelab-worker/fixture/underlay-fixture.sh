#!/usr/bin/env bash
# underlay-fixture.sh <up|down> — fixture stage two: put each of hw-fixture's
# K3s node containers on the tailnet, advertising its own /32, the way
# Option A puts poweredge, gmktec and hp on it. Run it INSIDE the homelab
# worker's Linux VM, as root, after `k3s-fixture.sh up`:
#
#   limactl shell --workdir / <host>-homelab-worker sudo bash -s -- up <underlay-fixture.sh
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes": "Reviewed cluster changes". Design:
# plan/homelab-k8s-worker-nodes/research/007-fixture-stage-two-underlay-2026-11-05.md.
#
#   up    install the worker image's pinned Tailscale release (SHA-256
#         checked) into each node container and start an ephemeral tailscaled
#         (--state=mem:, so the tailnet drops the device once it goes
#         offline). Each node logs in interactively as the untagged member
#         hw-fixture-<node> and advertises <its fixture IP>/32, with route
#         acceptance off. The run prints each login URL and each route to
#         approve, and waits LOGIN_TIMEOUT seconds (default 900) for both.
#         A node already on the tailnet with its route approved is kept.
#   down  stop each node's tailscaled; its ephemeral device leaves the tailnet.
#
# The commands it runs are found on PATH, so it can be exercised off-host.
set -euo pipefail

prog="underlay-fixture"
cluster="hw-fixture"
nodes="k3d-$cluster-server-0 k3d-$cluster-agent-0"
network="k3d-$cluster"
ts_version="1.104.4"
ts_sha256_arm64="a1c249ce6bdebef62e1ae3b997595555bce2ae4709bf95a718e9ca7a129dad7e"
login_timeout="${LOGIN_TIMEOUT:-900}"
poll="${POLL_SECONDS:-5}"
sock="/run/tailscale/tailscaled.sock"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

say() {
  printf '%s: %s\n' "$prog" "$*"
}

usage="usage: $prog <up|down>"
[ "$#" -eq 1 ] || die "$usage"
action="$1"
case "$action" in
  up | down) ;;
  *) die "$usage" ;;
esac

vm="$(hostname)"
case "$vm" in
  *-homelab-worker) ;;
  *) die "this is $vm, not a homelab worker VM; the fixture runs only inside a <host>-homelab-worker VM" ;;
esac

for node in $nodes; do
  docker inspect -f '{{.State.Running}}' "$node" 2>/dev/null | grep -qx true ||
    die "fixture node $node is not running; run k3s-fixture.sh up first"
done

ts() {
  docker exec "$1" tailscale --socket="$sock" "${@:2}"
}

# field <node> <JSON key>: the first string value of that key in the node's
# `tailscale status --json`, or "".
field() {
  ts "$1" status --json 2>/dev/null | sed -n "s/^ *\"$2\": *\"\\([^\"]*\\)\".*/\\1/p" | head -n 1
}

route_approved() {
  ts "$1" status --json 2>/dev/null | tr -d ' \n' | grep -q "\"PrimaryRoutes\":\\[\"$2\""
}

if [ "$action" = "down" ]; then
  for node in $nodes; do
    if docker exec "$node" sh -c 'kill "$(cat /run/tailscale/tailscaled.pid)"' 2>/dev/null; then
      say "stopped tailscaled on $node; its ephemeral device leaves the tailnet"
    else
      say "no tailscaled running on $node"
    fi
  done
  exit 0
fi

[ "$(uname -m)" = "aarch64" ] || die "no pinned Tailscale checksum for architecture $(uname -m)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSLo "$tmp/tailscale.tgz" "https://pkgs.tailscale.com/stable/tailscale_${ts_version}_arm64.tgz"
echo "$ts_sha256_arm64  $tmp/tailscale.tgz" | sha256sum -c - >/dev/null ||
  die "Tailscale $ts_version download failed its pinned SHA-256"
tar -C "$tmp" -xzf "$tmp/tailscale.tgz"

pending=""
for node in $nodes; do
  name="hw-fixture-${node#k3d-"$cluster"-}"
  ip="$(docker inspect -f "{{(index .NetworkSettings.Networks \"$network\").IPAddress}}" "$node")"
  [ -n "$ip" ] || die "fixture node $node has no address on network $network"
  route="$ip/32"
  if [ "$(field "$node" BackendState)" = "Running" ] && route_approved "$node" "$route"; then
    say "$node is on the tailnet as $name with $route approved; keeping it"
    continue
  fi
  if ! docker exec "$node" test -S "$sock"; then
    docker cp "$tmp/tailscale_${ts_version}_arm64/tailscale" "$node:/bin/tailscale"
    docker cp "$tmp/tailscale_${ts_version}_arm64/tailscaled" "$node:/bin/tailscaled"
    docker exec --detach "$node" sh -c "mkdir -p /run/tailscale && echo \$\$ >/run/tailscale/tailscaled.pid && exec tailscaled --state=mem: --socket=$sock --tun=tailscale0"
    say "started ephemeral tailscaled on $node"
  fi
  docker exec --detach "$node" tailscale --socket="$sock" up --hostname="$name" --advertise-routes="$route" --accept-routes=false
  pending="$pending $node=$name=$route"
done

# Every pending node's login URL and route are shown on each poll, so the
# maintainer can approve them all in one pass rather than node by node.
shown=""
waited=0
while [ -n "$pending" ]; do
  remaining=""
  for entry in $pending; do
    node="${entry%%=*}"
    rest="${entry#*=}"
    name="${rest%%=*}"
    route="${rest#*=}"
    state="$(field "$node" BackendState)"
    if [ "$state" = "Running" ] && route_approved "$node" "$route"; then
      say "$node is on the tailnet as $name with $route approved"
      continue
    fi
    remaining="$remaining $entry"
    url="$(field "$node" AuthURL)"
    if [ -n "$url" ]; then
      case "$shown" in
        *" $url "*) ;;
        *)
          say "approve the tailnet login of $name: $url"
          shown="$shown $url "
          ;;
      esac
    fi
    if [ "$state" = "Running" ]; then
      case "$shown" in
        *" route:$route "*) ;;
        *)
          say "approve route $route for device $name in the Tailscale admin console"
          shown="$shown route:$route "
          ;;
      esac
    fi
  done
  pending="$remaining"
  [ -n "$pending" ] || break
  [ "$waited" -lt "$login_timeout" ] ||
    die "not every fixture node is on the tailnet with its route approved after ${login_timeout}s ($pending); approve them and run '$prog up' again"
  sleep "$poll"
  waited=$((waited + poll))
done

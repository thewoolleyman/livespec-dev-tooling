#!/usr/bin/env bash
# converge-lan-address — set a homelab worker VM's declared static home-LAN
# address on its Lima bridged interface. Run as root inside the worker VM by
# start-homelab-worker-node-container.sh:
#
#   converge-lan-address.sh <interface> <address/prefix>
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes": "Home-LAN node". Design: plan/homelab-k8s-worker-nodes/research/008
# §3. The address is static because a VM bridged over the host's Wi-Fi is seen
# by the router under the host's MAC and cannot be given a DHCP reservation.
#
# Idempotent: it rewrites and applies its netplan file only when the file's
# bytes differ. `netplan apply` returns before networkd has set the address,
# so it then waits up to ADDRESS_WAIT_SECONDS (default 60) for the interface
# to carry it, and refuses if it never does. NETPLAN_FILE overrides the file.
set -euo pipefail

prog="converge-lan-address"
plan="${NETPLAN_FILE:-/etc/netplan/60-homelab-worker-lan.yaml}"
wait_seconds="${ADDRESS_WAIT_SECONDS:-60}"
poll="${POLL_SECONDS:-1}"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

[ "$#" -eq 2 ] || die "usage: $prog <interface> <address/prefix>"
iface="$1"
cidr="$2"
case "$cidr" in
  */*) ;;
  *) die "address '$cidr' has no /prefix" ;;
esac
ip link show dev "$iface" >/dev/null 2>&1 ||
  die "interface $iface is absent; the VM has no Lima bridged network"

want="$(mktemp)"
trap 'rm -f "$want"' EXIT
cat >"$want" <<EOF
network:
  version: 2
  ethernets:
    $iface:
      dhcp4: false
      addresses: [$cidr]
EOF
if ! cmp -s "$want" "$plan"; then
  install -m 0600 "$want" "$plan"
  netplan apply
  printf '%s: %s set on %s\n' "$prog" "$cidr" "$iface"
fi

waited=0
until ip -4 -o addr show dev "$iface" | grep -F " $cidr " >/dev/null; do
  [ "$waited" -lt "$wait_seconds" ] ||
    die "$iface does not carry $cidr ${wait_seconds}s after netplan apply"
  sleep "$poll"
  waited=$((waited + poll))
done
printf '%s: %s carries %s\n' "$prog" "$iface" "$cidr"

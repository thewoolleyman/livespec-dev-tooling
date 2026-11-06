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
# Idempotent: it rewrites and applies its netplan file only when the file
# differs, then refuses unless the interface carries the address.
set -euo pipefail

prog="converge-lan-address"
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

plan="/etc/netplan/60-homelab-worker-lan.yaml"
want="network:
  version: 2
  ethernets:
    $iface:
      dhcp4: false
      addresses: [$cidr]
"
if [ "$(cat "$plan" 2>/dev/null || true)" != "$want" ]; then
  printf '%s' "$want" >"$plan"
  chmod 0600 "$plan"
  netplan apply
  printf '%s: %s set on %s\n' "$prog" "$cidr" "$iface"
fi
ip -4 -o addr show dev "$iface" | grep -qF " $cidr " ||
  die "$iface does not carry $cidr after netplan apply"
printf '%s: %s carries %s\n' "$prog" "$iface" "$cidr"

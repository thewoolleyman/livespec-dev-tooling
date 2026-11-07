#!/usr/bin/env bash
# k3s-fixture.sh <up|egress|down> [agent|disabled] — the isolated K3s fixture a
# homelab worker change is proved against before it reaches production. Run it
# INSIDE a homelab worker's Linux VM, as root:
#
#   limactl shell --workdir / <host>-homelab-worker sudo bash -s -- up agent <k3s-fixture.sh
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes": "Reviewed cluster changes" (prove every production control-plane or
# network change against an isolated K3s fixture matching the fleet's version
# and network configuration first). Design:
# plan/homelab-k8s-worker-nodes/research/006-tailnet-and-fixture-corrections-2026-11-04.md.
#
#   up <mode>      create the k3d cluster hw-fixture (one server, one agent) at
#                  egress-selector-mode <mode>; an existing cluster is kept.
#   egress <mode>  rewrite the server's egress-selector-mode and restart only
#                  the fixture's server container, as production would.
#   down           delete the fixture cluster and its state directory, and
#                  the worker's fixture container and state if
#                  join-fixture-worker.sh created them.
#
# The server runs the fleet's pinned K3s image with the production server
# flags (--disable traefik --disable servicelb) and the production config.yaml
# keys (kubelet max-pods=200, local-storage disabled), with the default vxlan
# flannel and the default 10.42/16 and 10.43/16 CIDRs. Only the egress mode is
# a parameter. The API listens on 127.0.0.1:6550 inside the VM only.
#
# FIXTURE_ROOT (default /var/lib/hw-fixture) holds the server config and the
# kubeconfig; FIXTURE_WORKER_ROOT (default /mnt/lima-hwdata/fixture-worker)
# holds the worker's fixture state. The commands it runs are found on PATH, so
# it can be exercised off-host.
set -euo pipefail

prog="k3s-fixture"
cluster="hw-fixture"
root="${FIXTURE_ROOT:-/var/lib/hw-fixture}"
worker_root="${FIXTURE_WORKER_ROOT:-/mnt/lima-hwdata/fixture-worker}"
mounts="${PROC_MOUNTS:-/proc/mounts}"
k3s_image="rancher/k3s:v1.36.2-k3s1@sha256:6a47cea22c4b834d4ba72c89d291696b79ebe406251f90b446e4dff03513dd87"
k3d_version="v5.9.0"
k3d_sha256_arm64="03cde5cf23e6e8e67de5a039ecf26e5b85aca82fba3e5d13dadf904cd218a250"
api="127.0.0.1:6550"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

say() {
  printf '%s: %s\n' "$prog" "$*"
}

usage="usage: $prog <up|egress|down> [agent|disabled]"
action="${1:-}"
mode="${2:-}"
case "$action" in
  up | egress)
    [ "$#" -eq 2 ] || die "$usage"
    case "$mode" in
      agent | disabled) ;;
      *) die "egress-selector-mode '$mode' is not agent or disabled; $usage" ;;
    esac
    ;;
  down) [ "$#" -eq 1 ] || die "$usage" ;;
  *) die "$usage" ;;
esac

vm="$(hostname)"
case "$vm" in
  *-homelab-worker) ;;
  *) die "this is $vm, not a homelab worker VM; the fixture runs only inside a <host>-homelab-worker VM" ;;
esac

ensure_k3d() {
  if command -v k3d >/dev/null 2>&1 && k3d version | grep "k3d version $k3d_version\$" >/dev/null; then
    return 0
  fi
  [ "$(uname -m)" = "aarch64" ] || die "no pinned k3d checksum for architecture $(uname -m)"
  say "installing k3d $k3d_version"
  tmp="$(mktemp)"
  curl -fsSLo "$tmp" "https://github.com/k3d-io/k3d/releases/download/$k3d_version/k3d-linux-arm64"
  echo "$k3d_sha256_arm64  $tmp" | sha256sum -c - >/dev/null || die "k3d $k3d_version download failed its pinned SHA-256"
  install -m 0755 "$tmp" /usr/local/bin/k3d
  rm -f "$tmp"
}

write_config() {
  mkdir -p "$root"
  # Rewritten in place, never replaced: the server bind-mounts this file, and a
  # bind mount keeps the inode it was created with.
  cat >"$root/config.yaml" <<EOF
# Fixture copy of ci-runner/k3s/phase2/k3s-config/config.yaml: same keys, minus
# poweredge's tls-san, with egress-selector-mode set by $prog.
kubelet-arg:
  - "max-pods=200"
disable:
  - local-storage
write-kubeconfig-mode: "0644"
egress-selector-mode: "$1"
EOF
}

cluster_exists() {
  k3d cluster list --no-headers 2>/dev/null | awk '{print $1}' | grep -x "$cluster" >/dev/null
}

wait_ready() {
  for _ in $(seq 1 60); do
    if docker exec "k3d-$cluster-server-0" kubectl get --raw /readyz >/dev/null 2>&1; then
      say "fixture API ready at https://$api (egress-selector-mode $(grep '^egress-selector-mode' "$root/config.yaml" | cut -d'"' -f2))"
      return 0
    fi
    sleep 5
  done
  die "fixture API at https://$api did not become ready"
}

case "$action" in
  up)
    ensure_k3d
    if cluster_exists; then
      say "fixture cluster $cluster exists; keeping it (use '$prog egress <mode>' to change the egress mode)"
    else
      write_config "$mode"
      say "creating fixture cluster $cluster (k3s ${k3s_image%@*}, egress-selector-mode $mode)"
      k3d cluster create "$cluster" --image "$k3s_image" --servers 1 --agents 1 --no-lb \
        --api-port "$api" --wait \
        --volume "$root/config.yaml:/etc/rancher/k3s/config.yaml@server:0" \
        --k3s-arg "--disable=traefik@server:0" --k3s-arg "--disable=servicelb@server:0"
    fi
    k3d kubeconfig get "$cluster" >"$root/kubeconfig"
    chmod 0600 "$root/kubeconfig"
    wait_ready
    ;;
  egress)
    cluster_exists || die "fixture cluster $cluster does not exist; run '$prog up $mode' first"
    write_config "$mode"
    say "restarting the fixture server at egress-selector-mode $mode"
    docker restart "k3d-$cluster-server-0" >/dev/null
    wait_ready
    ;;
  down)
    # The worker container is removed only when it is the fixture's: its
    # enrollment mount is under the fixture worker root, never production's.
    worker="${vm#lima-}"
    if docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/homelab-worker"}}{{.Source}}{{end}}{{end}}' "$worker" 2>/dev/null |
      grep -x "$worker_root/enrollment" >/dev/null; then
      docker rm -f "$worker" >/dev/null
      say "removed fixture worker container $worker"
    fi
    # The worker's kubelet leaves volume mounts (projected tokens) under its
    # state root, which mount propagation keeps in the VM after the container
    # is gone; unmount them, deepest first, before removing the root.
    awk -v root="$worker_root/" 'index($2, root) == 1 {print $2}' "$mounts" | sort -r |
      while IFS= read -r mount; do
        umount "$mount"
        say "unmounted $mount"
      done
    rm -rf "$worker_root"
    if cluster_exists; then
      k3d cluster delete "$cluster"
    else
      say "fixture cluster $cluster is absent"
    fi
    rm -rf "$root"
    say "fixture removed"
    ;;
esac

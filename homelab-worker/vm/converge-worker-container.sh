#!/usr/bin/env bash
# converge-worker-container.sh <worker> <host> <image> <state-root> [host:<lan-ip> | <docker-network>]
# — start or reconcile the one worker container inside a homelab worker VM.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes". Design: plan/homelab-k8s-worker-nodes/research/005 §2 "Supervisor".
# The start task pipes this script into `sudo bash -s` in the VM, as it does
# the capability probe, so it reads no other repository file.
#
#   1. The worker's persistent state lives under <state-root> on the VM's XFS
#      data disk: containerd/, kubelet/, tailscale/ and enrollment/ (0700),
#      which the container mounts at /etc/homelab-worker.
#   2. The container runs systemd as PID 1 (kind node pattern): privileged,
#      private cgroup namespace, tmpfs /run and /tmp, /dev/net/tun, read-only
#      /lib/modules, stop signal SIGRTMIN+3. An absent container is created, a
#      stopped one started, and one on another image replaced; its state stays
#      on the data disk either way. A container of the same name whose
#      enrollment is under another state root is refused, never adopted. No enrollment material is passed in an
#      argument or an environment variable.
#   3. The worker joins the tailnet as <worker>, untagged. It never accepts
#      subnet routes: the tailnet is its identity, not its pod-network
#      underlay (spec v143). While it needs a login, the login URL is printed for
#      the operator to approve, and the run waits TAILNET_LOGIN_TIMEOUT
#      seconds (default 900) for it; the identity persists in tailscale/.
#   4. At boot the worker starts only after the disk holding <state-root> is
#      mounted. Started earlier it binds empty root-disk directories and loses
#      its tailnet identity and enrollment (measured on macbook-m4-max,
#      2026-11-06). Lima mounts the disk in cloud-final.service, after
#      multi-user.target, so gating docker.service on it deadlocks boot.
#      Instead homelab-worker-container.service, ordered after cloud-final and
#      docker and pulled in by cloud-init.target, waits for the mountpoint and
#      supervises the worker (docker start -a, Restart=on-failure); the
#      container itself runs with --restart no, because dockerd restores even
#      an on-failure container at daemon start, before the disk is mounted
#      (measured on macbook-m4-max, 2026-11-06).
#   5. br_netfilter is loaded and listed in modules-load.d: flannel and
#      kube-proxy need the bridge netfilter sysctls, and nothing else in the
#      VM loads the module at boot (measured on macbook-m4-max, 2026-11-06).
#   6. The node paths CI pods use are data-disk binds, because on the worker
#      they resolve inside the container: ci/storage/ is the local-path
#      provisioner's default storage (/var/lib/rancher/k3s/storage), so work
#      volumes outlive the container, and ci/hooks/ is the fleet container
#      hook tree (/usr/local/lib/ci-runner-k3s/hooks), read-only, which the
#      start task delivers (research 009). ci/bin/ is the pool binaries
#      directory (/usr/local/lib/ci-runner-k3s/bin), read-only: workflow pods
#      mount it idmapped (hostUsers: false), which the container's overlayfs
#      root refuses and the data disk's XFS accepts (measured on
#      macbook-m4-max, 2026-11-06). factory/workspaces/ is the factory
#      sandbox backend's workspace root (/srv/factory-workspaces, the one
#      path its `workspace_root` names fleet-wide; ansible role
#      factory_workspace_root), read-write, so a factory sandbox placed on the
#      worker keeps its workspace on the data disk. The VM's securityfs is bound
#      read-write at /sys/kernel/security: the kubelet decides AppArmor
#      support from it, Docker does not mount it into a container, and
#      without it the kubelet refuses every workflow pod confined by the
#      fleet's AppArmor profile; once it is visible, containerd loads its own
#      default profile through it, so a read-only bind fails every container
#      start (both measured on macbook-m4-max, 2026-11-06). A running worker
#      created without these binds, or with securityfs read-only, is
#      replaced; its state on the data disk is kept.
#   7. The node's host collector (DoD assertion 18) reads <state-root>/telemetry,
#      bound at /etc/otel-collector: the start task delivers its config.yaml
#      and, when it has the ingest key, .env; converge writes node.env with
#      WORKER_NODE_NAME and OTLP_PODS_ENDPOINT, the worker's cni0 bridge
#      address and port 4319 (the address the cluster's flannel gave this
#      node, read live), and restarts the collector. Without the key, or
#      before the bridge exists, the collector stays off and converge says so.
#   8. kubelet-config.yaml and kubelet.env (node name, node IP, host) are
#      written to enrollment/. The kubelet starts only once the operator has
#      delivered client-ca.crt there and either bootstrap-kubeconfig is there
#      too or the worker already holds its node kubeconfig.
#
# With host:<lan-ip>, production (research 008 §3): the container runs on the
# VM's host network, and <lan-ip> — the host's declared static home-LAN
# address, which the start task set on the VM's bridged lima0 — is the node
# IP. A VM not carrying <lan-ip> is refused before any container change.
#
# With <docker-network>, the isolated fixture's first stage: the container
# joins that Docker network, its address there is the node IP, and no tailnet
# login is attempted.
set -euo pipefail

prog="converge-worker-container"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

say() {
  printf '%s: %s\n' "$prog" "$*"
}

[ "$#" -eq 4 ] || [ "$#" -eq 5 ] || die "usage: $prog <worker> <host> <image> <state-root> [host:<lan-ip> | <docker-network>]"
worker="$1"
host="$2"
image="$3"
root="$4"
network="${5:-}"
lan_ip=""
case "$network" in
  host:*)
    lan_ip="${network#host:}"
    network="host"
    ip -4 -o addr show | grep -qF " inet $lan_ip/" || {
      carried="$(ip -4 -o addr show | awk '{print $2"="$4}' | tr '\n' ' ')"
      die "this VM does not carry the declared home-LAN address $lan_ip (it carries: ${carried:-none}); the worker container was not changed"
    } ;;
esac
case "$worker" in
  "$host-homelab-worker") ;;
  *) die "worker '$worker' is not $host-homelab-worker" ;;
esac
case "$image" in
  *@sha256:*) ;;
  *) die "image '$image' is not pinned by digest" ;;
esac
unit_dir="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
modules_dir="${MODULES_LOAD_DIR:-/etc/modules-load.d}"
bridge_sysctl="${BRIDGE_NF_SYSCTL:-/proc/sys/net/bridge/bridge-nf-call-iptables}"
login_timeout="${TAILNET_LOGIN_TIMEOUT:-900}"
poll="${POLL_SECONDS:-5}"

if [ "$(cat "$modules_dir/homelab-worker.conf" 2>/dev/null || true)" != "br_netfilter" ]; then
  mkdir -p "$modules_dir"
  printf 'br_netfilter\n' >"$modules_dir/homelab-worker.conf"
fi
modprobe br_netfilter || true
[ -e "$bridge_sysctl" ] ||
  die "br_netfilter is not loaded ($bridge_sysctl is absent) and modprobe br_netfilter failed; the worker container was not changed"

# The mountpoint of the disk holding <state-root>, read from its nearest
# existing ancestor; a state root on the root filesystem is refused.
probe_path="$root"
while [ ! -e "$probe_path" ]; do probe_path="$(dirname "$probe_path")"; done
disk_mount="$(findmnt -n -o TARGET -T "$probe_path" | head -n 1)"
case "$disk_mount" in
  "" | /) die "state root $root is not on the worker's data disk (it resolves to the root filesystem); the worker container was not changed" ;;
esac
# The earlier docker.service drop-in deadlocked boot; it must not remain.
stale_dropin="$unit_dir/docker.service.d/10-homelab-worker-state.conf"
reload=0
if [ -e "$stale_dropin" ]; then
  rm -f "$stale_dropin"
  reload=1
fi
worker_unit="$unit_dir/homelab-worker-container.service"
# $$ escapes systemd's own variable expansion in the unit file.
unit_text="[Unit]
Description=homelab worker $worker, started once its data disk is mounted
After=cloud-final.service docker.service
Requires=docker.service

[Service]
Type=simple
ExecStartPre=/bin/sh -c 'i=0; until mountpoint -q $disk_mount; do i=\$\$((i + 1)); [ \$\$i -ge 600 ] && exit 1; sleep 1; done'
ExecStart=/usr/bin/docker start -a $worker
ExecStop=/usr/bin/docker stop $worker
Restart=on-failure
RestartSec=5

[Install]
WantedBy=cloud-init.target"
if [ "$(cat "$worker_unit" 2>/dev/null || true)" != "$unit_text" ]; then
  mkdir -p "$unit_dir"
  printf '%s\n' "$unit_text" >"$worker_unit"
  reload=1
fi
if [ "$reload" = 1 ]; then
  systemctl daemon-reload
  systemctl enable homelab-worker-container.service
  say "the worker now starts at boot only after the disk holding $root is mounted"
fi

mkdir -p "$root/containerd" "$root/kubelet" "$root/tailscale" "$root/enrollment" \
  "$root/ci/storage" "$root/ci/hooks" "$root/ci/bin" "$root/telemetry" \
  "$root/factory/workspaces"
chmod 0700 "$root/enrollment" "$root/tailscale" "$root/telemetry"

run_container() {
  set -- --detach --name "$worker" --hostname "$worker" \
    --privileged --cgroupns=private \
    --security-opt seccomp=unconfined --security-opt apparmor=unconfined \
    --tmpfs /run --tmpfs /run/lock --tmpfs /tmp \
    --device /dev/net/tun \
    --volume /lib/modules:/lib/modules:ro \
    --volume "$root/containerd:/var/lib/containerd" \
    --volume "$root/kubelet:/var/lib/kubelet:rshared" \
    --volume "$root/tailscale:/var/lib/tailscale" \
    --volume "$root/enrollment:/etc/homelab-worker" \
    --volume "$root/ci/storage:/var/lib/rancher/k3s/storage" \
    --volume "$root/ci/hooks:/usr/local/lib/ci-runner-k3s/hooks:ro" \
    --volume "$root/ci/bin:/usr/local/lib/ci-runner-k3s/bin:ro" \
    --volume "$root/factory/workspaces:/srv/factory-workspaces" \
    --volume /sys/kernel/security:/sys/kernel/security \
    --volume "$root/telemetry:/etc/otel-collector" \
    --env container=docker \
    --stop-signal SIGRTMIN+3 \
    --restart no \
    --label "homelab-worker.livespec.dev/worker=$worker"
  if [ -n "$network" ]; then
    set -- "$@" --network "$network"
  fi
  docker run "$@" "$image" >/dev/null
}

if current="$(docker inspect -f '{{.Config.Image}} {{.State.Running}}' "$worker" 2>/dev/null)"; then
  # A container of this name whose enrollment lives under another state root
  # (the fixture's, or production's when converging the fixture) is not this
  # worker's: refuse rather than adopt, replace or start it.
  mounted="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/homelab-worker"}}{{.Source}}{{end}}{{end}}' "$worker")"
  [ "$mounted" = "$root/enrollment" ] ||
    die "container $worker keeps its enrollment at '$mounted', not $root/enrollment; remove that worker first (k3s-fixture.sh down removes the fixture's)"
  docker update --restart no "$worker" >/dev/null
  current_image="${current% *}"
  running="${current##* }"
  # Each bind as "<destination> <read-write>".
  mounts="$(docker inspect -f '{{range .Mounts}}{{.Destination}} {{.RW}}{{"\n"}}{{end}}' "$worker")"
  if [ "$current_image" != "$image" ]; then
    say "replacing container $worker ($current_image) with $image; its state on the data disk is kept"
    docker rm -f "$worker" >/dev/null
    run_container
  elif ! printf '%s\n' "$mounts" | grep -qx '/var/lib/rancher/k3s/storage true' ||
    ! printf '%s\n' "$mounts" | grep -qx '/usr/local/lib/ci-runner-k3s/hooks false' ||
    ! printf '%s\n' "$mounts" | grep -qx '/usr/local/lib/ci-runner-k3s/bin false' ||
    ! printf '%s\n' "$mounts" | grep -qx '/srv/factory-workspaces true' ||
    ! printf '%s\n' "$mounts" | grep -qx '/sys/kernel/security true' ||
    ! printf '%s\n' "$mounts" | grep -qx '/etc/otel-collector true'; then
    say "replacing container $worker, created without the current CI storage, hook, pool binaries, securityfs, telemetry or factory workspace binds; its state on the data disk is kept"
    docker rm -f "$worker" >/dev/null
    run_container
  elif [ "$running" = "true" ]; then
    # A boot race can start the worker before the data disk mounts, binding
    # empty root-disk directories; restart it so its binds resolve on the
    # data disk, before any tailnet step could mint a duplicate device.
    if [ "$(docker exec "$worker" stat -c %d /var/lib/tailscale 2>/dev/null)" != "$(stat -c %d "$root/tailscale")" ]; then
      say "container $worker is running with its state off the data disk (a boot race); restarting it"
      docker restart "$worker" >/dev/null
    else
      say "container $worker is already running $image; keeping it"
    fi
  else
    say "starting existing container $worker"
    docker start "$worker" >/dev/null
  fi
else
  say "creating container $worker from $image"
  run_container
fi

# backend_state: the worker's tailscaled BackendState, or "" while it is not up.
backend_state() {
  docker exec "$worker" tailscale status --json 2>/dev/null |
    sed -n 's/^ *"BackendState": *"\([A-Za-z]*\)".*/\1/p' | head -n 1
}

auth_url() {
  docker exec "$worker" tailscale status --json 2>/dev/null |
    sed -n 's/^ *"AuthURL": *"\([^"]*\)".*/\1/p' | head -n 1
}

if [ -n "$network" ] && [ "$network" != "host" ]; then
  node_ip="$(docker inspect -f "{{(index .NetworkSettings.Networks \"$network\").IPAddress}}" "$worker")"
  [ -n "$node_ip" ] || die "container $worker has no address on network $network"
  say "fixture network $network: node IP $node_ip; no tailnet login"
else
  state="$(backend_state)"
  if [ "$state" != "Running" ]; then
    say "worker $worker needs its tailnet login (state '${state:-starting}')"
    docker exec --detach "$worker" tailscale up --hostname="$worker"
    shown=""
    waited=0
    while [ "$(backend_state)" != "Running" ]; do
      url="$(auth_url)"
      if [ -n "$url" ] && [ "$url" != "$shown" ]; then
        say "approve the worker's tailnet login: $url"
        shown="$url"
      fi
      if [ "$waited" -ge "$login_timeout" ]; then
        die "worker $worker is not logged in to the tailnet after ${login_timeout}s; approve the login and run the start task again"
      fi
      sleep "$poll"
      waited=$((waited + poll))
    done
  fi
  # The tailnet is the worker's identity, not its underlay: a saved
  # RouteAll preference from an earlier enrollment survives `tailscale up`,
  # so turn route acceptance off explicitly every run.
  docker exec "$worker" tailscale set --accept-routes=false
  if [ -n "$lan_ip" ]; then
    node_ip="$lan_ip"
    say "worker $worker is a home-LAN node at $node_ip"
  else
    node_ip="$(docker exec "$worker" tailscale ip -4 | head -n 1)"
    [ -n "$node_ip" ] || die "worker $worker has no tailnet IPv4 address"
    say "worker $worker is on the tailnet at $node_ip"
  fi
fi

# The fleet kubelet configuration (research/005 §1, K3s v1.36.2 defaults),
# plus the TLS bootstrap and serving-certificate settings K3s does not use.
cat >"$root/enrollment/kubelet-config.yaml" <<'EOF_KUBELET'
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cgroupDriver: systemd
authentication:
  anonymous:
    enabled: false
  webhook:
    enabled: true
  x509:
    clientCAFile: /etc/homelab-worker/client-ca.crt
authorization:
  mode: Webhook
clusterDNS:
  - 10.43.0.10
clusterDomain: cluster.local
evictionHard:
  imagefs.available: 5%
  nodefs.available: 5%
failSwapOn: false
serializeImagePulls: false
resolvConf: /etc/resolv.conf
streamingConnectionIdleTimeout: 4h
singleProcessOOMKill: true
maxPods: 200
readOnlyPort: 0
rotateCertificates: true
serverTLSBootstrap: true
EOF_KUBELET
printf 'NODE_NAME=%s\nNODE_IP=%s\nWORKER_HOST=%s\n' "$worker" "$node_ip" "$host" >"$root/enrollment/kubelet.env"

if [ -s "$root/enrollment/client-ca.crt" ] &&
  { [ -s "$root/kubelet/kubeconfig" ] || [ -s "$root/enrollment/bootstrap-kubeconfig" ]; }; then
  docker exec "$worker" systemctl start kubelet
  say "kubelet started on $worker"
else
  say "worker $worker awaits enrollment: the operator delivers bootstrap-kubeconfig and client-ca.crt to $root/enrollment"
fi

if [ -s "$root/telemetry/config.yaml" ] && [ -s "$root/telemetry/.env" ]; then
  bridge="$(docker exec "$worker" ip -4 -o addr show dev cni0 2>/dev/null | awk '{print $4}' | cut -d / -f 1 | head -n 1 || true)"
  if [ -n "$bridge" ]; then
    printf 'WORKER_NODE_NAME=%s\nOTLP_PODS_ENDPOINT=%s:4319\n' "$worker" "$bridge" >"$root/telemetry/node.env"
    docker exec "$worker" systemctl restart otel-collector
    say "host collector started on $worker (host.name $worker, pod spans on $bridge:4319)"
  else
    say "worker $worker has no cni0 bridge yet; its host collector starts on the next run once the node runs a pod"
  fi
else
  say "worker $worker's host collector stays off: the start task delivers its config.yaml and, with the ingest key, .env to $root/telemetry"
fi

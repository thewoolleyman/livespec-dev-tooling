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
#   4. kubelet-config.yaml and kubelet.env (node name, node IP, host) are
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
login_timeout="${TAILNET_LOGIN_TIMEOUT:-900}"
poll="${POLL_SECONDS:-5}"

mkdir -p "$root/containerd" "$root/kubelet" "$root/tailscale" "$root/enrollment"
chmod 0700 "$root/enrollment" "$root/tailscale"

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
    --env container=docker \
    --stop-signal SIGRTMIN+3 \
    --restart unless-stopped \
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
  current_image="${current% *}"
  running="${current##* }"
  if [ "$current_image" != "$image" ]; then
    say "replacing container $worker ($current_image) with $image; its state on the data disk is kept"
    docker rm -f "$worker" >/dev/null
    run_container
  elif [ "$running" = "true" ]; then
    say "container $worker is already running $image; keeping it"
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

#!/usr/bin/env bash
# baseline.sh — make the disposable VM look like gmktec-xubuntu as measured.
#
# Runs INSIDE the guest as root: `vm.sh ssh sudo bash -s < baseline.sh`.
#
# WHAT IT REPRODUCES. docs/docker-engine-guard-design.md §"Measured state
# (2026-10-15)": iptables on the nft backend with FORWARD and INPUT policy
# ACCEPT; IPv4 forwarding 1, IPv6 forwarding 0/0, bridge-nf-call 1/1; no Docker
# package, chain, directory or socket; `/run/containerd` PRESENT and holding
# `runc/` and `s/` because k3s's embedded containerd keeps its shims there; the
# apt timers active.
#
# WHAT IT STUBS, and why. The VM runs no Tailscale and no LLM, but the role
# refuses to touch a host on which tailscaled or a declared must-stay-running
# unit is not active, and confirms only after the LLM's /health answers. So each
# is a stub unit with the REAL unit name, which the acceptance driver can stop to
# make the matching probe fail:
#   - tailscaled.service: a long-running no-op;
#   - local-homelab-llama-server.service: a stdlib HTTP server answering
#     GET /health with 200 on the port the role's probe is pointed at.
#
# WHAT IS REAL: k3s. The guard's observer samples a live node (guard child 4):
# the node-status read, the DNS-placement read delegated to the k3s server, a
# running pod's network namespace through `k3s crictl`, and the witness that
# finds k3s's containerd in `k3s-agent.service`'s cgroup. A stub cannot answer
# any of those (measured 2026-10-16, H-01). So the guest runs a real single-node
# k3s SERVER, installed under the unit name k3s-agent.service, at the cluster's
# own version. It is its own k3s server: root reaches it over ssh as `guard-vm`,
# and its admin kubeconfig stands at the node-status path.
#
# Idempotent: a second run leaves the guest as the first run left it.

set -euo pipefail

LLM_PORT="${LLM_PORT:-8080}"

[[ "$(id -u)" -eq 0 ]] || {
  echo "baseline.sh: run as root" >&2
  exit 1
}

# The cloud image ships iptables; make sure the nft backend is the one in use,
# as on gmktec.
update-alternatives --set iptables /usr/sbin/iptables-nft >/dev/null
update-alternatives --set ip6tables /usr/sbin/ip6tables-nft >/dev/null

# gmktec has no needrestart (measured 2026-10-15). The cloud image ships it,
# and its dpkg hook can restart services after a package transaction, which
# would make the guest behave unlike the host it stands in for.
if dpkg-query -W -f='${Status}' needrestart 2>/dev/null | grep -q 'install ok installed'; then
  DEBIAN_FRONTEND=noninteractive apt-get purge -y -q needrestart >/dev/null
fi

# gmktec's package index is kept current by its apt-daily timers, so its
# docker.io candidate is the audited 29.1.3-0ubuntu4.1 from
# resolute-updates/universe. The cloud image ships index lists that carry no
# docker.io at all although its sources name universe, which made H-01's
# audited download fail with "Version ... was not found" (measured
# 2026-10-16). Refresh the index once here, so the snapshot holds a current
# one; this changes no file under /etc/apt, which the role digests.
apt-get update -q >/dev/null

# Sysctls and the bridge netfilter module, as measured on gmktec.
modprobe br_netfilter
cat >/etc/modules-load.d/guard-baseline.conf <<'EOF'
br_netfilter
EOF
cat >/etc/sysctl.d/90-guard-baseline.conf <<'EOF'
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 0
net.ipv6.conf.default.forwarding = 0
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF
sysctl --quiet --system

iptables -P FORWARD ACCEPT
iptables -P INPUT ACCEPT
ip6tables -P FORWARD ACCEPT
ip6tables -P INPUT ACCEPT

install -d -m 0755 /usr/local/lib/guard-baseline

cat >/usr/local/lib/guard-baseline/llm_health.py <<'EOF'
"""Stub of the fleet LLM's /health: 200 on GET /health, 404 otherwise."""
import http.server
import sys


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - the stdlib names it
        code = 200 if self.path == "/health" else 404
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if code == 200:
            self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *args):
        pass


http.server.ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), Handler).serve_forever()
EOF

write_unit() {
  local name="$1" description="$2" exec_start="$3"
  cat >"/etc/systemd/system/${name}" <<EOF
[Unit]
Description=${description} (docker_engine acceptance STUB, not the real service)
After=network-online.target

[Service]
Type=simple
ExecStart=${exec_start}
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
}

write_unit tailscaled.service "tailscaled stub" "/bin/sleep infinity"
write_unit local-homelab-llama-server.service "LLM health stub" \
  "/usr/bin/python3 /usr/local/lib/guard-baseline/llm_health.py ${LLM_PORT}"

# The sandbox slice the daemon's cgroup-parent names must be loaded and active
# before the guard's first start (design "The daemon configuration"). On a
# factory host the docker_sandbox_slice role's systemd-only half installs it;
# here a minimal slice stands in, without that role's sizing.
#
# The stub is WANTED at boot, which the real slice is not. That role starts the
# slice when it converges and installs no [Install] section, so on a factory host
# the slice is active only from that converge until the next reboot, and the
# converge runs right before docker_engine's. Every acceptance case cold-boots
# from the `baseline` snapshot, so the stub has to come up active on its own to
# reproduce that state; without this every case refuses at preflight
# (measured 2026-10-16, H-01 on poweredge: ActiveState=inactive after `up`).
cat >/etc/systemd/system/fabro-sandbox.slice <<'EOF'
[Unit]
Description=Fabro sandbox slice (docker_engine acceptance STUB)
Before=slices.target

[Slice]

[Install]
WantedBy=slices.target
EOF

systemctl daemon-reload
systemctl enable --now tailscaled.service local-homelab-llama-server.service

# A real single-node k3s, as k3s-agent.service (INSTALL_K3S_NAME=agent), so
# its embedded containerd runs in the cgroup the guard's witness reads. The
# version is the cluster's own (`kubectl get nodes` on poweredge-xubuntu,
# 2026-10-16). Skipped when this exact k3s is already running.
K3S_VERSION="${K3S_VERSION:-v1.36.2+k3s1}"
if ! { systemctl is-active --quiet k3s-agent.service \
       && /usr/local/bin/k3s --version 2>/dev/null | grep -qF "${K3S_VERSION}"; }; then
  curl -sfL https://get.k3s.io \
    | INSTALL_K3S_VERSION="${K3S_VERSION}" INSTALL_K3S_NAME=agent \
      INSTALL_K3S_EXEC="server --node-name guard-vm --write-kubeconfig-mode 600 --disable traefik --disable servicelb --disable metrics-server" \
      sh -s - >/dev/null
fi
for _ in $(seq 1 60); do
  if k3s kubectl get pods -n kube-system --no-headers 2>/dev/null \
       | awk '$1 ~ /^coredns-/ && $3 == "Running" {found=1} END {exit !found}'; then
    break
  fi
  sleep 5
done
install -m 0600 /etc/rancher/k3s/k3s.yaml /etc/rancher/k3s/node-status-kubeconfig

# The guard delegates its pod listing as `ssh -o BatchMode=yes <k3s_server>
# k3s kubectl ...`, run as root. The guest is its own server, so root gets a
# key it trusts for itself, and `guard-vm` in root's known_hosts.
install -d -m 0700 /root/.ssh
[[ -f /root/.ssh/id_ed25519 ]] || ssh-keygen -q -t ed25519 -N '' -f /root/.ssh/id_ed25519
grep -qxF "$(cat /root/.ssh/id_ed25519.pub)" /root/.ssh/authorized_keys 2>/dev/null \
  || cat /root/.ssh/id_ed25519.pub >>/root/.ssh/authorized_keys
chmod 0600 /root/.ssh/authorized_keys
ssh-keyscan -q -t ed25519 guard-vm >/root/.ssh/known_hosts 2>/dev/null
systemctl enable --now apt-daily.timer apt-daily-upgrade.timer
systemctl enable --now fabro-sandbox.slice

# Refuse to call the baseline done unless it actually holds: the same facts the
# role's preflight and the design's measured state read.
fail=0
for unit in tailscaled.service k3s-agent.service local-homelab-llama-server.service fabro-sandbox.slice; do
  systemctl is-active --quiet "$unit" || {
    echo "baseline.sh: $unit is not active" >&2
    fail=1
  }
done
for fact in "net.ipv4.ip_forward=1" "net.bridge.bridge-nf-call-iptables=1"; do
  [[ "$(sysctl -n "${fact%%=*}")" == "${fact#*=}" ]] || {
    echo "baseline.sh: ${fact%%=*} is not ${fact#*=}" >&2
    fail=1
  }
done
iptables -S FORWARD | grep -qx -- '-P FORWARD ACCEPT' || {
  echo "baseline.sh: FORWARD policy is not ACCEPT" >&2
  fail=1
}
for absent in /var/lib/docker /etc/docker /run/docker.sock; do
  [[ ! -e "$absent" ]] || {
    echo "baseline.sh: $absent exists; this is not a Docker-free host" >&2
    fail=1
  }
done
if dpkg-query -W -f='${Status}\n' docker.io containerd runc 2>/dev/null | grep -q 'install ok installed'; then
  echo "baseline.sh: a Docker package is already installed" >&2
  fail=1
fi
[[ -d /run/containerd/s && -d /run/containerd/runc/k8s.io ]] || {
  echo "baseline.sh: k3s's /run/containerd paths are missing" >&2
  fail=1
}
curl -sf "http://127.0.0.1:${LLM_PORT}/health" >/dev/null || {
  echo "baseline.sh: the LLM health stub does not answer" >&2
  fail=1
}
k3s kubectl get pods -n kube-system --no-headers 2>/dev/null \
  | awk '$1 ~ /^coredns-/ && $3 == "Running" {found=1} END {exit !found}' || {
  echo "baseline.sh: no Running CoreDNS pod on the guest's k3s" >&2
  fail=1
}
ssh -o BatchMode=yes guard-vm k3s kubectl get --raw /api/v1/nodes/guard-vm/status >/dev/null 2>&1 || {
  echo "baseline.sh: root cannot reach the guest's k3s server as guard-vm" >&2
  fail=1
}
[[ "$fail" -eq 0 ]] || exit 1
echo "baseline.sh: guest matches the gmktec baseline"

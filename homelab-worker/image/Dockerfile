# Homelab worker node image: ghcr.io/thewoolleyman/livespec-worker-node.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes": "Worker image" — built from this repository's sources as a native
# OCI image for the host architecture, running upstream kubelet and containerd
# with no K3s agent, pinned to the fleet's Kubernetes minor (v1.36; the fleet
# runs v1.36.2+k3s1 and a kubelet may not be newer than its API server).
#
# Design: plan/homelab-k8s-worker-nodes/research/005-worker-implementation-brief-2026-11-04.md.
# systemd is PID 1 (the kind node pattern), so kubelet and containerd use the
# fleet's systemd cgroup driver. Flannel, kube-proxy and kube-router run as
# DaemonSets selected onto homelab workers, so the image carries only the node
# agent, its runtime, CNI plugins, Tailscale and AppArmor userspace, plus the
# node's host collector (otelcol-contrib, the fleet's pinned release; DoD
# assertion 18), which starts only once converge and the start task have
# delivered its configuration, node values and ingest key under
# /etc/otel-collector.
#
# Every downloaded asset is pinned by version AND per-architecture SHA-256 and
# selected by TARGETARCH. Only arm64 checksums are declared so far; building
# for another architecture fails at the checksum lookup rather than installing
# an unverified binary.
FROM ubuntu:24.04

ARG TARGETARCH
ARG KUBERNETES_VERSION=v1.36.2
ARG KUBELET_SHA256_arm64=b0b45db96f0e6bf996780b8a2b8d868bf538dc7c3a60cf604cf0ea2d65c24b06
ARG CONTAINERD_VERSION=2.3.7
ARG CONTAINERD_SHA256_arm64=e08530c6c8a23c612606da5d2832aed9bed8fc7f8c1b41df0f148a701b931d69
ARG RUNC_VERSION=v1.4.2
ARG RUNC_SHA256_arm64=ea54032310588e115633aa2f4bba8bf9500257f657e1deca88df5778775138db
ARG CNI_PLUGINS_VERSION=v1.9.1
ARG CNI_PLUGINS_SHA256_arm64=56171987d3947707c3563db2f4001bccaf50fd63468611b9f3cbecb1375ee7ec
ARG FLANNEL_CNI_VERSION=v1.9.1-flannel3
ARG FLANNEL_CNI_ASSET_VERSION=v1.9.1
ARG FLANNEL_CNI_SHA256_arm64=691c01b5a3375e2b13910ef7b713bc2b8137047fb09fba363f2f3e3796ad84d9
ARG CRICTL_VERSION=v1.36.0
ARG CRICTL_SHA256_arm64=68328594ccf780a80ae2b092d9f6ce484eec7cf540c275242e8fd954bfd95332
ARG TAILSCALE_VERSION=1.104.4
ARG TAILSCALE_SHA256_arm64=a1c249ce6bdebef62e1ae3b997595555bce2ae4709bf95a718e9ca7a129dad7e
ARG OTELCOL_VERSION=0.147.0
ARG OTELCOL_SHA256_arm64=1ab4a5b12327466b7395582eb6ea0732810acb2b5e4ea9b464bd336527e85e38

ENV container=docker
STOPSIGNAL SIGRTMIN+3

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN export DEBIAN_FRONTEND=noninteractive \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      systemd systemd-sysv dbus ca-certificates curl \
      iptables ipset conntrack ebtables ethtool socat iproute2 kmod \
      apparmor util-linux mount e2fsprogs xfsprogs \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* \
 && systemctl mask systemd-firstboot.service systemd-udevd.service systemd-logind.service \
      getty.target console-getty.service

# pick <VAR-PREFIX>: the TARGETARCH-specific checksum, or a hard failure.
RUN cat >/usr/local/bin/pinned-sha256 <<'EOF'
#!/bin/bash
set -euo pipefail
var="${1}_SHA256_${TARGETARCH:?TARGETARCH is unset}"
sum="${!var:-}"
[ -n "$sum" ] || { echo "no pinned SHA-256 for $1 on architecture $TARGETARCH" >&2; exit 1; }
printf '%s' "$sum"
EOF
RUN chmod 0755 /usr/local/bin/pinned-sha256

RUN export KUBELET_SHA256_arm64 CONTAINERD_SHA256_arm64 RUNC_SHA256_arm64 CNI_PLUGINS_SHA256_arm64 \
      FLANNEL_CNI_SHA256_arm64 CRICTL_SHA256_arm64 TAILSCALE_SHA256_arm64 OTELCOL_SHA256_arm64 \
 && cd /tmp \
 && curl -fsSLo kubelet "https://dl.k8s.io/release/${KUBERNETES_VERSION}/bin/linux/${TARGETARCH}/kubelet" \
 && echo "$(pinned-sha256 KUBELET)  kubelet" | sha256sum -c - \
 && install -m 0755 kubelet /usr/local/bin/kubelet \
 && curl -fsSLo containerd.tgz "https://github.com/containerd/containerd/releases/download/v${CONTAINERD_VERSION}/containerd-${CONTAINERD_VERSION}-linux-${TARGETARCH}.tar.gz" \
 && echo "$(pinned-sha256 CONTAINERD)  containerd.tgz" | sha256sum -c - \
 && tar -C /usr/local -xzf containerd.tgz \
 && curl -fsSLo runc "https://github.com/opencontainers/runc/releases/download/${RUNC_VERSION}/runc.${TARGETARCH}" \
 && echo "$(pinned-sha256 RUNC)  runc" | sha256sum -c - \
 && install -m 0755 runc /usr/local/sbin/runc \
 && mkdir -p /opt/cni/bin \
 && curl -fsSLo cni.tgz "https://github.com/containernetworking/plugins/releases/download/${CNI_PLUGINS_VERSION}/cni-plugins-linux-${TARGETARCH}-${CNI_PLUGINS_VERSION}.tgz" \
 && echo "$(pinned-sha256 CNI_PLUGINS)  cni.tgz" | sha256sum -c - \
 && tar -C /opt/cni/bin -xzf cni.tgz \
 && curl -fsSLo flannel.tgz "https://github.com/flannel-io/cni-plugin/releases/download/${FLANNEL_CNI_VERSION}/cni-plugin-flannel-linux-${TARGETARCH}-${FLANNEL_CNI_ASSET_VERSION}.tgz" \
 && echo "$(pinned-sha256 FLANNEL_CNI)  flannel.tgz" | sha256sum -c - \
 && tar -xzf flannel.tgz \
 && install -m 0755 "flannel-${TARGETARCH}" /opt/cni/bin/flannel \
 && curl -fsSLo crictl.tgz "https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRICTL_VERSION}/crictl-${CRICTL_VERSION}-linux-${TARGETARCH}.tar.gz" \
 && echo "$(pinned-sha256 CRICTL)  crictl.tgz" | sha256sum -c - \
 && tar -C /usr/local/bin -xzf crictl.tgz \
 && curl -fsSLo tailscale.tgz "https://pkgs.tailscale.com/stable/tailscale_${TAILSCALE_VERSION}_${TARGETARCH}.tgz" \
 && echo "$(pinned-sha256 TAILSCALE)  tailscale.tgz" | sha256sum -c - \
 && tar -xzf tailscale.tgz \
 && install -m 0755 "tailscale_${TAILSCALE_VERSION}_${TARGETARCH}/tailscale" /usr/local/bin/tailscale \
 && install -m 0755 "tailscale_${TAILSCALE_VERSION}_${TARGETARCH}/tailscaled" /usr/local/sbin/tailscaled \
 && curl -fsSLo otelcol.tgz "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v${OTELCOL_VERSION}/otelcol-contrib_${OTELCOL_VERSION}_linux_${TARGETARCH}.tar.gz" \
 && echo "$(pinned-sha256 OTELCOL)  otelcol.tgz" | sha256sum -c - \
 && tar -xzf otelcol.tgz otelcol-contrib \
 && install -m 0755 otelcol-contrib /usr/local/bin/otelcol-contrib \
 && rm -rf /tmp/*

COPY systemd/ /etc/systemd/system/
COPY containerd-config.toml /etc/containerd/config.toml
COPY crictl.yaml /etc/crictl.yaml

RUN systemctl enable containerd.service tailscaled.service kubelet.service otel-collector.service \
 && mkdir -p /var/lib/kubelet /var/lib/containerd /var/lib/tailscale /etc/homelab-worker /etc/otel-collector

LABEL org.opencontainers.image.source="https://github.com/thewoolleyman/livespec-dev-tooling" \
      org.opencontainers.image.description="livespec homelab worker node: upstream kubelet and containerd, no K3s agent"

ENTRYPOINT ["/sbin/init"]

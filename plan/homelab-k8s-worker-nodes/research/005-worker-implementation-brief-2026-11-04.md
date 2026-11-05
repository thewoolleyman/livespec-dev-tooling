> **Superseded in part, 2026-11-05:** [008](008-lan-worker-and-test-strategy-2026-11-05.md) replaces the tailnet underlay this brief recommends: §1's worker values (`--iface=tailscale0`, kubelet `--node-ip=<worker tailnet IPv4>`, serving-CSR SANs carrying the tailnet IPv4), §3's "Mixed LAN/tailnet underlay — Option A (recommended)", §4 slice 7 and risk 1. The M4 Max worker is a home-LAN node through a bridged Lima network. The rest of this brief still holds.

# Homelab worker node: implementation brief (plan homelab-k8s-worker-nodes)

Research date 2026-11-04, read-only. Every cluster fact below was read through
`ssh -o BatchMode=yes poweredge-xubuntu 'sudo -n ...'` (and plain `ssh gmktec-xubuntu` for its Tailscale prefs)
using get, describe, cat, journalctl, ss, ip and iptables -S only. Nothing was
applied, edited or restarted. Inputs:
`plan/homelab-k8s-worker-nodes/research/002-*.md` (image, bootstrap, networking),
`research/004-two-host-phases-2026-11-04.md`, and the spec section "Homelab worker
nodes" in `SPECIFICATION/non-functional-requirements.md`
(v131, PR 3412). The K3s source was read with `gh api` at tag `v1.36.2+k3s1`.

---

## 1. Measured cluster facts for a generic node join

### Versions and nodes (`kubectl get nodes -o wide`)
| Node | Role | InternalIP | PodCIDR | Kernel | Runtime | Taints |
|---|---|---|---|---|---|---|
| poweredge-xubuntu | control-plane (server with an embedded agent) | 192.168.1.200 | 10.42.0.0/24 | 7.0.0-38 | containerd://2.3.2-k3s2 | none |
| gmktec-xubuntu | agent | 192.168.1.156 | 10.42.1.0/24 | 7.0.0-31 | same | `livespec.io/factory-pressure=high:PreferNoSchedule` |
| hp-xubuntu | agent | 192.168.1.4 | 10.42.2.0/24 | 7.0.0-31 | same | none |

All three nodes run v1.36.2+k3s1 (`k3s version v1.36.2+k3s1 (01b6f04a)`, go1.26.4) on Ubuntu 26.04 amd64. All carry the label `k3s-role=arc-runner-host`. There is no ExternalIP on any node. kubelet runs with `--cloud-provider=external`, and the K3s CCM initializes each node from its `k3s.io/internal-ip` annotation.

### Flannel (node annotations, `/var/lib/rancher/k3s/agent/etc/flannel/net-conf.json`, `ip -d link`)
- net-conf: `{"Network":"10.42.0.0/16","EnableIPv4":true,"EnableIPv6":false,"Backend":{"Type":"vxlan"}}`.
- Annotations on every node: `flannel.alpha.coreos.com/backend-type=vxlan`, `backend-data={"VNI":1,"VtepMAC":...}`, `kube-subnet-manager=true`, `public-ip=<LAN IP>`.
- `flannel.1`: `vxlan id 1 local 192.168.1.200 dev eno1 ... dstport 8472`, **mtu 1450**. `cni0` mtu 1450. `ss -ulpn` shows UDP 0.0.0.0:8472.
- CNI conflist `10-flannel.conflist`: `cbr0`, cniVersion 1.0.0, plugins flannel (delegate `hairpinMode:true, forceAddress:true, isDefaultGateway:true`), portmap and bandwidth.
- Masquerade: the `FLANNEL-POSTRTG` chain MASQUERADEs `-s 10.42.0.0/16 ! -d 224.0.0.0/4`, after RETURN rules for intra-cluster traffic. Pod traffic to a tailnet 100.x address therefore leaves the node SNATed to that node's address.
- Embedded flannel version: `github.com/flannel-io/flannel v0.28.4` (from K3s `go.mod` at the tag).

### CIDRs and DNS
- Cluster CIDR `10.42.0.0/16`, with `--allocate-node-cidrs=true` on kube-controller-manager. The node mask is /24. Service CIDR `10.43.0.0/16`.
- `kubernetes` Service 10.43.0.1. CoreDNS Service `kube-system/kube-dns` **10.43.0.10** (53/UDP, 53/TCP, 9153). The kubelet `clusterDNS` is 10.43.0.10 and `clusterDomain` is cluster.local.
- The Corefile includes `hosts /etc/coredns/NodeHosts` (K3s-maintained) and `forward . /etc/resolv.conf`.

### API server and egress selector (k3s journal "Running kube-apiserver ...", `/var/lib/rancher/k3s/server/etc/egress-selector-config.yaml`)
- **The egress selector mode in effect is `agent`, the default.** The journal shows `Tunnel server egress proxy mode: agent`. `config.yaml` has no `egress-selector-mode` key. The egress config file sends the `cluster` selection as HTTPConnect to `https://127.0.0.1:6443` (the K3s supervisor tunnel server).
- Relevant apiserver flags: `--enable-bootstrap-token-auth=true`, `--authorization-mode=Node,RBAC`, `--enable-admission-plugins=NodeRestriction`, `--anonymous-auth=false`, `--kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname`, `--kubelet-certificate-authority=/var/lib/rancher/k3s/server/tls/server-ca.crt`, `--enable-aggregator-routing=true`, `--bind-address=127.0.0.1 --secure-port=6444`. The supervisor serves `*:6443` and proxies to the apiserver. 10250 is listening on `*`.
- **Source finding (K3s `pkg/daemons/control/tunnel.go` at v1.36.2+k3s1, `dialBackend`).** In any non-disabled mode, the tunnel server inserts every Node's InternalIP and ExternalIP with its kubelet port. A dial to `<nodeIP>:10250` (or the stream server port) is then rewritten to loopback and must use that node's remotedialer session. If no session exists, the dial is **rejected rather than tried directly**:
  `if toKubelet && strings.HasPrefix(err.Error(), "failed to find Session for client") { return conn, err }`.
  A generic kubelet has no session. So under the current `agent` mode, `kubectl logs/exec/port-forward/attach` and the apiserver's kubelet proxy will **fail** for the new node. `pod` and `cluster` modes share this kubelet path. Only `egress-selector-mode: disabled` (where `watch()` returns early and nothing is inserted) lets the apiserver dial the worker directly.
- Regression input for disabled mode: from poweredge, a TCP connect to `192.168.1.156:10250` and `192.168.1.4:10250` both reported **open**. Direct kubelet reachability for the existing agents already exists on the LAN. `ufw` is inactive on poweredge and gmktec.
- metrics-server (kube-system) scrapes kubelets **directly** from its pod. Its args are `--kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname --kubelet-use-node-status-port`. It does not go through the egress selector, so it needs a pod-to-worker-tailnet-IP path. The masquerade rules above cover the source address. Aggregated APIs are also registered: `v1beta1.metrics.k8s.io`, and kueue visibility `v1beta1`/`v1beta2`.

### NetworkPolicy enforcement
- **Enforced by K3s's embedded kube-router.** The journal shows `Starting network policy controller version v2.6.3-k3s1`. `iptables -S` has 341 `KUBE-ROUTER*` rules, with the chains KUBE-ROUTER-FORWARD, INPUT and OUTPUT. K3s `go.mod` replaces `cloudnativelabs/kube-router/v2 => k3s-io/kube-router/v2 v2.6.3-k3s1`. The controller runs inside each K3s agent process and programs only its own node's pods.
- Live policies: `factory/factory-egress` and `factory-mi-homelab/factory-egress`. Both have `podSelector: {}` with Ingress and Egress, allowing egress to kube-dns 53/UDP and TCP, to `100.64.0.0/10`, and to 443 on `0.0.0.0/0` except the RFC1918, CGNAT, loopback and link-local ranges. A worker that ignored these would silently widen factory egress.

### kube-proxy
- **Mode `iptables`.** `curl 127.0.0.1:10249/proxyMode` returns `iptables`, and there are 55 `KUBE-SVC` nat rules. The k3s journal shows `Running kube-proxy --cluster-cidr=10.42.0.0/16 --conntrack-max-per-core=0 --conntrack-tcp-timeout-close-wait=0s --conntrack-tcp-timeout-established=0s --healthz-bind-address=127.0.0.1 --proxy-mode=iptables`, with a kubeconfig at `agent/kubeproxy.kubeconfig`. The `system:node-proxier` ClusterRoleBinding binds `User:system:kube-proxy`.

### kubelet config the fleet uses (`agent/etc/kubelet.conf.d/00-k3s-defaults.conf` and `50-single-process-oom-kill.conf`)
`cgroupDriver: systemd`, webhook authn and authz with anonymous disabled, `clusterDNS: [10.43.0.10]`, `evictionHard imagefs/nodefs 5%`, `failSwapOn: false`, `serializeImagePulls: false`, `resolvConf: /run/systemd/resolve/resolv.conf`, `streamingConnectionIdleTimeout: 4h`, `singleProcessOOMKill: true`, `max-pods=200` (from the `kubelet-arg` in config.yaml), `--read-only-port=0`. K3s does **not** set `serverTLSBootstrap`, because the K3s supervisor issues serving certificates itself. The containerd config has `SystemdCgroup = true`, `snapshotter = "overlayfs"`, `enable_unprivileged_ports/icmp = true`.

### Bootstrap tokens, CSR and RBAC
- kube-controller-manager runs `--controllers=*,tokencleaner,-service,-route,-cloud-node-lifecycle`. This means **csrapproving, csrsigning and tokencleaner are on**, and **bootstrapsigner is off**: `kube-public/cluster-info` does not exist (measured `NotFound`). The worker must therefore pin the CA out of band, which it should do anyway.
- Signers: kubelet-client and kube-apiserver-client use `client-ca`, and `kubelet-serving` uses `server-ca` (`--cluster-signing-kubelet-serving-cert-file=.../server-ca.nochain.crt`). The apiserver verifies kubelets against `server-ca.crt`, so **a kubelet-serving CSR signed by the cluster is exactly what logs and exec need. A self-signed kubelet serving certificate will fail verification.**
- There are **no bootstrap-token Secrets** (`kube-system`, `type=bootstrap.kubernetes.io/token`: none). There are **no bindings for `system:bootstrappers`**, and no subject is bound to `system:node-bootstrapper`, `...:nodeclient` or `...:selfnodeclient`. Those ClusterRoles exist but are unbound. `kubectl get csr` returns no resources. Fleet-specific bindings that do exist: `clustercidrs-node` (`system:nodes` list/watch clustercidrs), the `ci-runner-node-status-patcher-<node>` per-node SAs, `factory-*-sandbox-launcher-node-reader`, and `system:node-proxier`.
- `k3s cloudprovider InstanceExists` always returns true (`pkg/cloudprovider/instances.go`), so the K3s CCM will not delete a foreign Node. A worker kubelet must **not** pass `--cloud-provider=external`. With that flag it would sit under the uninitialized taint until it set `k3s.io/internal-ip` annotations.

### Tailnet facts
- Existing nodes run Tailscale **1.104.4**. Tailnet IPs: poweredge 100.78.140.72, gmktec 100.79.195.82, hp 100.68.193.50. `tailscale0` mtu **1280**. Prefs on poweredge and gmktec: `RouteAll:false`, `AdvertiseRoutes:null`, `NoSNAT:false`, `NetfilterMode:2`. hp's prefs could not be read: SSH failed with host key verification.
- `ip rule` puts `lookup 52` (Tailscale) at priority 5270, ahead of main.
- No device carries tags (`Self.Tags: None`). MagicDNS suffix is `perch-rudd.ts.net`. The apiserver cert already has the SANs `poweredge-xubuntu.perch-rudd.ts.net` and `100.78.140.72` (config.yaml `tls-san`).
- `macbook-m4-max` is 100.125.10.110. `macbook-air` is 100.70.51.124 and was **connected through DERP relay "sao"** at read time, not a direct path. That is a throughput risk for VXLAN.

---

## 2. Worker image

New image `ghcr.io/thewoolleyman/livespec-homelab-worker` (name to ratify), built from `docker/homelab-worker/Dockerfile` by a new workflow. Do not reuse the fabro-sandbox chain.

### Components, pinned for arm64 (assets verified to exist, 2026-11-04)
| Component | Pin | Source and asset | Rationale |
|---|---|---|---|
| kubelet | **v1.36.2** | `dl.k8s.io/release/v1.36.2/bin/linux/arm64/kubelet` (+`.sha256`, HTTP 200) | Exact match to the apiserver. Skew policy forbids a kubelet newer than the apiserver. Upstream v1.36.6 and k3s v1.36.6+k3s1 exist (2026-10-28/11-03) and should be moved in lockstep with a fleet upgrade. |
| kube-proxy | **v1.36.2** | `registry.k8s.io/kube-proxy:v1.36.2` (manifest list includes linux/arm64), or the binary from dl.k8s.io | Match the fleet's `--proxy-mode=iptables` and its flag set. |
| containerd | **v2.3.x** (2.3.7 is latest; the fleet runs 2.3.2-k3s2) | `containerd-2.3.7-linux-arm64.tar.gz` (+`.sha256sum`) | Same minor as the fleet, and supports pod user namespaces (needs 2.0+). |
| runc | **v1.4.2** (matches K3s `go.mod`; v1.4.3 is the latest 1.4) | `runc.arm64` (+`.asc`) | Same line containerd is validated with in K3s. |
| CNI plugins | **v1.9.1** (K3s `go.mod` shows the same) | `cni-plugins-linux-arm64-v1.9.1.tgz` (+sha256) | bridge, host-local, portmap, bandwidth, loopback. |
| flannel CNI plugin | **v1.9.1-flannel3** | `cni-plugin-flannel-linux-arm64-v1.9.1.tgz`, or image `ghcr.io/flannel-io/flannel-cni-plugin:v1.9.1-flannel3` (arm64 present) | The `flannel` CNI type used by the fleet conflist. |
| flannel agent | **v0.28.4** (equals the K3s embedded version) | `flanneld-arm64`, or `ghcr.io/flannel-io/flannel:v0.28.4` (arm64 present) | Run with `--kube-subnet-manager`, VXLAN VNI 1, port 8472, `--iface=tailscale0`. |
| NetworkPolicy | **kube-router v2.6.3** in firewall-only mode | `docker.io/cloudnativelabs/kube-router:v2.6.3` (arm64 present) | The upstream base of the fleet's `v2.6.3-k3s1`. Flags: `--run-firewall=true --run-router=false --run-service-proxy=false`. |
| crictl | v1.36.0 | `crictl-v1.36.0-linux-arm64.tar.gz` | Diagnostics, with an explicit `runtime-endpoint`. |
| Tailscale | **1.104.4** (fleet parity; 1.104.5 is latest) | Static tarball `tailscale_1.104.4_arm64.tgz` from pkgs.tailscale.com (or image `tailscale/tailscale:v1.104.4`, arm64 present) | Kernel mode (`--tun=tailscale0`), state on a persistent volume, `--hostname=<host>-homelab-worker`. |
| apparmor userspace | from the Ubuntu 24.04 archive | `apparmor` package (`apparmor_parser`) | Loads the `ci-runner-workflow` profile (`ci-runner/k3s/phase2/apparmor/ci-runner-workflow`) into the VM kernel. The same parser path is used by `ansible/roles/apparmor_profile`. |

Follow the repo's checksum convention, as `GH_SHA256`/`SCCACHE_SHA256` already do in `docker/fabro-sandbox/*/Dockerfile`: one `ARG <X>_VERSION` and one `ARG <X>_SHA256` per asset, with `sha256sum -c` before install. Unlike the existing Dockerfiles, which hardcode `linux_amd64` and `x86_64`, select assets by **`TARGETARCH`** and keep a checksum per architecture.

### Base image
`ubuntu:24.04` (linux/arm64 present). It matches the Lima VM's userland, so the apparmor_parser feature ABI matches the 6.8 VM kernel, and it matches the fleet's apt conventions. `debian:trixie-slim` is the kind-style alternative. It is smaller, but its AppArmor userspace differs from the VM's.

### Supervisor
**systemd as PID 1, following the kind node pattern.** The fleet runs `cgroupDriver: systemd` and `SystemdCgroup=true`. systemd provides the delegated cgroup subtree, ordering (tailscaled, then containerd, then kubelet), restart-on-failure, journald logs and clean SIGRTMIN+3 shutdown without custom init code. 002 already says to avoid writing a new init system. The container run needs `--privileged --cgroupns=private`, tmpfs `/run` and `/tmp`, `container=docker` (or the equivalent), the stop signal `SIGRTMIN+3`, `/dev/net/tun`, `/lib/modules` read-only, and `/sys/kernel/security` writable for AppArmor loading.

The alternatives are tini or s6 with the cgroupfs driver. They mean less image, but kubelet and containerd would then need cgroupfs, which diverges from the fleet and adds custom health code. Not recommended.

### Where flannel, kube-proxy and kube-router run
There are two viable shapes.

- **(a) DaemonSets, recommended.** Run them as hostNetwork DaemonSets with `nodeSelector: homelab-worker.livespec.dev/class=worker` (or similar) and tolerations for the admission-hold taint and `node.kubernetes.io/not-ready`. Each gets its own ServiceAccount with RBAC: upstream flannel's role, `system:node-proxier`, and kube-router's netpol role. This is the standard kubeadm pattern. It needs no extra host-delivered credentials, and the images are multi-arch upstream. The cost is new cluster objects, which go through the reviewed-PR rule. The nodeSelector must never match the K3s nodes, which already run all three embedded (002: "Do not install a second cluster-wide Flannel DaemonSet").
- **(b) In-image systemd units.** This needs a scoped credential per component delivered at enrollment. The kubelet's node identity cannot be reused: under `AuthorizeNodeWithSelectors` a node is limited to reading itself, and K3s's own `pkg/agent/flannel/setup.go` notes this distinction. More secrets on the host.

With (a), the image contains kubelet, containerd, runc, CNI binaries, crictl, Tailscale, apparmor userspace and systemd. That matches the spec's "running upstream kubelet and containerd with no K3s agent".

### Outer runtime in the Lima VM
Lima's ubuntu template already ships containerd and nerdctl. Use **system (rootful) containerd** with `containerd: {system: true, user: false}`. kind supports a nerdctl provider, so systemd-in-container under nerdctl is a known pattern. Docker Engine inside the VM is the fallback.

The inner containerd store, kubelet dir and caches must live on a **VM-local XFS (reflink=1) or btrfs disk**, not overlay-on-overlay and not a macOS share. The Ubuntu cloud image root is ext4, and ext4 has no reflink, so the spec's reflink probe would fail on the root disk. Use a Lima `additionalDisks` raw disk formatted XFS in provisioning.

### How this repo publishes images (`.github/workflows/fabro-sandbox-image.yml`)
- Triggers: `pull_request` on image paths builds and pushes to an **ephemeral `registry:2` service at localhost:5000**, never to GHCR. A `push` to master on those paths publishes `ghcr.io/<owner>/livespec-fabro-sandbox`. `release: published` publishes semver tags (`paths` filters do not apply to release events).
- Tooling: `docker/setup-buildx-action@v4` (`driver-opts: network=host`), `docker/login-action@v4` (GITHUB_TOKEN with `packages: write`), `docker/metadata-action@v6` with `flavor: latest=false` and tags `type=sha,prefix=<layer>-sha-` and `type=semver,pattern=v{{version}},prefix=<layer>-`, and `docker/build-push-action@v7` with `push: true`, `provenance: false`, `cache-from/to: type=gha,scope=<layer>`.
- Digests: each step's `outputs.digest` is fed as a `FROM ${IMAGE}@<digest>` build-arg to the next layer, giving a hermetic chain. There is **no mutable `latest`**. Consumers pin immutable `sha-*`/`v*` tags. On release, `self-reconcile-pins` (with `needs: build`) rewrites self-sourced pins through `pin_autodiscovery` and the `bump-pin-rewrite` action, and `just check-fabro-image-pin-lockstep` guards pin lockstep.
- **The workflow declares no `platforms:`**, so today's output is single-arch amd64 from `ubuntu-latest`.

For the worker workflow, copy these conventions: tags `sha-<short>` and `v<X.Y.Z>`, `latest=false`, `provenance: false`, GHA cache and the ephemeral PR registry. Add `platforms: linux/arm64` (plus `linux/amd64` if wanted). Because the image is only verified downloads, a QEMU cross-build via `docker/setup-qemu-action` is cheap, though `ubuntu-24.04-arm` runners are an alternative. Record the resolved digest in the start task's host manifest and as a node annotation. Per CLAUDE.md, adding a file under `.github/workflows/` needs the exemption, label and wrapper in `.ai/fleet-and-secrets.md`.

---

## 3. Enrollment, policy, underlay and fixture

### Minimal reviewed RBAC and bootstrap (one-time cluster change, reviewed PR with rollback)
1. ClusterRoleBinding `homelab-worker-bootstrap`: Group `system:bootstrappers:homelab-worker` to ClusterRole `system:node-bootstrapper` (CSR create, get and watch).
2. ClusterRoleBinding `homelab-worker-autoapprove-client`: the same group to `system:certificates.k8s.io:certificatesigningrequests:nodeclient`. The csrapproving controller, which is enabled, then auto-approves the kubelet **client** CSR (signer `kubernetes.io/kube-apiserver-client-kubelet`, CN `system:node:<name>`, O `system:nodes`).
3. ClusterRoleBinding `homelab-worker-autorenew-client`: Group `system:nodes` to `...:selfnodeclient`. This enables client-cert rotation. It is scoped by the group, but it also applies to the K3s nodes. They do not use CSR rotation, so it is harmless, but record that in the review. Alternative: bind it per user `system:node:<host>-homelab-worker` for each declared host.
4. Per enrollment, **minted controller-side by the operator** (the start task cannot mint): a `kube-system/bootstrap-token-<id>` Secret with `usage-bootstrap-authentication: "true"`, `auth-extra-groups: system:bootstrappers:homelab-worker`, and a short `expiration` (for example 1h). tokencleaner, which is on, deletes it after expiry. The token reaches the VM as a file (spec: never a layer, Git, argv or an inspect-visible environment variable). The worker's bootstrap kubeconfig pins `server: https://poweredge-xubuntu.perch-rudd.ts.net:6443` (a SAN that is already present) and the CA `server-ca.crt` (bootstrapsigner and cluster-info are absent).
5. kubelet: `--bootstrap-kubeconfig`, `--kubeconfig` on a persistent volume, `rotateCertificates: true`, `serverTLSBootstrap: true`, `--node-ip=<worker tailnet IPv4>`, `--hostname-override=<host>-homelab-worker`, `--register-with-taints=homelab-worker.livespec.dev/admission=hold:NoSchedule`, a worker-class label, and the fleet kubelet config copied from the defaults above. NodeRestriction stops a kubelet from changing its own taints after registration, so the start task cannot lift the hold with node credentials. That matches the spec.

### Serving CSR approval
Built-in approvers never approve `kubernetes.io/kubelet-serving`. There are two options.

- **Pilot:** a reviewed operator-side `approve-homelab-worker-serving-csr <host>` script. It verifies `spec.username == system:node:<host>-homelab-worker`, the signer, usages `digital signature, server auth` (plus key encipherment), and SANs exactly `{<host>-homelab-worker, <host>-homelab-worker.perch-rudd.ts.net, <tailnet IPv4>}` where the IP equals the Node's InternalIP. Only then does it run `kubectl certificate approve`. Rotations re-request (roughly yearly) and need the same action.
- **Steady state:** an in-cluster approver such as postfinance `kubelet-csr-approver`, restricted with `providerRegex: ^[a-z0-9-]+-homelab-worker$` and `providerIpPrefixes: 100.64.0.0/10`. K3s nodes never submit serving CSRs, so there is no cross-impact. This is another reviewed cluster object.

Never give a worker CSR-approve RBAC or a signing CA.

### NetworkPolicy on the new node
K3s's kube-router (v2.6.3-k3s1) lives inside the K3s agent process and programs only its own node's iptables, so nothing would enforce policy on the worker. Replace it with **upstream kube-router v2.6.3 in firewall-only mode** on the worker class. That is the same lineage, and the iptables or nftables backend must match what the image's iptables binary uses. Run it as a DaemonSet (recommended) or as an in-image unit. Acceptance needs an explicit deny test: an allow policy admits traffic, a deny policy then blocks it on the worker, and the live `factory-egress` shape is enforced on a worker pod.

Readiness gating: the worker must not lose the hold until the policy agent reports synced. The spec's admission hold covers this if lifting it stays manual.

Alternative: Calico Felix in policy-only mode. It is heavier and has different semantics, so it is not recommended.

### Egress selector (required control-plane change)
The source finding in section 1 means **`egress-selector-mode: disabled` is required** for logs, exec, port-forward, attach and apiserver kubelet-proxy to reach a tunnel-less kubelet.

- Change: add `egress-selector-mode: disabled` to `ci-runner/k3s/phase2/k3s-config/config.yaml` (installed to `/etc/rancher/k3s/config.yaml`), then restart k3s on poweredge.
- Risks:
  1. **A k3s server restart kills running CI jobs.** The comment in config.yaml says so: "Do that restart at zero active jobs". It needs the normal drain-to-zero procedure.
  2. Every apiserver-to-kubelet connection to existing agents becomes a direct LAN dial. The 10250 ports were measured open from poweredge.
  3. It is unknown whether the agents' remotedialer tunnels need an agent restart or simply become unused. Prove it in the fixture.
  4. Aggregated APIs (metrics and kueue visibility) with `--enable-aggregator-routing` will dial pod IPs directly from the server host over flannel. That works today for pods on poweredge. Prove it for pods on agents.
- Rollback: remove the key and restart. Agent mode returns, and the worker's logs and exec break again, but nothing else does.
- Alternatives:
  - Embed a remotedialer client that speaks K3s's `/v1-k3s/connect` tunnel. That is a K3s agent in all but name and conflicts with the spec's "no K3s agent".
  - Register the worker with no InternalIP. kubelet always reports one, so this is not viable.

### Mixed LAN/tailnet underlay
The existing VTEPs advertise `public-ip=192.168.1.x`, and their `flannel.1` is `local 192.168.1.x dev eno1`. The worker's VTEP would advertise its tailnet IP and run flannel with `--iface=tailscale0`.

**Option A (recommended for the first proof): per-node /32 subnet routes.**
- Each existing node runs `tailscale set --advertise-routes=<its LAN IP>/32`, approved in the admin console. The worker runs with `--accept-routes`.
- Worker to node: VXLAN to 192.168.1.200 rides WireGuard to poweredge and is delivered locally.
- Node to worker: the outer destination 100.x is matched by table 52 with the fixed outer source 192.168.1.200. The worker's tailscaled accepts it only because 192.168.1.200/32 is in poweredge's AllowedIPs.
- Risks:
  1. The kernel routing of the outer packet with `dev eno1` set on the VXLAN device. Flannel's FDB entries carry no ifindex, so the lookup should be unconstrained, but this is **unproven**.
  2. Any tailnet device with accept-routes on will route 192.168.1.x through the tailnet. That includes the Macs at home, since macOS defaults to using subnets, and it would hijack their LAN path. The existing nodes measured `RouteAll:false` and must stay that way.
  3. MTU asymmetry: the worker's flannel derives 1280-50=1230, while existing nodes use 1450. Outer packets above 1280 are IP-fragmented (Linux VXLAN DF is unset by default). TCP MSS should follow the smaller end, but large UDP and PMTU edge cases need an explicit test.
  4. DERP relaying, as seen on the Air.
  5. Three production host changes (the Tailscale prefs on poweredge, gmktec and hp) plus admin approval. These are reviewed changes with rollback (`tailscale set --advertise-routes=`) and each gets an info-repo entry where applicable.

**Option B: move the whole fleet's flannel underlay to the tailnet.** Use `flannel-iface: tailscale0` with `node-ip`/`node-external-ip` set to tailnet IPs. It is symmetric and avoids subnet routes, but it sends all LAN node-to-node pod traffic through WireGuard (MTU 1280, CPU) and needs a rolling restart of every K3s node. K3s's native `--flannel-backend=tailscale` only works for K3s agents. This has a higher blast radius and should be the fallback if A fails.

**Option C:** a dedicated home subnet router (one node advertising 192.168.1.0/24). It has the same hijack risk, a single choke point and SNAT complications. Not recommended.

Tailnet prerequisite (owner action): **no tags exist today**. A scoped, short-lived, preferably ephemeral-for-fixture auth key tagged `tag:homelab-worker` needs a `tagOwners` entry. A restrictive ACL needs grants for worker to poweredge 6443, control plane to worker 10250, and nodes to worker UDP 8472 both ways. The current policy file was not readable here and needs to be read before changing it.

### Cheap isolated matching fixture (on the Air: arm64, 10 cores, 32 GiB, macOS 26.6.1; `limactl` not installed yet, `docker` CLI present)
- **Fixture VM `k3s-fixture`** (Lima vz, Ubuntu 24.04). Install k3s **v1.36.2+k3s1** with the production flags: `--disable traefik --disable servicelb`, `disable: [local-storage]`, `kubelet-arg max-pods=200`, the default vxlan flannel, and the default CIDRs 10.42/16 and 10.43/16. Inside it, run **k3d** with `rancher/k3s:v1.36.2-k3s1` (`--servers 1 --agents 1`) on its docker bridge. That gives a server with an embedded agent plus one K3s agent on a private "LAN", which emulates poweredge and gmktec. Arch differs from production (arm64 vs amd64), but version, flags and network config match, and those are what the spec says to match.
- **Worker VM**: the real production Lima template and start task, on a network that **cannot** reach the fixture's LAN. Verify that with a failed ping before adding routes. The fixture VM joins the tailnet with an ephemeral tagged key and advertises the k3d node /32s. Test both egress modes:
  - **Negative control:** in `agent` mode, `kubectl logs` against the worker fails with the "failed to find Session" path.
  - **Positive:** in `disabled` mode, logs, exec, port-forward and `kubectl top node` work, and `kubectl logs` on the k3d agent still works (the regression check).
- A cheaper first step is k3d alone on the worker VM's network, for the RBAC, CSR, kubelet bootstrap, kube-proxy, DNS and kube-router tests that do not need the underlay. Add the tailnet split second.

---

## 4. Recommended ordered slices (children)

Prerequisite: the "Homelab worker nodes" spec section must land through propose-change and revise before the first child is filed (004 §Routing). The heading-coverage rows go in with it.

1. **Fixture (portable, factory-eligible code; run on the Air).** Lima plus k3d fixture scripts pinned to v1.36.2+k3s1 with production-equivalent config. Record the baseline, plus the negative control that agent mode rejects a tunnel-less kubelet.
2. **Worker image and workflow.** `docker/homelab-worker/Dockerfile` (`TARGETARCH`, checksummed pins from section 2, systemd) and `homelab-worker-image.yml` (fabro conventions plus `platforms`). The workflow needs the exemption. Local native build on the Air.
3. **Start task, host list and VM capability probe.** `just start-homelab-worker-node-container <host>`, the declared host list (macbook-m4-max, macbook-air), Lima install-or-reuse with a minimum version, the vz VM with an XFS data disk, and the probe (AppArmor enforcing, userns with idmapped mounts, TUN, cgroup v2 delegation, rshared propagation, nested containerd, reflink). The start task and probe are factory-eligible code. Proving them on a host is a host change recorded in the info repo.
4. **Tailnet identity.** Policy tags, auth-key source, persisted tailscaled state, and the hostname `<host>-homelab-worker`. Owner action on the tailnet policy.
5. **Enrollment profile.** Bootstrap RBAC bindings, operator token mint, kubelet TLS bootstrap with a pinned CA, the hold taint, and the serving-CSR verifier and approver. Proven on the fixture.
6. **Node networking agents.** flannel v0.28.4, kube-proxy v1.36.2 and kube-router v2.6.3 firewall-only, as worker-class DaemonSets with RBAC. On the fixture: pod-to-pod both ways, ClusterIP, DNS 10.43.0.10, a NetworkPolicy deny test, and an MTU test.
7. **Underlay and egress-selector change.** Fixture proof of `egress-selector-mode: disabled` plus the per-node /32 subnet routes (Option A). Then one reviewed production PR (config.yaml key, the three nodes' advertise-routes, admin approval) with a recorded rollback, applied at zero active jobs.
8. **M4 Max production join under hold** (end of Phase C). Ready node, `system:node:macbook-m4-max-homelab-worker`, logs, exec, port-forward and stats, routing, DNS and policy proofs.
9. **Air rerun** (Phase D). Then Phases E and F per 004.

### Biggest unknowns, in rough risk order
1. **VXLAN over the mixed underlay**: outer-packet routing with `dev eno1` and a fixed LAN `local`, Tailscale AllowedIPs acceptance of LAN-sourced packets, 1280 vs 1450 MTU fragmentation, and DERP relaying (the Air was on relay "sao"). If Option A fails, Option B is a fleet-wide underlay change.
2. **The egress-selector `disabled` production restart**: CI-job blast radius, agent-side behavior, and the aggregated API paths.
3. **AppArmor profile loading, pod user namespaces (idmapped overlay and tmpfs) and reflink inside a privileged container in a Lima vz VM** (Ubuntu 24.04 kernel 6.8). Verify the state of the `UserNamespacesSupport` gate at v1.36.2.
4. **The tailnet policy**: there are no tags today, the ACL contents are unknown, and it needs owner edits.
5. Whether upstream kube-router v2.6.3 enforces the same NetworkPolicy semantics as the k3s fork, and whether it agrees on the iptables backend.
6. Serving-cert approval automation and rotation, and keeping the bootstrap token out of argv and environment through nerdctl.
7. Minor: CoreDNS `NodeHosts` is K3s-maintained and may not list the worker. Only node-name resolution from pods is affected.

Not read: hp-xubuntu's Tailscale prefs (SSH host key verification failed from this Mac and from poweredge), the tailnet ACL, and the M4 Max hardware (read macbook-m4-max-info).

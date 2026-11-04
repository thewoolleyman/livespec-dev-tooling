# Portable container worker nodes for spare home and cloud compute

Research date: 2026-11-03 UTC. Proposed implementation design; no worker image, bootstrap recipe, host installation, enrollment or cluster change was executed by this research.

Interface clarified 2026-11-04: one worker container per host or configured cloud execution target; the command accepts the host/target name and derives the worker identity.

Provenance: published as `docs/research/2026-11-03-portable-container-worker-nodes.md` (PR 3320, corrected by PR 3338) and moved unchanged in substance into plan `homelab-k8s-worker-nodes` on 2026-11-04. Later maintainer rulings in [001-macbook-air-first-dogfood.md](001-macbook-air-first-dogfood.md) govern where they differ from this report: the 2026 M5 MacBook Air is the FIRST dogfood host (not a Linux amd64 PC), the macOS runtime is Homebrew-installed Lima with the VZ backend installed or reused by the start just task (not Docker Desktop or Colima), and the first milestone is one representative CI job with factory workloads afterward. This report remains the design background for the worker image, bootstrap, networking, cache and telemetry sections.

## Recommendation and scope

**Build the custom OCI worker in livespec-dev-tooling. Start with one existing Linux amd64 PC, prove a representative workload, then enable native arm64 workloads on the Macs.** Keep a single image source and operator interface, with explicit cluster and runtime profiles. The supplied architecture decision is the preferred direction: upstream kubelet and containerd, standard Kubernetes authentication, no K3s agent dependency. Its portability is a property to prove, not something an OCI manifest alone supplies.

This is a separate option from the [cloud burst report](003-cloud-burst-capacity-2026-11-02.md), which examines provisioned cloud machines and their economics. Here the first capacity comes from already-owned PCs, a MacBook and a Mac Mini, with the same packaging usable on compatible cloud Docker hosts. The original report's workload admission, local storage and throughput criteria still apply.

**Run one worker container per host.** Its kubelet and nested containerd run multiple pods, each containing its own workload containers. Additional capacity comes from adding hosts, not from creating more worker containers on the same machine.

The proposed interface takes the host name:

```sh
just start-homelab-worker-node-container spare-pc
just start-homelab-worker-node-container macbook-m4
just start-homelab-worker-node-container mac-mini
just status-homelab-worker-node-container macbook-m4
just stop-homelab-worker-node-container macbook-m4
```

These are **proposed recipes, not commands available today**. The required argument identifies the physical host by its existing Tailscale name, or selects a declared cloud execution target. The wrapper derives one stable worker identity as `<host-or-target>-homelab-worker`: `macbook-m4` produces the container name, Kubernetes Node name and worker Tailscale hostname `macbook-m4-homelab-worker`. A rerun reconciles that same worker and its persistent storage. There is no replica count, instance suffix or second worker per physical host in the initial interface.

The existing host identity remains the bootstrap/administrative address. The derived worker has its own tailnet identity so its Linux network namespace is reachable, including inside a Mac's Linux VM; this is a second network identity, not a second worker container. Record the host-to-worker relationship explicitly and preserve the host's existing name and credentials. A cloud target resolves through configuration to the selected provider/service and runtime, with the same stable naming and single-worker lifecycle. It is eligible only if that service supports the required privileged nested runtime and networking; accepting a cloud target name does not establish those capabilities or authorize new paid resources.

Dev-tooling is the right owner: it already owns the workload images, CI node integration, cache provisioning, delegated gates and host configuration. Tailscale policy and credential issuance stay with their existing owners; collector configuration stays in `thewoolleyman/otel-collector`; future Talos fleet admission stays with homelab. Do not create another image registry, secret store, scheduler or observability product.

**Two qualifications change the implementation plan.** A generic worker needs a running CNI agent, Service routing and policy enforcement in addition to the components in the supplied decision. And Docker on macOS runs Linux containers in a VM: native macOS Tailscale, an arm64 worker image and `docker run --privileged` do not by themselves satisfy the existing jobs' Linux kernel, AppArmor, user-namespace and architecture requirements.

## Evidence and limits

Repository inspection used these local revisions; current manifests and executable code take precedence over historical comments:

| Repository | Revision | Inspected surfaces |
|---|---|---|
| livespec-dev-tooling | `7dfb82add8453fa9e9f8d505e230d69b0f9a43e6` | Image workflow/Dockerfiles, K3s configuration, ARC, Kueue, gates, caches, factory inventory and Ansible roles |
| mi-homelab/homelab | `e47a81b4e049b5f403b8e5c886b36e34e83093b3` | Current OS, network, ownership and secret constraints |
| livespec-orchestrator-beads-fabro | `3da03d7bc803f615ccc032b6d504b283c6fffc49` | Repository context; actual configured factory providers were read from dev-tooling inventory |
| otel-collector | `0d575ce08597a8bb01ef4accc9847bcedca568ba` | CI/agent collector shapes and existing macOS routing work; CI/agent configurations also fetched from GitHub |

Upstream documentation and source were fetched on 2026-11-03, linked beside the findings below. K3s source was inspected at `v1.36.2+k3s1`, the version recorded by the earlier report; confirm the serving cluster's version and flags before implementation. No live Mac/PC capability inventory, CSR bootstrap exercise, network proof, cache benchmark, current ledger survey or provisioning was performed. Engineering estimates below are judgments, not measured delivery times.

## What the worker image actually contains

Publish a new image such as `ghcr.io/thewoolleyman/livespec-worker-node`, separate from the **workload** image `livespec-fabro-sandbox`. The node executes those existing workload images in its own containerd; putting compilers and ACP adapters in the worker's root filesystem would neither install them into pods nor warm their image layers.

| Component | Purpose and configuration boundary |
|---|---|
| Upstream kubelet | Node registration, pod execution and authenticated kubelet API; version pinned to the supported target Kubernetes line |
| containerd 2.x, compatible runc, CRI client | Dedicated inner runtime, matching kubelet's cgroup driver and pod user-namespace requirements; own persistent store and socket |
| CNI executable plugins **and an actual CNI agent** | Current profile supplies compatible Flannel, its cluster network/backend settings, PodCIDR handling and annotations; future profiles use that cluster's CNI |
| kube-proxy or the cluster's equivalent | ClusterIP/Service routing; kubelet and Flannel do not supply it automatically |
| NetworkPolicy implementation | Equivalent enforcement to the current K3s policy controller; a worker that silently ignores factory policies is unacceptable |
| Tailscale in kernel networking mode | A distinct `tailscale0` inside each worker namespace; persisted device state, restricted enrollment and no host port publishing |
| Node support files | Pinned ARC hook, matching runner externals, architecture-correct sccache binary, AppArmor profile support, cache span emitter and required node paths |
| Small service supervisor and health checks | Start dependencies in order, forward signals, reap children, expose local diagnostics and fail readiness if a required service dies |

Use established containerized-node patterns for cgroups, writable `/run`, mount propagation and process supervision. [kind's Docker launch code](https://github.com/kubernetes-sigs/kind/blob/main/pkg/cluster/internal/providers/docker/provision.go) and [base image](https://github.com/kubernetes-sigs/kind/blob/main/images/base/Dockerfile) are useful references; they do not make an external-cluster join supported automatically. A conventional minimal systemd arrangement is acceptable if it reduces custom supervisor code; avoid building a new init system.

Use a private outer Docker network namespace, a delegated cgroup subtree and explicit persistent volumes for the host's single worker. Its inner runtime supplies the separate pod and workload-container namespaces; multiple pods do not require multiple outer worker containers. No Docker socket is mounted into build pods. Privilege at the outer node container is a host trust decision, not strong isolation from that host.

For the current profile, package support files at the paths the manifests already read, even where a path contains `k3s`. For example, `/usr/local/lib/ci-runner-k3s/hooks/2.336.0/index.js` is an existing hostPath contract; retaining that pathname does not require running a K3s agent. Render the actual CRI endpoint explicitly rather than relying on `k3s crictl` defaults.

## Standard bootstrap into the existing K3s cluster

**Standard Kubernetes authentication is feasible, but the cluster needs an enrollment profile.** K3s's [API-server source at the examined version](https://github.com/k3s-io/k3s/blob/v1.36.2%2Bk3s1/pkg/daemons/control/server.go) enables bootstrap-token authentication. This establishes one prerequisite; it does not establish that the exact RBAC, approvers and signer configuration needed by these workers already exist.

The controller-side preparation should install a narrowly scoped, reviewed enrollment path once. Then the wrapper can obtain a short-lived bootstrap credential through the existing authorized credential source, pin the cluster endpoint and CA, submit the node's CSR and wait for the verified result. The resulting kubelet client identity is `system:node:<host-or-target>-homelab-worker` in `system:nodes`, with certificate rotation and Node authorization/restriction preserved. Configure the node's serving certificate separately with the expected tailnet DNS/IP SANs.

[Kubernetes TLS bootstrap documentation](https://kubernetes.io/docs/reference/access-authn-authz/kubelet-tls-bootstrapping/) explicitly distinguishes client and serving certificates: built-in approvers do **not** automatically approve kubelet serving certificates. For the pilot, a controller-side bootstrap command may verify and approve the exact expected CSR. Do not grant every worker permission to approve arbitrary CSRs, place a signing CA on worker machines, or distribute cluster-admin kubeconfigs. CNI and kube-proxy need their own appropriately scoped identities; a node's kubelet identity is not a general node-listing credential. The [K3s Flannel integration](https://github.com/k3s-io/k3s/blob/v1.36.2%2Bk3s1/pkg/agent/flannel/setup.go) itself calls out this distinction.

The supplied host identifier selects configuration; **it is not authentication**. A previously authorized operator session or scoped bootstrap source is still necessary. There cannot be secure zero-credential enrollment of an arbitrary machine solely because it claims a known name. Keep enrollment material in protected files or a secret mount, never baked layers, Git, command argument values, logs or a Docker-inspect-visible secret environment variable.

Kubelet bootstrap and CNI readiness are separate stages. Mirror the cluster's PodCIDR allocation, Flannel backend/VNI/port/MTU, masquerading, CNI configuration and policy behavior. Do not install a second cluster-wide Flannel DaemonSet on existing K3s nodes: its embedded agents already run that function. Target any additional agents only at the new container-worker class. [K3s networking options](https://docs.k3s.io/networking/basic-network-options) and the examined source are configuration inputs, not permission to change every node's network.

**The important K3s control-plane change is egress selection.** The [server reference](https://docs.k3s.io/cli/server#networking) documents `egress-selector-mode=agent` as the default; it sends API-server operations through K3s agent tunnels. A generic node has no such tunnel. For this proposal, first prove `egress-selector-mode=disabled` in an isolated matching K3s cluster and direct connectivity from the real server's network to all required kubelets and Service endpoints. The documented disabled mode requires servers to retain their local agent. A production change is cluster-wide, requires the normal controlled restart/drain procedure, and must be regression-tested against existing nodes. Merely seeing the new Node become Ready does not prove `logs`, `exec`, `port-forward` or kubelet statistics work.

Pin a worker release to the deployed Kubernetes version rather than installing upstream latest; follow the [version-skew policy](https://kubernetes.io/releases/version-skew-policy/) for kubelet and kube-proxy. Preserve the resolved image digest and profile revision in the local non-secret manifest and node labels/annotations used for diagnostics.

## Networking through Tailscale without opening household ports

Run kernel-mode Tailscale **inside the worker's network namespace**, whether its binaries are bundled in the custom image or its pinned official container shares that namespace. Bundling is the simplest operator-facing packaging; a networking sidecar remains an implementation choice and does not constitute another Kubernetes worker. This gives the host's worker a routable node address under the derived `<host-or-target>-homelab-worker` name without requiring host networking or `-p` mappings. Host-native Tailscale provides bootstrap/administrative access under the existing host name, but it is not a substitute for the worker's network identity, especially on macOS.

[Tailscale's container parameters](https://tailscale.com/docs/features/containers/docker/docker-params) document persisted state, explicit hostname, login-once behavior and that userspace mode is the default. Set kernel mode deliberately, provide `/dev/net/tun` and the necessary privileges, and retain state across restarts. Its [containerboot implementation](https://github.com/tailscale/tailscale/blob/main/cmd/containerboot/main.go) supports `file:` credentials. Use short-lived enrollment material scoped to the worker tag; steady-state operation uses the persisted device identity. [Userspace SOCKS/HTTP proxying](https://tailscale.com/kb/1112/userspace-networking) is not the proposed transport for arbitrary CNI traffic.

The desired traffic paths are:

```text
Mac / PC / cloud Docker host
  worker namespace: Tailscale + kubelet + containerd + network agents
    -> tailnet -> Kubernetes API and existing node endpoints
    -> Flannel over tailnet/routed underlay -> remote pods and Services
    -> tailnet -> existing OTel gateway -> Honeycomb HTTPS
    -> normal outbound HTTPS -> registries, GitHub, dependencies and model APIs
```

Here "all networking through Tailscale" means private cluster/control/telemetry transport. Sending every public image pull and model request through an exit node is possible as a separate policy, but adds a bandwidth dependency with no capacity benefit. The bootstrap should validate ordinary outbound access and any approved proxy; it must not silently replace household routing or a user's corporate VPN.

**There is still a mixed-address underlay problem.** Existing nodes advertise LAN addresses, while the new workers would advertise tailnet IPs. Reaching `poweredge:6443` over Tailscale does not establish access to its LAN-addressed Flannel endpoint. Investigate an explicitly approved Tailscale subnet route to the required home node addresses, plus verified routes from every existing node to the workers. Prove return traffic, source NAT interactions and VXLAN endpoint behavior. Do not claim that subnet routing alone is already a working solution. The alternative is a reviewed node-address-plane change; do not casually rewrite the live fleet to avoid testing the first route.

| Flow | Required proof |
|---|---|
| Worker to API | CA-verified TCP 6443 over tailnet, including reconnect |
| API server to worker | Authenticated kubelet TCP 10250, streaming operations and stats over the selected egress path |
| Existing/new node pair in both directions | Matching Flannel encapsulation, currently VXLAN UDP 8472; correct MTU and no public listener exposure |
| Pod to pod/ClusterIP/DNS | Distinct assigned PodCIDRs, CoreDNS, kube-proxy rules and effective NetworkPolicy |
| Worker to caches/gateway | Namespace and tailnet policies permit only intended services; DNS works before and after pod networking |

No household router forwarding or public kubelet/VXLAN/OTLP port should be needed. Tailscale still needs its documented outbound control/relay connectivity; restrictive networks may force DERP, with a throughput cost. Bind private services to intended interfaces and apply tailnet ACLs; "no published Docker ports" does not mean services inside a privileged namespace are automatically safe.

The wrapper can converge its own settings and verify shared network policy. It cannot grant itself tailnet administration or silently authorize a subnet route. Missing shared prerequisites should produce one actionable diagnostic, with no partially admitted worker.

## Host portability and pod capacity

| Host | First implementation posture | What must be established |
|---|---|---|
| Linux amd64 PC or VM | First supported target, rootful Docker | Compatible kernel, cgroup delegation, nested runtime, AppArmor and pod user namespaces; local writable storage |
| Linux arm64 | Same node image source, native arm64 build | Every selected workload/support image and binary must also support arm64 |
| Apple Silicon MacBook/Mac Mini | Supported through a tested Linux VM runtime profile | Native arm64 workload chain, VM kernel/LSM/filesystems, configured VM CPU/RAM/disk and restart/sleep behavior |
| Intel Mac | Linux VM profile, amd64 workloads | Same kernel/LSM/filesystem and VM lifecycle checks; CPU architecture alone does not solve them |
| Podman, Windows/WSL2, managed container services | Later compatibility targets | Explicit privileged/nesting and networking proof; Docker API or OCI support alone is insufficient |

Reuse a compatible existing Docker installation. For an unprepared Linux host, the wrapper can idempotently install the supported rootful engine and required packages using the platform package manager. Do not treat rootless mode as the initial support target: it adds [cgroup and nesting requirements](https://kind.sigs.k8s.io/docs/user/rootless/) without adding capacity sooner.

On macOS, reuse a tested Docker Desktop installation if capable; otherwise use a named, reproducible Linux VM profile through [Colima](https://github.com/abiosoft/colima) or an equivalent existing runtime. Installation may require normal administrator authentication or a one-time runtime setup; the wrapper should detect this instead of waiting invisibly for a GUI. Reuse an installed package manager, report an absent one, and do not accept licensing terms automatically. Do not enable a runtime's bundled Kubernetes cluster: this container joins the existing control plane.

Do not use `--network=host` as a cross-platform shortcut. [Docker Desktop host networking](https://docs.docker.com/engine/network/drivers/host/) is opt-in from 4.34, operates at layer 4 and does not grant direct access to host interfaces. Per-worker kernel Tailscale inside the VM avoids depending on macOS host-interface binding.

The existing ARC workflow template requires `hostUsers: false` and a **Localhost AppArmor profile** (`ci-runner-workflow`). [Pod user namespaces](https://kubernetes.io/docs/concepts/workloads/pods/user-namespaces/) require compatible kernels, idmapped mounts and supporting runtimes; current documentation specifies containerd 2.0+ support and at least Linux 6.3 for the relevant tmpfs support. Loading the AppArmor profile is a capability of the underlying Linux kernel/LSM and its policy namespace, not merely a file copied into the node image. Test the real VM. If it cannot enforce this workload posture, reject that profile or provide a compatible Linux VM image; do not remove the isolation requirements to announce Mac support.

The current image chain is not yet a native Apple Silicon lane: the base Dockerfile downloads `gh_*_linux_amd64`, and the agent layer pins x86_64 sccache and herdr assets. The image build workflow has no multi-platform build declaration. The runner image digest, hook externals, populator image and all auxiliary images also need architecture checks. Convert asset selection to `TARGETARCH` with per-architecture checksums and publish manifest lists for the selected workload chain. Start Mac validation with the Python-only chain, then the Rust chain; do not use QEMU-emulated amd64 compiles as the promised capacity gain or relabel an arm64 node as amd64.

Allocate a host/VM resource budget to its single worker, then let Kubernetes schedule multiple pods within that budget. Verify that the kubelet's advertised allocatable resources fit the worker's configured envelope rather than assuming outer runtime limits automatically change Node capacity. The budget must include worker services, all nested pods and cache warmers while preserving capacity for the host's other uses. Follow the [capacity guidance](../../../.ai/ci-node-capacity-reads.md); no numeric pod or slot cap is authorized by this report.

Keep the Mac's storage in the Linux VM's local disk rather than a macOS shared source directory. A laptop closing its lid or losing power can strand jobs: use the normal drain command before planned sleep; unexpected disappearance must yield an identifiable failed/interrupted run, never green. Do not change global sleep policy without an explicit operator setting.

## Idempotent bootstrap and lifecycle contract

Keep the just recipe thin, delegating to one versioned bootstrap script and reviewed cluster profile. The required host/target name is sufficient only when the default cluster and authorized credential source have already been configured. Resolve cloud targets through declared provider/service configuration. Optional flags can select runtime, cluster profile and resource envelope; derive the physical-host label from the resolved target rather than requiring another worker identifier. Avoid a new configuration framework or replica-management interface.

1. Resolve and validate the requested host/target, derive `<host-or-target>-homelab-worker`, and acquire a lock for that canonical host/target. Verify the expected host and runtime context before installing anything; remote execution must explicitly handle credential delivery and storage on that target rather than assuming local paths exist on a remote daemon. Detect OS, CPU architecture and existing runtime.
2. Ensure the supported runtime is installed/running; select the named Mac VM where needed. Probe the **engine's Linux kernel**, not `uname` on Darwin, plus cgroups, TUN, networking modules, AppArmor, user namespaces, mount propagation and available disk. Persist only owned host changes and explain any restart required; never restart a shared engine with other running work automatically.
3. Read the host/target's existing worker manifest and its identity/state volumes. Reconcile the single existing worker, and refuse a second worker or a conflicting identity claim for that host. An unchanged rerun reuses the same derived name, Tailscale identity, Kubernetes Node and runtime state; it does not mint another device, append an instance suffix or wipe credentials.
4. Fetch missing enrollment material through the authorized source into restricted temporary files. Start the digest-pinned node container with private networking, explicit mounts/cgroups and a restart policy. Keep bootstrap credentials separate from persistent runtime identity and remove disposable enrollment material after use.
5. Establish Tailscale, verify exact hostname/device ownership and ACL reachability, then perform CA-pinned Kubernetes bootstrap. Start the runtime and cluster-specific network agents. Keep the node tainted/cordoned until the full node/workload check passes.
6. Converge support files, local storage, caches, telemetry and node labels. Prove one representative workload and advertise only the measured admission allocation through the owning control-plane configuration. Report image/profile revision, node/tailnet identity, health and useful next action without secret values.

Use separate persistent stores for device/kubelet identity, inner containerd and work/cache data. State belongs to the host/target's single worker; never clone a live identity volume onto another host. Preserve identity on a normal stop/start; a deliberate destroy revokes the worker's device/bootstrap identity, removes its Kubernetes Node after drain, and deletes only explicitly selected owned state. Preserve the physical host's Tailscale identity. Upgrades cordon/drain and replace that host's worker before admitting new pods; a digest change must not force-kill existing factory or gate work. A failed drain reports the remaining jobs and holds rather than deleting on a timer.

Record the enrollment material's expiry and support renewal/re-enrollment diagnostics. Rerunning the wrapper should recover a stopped container and detect stale cluster identity; it must not interpret an unavailable API as permission to delete identities. Protect key-bearing volumes at rest; the diagnostic manifest contains references and public identifiers, not secret values.

## Cache audit and the portable-node adaptation

The caches already have distinct ownership and consumers. Preserve these boundaries rather than mounting a common writable directory into unrelated jobs.

| Existing cache/path | Current implementation | Behavior required on the container worker |
|---|---|---|
| Outer image store | Docker holds images used by the host | Pulling the worker here does **not** warm the nested workload store |
| Workload image store | Node containerd holds pinned CI/factory images; image warm/prune roles target actual configured pins | Persist the inner store and warm through its CRI socket; adapt commands that assume `k3s crictl` and data paths |
| GHCR pull-through mirror | `warm-cache/registry-mirror/` uses the cache carrier's hostPort 5001 and K3s `registries.yaml` | Generic containerd needs equivalent `certs.d/hosts.toml` configuration and an explicit upstream fallback, or initially pull pinned images directly; a K3s YAML file is not consumed by upstream containerd |
| Warm uv generations | Trusted populator builds from current routed locks, verifies/budgets, publishes atomically; provisioner seeds private reflinks | Reuse the per-node warmer and same-filesystem layout; do not copy a whole home cache at each job start |
| PyPI files proxy | Carrier nginx caches absolute locked artifact URLs; gate jobs also use file/Simple-API fallback | Keep existing service initially; measure its WAN cost. Changing only `UV_INDEX_URL` does not cache frozen locks' absolute wheel URLs |
| Cargo crate downloads | Carrier crates proxy serves registry/index/artifacts; ARC hook writes Cargo configuration | Reach it through working Services or use an explicit bounded direct fallback when unavailable; do not mount a shared mutable `CARGO_HOME` |
| CI Rust compilation cache | Carrier Redis, default read-only jobs, trusted default-branch writer only | Preserve server-enforced ACL separation; correct architecture/toolchain/profile keys; verify hits from the new node |
| Warm Rust target generations | Carrier publishes ASAN fuzz trees; local provisioner reflinks published generations | UV-only node warmer does not populate these; use an architecture-matched generation path or explicitly record cold fuzz behavior |
| Factory compilation cache | Agent image has its own sccache wrapper/config, historically `redis://172.17.0.1:6379` | Configure a reachable endpoint for this backend; nested Docker's gateway is not the existing factory host |
| Delegated pre-commit/pre-push | Gate Job gets a private seeded uv PVC, PyPI fallback, read-only Redis and exact source refs | Preserve these while adding placement; a new Node does not automatically change the existing gmktec-only gate flavor |

Source anchors: [warm-cache design](../../../ci-runner/k3s/phase2/warm-cache/README.md), [per-node warmer](../../../ci-runner/k3s/phase2/warm-cache/warm-cache-cronjob.yaml), [provisioner](../../../ci-runner/k3s/phase2/local-path-provisioner/local-path-provisioner.yaml), [ARC hook](../../../ci-runner/k3s/phase2/arc/hook-pod-template.yaml), [sccache](../../../ci-runner/k3s/phase2/sccache/README.md), [agent image](../../../docker/fabro-sandbox/agent/Dockerfile), [image warm role](../../../ansible/roles/sandbox_image_warm/defaults/main.yml), [gate template](../../../ci-runner/k3s/phase2/gates/gate-job-template.yaml) and [source mirror](../../../ci-runner/k3s/phase2/gates/README.md).

**Reuse the existing per-node uv DaemonSet first.** It already selects non-carrier nodes with `ci-runner.io/warm-uv-cache=true`, sets `WARM_CACHE_UV_ONLY=true`, runs immediately then every 30 minutes, and writes `/var/lib/rancher/k3s/storage/.warm`. Its current workload image must be multiarch before arm64 admission. The carrier remains the sole cargo/sccache/target writer; do not give each new worker the shared writer secret. Rebuilding a uv generation natively on arm64 selects appropriate platform artifacts, unlike copying an amd64 cache and assuming complete hits.

**Filesystem support is a real portability condition.** Provisioning uses `cp -a --reflink=always` from `.warm` into sibling work PVCs. The warm root and work directories must share a reflink-capable filesystem. An arbitrary Docker volume, especially a VM's default ext4 filesystem, does not establish that capability. Prefer a local XFS work/cache volume following the [storage guidance](../../../.ai/ci-node-storage-tiers.md), implemented as a suitable VM disk or, if needed, a tested per-worker local disk image with reflink support. Do not format an operator disk automatically. Verify the actual clone operation inside the node and measure its cost. An initial cold cache is correct but must be reported; a new expensive full-copy fallback is not an optimization.

The existing provisioner deliberately gives jobs private copy-on-write inodes; writable hardlink seeds or a shared writable warm lower would reintroduce cache poisoning. Preserve verifier checks, budgets, atomic publication, retained-generation pruning, kill switches and cold canaries. Local-path PVCs are node-bound, and their requested size is not an enforced filesystem quota: monitor actual free space and prune safely without deleting active job data.

For the first LAN workers, retain the shared PyPI/crates/Redis services and measure them; do not deploy three new proxies per laptop. For WAN workers, compare warm and cold execution with home uplink and RTT. Add a node/site-local artifact proxy or bounded read-through tier only if measured misses/transfer time justify it. A separate Redis replica is not free improvement: sccache's many reads can remain latency-sensitive, and maintaining trusted writer semantics across replicas is extra work. Do not stretch writable filesystems or replicate Redis synchronously over the WAN.

Compilation-cache keys are architecture-, compiler-, flags-, profile- and sometimes path-dependent. An arm64 compiler cannot reuse x86 object files. The current sccache documentation also notes workspace path matching (`/__w/<repo>/<repo>`), incremental restrictions, uncached linker/proc-macro work and coverage-profile gaps. Keep common paths and verify useful hits rather than promising universal reuse. Factory paths/profiles differ from ARC and may benefit less even when Redis is reachable.

The factory image's `sccache-or-rustc` wrapper provides cold correctness when its backend cannot start; preserve it and its telemetry. Do not assume the ARC hook configures factory pods: backend-specific endpoint/config projection must be verified, including fail-closed environment allowlists. The current configured factory process specs use 4 CPU and 7629 MiB per sandbox; keep reservation-based placement and measure before any resource reduction.

## Telemetry without Honeycomb credentials on every worker

**Use the existing OpenTelemetry Collector architecture, with a private gateway receiver.** The Kubernetes control plane is not itself an OTLP proxy. A collector on poweredge or an existing infrastructure host can receive OTLP over Tailscale and export to Honeycomb using its existing ingest identity. This needs a small collector configuration addition, not another telemetry system or a custom forwarding protocol.

Current evidence: the [CI collector](https://github.com/thewoolleyman/otel-collector/blob/main/config.ci-runner-host.yaml) has loopback OTLP receivers and a pod-facing listener at its own cni0 address; it also discovers nodes and reads kubelet stats through the API-server proxy. The [plain agent collector](https://github.com/thewoolleyman/otel-collector/blob/main/config.k3s-agent-host.yaml) collects host metrics but has no OTLP listener. Neither proves a tailnet-bound gateway exists. Add a receiver bound specifically to the gateway's tailnet interface, restricted by worker-tag ACLs; validate the live serving config before directing workers to it. Preserve processors, signal routing and resource attribution, and avoid double-scraping kubelet metrics already collected centrally.

Inside each new worker, a small collector accepts the existing cache/build spans at **that node's** cni0 gateway and forwards them over the tailnet. The [cache emitter](../../../ci-runner/k3s/phase2/cache-telemetry/README.md) derives this gateway in each pod; pointing every worker at poweredge's `10.42.0.1` would silently lose spans. Carry node ID, physical-host ID, architecture, cluster, image digest and VM/container scope. A Linux collector inside a Mac VM reports Linux VM resources, not native macOS totals or Apple GPU availability.

Factory build spans also pass through the orchestrator-owned receiver/dispatcher path; ensure its established transformation and endpoint projection are retained rather than bypassed by a new gateway. Provision no Honeycomb ingest key into ordinary build pods. Use bounded queues/retry and telemetry loss/heartbeat visibility; an unreachable collector must not turn a successful compile into a failed gate, and missing telemetry must not count as healthy.

If a tailnet collector receiver cannot be made available quickly, the bounded fallback is a per-worker collector exporting HTTPS directly to Honeycomb with a scoped ingest credential injected at runtime. The wrapper tests the configured Honeycomb endpoint and reports denied egress; it does not open inbound household ports or grant itself authority to weaken firewalls. Direct export is optional fallback, not a second mandatory implementation before the first worker can run.

## Scheduling and GitOps integration

Keep the existing cluster controllers and declarative manifests. The wrapper owns a worker's runtime and enrollment, while the cluster configuration owns workloads, admission and policy. Add a container-worker class label and initial taint; target the canary deliberately rather than exposing the whole pool before capability tests pass.

- **ARC:** current [values](../../../ci-runner/k3s/phase2/arc/values-livespec-dev-tooling.yaml) require the fleet hook hostPath and compatible runner externals. [ResourceFlavor](../../../ci-runner/k3s/phase2/kueue/resource-flavor.yaml) matches `k3s-role=arc-runner-host`, and admission uses `ci-runner.io/churn-slot`. New capacity needs the right labels, measured resource advertisement and an explicit quota allocation. ARM workloads need architecture-aware placement/flavors and matching runner/workload images; avoid mixed-architecture runner/workflow pairs on a shared local PVC.
- **Delegated gates:** [gates-flavor](../../../ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml) currently selects `gmktec-xubuntu`. Extend it deliberately only after proving the new node, credentials, cache path, source mirror and exact tree/base refs. Keep gate verdict and lost-run semantics unchanged.
- **Factory:** eligibility, namespace quotas, provider configuration and dispatcher limits remain separate from Kueue's ARC admission. Add proven compatible nodes to placement without restarting the factory service. A host's single worker may run multiple factory pods within its admitted budget; long model runs should initially use stable plugged-in hosts.

The existing [boot converge](../../../ci-runner/k3s/phase2/reconstruct/converge-ci-stack.sh) is the current declarative delivery mechanism. Package new node support and cluster manifests through it and the wrapper's profile; do not install Flux as an unrelated prerequisite. A rebuilt node should reconcile into the same intended role without transferring ownership of cluster controllers to the laptop.

## Publishing and future Talos compatibility

Follow the existing [Fabro image workflow](../../../.github/workflows/fabro-sandbox-image.yml): GitHub Actions Buildx, PR build validation without public publication, GHCR publication on relevant master changes and releases, SHA and semver tags, digest-pinned consumption and no mutable `latest`. Use a new image workflow/path rather than adding the worker as a compiler-image layer. Multiarch builds need explicit `linux/amd64` and `linux/arm64` manifests and architecture-specific asset verification; run hardware capability proofs separately from image build success. Workflow changes follow the repository's existing authorization policy when implemented.

The current homelab tree declares Talos/Omni lifecycle but provides no inspected worker-image publication convention to supersede dev-tooling's existing one. Reuse the working GHCR convention; do not wait for an imagined homelab image pipeline.

**Future Talos support requires an explicit architectural accommodation.** The current [homelab constraints](https://github.com/mi-homelab/homelab/blob/e47a81b4e049b5f403b8e5c886b36e34e83093b3/SPECIFICATION/constraints.md) require Talos for Kubernetes server nodes, KubeSpan for node transport and Tailscale as an access plane whose outage cannot stop in-cluster communication. A Linux container with upstream kubelet and Tailscale transport is not an Omni-managed Talos machine and does not implement KubeSpan. Calling it an external client does not remove the fact that it joins the cluster as a worker.

Keep a future generic external-worker profile possible, but record it as an exception/change to those homelab policies before production admission. It needs independently proven API bootstrap/signing, CNI, Service and policy agents, node transport and lifecycle ownership. Standard Kubernetes APIs improve reuse; they do not guarantee the exact same image contains a future CNI's kernel/eBPF dependencies or that KubeSpan discovers a non-Talos node. A profile may require a new image build from the same source.

[Talos itself has a Docker mode](https://docs.siderolabs.com/talos/v1.12/platform-specific-installations/local-platforms/docker), documented for CI/local testing with unavailable upgrade/reset APIs in container mode. It is useful for a later compatibility fixture, not evidence that this generic worker is a supported Omni-managed production node. Defer the supplied decision's Talos validation criterion to phase two as requested; phase one must clearly claim **K3s validated, Talos unverified**.

## Fast implementation sequence and acceptance

Use a short feasibility proof before polishing the bootstrap. One engineer familiar with this fleet could reasonably budget **half to one day** for the critical generic-worker/network spike, then **roughly 3–6 further engineer-days** for the first supported Linux package, credential flow, cache/telemetry integration and lifecycle proof. Native Mac support is additional work, plausibly **2–5+ days** depending on workload multiarch conversion and VM kernel/AppArmor support. These are low-confidence estimates; a missing kernel capability or required cluster network change can dominate them. No estimate includes waiting for credentials or host access.

1. **Prove the hard path first.** Use an isolated matching K3s control plane and one Linux amd64 node container. Demonstrate standard bootstrap, serving certificates, direct kubelet access, Flannel/Services/DNS and policy enforcement. Establish the production underlay/control-plane change and rollback before touching the live server. If this cannot work without a broader network refactor, report that result promptly; do not hide a K3s agent in the image or silently create a second cluster.
2. **Ship the smallest working package.** Add the Dockerfile/service configuration, thin just recipes and idempotent bootstrap with one supported Linux profile. Connect the existing publishing convention, node support files, uv warmer and OTel gateway. Test a single canary and repeat start/stop/restart before general admission.
3. **Add native Apple Silicon capacity.** Publish the node and selected Python workload/support chain for arm64; prove a compatible Linux VM profile, storage and existing pod isolation on an actual Mac. Then enable the Rust/factory chains where their binaries and jobs are ready. This is part of the intended feature, not satisfied by an ARM Node sitting idle.
4. **Expand only the useful paths.** Add measured ARC allocation, then gates and stable-host factory placement. Introduce WAN-specific cache improvements only where the measurements show a benefit. Talos, Podman/rootless parity, autoscaling and an all-host management dashboard are deferred.

Acceptance evidence must cover:

| Area | Required result |
|---|---|
| Idempotence and identity | Repeated bootstrap with the same host/target name preserves exactly one worker container, worker device and Kubernetes Node under `<host-or-target>-homelab-worker`; a second worker on that host is refused, different hosts receive distinct identities, and any existing host Tailscale identity is preserved |
| Runtime and capacity | Multiple pods run concurrently through the single worker's inner containerd; advertised allocatable resources, cgroup accounting and runtime limits respect the host/VM budget; architecture matches executable workloads |
| Network and policy | Bidirectional old/new-node pods, DNS/ClusterIP, deny/allow NetworkPolicy tests, API streaming and stats, MTU, reconnect and no public host port exposure |
| Actual fleet workload | A routed ARC job with the real hook/AppArmor/userns posture succeeds; gates and factory each need their own proof before claiming support |
| Cache correctness and performance | Cold/warm timings and image bytes, local uv generation/reflink, sccache hits, writer denial, cache outage/cold canary, free-space bound and architecture-correct artifacts |
| Telemetry | Worker heartbeat, node attribution and a real cache/build span reach the intended Honeycomb dataset through the chosen path; no duplicated central kubelet scraping |
| Lifecycle and failure | Container restart, runtime/host reboot, drain/update, safe removal, laptop/network loss and stale identities have explicit outcomes; lost jobs never produce success |
| Net benefit | Representative completed jobs/hour and p95 queue-to-result improve without excessive home uplink, API latency or interactive-host impact |

The fastest useful outcome is a real existing job completing on spare hardware with repeatable startup and a warm second run. Proving that result takes priority over universal runtime compatibility or future autoscaling. The custom image remains the chosen packaging; generic networking, Apple Silicon workload compatibility and Talos policy compatibility remain explicit engineering work rather than promises hidden behind the word "portable".

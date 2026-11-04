> **Superseded in part, 2026-11-04:** [004-two-host-phases-2026-11-04.md](004-two-host-phases-2026-11-04.md) now governs. The plan runs a worker on both the MacBook M4 Max (first) and the MacBook Air, in phases A-F. The 16-assertion Definition of Done and the stage list in this note are replaced by 004's. The statements, hardware, Lima policy and feasibility findings below still hold where 004 does not change them.

## The maintainer's statement of what done means

OK, I'd like to turn this into a plan, and have the first dogfood  be my new 2026 Macbook Air (maxed out, I'll provide the hardware details).

And I'd ideally like to try to actually implement this on the local macbook air, since this VPS is overloaded. In the local herdr, just bootstrapping whatever I need to build it locally.

Tell me the feasability of that.

One representative CI job, with factory workloads afterward (Recommended)

## Definition of Done assertions derived from that statement

- An operator can develop and build the native ARM worker image from the 2026 M5 MacBook Air's local herdr session without executing those builds on the VPS.
- The start-homelab-worker-node-container just task installs or reuses Lima, converges its named Linux VM, and reconciles exactly one macbook-air-homelab-worker from the macbook-air host argument.
- The MacBook Air's worker completes a representative native arm64 CI job scheduled by the existing K3s cluster with the required pod isolation enforced.
- Repeated representative CI jobs reuse node-local caches while keeping writable job state private.
- The existing telemetry route attributes the worker's health and workload cache/build spans to macbook-air-homelab-worker.
- Restarting the worker preserves its identity and permits a subsequent representative CI job to complete.
- After the CI dogfood milestone, the worker completes a representative factory sandbox task through the established factory backend.
- The macbook-air-homelab-worker image is built from livespec-dev-tooling sources as a native arm64 OCI image running upstream kubelet and containerd, and is published to GHCR under the repository's existing image publication conventions.
- The worker joins the existing K3s cluster through standard Kubernetes TLS bootstrap with no K3s agent inside the image, and the control plane streams the worker's pod logs and exec sessions and reads its kubelet stats.
- Pods on macbook-air-homelab-worker reach pods on the existing nodes, ClusterIP Services and cluster DNS across the mixed LAN and tailnet route, and a NetworkPolicy denies traffic to such a pod that an allow policy otherwise admits.
- Before admitting any workload, the start task's probe of the Lima VM reports enforced AppArmor, pod user namespaces with idmapped mounts, TUN, delegated cgroups, mount propagation, nested containerd and reflink-capable local storage, and it stops with an actionable diagnosis when any of them is missing.
- Rerunning the start task for macbook-air reuses the installed Lima without upgrading it, keeps the named VM's disk, the worker's identity and its caches, and refuses to create a second worker on the same host.
- The MacBook Air keeps its existing macbook-air Tailscale identity while the worker runs under its own separate macbook-air-homelab-worker tailnet identity.
- The representative CI job's workload and support images run natively as arm64 on the worker without CPU emulation.
- From the Mac checkout, the guarded bd CLI reads and writes this repository's shared ledger tenant through an approved connection, with no local beads store created.
- Every production cluster network or control-plane change the worker needs is applied through a reviewed change that carries a recorded rollback.

# MacBook Air first dogfood: feasibility and implementation direction

## Confirmed direction

The maintainer named the 2026 MacBook Air as the first dogfood and local herdr as the implementation venue. The explicit milestone choice was one representative CI job, followed by factory workloads. This changes the earlier report's Linux-amd64-first ordering. One worker per host and host-derived naming are retained.

Creation records the maintainer's supplied objective and CI-first confirmation above. The remaining assertions are the session's concrete derivation of that objective and the already requested bootstrap, cache, telemetry and lifecycle requirements; they do not claim any runtime proof has occurred.

Assertions 1-7 were derived at creation (2026-11-04, epic `livespec-dev-tooling-ko26ez`, then slug `portable-container-worker-macbook-air`). Assertions 8-16 were added on 2026-11-04 when the plan was renamed to `homelab-k8s-worker-nodes`; each restates one decision of the maintainer's restart brief quoted verbatim below. Assertions 1-7 are unchanged.

### The maintainer's restart-brief decisions (verbatim, 2026-11-04)

> 1. A custom portable OCI Kubernetes worker owned and published by livespec-dev-tooling, using upstream kubelet/containerd and standard Kubernetes bootstrap. Existing K3s first; Talos support later. Keep the existing GHCR publication conventions.
> 2. Exactly ONE worker container per physical host or declared cloud execution target. Multiple pods run inside that worker. The command takes the HOST/target name and derives <host>-homelab-worker for the container, Kubernetes Node and separate worker Tailscale identity. Preserve the physical host's existing identity.
> 3. First dogfood: the new 2026 MacBook Air, Mac17,4, Apple M5, 10 CPU cores (4 Super + 6 Efficiency), 32 GB RAM, approximately 878 GB free of a 995 GB disk. Tailscale DNS was macbook-air.perch-rudd.ts.net, observed online; verify current state. Target argument macbook-air; worker name macbook-air-homelab-worker.
> 4. Implement and build locally in the Mac's local herdr, because the VPS is overloaded. Bootstrap only the needed native development tooling, authorized credentials and shared-ledger access. The existing credential wrapper supports Darwin/Keychain; the ledger's committed loopback address needs an approved tunnel/config. Do not create a substitute local ledger or run bd init.
> 5. Lima setup AND installation belong inside the idempotent just start-homelab-worker-node-container macbook-air task. Preferred: Homebrew native ARM Lima package, installing only if missing and reusing a compatible installation; Apple's native VZ backend; a named, reproducible Ubuntu arm64 VM with rootful Docker. Preserve VM disk, worker identity and caches on reruns; surface unavoidable first-run Homebrew/admin interaction. Avoid unconditional upgrades or a self-bundled Lima distribution.
> 6. The user explicitly selected ONE REPRESENTATIVE CI JOB as the first dogfood milestone, with FACTORY WORKLOADS AFTERWARD. Factory dogfood remains a later phase of this plan. Talos/cloud/autoscaling/runtime parity are explicit later scopes.
> 7. Prove the real VM's AppArmor, pod user namespaces/idmapped mounts, TUN, cgroups/mount propagation, nested runtime and local reflink-capable storage. Build native ARM workload/support images. Prove existing-cluster bootstrap, kubelet streaming/stats, CNI/Services/DNS, NetworkPolicy and mixed LAN/tailnet routing. Retain existing security and reviewed cluster-change boundaries. Caches and telemetry must work on the new host, with private writable job state and useful warm runs. Node registration alone is not dogfood success.

Node registration alone satisfies none of the assertions: assertions 3, 4, 6 and 7 each require a real job or task to complete on the worker.

## Research in this plan

- [002-portable-container-worker-nodes-2026-11-03.md](002-portable-container-worker-nodes-2026-11-03.md) — the portable-worker design report (image contents, standard bootstrap, Tailscale networking, lifecycle contract, cache audit, telemetry, publishing, acceptance table). Formerly `docs/research/2026-11-03-portable-container-worker-nodes.md`.
- [003-cloud-burst-capacity-2026-11-02.md](003-cloud-burst-capacity-2026-11-02.md) — background comparison of provisioned cloud workers and their economics; a separate subject, not implementation authority. Formerly `docs/research/2026-11-02-homelab-burst-worker-node.md`.
- [004-two-host-phases-2026-11-04.md](004-two-host-phases-2026-11-04.md) — the two-host revision: M4 Max and MacBook Air workers, host-change discipline through the info repositories, phases A-F and the current Definition of Done.

The rulings in this note govern where the reports differ: Mac first rather than Linux amd64 first, Homebrew/Lima/VZ inside the start task rather than Docker Desktop or Colima, one worker per host, and CI first with factory afterward.

## Hardware and observed access

Supplied hardware: MacBook Air, Mac17,4, model Z1LY000KFLL/A, Apple M5, 10 CPU cores (4 Super and 6 Efficiency), 32 GB memory. Supplied local storage: 994.61 GB capacity and 878.33 GB free. These are the maintainer's measurements, not independent local probes.

On 2026-11-04, read-only Tailscale status reported MacBook Air online with DNS name macbook-air.perch-rudd.ts.net; re-checked at 01:40Z the same day from the VPS, it was online (`active; direct`, tailnet address 100.70.51.124, OS macOS). Use macbook-air as the canonical target and macbook-air-homelab-worker as the container, Kubernetes Node and worker tailnet name. The physical host keeps its existing tailnet identity. This VPS's herdr reported no saved SSH machines; no remote shell login or Mac installation was attempted.

The machine is a credible native ARM development and first-worker host. Memory and disk are sufficient for a bounded Linux builder/worker VM; real interactive impact, thermal behavior, sustained throughput and safe admission still need measurement. Mixed CPU cores are not equivalent to ten identical server cores. Start with one representative job; no pod or churn-slot count is derived from this hardware listing.

## Local development and VM layout

Use a native macOS coding-agent session in the existing local herdr, a local Git checkout and local builds. Keep the shared ledger, existing cluster, credential sources and telemetry ownership where they are; do not install a second Dolt server or Kubernetes control plane on the Mac to make development possible. A small isolated control-plane fixture may be used for compatibility tests before a production network change.

Recommended runtime: a pinned Ubuntu arm64 Linux VM managed by Lima with Apple's native Virtualization.framework (vz), rootful Docker inside the VM, and one custom worker container running upstream kubelet/containerd. Pods run in that container's inner runtime. No x86 emulation or nested hypervisor is required for native arm64 workloads. VZ supports native guests on the matching CPU architecture; see [Lima VZ](https://lima-vm.io/docs/config/vmtype/vz/). Lima's default guest is Ubuntu; see [Lima configuration](https://lima-vm.io/docs/config/). Pin the actual tested guest image and configuration rather than relying on changing defaults.

Use the VM's Linux disk for inner containerd, work volumes and warm caches. Do not use a macOS shared source directory for reflink seeds or kubelet state. Choose a tested local filesystem layout that supplies idmapped mounts and same-filesystem reflinks, with an explicit disk-space bound. The first probe must establish AppArmor enforcement, pod user namespaces, cgroup accounting/delegation, TUN and nested containerd, rather than weakening the existing ARC security posture when a default runtime lacks a capability.

## Idempotent Lima installation belongs to the start task

The maintainer explicitly asked whether Lima setup/install belongs in the idempotent just task; it does. The proposed command is `just start-homelab-worker-node-container macbook-air`. There is no mandatory separate manual Lima setup step.

Preferred installation is Homebrew's native arm64 Lima package. Homebrew distributes the macOS executables; VZ is the virtualization backend. Reuse a compatible installed Lima, install a missing Lima through `brew install lima`, and verify the supported version before using it. Do not silently upgrade a compatible runtime on every invocation or replace a user's other VMs. Keep a named project-owned VM and its provisioned Linux configuration under declarative control. If Homebrew itself is missing, surface the standard first-run installer and required administrator interaction, then continue explicitly; a noninteractive invocation must return an actionable prerequisite instead of hanging at an invisible prompt. A self-bundled Lima distribution is deferred because it adds packaging/update ownership without improving the first dogfood.

The task must ensure the intended VM is running, its Docker engine and node prerequisites are present, scoped credentials and networking are configured, and the worker is started or reconciled. Reruns preserve VM storage, cache generations and the worker's node/device identity. Development-tool bootstrap precedes use of just on a new checkout; it is separate from worker-runtime provisioning.

## Development bootstrap prerequisites

Discover and reuse the Mac's existing Git, herdr, coding-agent login and package manager. Bootstrap the repository's pinned mise/uv/just/lefthook tools and native ARM Docker CLI/build support, set this checkout's platform-correct primary path, and use the normal worktree/PR protocol. Do not transplant the VPS's absolute /data paths into the Mac checkout.

The installed 1Password environment wrapper already contains an explicit Darwin path using macOS Keychain; reuse that supported installer and scoped sources instead of copying VPS credential files. Verify the pinned beads lifecycle guard and Darwin CLI, and make the existing per-repo tenant reachable through an approved secure connection. The committed tenant address is loopback 127.0.0.1:3307, so a Mac needs a tunnel/proxy or another owner-approved connection configuration; a fresh clone alone does not provide ledger connectivity. Never run bd init to invent a local store. Confirm secret presence without printing values.

Current pre-commit/pre-push configuration delegates gates to the existing cluster. Moving implementation to the Mac moves editing/build/probe CPU off the VPS; it does not automatically relocate every central review gate. Keep those gates unless a separately governed change moves them.

## Implementation stages

Each stage names the plan assertions it moves toward proof. No stage's completion discharges an assertion; the plan-level proof does.

1. **Stage 0 — Mac development bootstrap (local herdr).** Clone the repository on the Mac, install the pinned toolchain, record the Mac's own primary path, install the credential wrapper's Darwin/Keychain path, and reach the shared ledger tenant through an approved tunnel. Prove a worktree → commit → push round trip from the Mac. Assertions 1 and 15.
2. **Stage 1 — Mac capability probe and the idempotent start task.** Write the Homebrew/Lima/VZ install-or-reuse step and the named Ubuntu arm64 VM with rootful Docker, then probe the real VM for AppArmor, pod user namespaces with idmapped mounts, TUN, cgroup delegation, mount propagation, nested containerd and reflink storage. Measure first; if the guest lacks a capability, choose a compatible pinned guest rather than weaken policy. Assertions 2, 11, 12 and 13.
3. **Stage 2 — worker image and existing-cluster integration.** Build the arm64 worker image (upstream kubelet/containerd, CNI agent) through the GHCR conventions; prove standard bootstrap, serving certificates, kubelet streaming/stats, Flannel/Services/DNS and NetworkPolicy against an isolated matching K3s fixture first, then against production with an admission hold. Any K3s egress-selector or underlay change goes through a reviewed change with rollback. Assertions 8, 9, 10 and 16.
4. **Stage 3 — native ARM CI dogfood.** Convert the Python-lane workload and support image chain to `TARGETARCH`, route one representative CI job to the worker with the real hook/AppArmor/userns posture, then run it warm and after a worker restart. Verify node-local uv/reflink caches, private writable job state and telemetry attribution. Assertions 3, 4, 5, 6 and 14.
5. **Stage 4 — factory dogfood.** After Stage 3, adapt factory placement, credentials, caches and telemetry, and complete one real factory sandbox task on the worker. Assertion 7.

Stage 0 and Stage 1 run on the Mac before any implementation child is filed. Their measurements decide how stages 2-4 are sliced. The portable worker has no governing heading in `SPECIFICATION/` yet, and a child's Definition of Done must reference one. So before filing the first children, propose the worker's scenarios through `/livespec:propose-change`, and revise them in.

Mac-local implementation is the maintainer's stated venue. It does not require turning the Mac into a Fabro server first. Children whose proof needs the Mac host are recorded as factory-ineligible, with the Mac-local session as their route. Portable code may still take the factory route. Later work-item routing must explicitly preserve that venue for Mac host integration/proofs, rather than dispatching the Mac-specific proof onto an unrelated Linux factory and calling it done. Portable code and normal repository review gates still use their established governance.

## Initial feasibility proof and stop conditions

Local development is high-confidence. The first actual worker is conditional on a short capability and network proof. Fail with an actionable diagnosis if the selected VM cannot enforce AppArmor/user namespaces, provide cgroup/mount/TUN capabilities or preserve cache correctness; choose a compatible pinned Linux guest rather than disabling policy. If generic K3s kubelet access or the mixed LAN/tailnet underlay needs a larger refactor, surface that measured result before claiming a useful worker.

A half-to-one-day initial probe and several subsequent engineering days are planning estimates, not measured promises. No sustained M5 throughput, local service readiness, Docker VM capability or successful cluster job has yet been measured. Hardware capacity is unlikely to be the limiting integration problem.

## Scope and explicit deferrals

Initial scope is local implementation bootstrap, idempotent Homebrew/Lima/VM provisioning, a custom generic native ARM worker, one worker per host, existing K3s integration, a real CI dogfood, cache/telemetry/lifecycle proof, then factory dogfood. The initial CI workload should use the Python lane to reduce the first ARM conversion surface; the exact repository/job is selected against current routing and image support during implementation.

Talos production enrollment/KubeSpan policy accommodation, cloud container-service deployment, autoscaling, rootless/Podman parity, and independent home-outage backup are deferred to explicit follow-up scopes after this Mac CI/factory proof. Other-host compatibility remains an image/profile design goal; live validation on other hosts is deferred until the first Mac proof has established a reusable artifact. Revisit these in a later scope event before filing their implementation children. Never count this VM as an Omni-managed Talos machine.

No implementation children are admitted by this initial planning note. First measure the Mac bootstrap/runtime surface, then file small, evidence-based slices through the normal work-item intake. The ledger owns plan status and handoffs; this note records decisions and research.

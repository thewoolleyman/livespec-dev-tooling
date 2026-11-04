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

# MacBook Air first dogfood: feasibility and implementation direction

## Confirmed direction

The maintainer named the 2026 MacBook Air as the first dogfood and local herdr as the implementation venue. The explicit milestone choice was one representative CI job, followed by factory workloads. This changes the earlier report's Linux-amd64-first ordering. One worker per host and host-derived naming are retained.

Creation records the maintainer's supplied objective and CI-first confirmation above. The remaining assertions are the session's concrete derivation of that objective and the already requested bootstrap, cache, telemetry and lifecycle requirements; they do not claim any runtime proof has occurred.

Background: [portable-worker research](../../../docs/research/2026-11-03-portable-container-worker-nodes.md) and [cloud-burst comparison](../../../docs/research/2026-11-02-homelab-burst-worker-node.md). The newer maintainer rulings in this note govern first-host selection, naming and installation behavior.

## Hardware and observed access

Supplied hardware: MacBook Air, Mac17,4, model Z1LY000KFLL/A, Apple M5, 10 CPU cores (4 Super and 6 Efficiency), 32 GB memory. Supplied local storage: 994.61 GB capacity and 878.33 GB free. These are the maintainer's measurements, not independent local probes.

On 2026-11-04, read-only Tailscale status reported MacBook Air online with DNS name macbook-air.perch-rudd.ts.net. Use macbook-air as the canonical target and macbook-air-homelab-worker as the container, Kubernetes Node and worker tailnet name. The physical host keeps its existing tailnet identity. This VPS's herdr reported no saved SSH machines; no remote shell login or Mac installation was attempted.

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

## Implementation sequence

1. Establish the local herdr checkout, native toolchain, scoped credentials and shared-ledger reachability, with a reproducible bootstrap path.
2. Build the Lima/Ubuntu capability probe and idempotent host-to-VM setup; prove the existing pod security/filesystem requirements on the actual Air before constructing the full node integration.
3. Build the custom arm64 worker image and the selected ARM CI/support image chain, converting hardcoded amd64 assets where needed. Validate in an isolated matching K3s fixture and reuse the established GHCR build/release model.
4. Prove standard Kubernetes bootstrap, serving certificates, CNI, Service/DNS, NetworkPolicy and control-plane-to-kubelet paths. Any K3s egress-selector or existing-node routing change needs the normal controlled production change and rollback, not an automatic laptop bootstrap side effect.
5. Join macbook-air-homelab-worker with an initial admission hold, run a representative real CI job, then repeat it warm and after restart. Verify node-local uv/reflink behavior, architecture-correct compilation caches, job isolation and attributed telemetry. Record queue-to-result and interactive-host impact before expanding admission.
6. After the CI milestone, add the factory backend placement/credential/cache/telemetry adaptation and complete one real factory sandbox task. Keep resource requests and verdict integrity; interrupted jobs must remain identifiable.

Mac-local implementation is the maintainer's stated venue. It does not require turning the Mac into a Fabro server first. Later work-item routing must explicitly preserve that venue for Mac host integration/proofs, rather than dispatching the Mac-specific proof onto an unrelated Linux factory and calling it done. Portable code and normal repository review gates still use their established governance.

## Initial feasibility proof and stop conditions

Local development is high-confidence. The first actual worker is conditional on a short capability and network proof. Fail with an actionable diagnosis if the selected VM cannot enforce AppArmor/user namespaces, provide cgroup/mount/TUN capabilities or preserve cache correctness; choose a compatible pinned Linux guest rather than disabling policy. If generic K3s kubelet access or the mixed LAN/tailnet underlay needs a larger refactor, surface that measured result before claiming a useful worker.

A half-to-one-day initial probe and several subsequent engineering days are planning estimates, not measured promises. No sustained M5 throughput, local service readiness, Docker VM capability or successful cluster job has yet been measured. Hardware capacity is unlikely to be the limiting integration problem.

## Scope and explicit deferrals

Initial scope is local implementation bootstrap, idempotent Homebrew/Lima/VM provisioning, a custom generic native ARM worker, one worker per host, existing K3s integration, a real CI dogfood, cache/telemetry/lifecycle proof, then factory dogfood. The initial CI workload should use the Python lane to reduce the first ARM conversion surface; the exact repository/job is selected against current routing and image support during implementation.

Talos production enrollment/KubeSpan policy accommodation, cloud container-service deployment, autoscaling, rootless/Podman parity, and independent home-outage backup are deferred to explicit follow-up scopes after this Mac CI/factory proof. Other-host compatibility remains an image/profile design goal; live validation on other hosts is deferred until the first Mac proof has established a reusable artifact. Revisit these in a later scope event before filing their implementation children. Never count this VM as an Omni-managed Talos machine.

No implementation children are admitted by this initial planning note. First measure the Mac bootstrap/runtime surface, then file small, evidence-based slices through the normal work-item intake. The ledger owns plan status and handoffs; this note records decisions and research.

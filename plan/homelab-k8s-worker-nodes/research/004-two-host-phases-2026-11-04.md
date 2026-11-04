## The maintainer's statement of what done means (revision 2, verbatim, 2026-11-04)

> OK, I want to change this plan some.  I want the worker nodes to be able to run on BOTH the macbook air and my maxbook m4 max (which is at home and always on, whereas the macbook air may be closed sometimes).
>
> BOTH of these should be provisioned in the same way, in parallel, and brought up.  This will help eliminate machine-specific quirks.
>
> Note that the m4max DOES NOT NEED TO BE A DEV BOX.  It only needs enough to run the worker container.  In constrast, I am running actual local terminals on the macbook air for livespec, as a dogfood of running non-vps sessions in livespec and making sure livespec tooling and ecosystem still works on mac.
>
> herdr will be installed on the m4 max, and set up as a herdr remote to be driven directly from the macbook air herdr client as a connected herdr server.
>
> An additional constraint I want to add is that all the host-level changes MUST be documented and pushed in the corresponding *-info repo for the air / m4 max hosts.  These can be done via typing into dedicated macbook-<air|m4-max>-homelab-k8s-worker-nodes-agent-comms herdr tabs (all herdr tabs are in workspaces named after their owning repo and kept organized that way).
>
> Separate the plan into phases, e.g. getting the m4 max with (ONLY!) necessary prereqs and documented, and also getting macbook air ready to drive local development, and then driving the actual implementation of the container and worker node.  The worker node should be set up FIRST on the m4-max, and def of done to be that it's joined to the current fleet.  THEN we can do it again on air (which should be simple and identical).

The earlier statement and the restart-brief decisions in [001-macbook-air-first-dogfood.md](001-macbook-air-first-dogfood.md) still hold except where this revision changes them. This note governs the Definition of Done and the phases from 2026-11-04 on; 001's stage list and its 16-assertion Definition of Done are superseded.

## Definition of Done assertions derived from that statement

- The macbook-m4-max host carries only the prerequisites its worker container and its remote operation need, with no livespec development toolchain, ledger access or livespec coding session installed for this plan.
- A herdr server runs on macbook-m4-max, and the MacBook Air's local herdr client drives it as a connected remote.
- Livespec coding sessions in the MacBook Air's local herdr develop and build livespec-dev-tooling, including the native arm64 worker image, without executing those builds on the VPS.
- From the MacBook Air checkout, the guarded bd CLI reads and writes this repository's shared ledger tenant through an approved connection, with no local beads store created.
- Every host-level change this plan makes on either Mac is documented in, and pushed to, that host's info repository (macbook-air-info or macbook-m4-max-info).
- The worker image is built from livespec-dev-tooling sources as a native arm64 OCI image running upstream kubelet and containerd, and is published to GHCR under the repository's existing image publication conventions.
- For each of the host arguments macbook-m4-max and macbook-air, the start-homelab-worker-node-container just task installs or reuses Lima, converges its named Linux VM, and reconciles exactly one <host>-homelab-worker through the same code path.
- Before admitting any workload on either host, the start task's probe of the Lima VM reports enforced AppArmor, pod user namespaces with idmapped mounts, TUN, delegated cgroups, mount propagation, nested containerd and reflink-capable local storage, and it stops with an actionable diagnosis when any of them is missing.
- Rerunning the start task on either host reuses the installed Lima without upgrading it, keeps the named VM's disk, the worker's identity and its caches, and refuses to create a second worker on that host.
- Each Mac keeps its existing Tailscale identity while its worker runs under its own separate <host>-homelab-worker tailnet identity.
- macbook-m4-max-homelab-worker joins the existing K3s fleet as a Ready node through standard Kubernetes TLS bootstrap with no K3s agent inside the image, and the control plane streams its pod logs and exec sessions and reads its kubelet stats.
- Pods on each worker reach pods on the existing nodes, ClusterIP Services and cluster DNS across the mixed LAN and tailnet route, and a NetworkPolicy denies traffic to such a pod that an allow policy otherwise admits.
- Every production cluster network or control-plane change the workers need is applied through a reviewed change that carries a recorded rollback.
- After macbook-m4-max-homelab-worker has joined, macbook-air-homelab-worker joins the existing K3s fleet as a Ready node from the same image and start task, with no host-specific code path beyond the host argument.
- Each worker completes a representative native arm64 CI job scheduled by the existing K3s cluster with the required pod isolation enforced.
- The representative CI job's workload and support images run natively as arm64 on each worker without CPU emulation.
- Repeated representative CI jobs on a worker reuse its node-local caches while keeping writable job state private.
- The existing telemetry route attributes each worker's health and workload cache/build spans to that worker's <host>-homelab-worker name.
- Restarting a worker preserves its identity and permits a subsequent representative CI job on it to complete.
- After the CI dogfood milestone, a worker completes a representative factory sandbox task through the established factory backend.

## How the revision maps to the earlier 16 assertions

Assertions 1, 2, 5 and 14 are new. Assertions 3 and 4 restate the earlier assertions 1 and 15 for the MacBook Air as the development host. The rest restate earlier assertions 2-14 and 16 for both hosts instead of the MacBook Air alone; assertion 11 is the earlier assertion 9 pinned to the M4 Max, which is the first worker. No earlier requirement was dropped.

"Joined to the current fleet" is the done condition of Phase C (assertion 11 with assertions 12 and 13 for that worker). It is a phase boundary, not the plan's finish: the CI and factory dogfood phases stay in this plan, because the earlier ruling that node registration alone is not dogfood success still stands. Joined means a Ready node under standard bootstrap whose control-plane streaming, routing and policy enforcement are proved; the node stays under an admission hold so no CI workload lands on it until Phase E.

## Hosts

| | macbook-m4-max | macbook-air |
|---|---|---|
| Role | Always-on worker host at home. Not a development box. | Development host (livespec coding sessions in local herdr) and second worker. May be closed. |
| Tailnet name | `macbook-m4-max` (observed offline from the VPS at 15:21Z on 2026-11-04; verify) | `macbook-air` (observed online the same minute) |
| Worker name | `macbook-m4-max-homelab-worker` | `macbook-air-homelab-worker` |
| Info repository | `thewoolleyman/macbook-m4-max-info` | `thewoolleyman/macbook-air-info` |
| herdr | Server, connected as a remote of the Air's herdr client | Local herdr client; the plan session runs here |
| Agent-comms tab | `macbook-m4-max-homelab-k8s-worker-nodes-agent-comms`, in the `macbook-m4-max-info` workspace | `macbook-air-homelab-k8s-worker-nodes-agent-comms`, in the `macbook-air-info` workspace |

The M4 Max's hardware is not yet recorded in this plan. Read it from macbook-m4-max-info rather than assuming it.

## Status when this revision was written (15:30Z, 2026-11-04)

Work already done in the Air's local herdr under the earlier Stage 0 counts toward the phases below; it is not repeated.

- **Phase B is largely done.** The Stage 0 evidence comment on the epic (14:24Z) records a worktree → commit → push round trip from the Air (PR 3394, master `b4346a5c`), its pre-push delegated to the cluster (gate `20261104T134204Z-99758` passed), the Air enrolled as a delegated-gates client, and ledger read and write through the SSH tunnel. macbook-air-info records each host change (commits from 02:00Z to 15:09Z). Known caveat: a delegated gate wait does not survive the Air sleeping; it ends with no verdict, never a pass.
- **A developer-host contract is ratified.** Spec v130 (`07dfece9`) adds the non-functional-requirements section "Developer host platforms" and six scenarios. Their heading-coverage rows are spec-first TODOs at the integration tier owned by this epic, so their tests are owed work of this plan.
- **Phase A has started.** macbook-m4-max-info `f9c2953` (15:08Z) records herdr 0.9.5 installed from Homebrew with its Claude and Codex integrations. No remote profile or `~/.ssh/config` exists yet, and remote connectivity is untested. From the VPS at 15:21Z, macbook-m4-max showed offline on the tailnet.

## Host-change discipline

Every change to either Mac's host state — a Homebrew package, a launchd job, a herdr server, Lima and its VM, a Tailscale identity, a credential source — is made by that host's info-repo agent and recorded and pushed in that info repository. The plan session on the Air asks for a change by typing a request into the host's agent-comms tab and reads the result back from the pushed info-repo commit, not from the tab's reply. The plan session does not change host state itself.

Bootstrap order for the M4 Max tab: until the M4 Max's herdr server is connected to the Air's client, the `macbook-m4-max-info` workspace and its agent-comms tab run on the Air's local herdr, and that agent reaches the M4 Max over Tailscale SSH (see that repo's Tailscale daemon runbook). Once the remote is connected, the workspace runs on the M4 Max's herdr server.

The worker's own start task is repository code, not a host change: its recipe and script live in livespec-dev-tooling. Running it on a host, and every prerequisite it installs there, is a host change and is recorded in that host's info repository.

## Phases

Phases A and B run in parallel. Phase C waits on both. Each phase names the assertions it moves toward proof; no phase's completion discharges an assertion, the plan-level proof does.

1. **Phase A — M4 Max prerequisites, minimal and documented.** Through the M4 Max agent-comms tab: confirm the host is reachable, install the herdr server and connect it as a remote of the Air's herdr client, and install only what running the worker needs (expected: Homebrew if absent, a runtime checkout of livespec-dev-tooling with mise and just to run the start task, and the scoped enrollment-credential source the worker needs; Lima itself is installed by the start task). No bd, no ledger tunnel, no livespec development toolchain. Each item is recorded and pushed in macbook-m4-max-info. Assertions 1, 2, 5.
2. **Phase B — MacBook Air ready to drive local development** (largely done; see the status above). What remains is the Air's herdr client driving the M4 Max remote, shared with Phase A, and the two agent-comms tabs. The full scope, through the Air agent-comms tab for host changes: the pinned toolchain (mise, uv, just, lefthook, a bash 4+ on `PATH`), the credential wrapper's Darwin/Keychain path, the guarded bd, the approved ledger tunnel, and a proved worktree → commit → push round trip from the Air. Each host change is recorded and pushed in macbook-air-info. Assertions 3, 4, 5.
3. **Phase C — worker implementation, first brought up on the M4 Max.** Developed from the Air. Implement the start task and its VM capability probe, build and publish the arm64 worker image, and prove standard bootstrap, streaming and stats, routing, DNS and NetworkPolicy against an isolated matching K3s fixture first, then join `macbook-m4-max-homelab-worker` to the production fleet under an admission hold. Any K3s egress-selector or underlay change goes through a reviewed change with rollback. Done when the M4 Max worker is joined. Assertions 6-13.
4. **Phase D — the same worker on the MacBook Air.** Run the identical start task with `macbook-air` and join `macbook-air-homelab-worker`. A difference needed here is a machine-specific quirk: fix it in the shared code path, then rerun the M4 Max to confirm it still converges. Assertions 7-10, 12, 14.
5. **Phase E — native ARM CI dogfood on each worker.** Convert the Python-lane workload and support image chain to `TARGETARCH`, lift the admission hold for one representative CI job, run it warm and after a worker restart, on the M4 Max first and then the Air. Assertions 15-19.
6. **Phase F — factory dogfood.** After Phase E, adapt factory placement, credentials, caches and telemetry, and complete one real factory sandbox task on a worker. Assertion 20.

## Routing and children

Host-side proofs on either Mac are factory-ineligible; their route is the plan session in the Air's local herdr, with host changes made through the agent-comms tabs. Portable code may still take the factory route.

No implementation children are filed yet. The portable worker still has no governing heading in `SPECIFICATION/`, so before the first Phase C child is filed, the worker's scenarios go through `/livespec:propose-change` and a revise. Phase A and Phase B are host setup recorded in the info repositories, not ledger children of this plan.

## Explicit deferrals (unchanged in substance)

- Talos production enrollment and KubeSpan policy accommodation: after the CI and factory dogfood; reconsider in a later scope event.
- Cloud deployment, autoscaling, rootless/Podman parity, live qualification of hosts other than these two Macs, and home-outage backup: after the reusable worker artifact exists; reconsider in a later scope event.
- A self-bundled Lima distribution: deferred; Homebrew's Lima is the pilot path.

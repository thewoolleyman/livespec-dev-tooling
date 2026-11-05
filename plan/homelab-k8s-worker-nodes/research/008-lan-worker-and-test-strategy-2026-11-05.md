# 008 — LAN-bridged M4 Max worker, roaming hosts deferred, and the test strategy (2026-11-05)

This note governs the plan's design and Definition of Done from 2026-11-05 on. It supersedes, in part:

- [002](002-portable-container-worker-nodes-2026-11-03.md): its flannel-over-tailnet underlay (note added there).
- [004](004-two-host-phases-2026-11-04.md): the Definition of Done (replaced by §6 here) and Phase D (deferred, §3).
- [005](005-worker-implementation-brief-2026-11-04.md): §1's tailnet node IP and flannel interface, §3's Option A
  recommendation, §4 slice 7 and risk 1 (banner added there).
- [006](006-tailnet-and-fixture-corrections-2026-11-04.md) §1 "ACL. No change is needed" (wrong, §2 here).
- [007](007-fixture-stage-two-underlay-2026-11-05.md): Option A as the production underlay (§1, §3), §4's "There is no ACL
  change" (§2), and §5's production /32 routes (dropped, §3).

Everything else in 001-007 still holds.

## The maintainer's direction (verbatim, 2026-11-05)

On stage two:

> Ready for stage two logins.

On the route grant, after asking whether it only lets the tailnet reach the fixtures:

> Stop, lets do the route grant first.    Then I want you to fully update your plan and any docs and research to reflect this new direction before you actually take it. Update the definition of done and anything else, and then kick off a Fable reviewer to make sure that it's all up to date and you didn't miss anything.

On tests:

> how can we keep the fixture scripts from rotting? Is there nothing that excercises them in isolation?  Why are they just for fixtures, can most of their logic be extracted into real prod supporting code?

> I don't want to reinvent the world or overengineer this. Just have some solid tests, and easy to reuse tests for future changes that won't rot.  But also just wanna get this done.  Thoughts?

On the pod network, after stage two failed:

> Start with the lan bridge, we will worry about the roaming machines like air later, it can be deferred for now.

On branches:

> Go ahead and delete old branches.  You don't have to ask this

## 1. What stage two proved

Record: macbook-m4-max-info `c62eaff2` (posted on livespec-dev-tooling-y4unt4). The fixture's K3s nodes advertised their own
/32s over the tailnet, and the worker ran in production mode with `--accept-routes`.

- **Control plane to worker over the tailnet works.** With the routes distributed, the worker bootstrapped with no new login,
  its serving CSR was approved, and logs, exec, port-forward and kubelet stats on the worker passed, plus logs on a K3s node.
- **Pod networking over the tailnet does not.** All 8 pod-network checks failed (pod-to-pod both ways, large TCP both ways,
  large ICMP, ClusterIP and DNS, DNS at 10.43.0.10, NetworkPolicy lifted). The NetworkPolicy-deny PASS is vacuous.
- **Root cause.** A K3s node's flannel VXLAN device is bound to its LAN interface (`dev eth0` in the fixture, `eno1` on
  poweredge). VXLAN to the worker's tailnet VTEP is therefore forced out the LAN to the gateway
  (`ip route get 100.86.228.81 oif eth0` → `via 172.18.0.1 dev eth0`) and lost. 007 §1 reasoned about AllowedIPs in both
  directions but missed the device binding; no route can override it. Production would fail the same way.
- **Path.** The worker reached both fixture nodes only via DERP (sfo), 39-57 ms, with no direct connection, although all three
  run in one VM.

Making a worker reachable over the tailnet alone needs every K3s node's flannel on `tailscale0` (K3s's own Tailscale
integration, `--vpn-auth`, has that shape). That is a production-wide change. It is deferred with the roaming hosts (§3).

## 2. The tailnet route grant (applied)

Tailscale distributes an approved subnet route only to devices the policy lets reach the routed addresses. The flat
`autogroup:member → autogroup:member` grant covers members' own 100.x addresses, not routes they advertise. So the fixture's
approved routes reached no peer. 006 §1 ("ACL. No change is needed") and 007 §4 ("There is no ACL change") were wrong.

tailscale-admin#42 (maintainer approved; merged and applied by GitOps about 21:15Z) adds host aliases
`homelab-fixture-server` (172.18.0.2/32) and `homelab-fixture-agent` (172.18.0.3/32), a grant from `autogroup:member` to
them, a policy test, and an acl-policy contract requirement. No tag, auth key or autoApprover. Rollback: revert it.

It also removed two policy tests naming the departed `nix-controller` device, which Tailscale rejected. They had failed every
apply since 2026-08-17, so the live policy still predated the tag retirement (tailscale-admin #33). That retirement went live
with #42. The live network map had shown no tagged device since 2026-09-06, so nothing lost access.

The grant stays. It points at nothing while the fixture is down and matches again if the fixture is rebuilt, because Docker
assigns the same addresses on a fresh fixture network. The fixture's two tailnet devices keep their state in memory only, so a
rebuild logs in as new devices; the maintainer deletes the old offline entries.

## 3. Decision: the M4 Max worker is a home-LAN node; roaming hosts are deferred

**The M4 Max worker joins as an ordinary LAN node.** Its Lima VM gets a bridged interface on the home LAN, and the worker's node
IP is that LAN address. Flannel's VXLAN then reaches every K3s node directly on the LAN at full MTU, as stage one proved on the
fixture's Docker network (all 11 checks; `a97ec2f3`, `87570a5a`). No production network change is needed beyond the
egress-selector change already merged in livespec-dev-tooling#3430.

Feasibility is measured (macbook-m4-max-info `889b1fc4`, `373e5c8e`):

- The M4 is on Wi-Fi `en0`, 192.168.1.130/24, gateway 192.168.1.1. poweredge (192.168.1.200), gmktec (192.168.1.66) and hp
  (192.168.1.4 on ethernet, 192.168.1.54 on Wi-Fi) are on the same /24. An earlier reading of hp as 10.0.0.168 was the
  Tailscale endpoint the M4 chose, not hp's address; `889b1fc4` is corrected by `373e5c8e`.
- socket_vmnet v1.2.2 is installed root-owned under `/opt/socket_vmnet` (checksum verified), `/etc/sudoers.d/lima` passes
  `limactl sudoers --check` (mode 0444), and the worker VM has `networks: [{lima: bridged}]` on `en0`. Each step has a recorded
  rollback.
- The VM's `lima0` got 192.168.1.131/24 by DHCP. From inside the VM the router, poweredge, gmktec and hp answer with 0% loss and
  are REACHABLE neighbours, and the router leased the VM's own MAC, so the Wi-Fi access point accepts the bridge.

**Deferred: roaming workers.** The MacBook Air worker (Phase D, livespec-dev-tooling-t5ervh) and any worker that must reach the
fleet over the tailnet alone are deferred. Reconsider them in a later scope event, starting with the cluster-wide
flannel-over-`tailscale0` question proved in the fixture first. 007 §5's production /32 routes are dropped: a LAN worker does
not need them, and with them the macOS route-acceptance risk of 007 §5 goes away.

**Design consequences for the implementation:**

1. **Start task.** The Lima template declares the bridged network. The task checks the host prerequisites (socket_vmnet under
   `/opt/socket_vmnet`, a passing `limactl sudoers --check`) and stops with an actionable diagnosis when they are missing, like
   the capability probe. Installing them is a documented host change in the host's info repository, not something the task
   does: they need root, and this Mac's Homebrew prefix is user-owned. An existing VM without the bridged network is refused
   with a diagnosis naming the setting, as the spec already requires; adding it to the M4's VM was done once, by hand, recorded
   in `373e5c8e`.
2. **Worker container network.** The worker uses the VM's LAN address as its node IP. Recommended: host networking inside the
   VM, which is dedicated to the worker, so the node IP is `lima0`'s address and flannel's interface is `lima0`. The alternative,
   a Docker macvlan network on `lima0`, needs a static LAN address outside the router's DHCP pool. Settle this in the
   implementation child with a fixture-free host check.
3. **Stable node IP.** The node IP must not change under a running node. Lima keeps a stable MAC per instance; a DHCP
   reservation for that MAC on the home router is a maintainer action, asked with the production prerequisites (§5 item 4).
   Until it exists, a changed lease is detected, not papered over: the converge step refuses when the VM's LAN address differs
   from the registered Node's InternalIP (livespec-dev-tooling-ko26ez.2).
4. **Cluster values.** `homelab-worker/networking/cluster.yaml` changes `flannel-iface` from `tailscale0` to the LAN interface
   and `api-server-host` to poweredge's LAN address, after confirming that address is a SAN of the API server's certificate.
   The worker stops enabling `--accept-routes` (Option A's route acceptance), and `networking/flannel.yaml`'s "tailscale0 in
   production" comment is corrected, both under livespec-dev-tooling-ko26ez.2.
5. **Worker tailnet identity.** The spec still requires the worker's own `<host>-homelab-worker` tailnet identity, persisted
   across restarts. It is no longer the pod-network underlay. After the VM restart for the bridge, the worker's tailscaled
   reported `NeedsLogin`; whether the identity survived a VM restart must be measured before it is relied on (assertion 10).
6. **The fixture.** Stage one's fixture proof already covers the LAN shape. The fixture's K3s API did not come back after the
   VM restart; it is rebuilt with `k3s-fixture.sh down` and `up` when a fixture proof is next needed, not now. Its two in-memory
   tailnet devices are gone; their offline entries in the admin console are for the maintainer to delete.

These consequences change the "macOS VM runtime" and "Host tailnet identity" rules of `SPECIFICATION/non-functional-requirements.md`
§"Homelab worker nodes" only by addition (the bridged network and its host prerequisites). A propose-change and revise land them
before the implementation child is admitted.

## 4. Test strategy

The maintainer asked for solid, reusable tests that do not rot, without over-engineering. Decided:

- **Fast tests (CI and factory sandboxes).** Every homelab-worker script keeps stub-based tests under
  `tests/spec/test_homelab_worker_*.py`: fake `limactl`, `docker`, `kubectl` and `tailscale` executables asserting the commands
  issued and the refusals. They run on every commit, so a logic break fails immediately. Each future change adds a test there.
- **Production scripts, thin fixture wrappers.** The join sequence and the cluster-side proof are production code, not fixture
  code:
  - `homelab-worker/join-worker.sh <host> --api-server <url>`: apply the enrollment RBAC and networking agents, mint the
    enrollment, converge the worker, wait for the Node, approve its serving CSR. It already composes the production
    `mint-bootstrap-token.sh`, `converge-worker-container.sh` and `approve-serving-csr.sh`.
  - `homelab-worker/prove-worker.sh <host> --peer-node <node>`: the 14 checks (logs, exec, port-forward, kubelet stats, logs on
    the peer node, pod-to-pod both ways, large TCP both ways, large ICMP, ClusterIP and DNS, DNS 10.43.0.10, NetworkPolicy
    deny and lift) against whatever cluster the caller's `kubectl` reaches. With `--expect-streaming-failure` it runs the negative
    control instead: logs and exec on the worker MUST fail, as at `egress-selector-mode: agent`.
  - `join-fixture-worker.sh` and `prove-fixture-worker.sh` shrink to wrappers that supply the fixture's kubectl shim, API
    server and node names. Only `k3s-fixture.sh` and `underlay-fixture.sh` stay fixture-only.
  The production join of each worker, every re-enrollment, and every proof after a cluster change run the same scripts for real,
  which is what keeps them from rotting.
- **Not doing:** headscale, a privileged CI lane, persisted fixture tailnet state, or a new test framework. The fixture is an
  on-demand rehearsal on the M4, captured on the host.
- **Heading coverage.** Seven rows in `tests/heading-coverage.json` owned by this plan are `TODO`: `## Homelab worker nodes` and
  its six scenarios (the start task refusing an undeclared host, a VM missing a capability, a rerun reusing Lima, a second
  worker refused, the host's tailnet identity unchanged, and the admission hold). Each is mapped to its stub test by the child
  that delivers the behaviour (livespec-dev-tooling-ko26ez.1 and .2, with the start-task and enrollment children for theirs).
  The H2 row's reason still names host-captured runs on both Macs; it is corrected to the M4 Max start task and production
  `prove-worker.sh` run when it is mapped.

## 5. Phases from here

1. Plan update (this note, the epic Definition of Done, the carrier map) and an independent review, then the spec
   propose-change and revise for §3.
2. Implementation child: extract `join-worker.sh` and `prove-worker.sh`, fixture scripts to wrappers.
3. Implementation child: the LAN-bridged worker (§3 items 1-4).
4. Production prerequisites: the poweredge K3s restart that makes `egress-selector-mode: disabled` live (livespec-dev-tooling#3430,
   with the coordinator), the networking agents and RBAC applied to production, and the DHCP reservation.
5. Phase C done: `join-worker.sh macbook-m4-max` against production, then `prove-worker.sh` against production with a K3s node as
   the peer, captured on the host.
6. Phase E: native arm64 CI dogfood on the M4 Max worker. Phase F: factory dogfood.

## 6. Definition of Done (revision 3)

Assertions 1-6 are unchanged from 004. The Air's worker assertions move to the deferral. New assertions are 14 and 21.

1. The macbook-m4-max host carries only the prerequisites its worker container and its remote operation need, with no livespec development toolchain, ledger access or livespec coding session installed for this plan.
2. A herdr server runs on macbook-m4-max, and the MacBook Air's local herdr client drives it as a connected remote.
3. Livespec coding sessions in the MacBook Air's local herdr develop and build livespec-dev-tooling, including the native arm64 worker image, without executing those builds on the VPS.
4. From the MacBook Air checkout, the guarded bd CLI reads and writes this repository's shared ledger tenant through an approved connection, with no local beads store created.
5. Every host-level change this plan makes on either Mac is documented in, and pushed to, that host's info repository (macbook-air-info or macbook-m4-max-info).
6. The worker image is built from livespec-dev-tooling sources as a native arm64 OCI image running upstream kubelet and containerd, and is published to GHCR under the repository's existing image publication conventions.
7. For the host argument macbook-m4-max, the start-homelab-worker-node-container just task installs or reuses Lima, converges its named Linux VM with a bridged home-LAN network, and reconciles exactly one macbook-m4-max-homelab-worker, through the code path every declared host shares.
8. Before admitting any workload, the start task's probe of the Lima VM reports enforced AppArmor, pod user namespaces with idmapped mounts, TUN, delegated cgroups, mount propagation, nested containerd and reflink-capable local storage, and the task stops with an actionable diagnosis when any of them, or the bridged network's host prerequisites, is missing.
9. Rerunning the start task reuses the installed Lima without upgrading it, keeps the named VM's disk, the worker's identity and its caches, and refuses to create a second worker on that host.
10. The M4 Max keeps its existing Tailscale identity while its worker runs under its own separate macbook-m4-max-homelab-worker tailnet identity, which persists across worker and VM restarts.
11. macbook-m4-max-homelab-worker joins the existing K3s fleet as a Ready node through standard Kubernetes TLS bootstrap with no K3s agent inside the image, using its home-LAN address as its node IP, and the control plane streams its pod logs and exec sessions and reads its kubelet stats.
12. Pods on the worker reach pods on the existing nodes, ClusterIP Services and cluster DNS across the home LAN, large transfers cross it intact, and a NetworkPolicy denies traffic to such a pod that an allow policy otherwise admits.
13. Every production cluster network, control-plane or tailnet-policy change the worker needs is applied through a reviewed change that carries a recorded rollback.
14. The worker's join and its cluster-side proof are production scripts (join-worker.sh and prove-worker.sh) that ran against the production fleet for that join, and the isolated fixture reaches them only through thin wrappers.
15. The worker completes a representative native arm64 CI job scheduled by the existing K3s cluster with the required pod isolation enforced.
16. The representative CI job's workload and support images run natively as arm64 on the worker without CPU emulation.
17. Repeated representative CI jobs on the worker reuse its node-local caches while keeping writable job state private.
18. The existing telemetry route attributes the worker's health and workload cache/build spans to macbook-m4-max-homelab-worker.
19. Restarting the worker preserves its identity and permits a subsequent representative CI job on it to complete.
20. After the CI dogfood milestone, the worker completes a representative factory sandbox task through the established factory backend.
21. Every homelab-worker script has fast stub-based tests that run in CI, and the `## Homelab worker nodes` heading-coverage entry and its six scenario entries map to tests rather than TODO.

How this maps to 004's 20: 1-6 are unchanged. 7-12 restate 004's 7-12 for the M4 Max on the LAN; the start task still serves
every declared host through one code path, so the Air needs no new code when it returns. 13 widens 004's 13 to tailnet-policy
changes. 004's 14 (the Air joins) is deferred. 15-20 restate 004's 15-20 for the M4 Max worker. 14 and 21 are new. Nothing else
was dropped.

### Deferred (reconsider in a later scope event)

- The MacBook Air worker: its start-task run, join, CI and factory dogfood (004 assertion 14 and the Air halves of 7-12 and
  15-19), and any worker that reaches the fleet over the tailnet alone.
- Cluster-wide flannel over `tailscale0` (§1), proved in the fixture before any production change.
- Unchanged from earlier scope events: Talos, KubeSpan, cloud targets, autoscaling, rootless/Podman parity, other hosts,
  home-outage backup, a self-bundled Lima.

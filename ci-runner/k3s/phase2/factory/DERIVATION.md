# DERIVATION — the `factory` namespace's quota and egress targets

Every number in `./factory-namespace.yaml` is derived here, beside the manifest
it governs, the way `../kueue/DERIVATION.md` sits beside the queues. Two things
in that file cannot be read off anything else, and both are load-bearing:

- **The ResourceQuota is the ONLY bound on what factory runs take from the CI
  pool.** Maintainer ruling of 2026-10-13 (livespec plan
  `factory-worker-nodes-gitops`, epic `livespec-sqvj7p`, research/001 ruling 3):
  `poweredge-xubuntu` stays untainted and runs factory pods too, Kueue is NOT in
  the factory path, and the churn-slot derivation is not re-done. There is no
  second gate behind this one, and an absent or over-large quota raises nothing
  — it just admits.
- **The NetworkPolicy's egress targets were READ, not recalled.** The work-item
  requires the endpoints to come from the live Fabro instance configuration on
  `hp-xubuntu` rather than from memory. Where each one was read is recorded
  below, with what the read returned.

Work-item `livespec-dev-tooling-f5e6vl`. Applied at every boot by
`../reconstruct/converge-ci-stack.sh` step 10e; installed onto the host by the
`ci_converge_unit` Ansible role.

## The node capacities this is sized against

Measured live on 2026-10-13 and recorded in the plan's research/001 ("What
exists today", "hp-xubuntu as measured on 2026-10-13"). The quota is
NAMESPACE-WIDE — it bounds the factory's total across the pool, not any one
node — so all three nodes are in view.

| Node | Role | Capacity | What already claims it |
|---|---|---|---|
| `poweredge-xubuntu` | k3s server; runs the whole CI pool | **72 CPUs**, **377 GB** | `ADMISSION_CAPACITY_C=32` churn slots; `../kueue/DERIVATION.md` records that its 72 threads saturate at 35–46 running jobs |
| `gmktec-xubuntu` | k3s agent | **32 threads**, **62 GB** | `ADMISSION_CAPACITY_C=12`; `gates-cq` already holds 15 cpu / 24 Gi of the ~50 GiB available to pods (the rest is the firmware iGPU carveout its phase0 profile records as off-limits) |
| `hp-xubuntu` | the Fabro server host, joining factory-only | **16 CPUs**, **30 GB** | the `fabro-sandbox.slice` Docker budget (MemoryHigh 22G, MemoryMax 24G, CPUQuota 1400%) plus both Fabro servers outside it |

**hp is PLUMBING today, and the quota does not pretend otherwise.** Honest
arithmetic on a 30 GB host whose Docker slice may take 24 GB leaves hp about
**3 GiB** and under one CPU allocatable to pods while the slice runs at its
current size (plan research/001, "The coexistence budget as currently known").
Not one factory pod at the envelope below fits on hp until the backend plan's
cutover steps the slice down. That is a SCHEDULING fact, and this quota is an
ADMISSION bound — the distinction `../kueue/DERIVATION.md` draws as "The
physical cap is the scheduler, not Kueue" and "Admission is not scheduling".
Sizing the quota down to what hp can hold today would cap the whole namespace at
hp's temporary floor; sizing it to hp's eventual capacity would be a number
nothing has measured. It is sized against what the POOL can give up, and the
scheduler refuses what no node can hold.

## The quota

**Per-run envelope — 4 cpu / 8GB, and it is committed rather than estimated.**
`ansible/inventory/host_vars/hp-xubuntu.yml` declares the sandbox environment
the factory's own runs are prepared in, for the `fabro-server-candidate`
instance:

```yaml
environments:
  - id: livespec-ci
    image: ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.93.5
    cpu: 4
    memory: 8GB
```

That is the only committed statement of a factory run's size in the fleet, so it
is the unit this quota counts. It is also what the Docker slice's own numbers
corroborate: 24 GB across the fleet instance's 10 admitted runs is ~2.4 GB of
RESIDENT memory per run, well inside an 8GB envelope — the envelope is the
sizing figure, not the measured working set.

**Concurrency target — 3, a deliberate first value.** The same reasoning
`../kueue/DERIVATION.md` applies to the gates quota ("The two numbers: 15 cpu
and 24 Gi"): enough that a run and a re-dispatch do not serialize, small enough
to leave the envelope to the workload that already owns the box. It is NOT hp's
`max_concurrent_runs: 10`: that number is the Docker factory's cap on a host
with its own 16 cores, while this quota's capacity comes out of a CI pool whose
own derivation already spends poweredge at saturation.

| term | arithmetic | value |
|---|---|---|
| `requests.cpu` | 3 runs x 4 cpu | **12** |
| `requests.memory` | 3 runs x 8 Gi | **24Gi** |
| `limits.cpu` | 3 runs x 4 cpu | **12** |
| `limits.memory` | 24Gi + one run's headroom | **32Gi** |
| `pods` | 3 runs x (1 sandbox + 1 in-flight replacement) | **6** |

`limits.memory` is deliberately NOT `3 x 8Gi`. At 32Gi **cpu binds first at
exactly three runs**, which is the intended behaviour, and a run whose peak RSS
overshoots degrades throughput instead of blocking admission outright — the same
choice, for the same reason, as the gates quota's 24 Gi against an 18 Gi
estimate.

**Checked against each node.** 12 cpu is 17% of poweredge's 72 and leaves 60
threads for a pool that saturates at 35–46 jobs; 24Gi is 6.4% of its 377 GB. On
gmktec, 12 cpu / 24Gi fits what is left after `gates-cq`'s 15 cpu / 24 Gi inside
the ~50 GiB pod envelope only if gates are idle — which is correct, because
nothing pins factory pods to gmktec and the scheduler, not this quota, decides.
On hp nothing fits yet, as above.

**THIS IS A FIRST VALUE TO CONFIRM BY SOAK, NOT A MEASUREMENT.** What a soak
must settle: a factory run's actual peak cpu and RSS inside a pod (the Docker
numbers above are a different cgroup shape), whether 3 concurrent runs is what
the pool can absorb beside CI, and whether `cpu` remains the right binding term.
Revise the table when it does, and record the measurement rather than replacing
one estimate with another.

## The quota, raised to eight runs (2026-10-24)

**Why it moved.** The 3-run value above was a first value for a factory that
did not yet send its runs here. On 2026-10-24 gmktec production's default
`livespec-ci` environment moved onto the `kubernetes` provider
(livespec-dev-tooling #2795, plan kubernetes-sandbox-backend, bd-ib-nmuyjc),
and the per-repository flips routed the fleet's dispatches to the same pods.
The fleet cap was 8, so every 4th launch was refused at sandbox acquire with
`exceeded quota: factory-runs` (403), which Fabro classes `deterministic`:
runs 01M5NV31WA2Q (bd-ib-57ss2n) and 01M5NV96ZBFY (bd-ib-pziqbf) died that way
at 0 ms, after their whole pre-launch phase.

**Measured, not estimated** (read from the cluster on 2026-10-24 with
`kubectl get nodes` and `kubectl describe node`):

| node | allocatable cpu | allocatable memory | schedulable for factory pods |
|---|---|---|---|
| `poweredge-xubuntu` | 72 | 377 GiB | yes (untainted) |
| `gmktec-xubuntu` | 32 | 62 GiB | yes (untainted) |
| `hp-xubuntu` | 0.5 | 4.7 GiB | no room (tainted `node-role/ci`, factory-only, kubelet reservation leaves 500m) |

The CI ClusterQueues' nominal cpu sums to **61** (`gates-cq` 15,
`livespec-orchestrator-beads-fabro-cq` 29, `livespec-dev-tooling-cq` 6,
`phase1-proof-cq` 2, `livespec-cq` 2, and seven repositories at 1).

| term | arithmetic | value |
|---|---|---|
| `requests.cpu` | 8 runs x 4 cpu | **32** |
| `requests.memory` | 8 runs x 8 Gi | **64Gi** |
| `limits.cpu` | 8 runs x 4 cpu | **32** |
| `limits.memory` | 64Gi + one run's headroom | **72Gi** |
| `pods` | 8 runs x (1 sandbox + 1 in-flight replacement) | **16** |

**Checked against the pool.** CI at full nominal plus eight runs is
61 + 32 = **93 of ~104** schedulable cpu, leaving about 11 for system pods.
Memory does not bind: 64Gi of ~439 GiB. cpu still binds first, as above.

**Why not twelve.** 61 + 48 = 109 exceeds 104: with CI at nominal, the 9th
to 12th pods would sit Pending past the plugin's 600 s start timeout and fail
the same way. Twelve needs a node added or the CI queues shrunk, and a fleet
cap above eight is unsupported by this quota until then.

**Workspace disk at sixteen pods**, measured the same day at
`/srv/factory-workspaces`: `poweredge-xubuntu` 160 G free (24 workspace
directories present), `gmktec-xubuntu` 153 G free (10 present). Sixteen pods
all on one node is about 10 G per workspace at the binding node; see
`ansible/roles/factory_workspace_root/CAPACITY.md`. The per-run disk
high-water mark is still unmeasured, so that stays a soak item.

## The egress targets

The policy default-denies ingress (`podSelector: {}`, `ingress: []`) and allows
exactly three egress classes. It is a real bound rather than decoration:
`../k3s-config/config.yaml` passes no `--disable-network-policy`, so k3s's
bundled NetworkPolicy controller enforces it.

### 1. Cluster DNS — `53` UDP and `53` TCP to CoreDNS in `kube-system`

Named by namespace plus CoreDNS's own `k8s-app: kube-dns` label, never by the
Service address, which is not a committable literal across a rebuild.

Read where a pod's resolver actually comes from, not assumed: inside a live hp
Docker sandbox on 2026-10-13, `/etc/resolv.conf` names `nameserver 192.168.1.1`
with `search perch-rudd.ts.net` — the HOST's LAN resolver, because a Docker
sandbox shares the host's resolution path. A pod does not: it resolves through
CoreDNS, which forwards upstream itself. So the LAN resolver is deliberately NOT
an egress target here; granting it would widen the policy onto the homelab LAN
to buy a path pods never take.

### 2. The tailnet — `100.64.0.0/10`, all ports

ONE rule covers both tailnet endpoints, and the absent port list is a
measurement rather than laziness.

**The telemetry receiver.** Read from the live Fabro instance configuration on
hp as the work-item requires — specifically from the environment a dispatch
projects into its sandbox, measured inside an hp sandbox on 2026-10-13:

```text
LIVESPEC_SANDBOX_OTEL_ENDPOINT=http://100.89.189.118:35129
```

`POST /v1/traces` to it answered HTTP 200 from inside that sandbox. Both halves
of that value are derived at dispatch time, which is why no port literal belongs
in the manifest: the orchestrator's `_dispatcher_otel_endpoint` binds the
**dispatcher's own tailnet address** for a remote-factory dispatch (so the
sandbox exports back over the tailnet from either end), and the port is the
receiver's **ephemeral bound port** for that dispatcher process. A port literal
here would read tight and fail closed at the next dispatch. The committed
drop-in `ansible/roles/fabro_server/files/otel.conf` names
`http://172.17.0.1:4318` instead — the docker bridge gateway, which is the
SAME-HOST case and names "whatever host reads it", so it is correct for a Docker
sandbox beside its dispatcher and unreachable from a pod anywhere else.

Note this is NOT the CI lane's receiver. `../arc/hook-pod-template.yaml` posts a
runner pod's cache and build spans to the host collector's keyless `otlp/pods`
listener on each node's own cni0 gateway at port 4319, derived in the pod. That
listener's cni0-only bind IS its access control and it serves CI jobs; factory
runs export to their dispatcher over the tailnet.

**The beads Dolt tenant.** `.beads/config.yaml` commits the connection as
`dolt.server-host: 127.0.0.1` / `dolt.server-port: 3307` (mirrored by
`.livespec.jsonc`'s impl-plugin `connection` block). Probed from inside an hp
sandbox on 2026-10-13, TCP to `127.0.0.1:3307`, `172.17.0.1:3307` and
`100.89.189.118:3307` was REFUSED in all three cases — a Docker sandbox does not
reach the tenant today; the dispatcher does, host-side, through the
`with-livespec-env.sh` credential wrapper. So a committed per-endpoint literal
for the tenant would be a guess at where a FUTURE pod reaches a server that
listens on loopback on whichever tailnet member hosts it. The tailnet rule is
the honest shape, and proving the reach per node is the plan's own verify child
(`livespec-dev-tooling-sszvvw`).

Why the whole `100.64.0.0/10` and not a host address: that is Tailscale's CGNAT
range, so one CIDR names every tailnet member — poweredge is `100.78.140.72`
(`../k3s-config/config.yaml`'s `tls-san`), hp is `100.68.193.50` (plan
research/001), and the dispatcher measured above is a third. Pinning the
current three would break at the next member and is not a tighter bound in any
way that matters: every address in the range is already a machine the fleet
authenticates onto a private tailnet.

### 3. The sandbox image registry — TCP `443` off-site

`ghcr.io` and its CDN, whose addresses are not committable literals either. Read
from the same `environments` entry quoted above: the image is
`ghcr.io/thewoolleyman/livespec-fabro-sandbox`, pinned by the orchestrator's
`implement-work-item` workflow.

Expressed as `0.0.0.0/0` with everything private excepted —
`10.0.0.0/8`, `100.64.0.0/10` (rule 2 owns the tailnet),
`127.0.0.0/8`, `169.254.0.0/16`, `172.16.0.0/12` and `192.168.0.0/16` — so the
rule reaches off-site and never the homelab LAN, the pod CIDR, a node address or
the link-local metadata range.

**The image PULL itself is not what this rule serves.** A kubelet pulls a pod's
image before the pod exists, and a NetworkPolicy governs pod traffic only, so no
rule here can grant or deny it; on this pool the pull also goes through the ghcr
pull-through mirror each node's `registries.yaml` points at
(`../warm-cache/registry-mirror/`). The rule is for the pod's OWN off-site
traffic — a tool inside the sandbox fetching from the registry, and the same 443
every package index the sandbox's toolchain reads lives behind.

## The widening

`./factory-rbac.yaml` started at the pod lifecycle and nothing else. Three
grants were added by work-item `livespec-dev-tooling-pvykv7`, requested
2026-10-16 by the livespec-orchestrator-beads-fabro plan
`kubernetes-sandbox-backend` (epic `bd-ib-nmuyjc`, its research note 003
section 7.3) for the `bd-ib-ad6dby` lifecycle proofs, which run from
`hp-xubuntu` as `cwoolley` against what this plan delivers. Each one is here
because a lifecycle QUESTION has no answer without it, and each is recorded with
the question rather than with the verb list, because the verb list is already in
the manifest and only the question can say whether the grant may later shrink.

**A verb added live is gone at the next boot.** That is why this is a committed
widening and not a `kubectl edit`: the k3s datastore is a tmpfs
(`../datastore-tmpfs/`), the boot converge re-applies this whole directory at
every `poweredge-xubuntu` boot (`../reconstruct/converge-ci-stack.sh` step 10e),
and anything not in these files is wiped by the next reboot with no error
anywhere.

### 1. `nodes` — `get` and `list`, cluster-scoped

**The question: did the NODE leave, or did the POD die?** From inside the
`factory` namespace those are one observation — the pod is gone and nothing in
the namespace says whether its machine is still in the cluster. The plugin needs
to tell a `NotReady` node from a lost pod, and without this read every node-loss
check answers `403`, which is indistinguishable from a healthy cluster with a
dead pod.

**Cluster-scoped is forced, not chosen.** `nodes` is a cluster-scoped resource,
so a namespaced Role cannot name it at all — the same constraint
`../node-status-credential/node-status-patch-rbac.yaml`'s header records for
`nodes/status`. This is the ONLY cluster-scoped grant the launcher credential
holds, delivered by one ClusterRole and one ClusterRoleBinding bound to the
single subject `factory:sandbox-launcher`.

**The narrowing is the verb set, and it could not have been `resourceNames`.**
Kubernetes applies `resourceNames` only to requests that name a single object,
so `list` is not restrictable by it at all — and enumerating the nodes the
plugin has NOT been told about is the whole point of the read, so a name list
would either break it or be decoration. `get` and `list` and nothing else: no
`watch`, which was not asked for, and emphatically no `patch`, `update` or
`delete`, any of which would let a leaked sandbox token untaint, drain or evict
a node in the CI pool.

### 2. `networkpolicies` — `create`, `get`, `list`, `delete`, in `factory`

**The question: what may THIS sandbox reach?** The `factory-egress` policy
derived above is a NAMESPACE baseline: it default-denies ingress and allows the
three egress classes every factory pod needs. A sandbox that needs more than the
baseline gets a per-pod NetworkPolicy the plugin creates beside its pod and
deletes with it, each one punching a hole in that baseline. `create` and
`delete` are the lifecycle; `get` and `list` are how the plugin finds the
policies it owns in order to reap them.

**It does NOT hand `factory-egress` to the plugin to manage, and RBAC cannot
say so directly.** `resourceNames` is an ALLOW list, not a deny list, and it
does not apply to `create` at all, so there is no way to spell "every
NetworkPolicy except `factory-egress`". Two things stand in for the rule RBAC
cannot express: `update` and `patch` are withheld, so the baseline cannot be
rewritten in place; and the boot converge re-applies `./factory-namespace.yaml`
at every boot, so a baseline deleted between boots is restored. The residual —
a token that could `delete factory-egress` and leave the namespace on the k3s
controller's default-allow until the next converge — is accepted here because
`delete` is what makes the per-pod policies reapable, and the alternative is a
plugin that leaks a policy per sandbox forever.

### 3. `events` — `list` and `watch`, in `factory`

**The question: is `Pending` out of quota, or unschedulable?** A pod held out by
this namespace's ResourceQuota and a pod no node can hold are both `Pending`
with the same `status.phase`; the only thing that distinguishes them is the
Event the API server records — `FailedCreate` against the quota,
`FailedScheduling` against the scheduler. The distinction is load-bearing for
this namespace in particular, because the derivation above makes the quota the
ONLY admission bound and `hp-xubuntu` is plumbing today with nothing at the
4 cpu / 8GB envelope fitting on it, so BOTH failures are live and they demand
opposite responses: wait for a slot, or stop waiting.

Read-only on purpose — the plugin never writes an Event. `watch` is granted
beside `list` because the interesting Event arrives AFTER the pod is created,
and polling a list for it is the same read with worse latency.

### 4. `pods/exec` — `get` beside `create`, and `pods` — `patch`, in `factory`

Both were found live on 2026-10-16 by the kubernetes-sandbox-backend lifecycle
proof (bd-ib-ad6dby). The plugin's own kind CI runs as cluster-admin, so it never
saw the gap.

- **`get` on `pods/exec`.** Exec streams over WebSocket, and the upgrade
  request is an HTTP GET, which the API server authorizes as `get` on the
  `exec` subresource. With `create` alone, every exec from hp answered 403
  (`cannot get resource "pods/exec"`) on both the v5 and v4 channel protocols.
  To check this, use `kubectl auth can-i get pods --subresource=exec -n factory`.
  The slash form `get pods/exec` names a pod called `exec` and answers for
  plain `get pods`, so it reports yes even while the grant is missing.
- **`patch` on `pods`.** The plugin relabels a live sandbox pod with a merge
  patch (its `lifecycle.labels` capability, which Petri uses to retag a lease).
  It adds no power that `create` and `delete` in the same namespace do not
  already hold.

### Still no secrets, at either scope

The one grant that stays absent, and the only one with no question behind it
that the dispatcher does not already answer: the sandbox's own credentials are
projected INTO it by the dispatcher, so a verb on `secrets` would buy nothing
and widen the blast radius of a leaked token to every secret in the namespace.
Neither the Role nor the ClusterRole names `secrets`, and
`tests/livespec_dev_tooling/test_ci_runner_k3s_factory_namespace.py` asserts
that at both scopes.

## What is deliberately NOT here

- **No Kueue anything.** Nothing in this namespace is denominated in
  `ci-runner.io/churn-slot` and nothing admits through a ClusterQueue, per the
  2026-10-13 ruling. The ten per-repo `nominalQuota` values still sum to exactly
  `C = 44` and this namespace does not appear in that apportionment.
- **No node selector and no toleration.** Which nodes a factory pod may land on
  is the backend plugin's design child to decide
  (livespec-orchestrator-beads-fabro plan `kubernetes-sandbox-backend`, epic
  `bd-ib-nmuyjc`), and a selector committed here would be this repository
  guessing at it.
- **No grant on secrets, and exactly one cluster-scoped grant — the `nodes`
  read of §"The widening" §1.** See `./factory-rbac.yaml`'s header; the Role's
  rules, the ClusterRole's single rule and the absence of `secrets` at both
  scopes are asserted by
  `tests/livespec_dev_tooling/test_ci_runner_k3s_factory_namespace.py`.

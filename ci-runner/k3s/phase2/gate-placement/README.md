# gate-placement: steer gate admission off a CPU-saturated node

Work item `livespec-dev-tooling-gvo7fa`, under plan `dev-host-test-gate-load`
(epic `livespec-dev-tooling-6vuiwe`). Design C, ruled by the maintainer
2026-11-08. The contract is the "Placement by node pressure" bullet of
`SPECIFICATION/contracts.md` §"Delegated pre-push gate".

## Why

`gates-cq` admits by topology-aware admission, which subtracts the REQUESTS of
pods Kueue does not manage. CI runner pods request no CPU (only
`ci-runner.io/churn-slot`), so runner load is invisible to gate admission: a node
that runners saturate reads as free, and an admitted gate's 5-CPU request then
takes CPU from those runners by CFS weight. On 2026-11-07 at 21:09Z gmktec-xubuntu
was 0% idle with CI-slice pressure avg60 52 while poweredge-xubuntu was 18.6% idle
with pressure 0.06 and no gate lane. The committed flavor order is static, so it
cannot follow load as it moves.

This mechanism gives runner pods NO CPU request (any such request belongs to the
fixed factory-vs-CI share owned by `gmktec-factory-placement`) and neither reads
nor writes `ci-runner.io/factory-admit`.

## What runs where

| File | Runs on | What it does |
|---|---|---|
| `publish-gate-lane-readings.sh` + `.service`/`.timer` (30 s) | EVERY `ci_pool` node (role `gate_placement_publisher`, no `when:`) | Writes `cpu.idle60` (idle % over the last 60 s, from `/proc/stat`) and `ci.slice.some.avg60` (the BestEffort slice's `cpu.pressure`) onto its OWN Node as the condition `LivespecGateLaneCPU`. A reading it cannot take is published as `unreadable`, never 0. |
| `reconcile-gate-lane-order.sh` + `.service`/`.timer` (30 s) | the k3s server (role `gate_placement_reconciler`) | Reorders the flavors of `gates-cq` so a newly submitted gate Job is admitted on an unsaturated lane. |

No new credential: a condition is node *status*, written through the node-status
credential every agent already holds (the admin kubeconfig on the server), as the
factory pressure publisher does.

The node-level PSI that `../factory-pressure-placement/` publishes is a DIFFERENT
reading. On a mixed node it counts throttled factory sandboxes and reads high with
cores idle (`.ai/ci-node-capacity-reads.md`), so it never stands in for the CI
slice's pressure.

## The rule

A node is **saturated** when its CPU idle is under 5% AND the CI slice's pressure
avg60 is above 30 (`.ai/ci-node-capacity-reads.md`, legacy-coordinator-agent
2026-11-04).

The **lever is the flavor order** of `gates-cq`: Kueue tries flavors in list order
and admits on the first whose node has room. Per pass the reconciler:

1. Derives the lanes from the LIVE queue: a flavor whose `ResourceFlavor` selects
   `kubernetes.io/hostname` is a node lane. No node is named in the script, and
   `cluster-queue-gates.yaml`'s test requires exactly one gates flavor per
   `ci_pool` member, so a node that joins the pool is covered with no edit to the
   mechanism. Other flavors (the container-worker flavors) stay in front.
2. Reads each lane node's `LivespecGateLaneCPU` condition.
3. Orders the lanes: unsaturated lanes in static order, then saturated lanes in
   static order, then lanes whose node cannot run the gate architecture. When
   EVERY lane is saturated that is the static order, so saturation alone never
   leaves the queue without a lane.
4. Patches `/spec/resourceGroups/<i>/flavors` only when the order changed, with a
   `test` of the queue's `resourceVersion`. Every flavor object is written back as
   read: **quota is never changed**, and no `WorkloadPriorityClass` is added
   (`gate-priority` stays the only class).

The **static lane order** is the order the converge composes: container-worker
flavors first (`kueue/converge-worker-queues.sh`), then the order committed in
`kueue/cluster-queue-gates.yaml`, which `ci_converge_unit` installs beside the
script at `/usr/local/lib/ci-runner-k3s/kueue/cluster-queue-gates.yaml`. The
reconciler never writes the committed files. A converge run restores the static
order and the next pass re-applies the choice.

**Architecture.** A lane whose node's `kubernetes.io/arch` is not one of the
`gate gate` architectures in `workload-arch.conf` is neither unsaturated nor a
lane with room: it is not read and it sorts last.

**Unread readings.** A condition that is absent, older than 90 s, `unreadable` or
malformed, or a lane node the cluster does not know, is logged by node and reading
(`UNREAD node=<n> reading=<r> why=<w>`) and is NEVER taken as saturated or free.
The whole queue falls back to the static order. If the committed queue file or
`workload-arch.conf` cannot be read, the reconciler changes nothing and exits 1.

## Logging

Every pass logs a `DECISION` line with every lane node's readings. Every change it
makes logs a `CHANGE` line: old order, new order, the reason and the readings that
caused it. Read them with:

```bash
journalctl -u reconcile-gate-lane-order
/usr/local/lib/ci-runner-k3s/reconcile-gate-lane-order.sh --dry-run
```

## Rollout

```bash
just ansible-drift ansible/ci-pool.yml --tags ci_converge_unit,gate_placement
just ansible-apply ansible/ci-pool.yml --tags ci_converge_unit,gate_placement
```

The publisher starts first and needs a minute of samples before `cpu.idle60` is
readable, so the reconciler holds the static order until then. Revert: disable
`reconcile-gate-lane-order.timer`, then rerun `kueue/converge-worker-queues.sh`
(or apply `cluster-queue-gates.yaml`) to restore the static order.

## Not in scope

A priority lane for queue-relieving changes (ledger rider 1) is a separate design:
the spec for this item forbids a second `WorkloadPriorityClass` here.

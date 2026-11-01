## The maintainer's statement of what done means

you need to make the observability part of your plan. That needs to be part of your definition of done: to observe everything about Kubernetes that is necessary and follows best practices to manage it.

## Definition of Done assertions derived from that statement

- Every node the k3s cluster lists reports CPU usage, memory working set, filesystem usage and capacity, network I/O, and its Ready, MemoryPressure, DiskPressure and PIDPressure conditions into the Honeycomb livespec environment's metrics dataset, attributed by k8s.node.name, with datapoints in every 15-minute window, and its host collector's hostmetrics arrive with host.name equal to that node's name.
- Every running pod's CPU and memory usage rows in Honeycomb carry k8s.node.name and k8s.namespace.name equal to the API server's scheduling, including the factory and factory-mi-homelab namespaces, and per node the containers' CPU and memory requests and limits are queryable beside that node's allocatable CPU and memory.
- Per namespace, including factory and factory-mi-homelab, Honeycomb shows pod phase counts (pending, running, failed), container restart counts, OOM-killed container terminations, and pods unschedulable or pending past admission.
- Honeycomb shows the k3s API server's availability, datastore health (the kine/SQLite datastore's size, its filesystem's used share, and the API server's datastore request latency), the factory and factory-mi-homelab namespace ResourceQuotas' used against hard limits (factory-runs, factory-mi-homelab-runs), and each Kueue ClusterQueue's admitted and pending workloads and quota usage for the CI runner and gate queues.
- A Honeycomb board in the livespec environment shows per-node load and pressure, pod usage by node and namespace, workload health and factory queue and quota usage, and triggers fire on node CPU saturation, node memory pressure or working set above threshold, any node going silent, OOM kills or crash-looping containers in a factory namespace, and factory pods pending past a threshold.
- Every cluster node's collector configuration, and every board and trigger definition behind assertion 5, is converged from committed GitOps state, so a drift report on a node or definition that differs from the merged configuration reports the difference.

# Charter — kubernetes-observability

Created 2026-11-01 by the kubernetes-node-observability seat (session
25de2a81), on assignment from the coordinator legacy-coordinator-agent (epic
livespec-dev-tooling-6tgd2z, maintainer priority #7).

## Origin

Epic livespec-dev-tooling-dfixhe (gitops-fleet-capacity-monitoring) is being
dissolved. It took the Kubernetes-observability scope as its assertions 7-12
on 2026-10-24, at the maintainer's direction. Its first owning plan,
kubernetes-node-observability (epic livespec-dev-tooling-dfdiil), was archived
on 2026-10-31 with the node-level subset verified. This plan carries assertions
7-12 forward under their own owner, so dfixhe can archive.

## The maintainer's statement (verbatim, 2026-10-24 ~16:2xZ, recorded on dfixhe)

> you need to make the observability part of your plan. That needs to be part
> of your definition of done: to observe everything about Kubernetes that is
> necessary and follows best practices to manage it.

## Definition of Done

The six assertions are dfixhe assertions 7-12, carried over verbatim. One
cross-reference is renumbered: dfixhe 12 says "assertion 11", and here that
assertion is number 5. No new assertion was invented. They were derived and
re-worded on dfixhe by the coordinator, by scope events on 2026-10-24.

| Here | dfixhe | Short name |
|---|---|---|
| 1 | 7 | node USE signals and host metrics |
| 2 | 8 | pod usage attribution, requests and limits against allocatable |
| 3 | 9 | per-namespace workload health |
| 4 | 10 | API server, datastore, ResourceQuota, Kueue |
| 5 | 11 | board and triggers |
| 6 | 12 | GitOps convergence and drift of collectors, boards and triggers |

## Ledger verification, 2026-11-01

- **1 (dfixhe 7).** Carried and closed on dfdiil: a2aiza, b7wwgy, ool6ws. These
  are dfdiil assertions 1, 2, 3 and 5. dfdiil's plan Proof of Done was captured
  2026-10-28T02:04Z against v1.137.0 and ci-runner-host.8, and verified at
  02:09Z by a different session (603dd4ce). STATUS: met on the ledger. It is
  re-captured in this plan's own proof.
- **2 (dfixhe 8).** Covered for the `factory` namespace by dfdiil assertions 4
  and 6 (a2aiza, uftb4o). The `factory-mi-homelab` namespace is NOT separately
  captured anywhere. The coordinator's Honeycomb read of 2026-10-24 saw
  homelab pod CPU rows before node attribution existed. STATUS: open for the
  homelab half, which a plan-level read discharges.
- **3 (dfixhe 9).** Carried by ec2rkp, t6om4l and 2zii7l, all closed; t6om4l
  closed on host_verified at 2026-10-31T00:47Z. One residual is open:
  `k8s.container.status.last_terminated_reason` on a restarted container. That
  is livespec-dev-tooling-jmwa7k, which waits on a natural container restart.
  STATUS: open on jmwa7k.
- **4 (dfixhe 10).** Carried by vdleg7 (control-plane emitter) and t6om4l
  (board, quota, Kueue and datastore triggers), both closed and host_verified.
  STATUS: met on the ledger.
- **5 (dfixhe 11).** Carried by uftb4o (node board and triggers) and t6om4l
  (workload board and the factory-namespace OOM, CrashLoopBackOff and pending
  triggers), both closed. STATUS: met on the ledger.
- **6 (dfixhe 12).** The collector half is carried by ool6ws, hrdj6s and
  rval5v, all closed, plus livespec-dev-tooling-aqzi32, which is in acceptance
  waiting on its host capture. aqzi32 closes the hole where drift read a stale
  raw.githubusercontent cache of `main` for up to 300 s after a merge, and so
  reported no change. The board and trigger half is NOT met.
  `ci-runner/observability/boards/apply-boards.sh` and
  `triggers/apply-triggers.sh` converge the committed definitions idempotently
  (t6om4l), but neither has a drift or check mode. A live definition that
  differs from the merged one is overwritten on the next apply, and nothing
  reports the difference. STATUS: open. It needs a new child that adds a
  read-only drift report to both appliers.

## Children

- **livespec-dev-tooling-jmwa7k** — re-parented from dfixhe; carries 3.
- **livespec-dev-tooling-aqzi32** — parentless until now; carries 6. Owned by
  this seat; its capture watcher is armed until 2026-11-06T00:00Z.
- **A new item: drift reports for the board and trigger appliers** — carries 6.
- **livespec-dev-tooling-ipcm33** — re-parented from dfixhe as directed. It
  carries none of this plan's assertions: factory step telemetry is
  factory-path work, not cluster observability. Disposition: close it as moved
  to its orchestrator successor bd-ib-tqzazn. The disposition primitive refused
  that close on 2026-10-30 with `undeterminable_tier`, because ipcm33 carries
  no spec-change-tier record. It stays here until that refusal is cleared on
  the normal path.

## Deferrals (each concrete)

- **A hostmetrics DaemonSet replacing host collectors.** Deferred to the
  Talos/Omni rollout, as recorded at dfdiil's archive. Host collectors already
  satisfy assertion 1.
- **docker_stats on gmktec.** It is outside Kubernetes. Reconsidered by
  whichever plan inherits dfixhe's capacity scope.
- **Factory pod placement.** It is a scheduling decision, not observability.
  It goes with dfixhe's assertions 1-6 to the gmktec-cutover owner the
  coordinator names.

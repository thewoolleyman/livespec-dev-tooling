# 010 — Routes to full cluster load on the arm64 worker (2026-11-09)

Written by the homelab-k8s-worker-nodes seat on the VPS after the seat moved
there from the MacBook Air (maintainer, 2026-11-09 15:18Z). It answers
legacy-coordinator-agent's 15:15Z measurement: the M4 was not taking full
cluster load. The coordinator accepted these routes at about 15:28Z.

## Measured state, 2026-11-09 15:19:55Z

Read through poweredge-xubuntu's kubectl:

- macbook-m4-max-homelab-worker: Ready, 12 CPU allocatable.
- Its enrollment values: `ci-runner.io/churn-slot` 2,
  `gate-share-millicores` 6000, `k3s-role=arc-runner-host`, and the class
  taint `homelab-worker.livespec.dev/class=worker:NoSchedule`.
- Live load: 2 arm64 runner pods Running, plus 1 pending in
  `livespec-dev-tooling-arm64-cq`. 1 gate Running, and 6 gates Completed in
  the past hour.
- These values come from the MacBook Air seat's 09:16Z apply. That seat's
  branch was never pushed and is lost.

## Sizing: lend an unenrolled class's share

Each class the worker is enrolled in gets an equal share of its allocatable
CPU. On 12 CPU with the factory class unenrolled, that is 6000m each:

| Class | Share | Units |
|-------|-------|-------|
| CI | 6000m | 2 churn slots of 2.73 CPU (5.46 CPU) |
| Gate | 6000m | 1 gate of 5 CPU / 8 Gi |

That is 10.46 of 12 CPU admissible. A second gate would need 10 CPU, so a
larger gate share adds nothing.

When the factory enrolls, each share becomes 4000m: 1 slot, 1 gate and
1 factory pod.

Spec: proposal `homelab-worker-lend-idle-share` (livespec-dev-tooling#3876), ratified
as v168 (livespec-dev-tooling#3879, merged 16:21:46Z). Code is on branch
`homelab-worker-lend-idle-share`.

## (a) CI beyond livespec-dev-tooling's two jobs

**Image architectures.** Measured with `docker manifest inspect`:

- `livespec-fabro-sandbox:python-v1.189.0` and `python-v1.187.0` are
  amd64 + arm64 indexes.
- `python-v1.64.1`, `python-rust-v1.171.0` and `python-rust-v1.189.0` are
  single-platform (amd64).

**Each repository's CI pin**, from its master `ci.yml`:

| Repository | Pin | arm64? |
|------------|-----|--------|
| livespec | python-v1.189.0 | yes |
| livespec-orchestrator-beads-fabro | python-v1.189.0 | yes |
| livespec-driver-claude | python-v1.189.0 | yes |
| livespec-driver-codex | python-v1.189.0 | yes |
| livespec-driver-pi | python-v1.189.0 | yes |
| livespec-overseer | python-v1.189.0 | yes |
| livespec-orchestrator-git-jsonl | python-v1.187.0 | yes |
| livespec-runtime | python-v1.64.1 | no |
| livespec-console-beads-fabro | python-rust-v1.171.0 | no |
| livespec-dev-tooling (python-rust and fuzz jobs) | — | no |
| fabro | — | no |

So `workload-arch.conf`'s "amd64-only sandbox tag" reason is stale for the
seven repositories marked yes.

**Why a release-line flip alone is wrong.** Every fleet ClusterQueue shares
the one `churn-slot-flavor`, whose only nodeLabel is
`k3s-role=arc-runner-host`, and the M4 carries that label. If a release line
flips to `amd64,arm64`, its pods tolerate the class taint. They would then
take the worker's churn slots against x86 quota, mixing the accounting.
(#3770's lendingLimit 0 exists for the converse case: an x86 job admitted on
an arm64 slot.)

**Design.**

1. `churn-slot-flavor` gains `kubernetes.io/arch: amd64` in its nodeLabels,
   so x86 quota places only on x86 nodes.
2. A `churn-slot-worker-arm64-flavor` ResourceFlavor is added, rendered by
   `converge-worker-queues.sh` like `gates-worker-arm64-flavor`:
   - nodeLabels: `homelab-worker.livespec.dev/class=worker` and
     `kubernetes.io/arch=arm64`;
   - it tolerates the class taint;
   - its quota is the enrolled arm64 workers' churn slots.

   That quota sits in one ClusterQueue and is lent through the cohort only
   to queues that list the flavor. The lending is flavor-scoped, so lending
   is safe here, unlike on the shared flavor.
3. Each eligible repository's ClusterQueue lists the worker flavor AFTER
   `churn-slot-flavor`, and its release line flips to `amd64,arm64`. Kueue
   then injects the arm64 nodeSelector only when it assigns the worker
   flavor.
4. Each repository gets one canary run on arm64 before its line flips,
   because steps outside the job container can fetch amd64 binaries.

**Ordering.** Item 1 changes the selector of every fleet runner. Read the
live nodes' arch labels before applying it.

## (b) Factory sandboxes

**What exists.** `python-agent-v1.189.0-arm64` and
`python-agent-sha-543b821-arm64` are published (a3brdf's image half). The
1.189.0 release run 42615777379 failed only at `self-reconcile-pins`.

**What is owed, in order:**

1. a3brdf's on-node probe, through a committed proof route. A hand-applied
   pod is refused by `fleet_host_guard`.
2. smzkpu: preserve-before-cancel reach to the M4, through `kubectl exec` per the coordinator's 15:35Z ruling (livespec-orchestrator-beads-fabro#4756). The M4 runs plain
   containerd, so the check uses plain `crictl`, plus a per-node ssh user.
   This seat owns smzkpu since 2026-11-09 ~15:28Z.
3. The factory-flip PR:
   - the `workload-arch.conf` factory arm64 line;
   - a worker-class pod budget of 1, counted in the launch-cap sum;
   - coordinator-duties §10's one-run gate on the arm64 image.

## Not changed by this note

livespec-dev-tooling-ko26ez.8 (departure proof), the 24-hour live-load window,
and the remove-and-rejoin proof of ko26ez.7 stay as the 2026-11-08 handoffs
describe them. The window starts once all three classes run on the worker.

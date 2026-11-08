# factory-budget-admission: a fixed number of factory sandboxes per node

**TEMPORARY.** This is the fixed factory-vs-CI CPU share. The maintainer adopted it
on 2026-11-08 at about 14:3xZ: "OK, go with fixed CPU share, as a temporary
workaround to a better solution". legacy-coordinator-agent approved the mechanism
under plan `gmktec-factory-placement` (epic `livespec-dev-tooling-me5aqz`, research
note 003).

**End condition:** it is replaced by the better solution. That solution stays a
maintainer design item. When it lands, delete this directory, the
`factory_budget_reconciler` role, every `factory_pod_budget` value and the
`ci-runner.io/factory-admit` entry in `sandbox_driver_kubernetes_node_selector`.

## Why

Factory sandbox pods are Burstable: they request 3 CPU and are limited to 6. CI
runner pods are BestEffort and request no CPU. Under contention the CFS weights,
burstable 743 against besteffort 1, give the factory every contended cycle. The
scheduler cannot see CI load, so it keeps placing sandboxes on a node whose CI
is starving.

Measured on 2026-11-08 (scope events on me5aqz; note 003):

| | gmktec-xubuntu (32) | poweredge-xubuntu (72) |
|---|---|---|
| Idle | 0.23 % | 3.66 % |
| CI BestEffort `cpu.pressure` avg60 | 37.5, saturated | 16.5 |
| Factory cores | 25.4 | 41.9 |
| CI cores | 5.4 | 24.5 |

At 13:5xZ, expedited's master coverage pods on gmktec got 0.38 and 0.59 cores.
The only lever available then was a whole-fleet launch pause.

## The one number

The budget is one committed value per node, `factory_pod_budget`, set in that node's
`ansible/inventory/host_vars/<node>.yml`. The factory_budget_reconciler role
renders every ci_pool host's value into `/etc/livespec/factory-pod-budgets.conf` on
the k3s server. A factory node with no value gets **0**, so it takes no sandbox
until it declares a budget. That makes the gate opt-in for:

- any node enrolled later, including homelab-k8s-worker-nodes' workers;
- the `factory-mi-homelab` instance and the wrlwvk candidate, whose pods are counted
  and gated like the fleet's because they read the same plugin configuration.

| Node | Budget | Derivation and caveats |
|---|---|---|
| gmktec-xubuntu | 6 | CI p95 and median by concurrent factory sandboxes on gmktec, from ci-runtime-and-cost's Stage A rows (2026-11-04T14:00Z to 2026-11-08T11:35Z). The orchestrator coverage-shard median bends past 5 sandboxes (5.9, then 8.6, then 15.1 min). Factory implement turns slow at 8 or more sandboxes. Caveats: the 8-9 band is thin (n=19), the bands correlate with time of day and job mix, and the value was not derived jointly with `C`. |
| poweredge-xubuntu | 9 | **Measured from the 2026-11-08 CI burst.** The canary-phase value of 15 tripped at 18:59:34Z: 11 sandboxes with 30 CI pods put CI BestEffort `cpu.pressure` avg60 at 30.53. The fleet cap went 18 -> 9 first, then the budget to 6. In the same burst, 10 sandboxes with 29 CI pods put it at 17.75 (19:16Z). 9 is one notch below that single measured-safe point. The orchestrator-shard p95 method reads about 5. The budget was raised 6 -> 9 first and the fleet cap 9 -> 12 after. The sum is 15, which matches fleet cap 12 + candidate cap 1 + mi-homelab cap 2. The TRIPWIRE below still applies. |
| hp-xubuntu | 0 | It has been `FACTORY_NODE=false` since 2026-11-03 and carries no `ci-runner.io/factory` label. |

**The poweredge TRIPWIRE.** If poweredge's CI BestEffort `cpu.pressure` avg60 passes
30 at any read during or after the gmktec canary, set poweredge to its method number
(5-6). Lower the dispatcher's fleet cap to the new sum FIRST, then apply the lower
budget.

## The sum must cover the launch caps

A first-placement pod that no node admits waits for sandbox-driver-kubernetes'
600 s `start_timeout_secs` and then fails sandbox start. bd-ib-nmuyjc.5's stability
bar counts that as an infrastructure failure. Two rules prevent it:

1. **Keep every launch cap that places sandboxes at or below the sum of the budgets.**
   The reconciler counts the pods of EVERY instance on the cluster, so the caps
   that must fit are the fleet cap plus the candidate and mi-homelab caps. Lower a
   cap BEFORE lowering a budget.
2. **The reconciler fails open.** When every factory node is at or over its budget,
   the node with the most headroom stays admitted, and the cycle logs `OVERFLOW`.
   A gated pod therefore waits at most one cycle, about 30 s, and never the start
   timeout. An `OVERFLOW` line means rule 1 is broken. Fix the cap; do not raise the
   budget to silence it.

Deriving the fleet cap FROM the sum, so that the two are not two numbers, is a
filed follow-up. Today the fleet cap is a runtime file the dispatcher owns
(`tmp/petri-canary/fleet-cap` in the orchestrator launch clone), so no commit-time
check can read it.

## What is gated

Only a sandbox's FIRST placement. sandbox-driver-kubernetes v0.8.2 gives a later
pod of the same sandbox (resume, recreate) and its cleanup pod `pinned_to(node)`
affinity and no node selector (`src/pod.rs`). A label flip therefore never strands
a running run. CI runner, hook and gate pods do not select the label, and nothing
is tainted, so no CI template changes.

## Kill switch

Set `Environment=FACTORY_BUDGET_GATE=off` in `reconcile-factory-budget-admit.service`
and apply the `factory_budget_admission` tag of `ansible/ci-pool.yml`. The next
cycle sets `ci-runner.io/factory-admit=true` on every factory node. Fabro needs no
restart, because the selector stays as it is and every node then matches it.

## Rollout order (confirm the reader before the write)

1. Apply the `factory_budget_admission` tag of `ansible/ci-pool.yml`. Confirm that
   every `ci-runner.io/factory=true` node carries `ci-runner.io/factory-admit`:
   `kubectl get nodes -L ci-runner.io/factory,ci-runner.io/factory-admit`.
   Until step 2 the label steers nothing.
2. Apply the `sandbox_driver_kubernetes` tag of `ansible/fabro-hosts.yml`. It
   renders the selector entry into every config home. The deployed file predates
   the role's `kubernetes.io/arch` entry, so that entry lands too. It is harmless,
   because every factory node is amd64.

**No Fabro restart is needed.** Each run's worker spawns its own plugin process,
and that process creates the run's pod, so the pod is placed with the `config.toml`
read when the run launched. The server's own long-lived plugin child does not place
pods. A run launched after the step 2 render therefore places with the gate, and a
run already placed keeps its node. This was
measured on the first apply, on 2026-11-08 by kubernetes-sandbox-backend. The
fleet server had run unrestarted since 2026-11-07T03:42Z, and its `config.toml`
was written at 18:47:31Z. Run `01M6Y7RX3E0S`'s plugin launched at 18:47:16Z, before
the write, and its pod carried no `factory-admit` selector. Run `01M6Y7W275A3`'s
plugin launched at 18:48:59Z, and its pod was created on poweredge at 18:49:00Z
carrying the selector. The plugin does load its configuration once per process
(`main.rs`). What matters is which process creates the pod: the run's own one,
not the long-lived child the server keeps.

Revert in reverse order: drop the selector entry and apply step 2's tag again, so
runs launched after that render place without the gate, then remove the role.
For an immediate stop, use the kill switch.

## Files

| File | Runs on | What it does |
|---|---|---|
| `reconcile-factory-budget-admit.sh`, with its `.service` and `.timer` (every 30 s) | the k3s server (role `factory_budget_reconciler`) | Counts each factory node's sandbox pods and sets `ci-runner.io/factory-admit`. |

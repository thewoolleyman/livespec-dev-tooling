# `factory_budget_reconciler` — per-node factory pod budgets

**TEMPORARY.** This is the fixed factory-vs-CI CPU share the maintainer adopted on
2026-11-08 ("OK, go with fixed CPU share, as a temporary workaround to a better
solution"). It ends when the better solution replaces it; that stays a maintainer
design item (plan gmktec-factory-placement, research note 003). The mechanism, the
fail-open rule, the kill switch and the rollout order are in
`ci-runner/k3s/phase2/factory-budget-admission/README.md`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `factory_pod_budget` | none, which means 0 | How many factory sandbox pods this node may hold. It is the ONE source of truth for factory placement. The role, which runs on the k3s server, renders every ci_pool host's value into `/etc/livespec/factory-pod-budgets.conf`. A `ci-runner.io/factory=true` node without one takes no new sandbox, so a node enrolled later must declare its budget. |

## The values, and how each was derived

| Node | Value | Derivation and caveats |
| --- | --- | --- |
| `gmktec-xubuntu` | 6 | Derived from CI p95 and median by concurrent factory sandboxes on the node, using ci-runtime-and-cost's Stage A rows (2026-11-04T14:00Z to 2026-11-08T11:35Z). The orchestrator coverage-shard median bends past 5 sandboxes (5.9, then 8.6, then 15.1 min), and the live CI slice was saturated (avg60 37.5). Caveats: the 8-9 band is thin, the bands correlate with time of day and job mix, and the value was not derived jointly with `C`. |
| `poweredge-xubuntu` | 9 | Measured from the 2026-11-08 CI burst, with 29-30 CI pods on the node. 11 sandboxes put CI BestEffort `cpu.pressure` avg60 at 30.53 (18:59:34Z), which fired the tripwire on the canary value of 15, and the fleet cap went 18 -> 9 first, then the budget to 6. 10 sandboxes put it at 17.75 (19:16Z). 9 is one notch below that single measured-safe point. The budget was raised 6 -> 9 first and the fleet cap 9 -> 12 after. The sum is 15, which matches fleet 12 + candidate 1 + mi-homelab 2. TRIPWIRE: if avg60 passes 30 at any read, lower the fleet cap to 9 FIRST, then set this to 6. |
| `hp-xubuntu` | 0 | It has been `FACTORY_NODE=false` since 2026-11-03, so it is not a factory node. The 0 is declared so that the intent can be read here. |

**The sum must cover every launch cap that places sandboxes:** the fleet cap
plus the candidate and mi-homelab caps. The reconciler fails open rather than
leave a sandbox Pending, and it logs `OVERFLOW` when this rule is broken.

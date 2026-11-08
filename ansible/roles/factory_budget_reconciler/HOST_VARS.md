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
| `poweredge-xubuntu` | 15 | Canary-phase value with a TRIPWIRE (coordinator ruling (a), 2026-11-08). It makes the sum 21, which matches fleet 18 + candidate 1 + mi-homelab 2. With a smaller sum, the fail-open at full load would hand overflow back to gmktec. Read literally, the same method gives about 5. The live CI slice was not saturated at 11 sandboxes (avg60 16.5), and the canary reports this node's CI pressure at every read. If its CI BestEffort `cpu.pressure` avg60 passes 30 at any read, set it to 5-6, lowering the dispatcher's fleet cap to the new sum FIRST. |
| `hp-xubuntu` | 0 | It has been `FACTORY_NODE=false` since 2026-11-03, so it is not a factory node. The 0 is declared so that the intent can be read here. |

**The sum must cover every launch cap that places sandboxes:** the fleet cap
plus the candidate and mi-homelab caps. The reconciler fails open rather than
leave a sandbox Pending, and it logs `OVERFLOW` when this rule is broken.

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
| `gmktec-xubuntu` | 7 | Raised 6 -> 7 on 2026-11-10 by legacy-coordinator-agent's cap ruling (about 04:4xZ), so that the budget sum 16 covers fleet cap 12 plus the candidate cap 1, the mi-homelab cap 2 and the expedited guard slot 1. GUARDS for the first 6 h: return to 6, lowering the fleet cap to 11 FIRST, if the green rate per finished run falls below 75%, or if gmktec twice meets saturation (idle under 5% AND the CI slice's avg60 over 30). The 6 was derived from CI p95 and median by concurrent factory sandboxes on the node, using ci-runtime-and-cost's Stage A rows (2026-11-04T14:00Z to 2026-11-08T11:35Z). The orchestrator coverage-shard median bends past 5 sandboxes (5.9, then 8.6, then 15.1 min), and the live CI slice was saturated (avg60 37.5). Caveats: the 8-9 band is thin, the bands correlate with time of day and job mix, and the value was not derived jointly with `C`. |
| `poweredge-xubuntu` | 9 | Measured from the 2026-11-08 CI burst, with 29-30 CI pods on the node. 11 sandboxes put CI BestEffort `cpu.pressure` avg60 at 30.53 (18:59:34Z), which fired the tripwire on the canary value of 15, and the fleet cap went 18 -> 9 first, then the budget to 6. 10 sandboxes put it at 17.75 (19:16Z). 9 is one notch below that single measured-safe point. The budget was raised 6 -> 9 first and the fleet cap 9 -> 12 after. The sum is 15, which matches fleet 12 + candidate 1 + mi-homelab 2. TRIPWIRE: if avg60 passes 30 at any read, lower the fleet cap to 9 FIRST, then set this to 6. Stepped 9 -> 11 on 2026-11-11 (~18:03Z, legacy-coordinator-agent 5bf269cf) after PR CI moved to hosted runners, under a re-grade: master CI p95 admitted only while this node held 10-11 factory pods, line 1.2x the 2026-11-10/11 baseline, graded at n >= 20 per job. Reverted 11 -> 9 on 2026-11-13 by that re-grade's FAIL (livespec-dev-tooling#4198, #4465): check-coverage reached n=20 with p95 142 s against its 128.4 s line, and check-python-batch read 244 s against 196.8 s at n=15. The fleet cap went 20 -> 18 first (in force 05:31:01Z). |
| `hp-xubuntu` | 2 | FACTORY_NODE=true again since the 2026-11-11 factory trial. It went 2 -> 1 at ~05:15Z that day (gates-first rule: gates-cq had 3 pending while hp's gate flavor held 5 cpu idle), then 1 -> 2 on 2026-11-12 (legacy-coordinator-agent ruling 245a3c34, livespec-dev-tooling#4320, after #4302 shrank hp's gate lane to one gate). Derivation: allocatable 14.5 cpu / 27.2 GiB, less one gate (5 / 8) and warm-uv-cache (0.7 / 0.7), against a 3 cpu / 7.45 GiB sandbox: cpu 2.93, memory 2.48, so 2. Its condition read (1 gate + 2 factory pods, 2026-11-12 14:41Z: idle 0.26%, besteffort avg60 14.38) kept 2. REVERT to 1 if idle < 5% AND kubepods-besteffort cpu.pressure some avg60 > 30. |
| `gamingpc-xubuntu` | 1 | Its gate lanes reserve 5 cpu / 8 GiB at the base value 2 (memory (30.4 - 8 - 0.5) / 7.45 = 2.94). Cut to 1 on 2026-11-12 ~19:4xZ (legacy-coordinator-agent GO, R301; plan gate-job-resources) while gates-gamingpc-flavor holds TWO gate units, 10 cpu / 16 GiB, for a hand-land burst: memory (30.4 - 16 - 0.5) / 7.45 = 1.86 and cpu (16 - 10 - 0.5) / 3 = 1.83, so 1. REVERT to 2, with the gate lane back to 5 / 8 GiB, when that burst ends and gate waits re-measure under 300 s. |

**The sum must cover every launch that can place a sandbox on a budgeted node.** The reconciler fails open
rather than leave a sandbox Pending, and it logs `OVERFLOW` when this rule is broken. Which launches those are
is read from the launcher and the sandbox driver's placement, not from this file:

- **Lanes inside the launcher's fleet count** (read 2026-11-13 from the 44 running launchers, all
  `tmp/petri-canary/dispatch-dual-r681b.sh` in livespec-orchestrator-beads-fabro, line 262):
  `fleet = gmk_live + hl_live + cand_live + markers` (hp and vps read 0, retired). So the petri lane (`:32276`),
  the mi-homelab lane (`:32277`), the candidate lane (`:32278`) and in-flight markers all count against the one
  fleet cap. `candidate-cap` and `hl-cap` are sub-limits inside it, not additions to it. The homelab-worker-arm64
  lane is NOT in the count (`arm_live` is excluded), although its launches still wait for the fleet to be under
  the cap. The committed `fleet-launch/dispatch-dual.sh` on orchestrator master counts only
  `gmk_live + hl_live + markers`, so a launcher running that file would leave the candidate lane outside the cap.
- **Where each lane's sandbox pods land** (this repository's `sandbox_driver_kubernetes` role): petri, candidate
  and mi-homelab all render the default node selector, `ci-runner.io/factory=true`, the factory architecture
  (amd64) and `ci-runner.io/factory-admit=true`. So they land only on the budgeted factory nodes above, and the
  reconciler counts them there whatever the namespace (mi-homelab's pods run in `factory-mi-homelab`). Only an
  instance in `sandbox_driver_kubernetes_worker_config_homes` (the homelab-worker-arm64 instance) selects
  `homelab-worker.livespec.dev/class=worker` plus its own architecture. Its pods land on the M4 worker, which has
  no budget here and consumes none.

So the sum must cover the fleet cap, plus any lane outside the fleet count that lands on a budgeted node. Read
2026-11-13: no such lane exists under the running launcher.

**Measured state, 2026-11-13 ~06:50Z (no value changed by this note):** the budgets sum to 19 (7 + 9 + 2 + 1)
once poweredge's revert to 9 lands. The fleet cap is 18 (since 05:31:01Z), with `candidate-cap` 3 and `hl-cap`
2 inside it. Under the running launcher that leaves 1 slot of slack and no shortfall. The earlier wording of this
rule added the candidate and mi-homelab caps to the fleet cap (18 + 1 + 2 = 21, or 23 at `candidate-cap` 3), and
by that wording the sum is 2 to 4 short. The shortfall is real only for a launcher that counts the candidate lane
outside the fleet cap, which is the committed `fleet-launch/dispatch-dual.sh` and not the running copy. The cap
number is legacy-coordinator-agent's call: the cap follows the budgets, never the reverse.

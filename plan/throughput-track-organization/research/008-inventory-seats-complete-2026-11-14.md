# Inventory completed: a seat for every PARTIAL plan, and corrected counts (2026-11-14)

The fourth independent review (session ef0eaf8a, 2026-11-14T05:53:38Z) reproduced assertions 2 to 5 and failed
assertion 1 on one gap: the three data records class 40 plans PARTIAL, but notes 004 and 007 between them gave a
seat, or "none", for only some of them, and note 004's counts did not match the records. This note closes that. It
supersedes note 004's "Counts" paragraph, its PARTIAL section, and note 007's seat table.

## Counts, taken from the data records themselves

| Record | CORE | PARTIAL | NONE |
|---|---|---|---|
| `data/inventory-livespec-dev-tooling.md` | 13 | 12 | 12 |
| `data/inventory-livespec-orchestrator-beads-fabro.md` | 8 | 21 | 16 |
| `data/inventory-other-repositories.md` | 7 | 7 | 27 |

Two corrections to note 004 follow from the records: livespec-console-beads-fabro/optimize-console-builds and
livespec/livespec-ci-on-hetzner are classed CORE there (note 004 listed both as PARTIAL), and the orchestrator has
21 PARTIAL plans, of which note 004 named 10 and referred to the rest as "ten plans".

## The seat of every PARTIAL plan

Source for every row: legacy-coordinator-agent's herdr roster read of 2026-11-13 ~23:0xZ, recorded on
livespec-dev-tooling-q26e3c at 23:02:44Z (vmi3006760, gamingpc-xubuntu, chads-macbook-pro, hetzner-xubuntu), and
this seat's own read of vmi3006760 at 21:55Z. "none" means the plan had no live seat in either read.

### livespec-dev-tooling (12)

| Plan (epic) | Seat at ~23:0xZ on 2026-11-13 |
|---|---|
| kubernetes-observability (livespec-dev-tooling-s2aqob) | vmi3006760, workspace livespec-dev-tooling |
| ci-cache-optimization (livespec-dev-tooling-7zozck) | vmi3006760, workspace livespec-dev-tooling |
| gmktec-factory-placement (livespec-dev-tooling-me5aqz) | vmi3006760, workspace livespec-dev-tooling |
| dev-host-disk-retention (livespec-dev-tooling-qgwxo4) | vmi3006760, workspace livespec-dev-tooling |
| expedited-incident-response-flag (livespec-dev-tooling-bqnzcm) | vmi3006760, workspace livespec-dev-tooling |
| expedited-incident-hardening (livespec-dev-tooling-dh3hub) | vmi3006760, workspace livespec-dev-tooling |
| radar-and-deterministic-admission (livespec-dev-tooling-w7ley3) | none |
| token-spend-analysis (livespec-dev-tooling-6lv7ze) | none |
| console-factory-build-telemetry (livespec-dev-tooling-bfvbsw) | none |
| software-factory-gap-map (livespec-dev-tooling-oft4bu) | none |
| mutation-testing-keystone (no epic) | none |
| version-lockstep-release-race (livespec-dev-tooling-zbkur6) | none |

### livespec-orchestrator-beads-fabro (21)

| Plan (epic) | Seat at ~23:0xZ on 2026-11-13 |
|---|---|
| legacy-dispatcher-agent (bd-ib-ynnykl) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| spec-implementation-lockstep (bd-ib-ax3rds) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| kubernetes-sandbox-backend (bd-ib-nmuyjc) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| factory-run-work-preservation (bd-ib-nckst7) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| anthropic-burn-mitigation (bd-ib-b2jzxw) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| fabro-currency (bd-ib-6tcjfx) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| goal-template-opener-handling (bd-ib-fe3zrm) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| dispatch-control-plane (bd-ib-k6dqwc) | vmi3006760, workspace livespec-orchestrator-beads-fabro (a Codex seat) |
| hp-factory-failure-follow-ups (bd-ib-qieqc6) | none |
| checkpoint-commit-hook-failures (bd-ib-hcwmnq) | none |
| factory-test-first-enforcement (bd-ib-q622ls) | none |
| factory-configurable-model-fallback-priority (bd-ib-jxvgq5) | none |
| factory-run-wall-budget (bd-ib-hqt3s5) | none |
| failure-evidence-retention (bd-ib-4aebpa) | none |
| pr-stage-backgrounded-push-fault (bd-ib-ctagnf) | none |
| provisional-fleet-launch (bd-ib-klkbxp) | none |
| relay-delivery-and-progress-deadline (bd-ib-lrik25) | none |
| run-control-lease-and-versioned-instructions (bd-ib-afxq63) | none |
| run-lifecycle-false-verdicts (bd-ib-qen6rr) | none |
| runaway-process-containment (bd-ib-wcuauj) | none |
| silent-failure-surfaces (bd-ib-cewr) | none |

### Other repositories (7)

| Plan (epic) | Seat at ~23:0xZ on 2026-11-13 |
|---|---|
| livespec-overseer/herdr-overseer (overseer-uzvcbn) | vmi3006760, workspace livespec-overseer |
| livespec-overseer/fleet-plumbing-and-dispatch-reliability (overseer-cajdwp) | none |
| livespec-overseer/caam-generic-limit-windows (overseer-rumvpf) | none |
| livespec-overseer/llm-provider-manager (overseer-tm2qtw) | none |
| livespec-overseer/session-obligation-recovery (overseer-527by2) | none |
| livespec/fleet-delivery-lane-visibility (livespec-n33rwg) | none |
| homelab/steady-state-loop-hardening (hl-nkuzaz per the plan file; ledger unread from hetzner-xubuntu) | none |

The seats of the two plans the records class CORE but note 004 listed as PARTIAL: optimize-console-builds
(livespec-console-beads-fabro-gqmtwa), none; livespec-ci-on-hetzner (livespec-h22nve), none.

## Smaller corrections

- Note 007 dates the second re-wording of assertion 3 "~03:1xZ"; the scope event is 2026-11-14T03:02:55Z.
- The two proposals this plan withdrew were then decided by their owners at 2026-11-14 ~03:39Z: bd-ib-jaaya5 was
  RELEASED by anthropic-burn-mitigation and is a child of sandbox-commit-gate-follow-ups (bd-ib-3goerg); bd-ib-hap62u
  was KEPT by publish-draft-green-work-loss (bd-ib-acrr56), which carries it as a row-6 carrier in place.
- Track-map gap 6 (gamingpc lanes) was closed with no item by throughput-plans-coordinator's measured ruling,
  recorded on livespec-dev-tooling-ukoeah at 2026-11-14T03:36:21Z.
- The rank 3 and 4 carriers of the handoff scope event are corrected in report 13 on the epic: bd-ib-rowuou is not a
  carrier.
- ci-reliability-leftovers' seat was opened by legacy-coordinator-agent in workspace throughput-improvements on
  hetzner-xubuntu, not in workspace livespec-dev-tooling as note 007 said it would be. fleet-flaky-tests (rank 11)
  keeps its tab in workspace livespec-dev-tooling on hetzner-xubuntu.
- **Merge-quiet breach by this seat.** On 2026-11-14 this seat merged livespec-dev-tooling#4615 (04:25Z), #4630
  (05:17Z) and #4608 (05:38Z) by hand, and re-armed auto-merge on two of them, inside the merge-quiet window of
  incident asxhj3, after legacy-coordinator-agent's notices on the epic at 04:32:44Z and 05:18:49Z, which it had not
  read. Recorded in report 14 on the epic. This note and the archive move were held until QUIET OFF.

# Program board — the tracks this plan references, and what it asks of them

This plan OWNS dev-tooling work only (the mechanism and dev-tooling's own
burn-down). Every other repository's burn-down is REFERENCED here by tenant /
id and dispatched, executed and closed from THAT repository through its own
factory; it is never worked around from this thread. Consequences (same rules
as `livespec-console-beads-fabro/retire-overseer-and-redesign-control-plane-around-console`):

- **No status column.** Status lives in the ledgers and is read fresh from
  one `bd list --status all --json -n 0` per tenant per session. A status in
  a file is a shadow ledger. This file changes when the STRUCTURE changes — a
  track is added, closed or re-homed, or a ruling lands.
- **Children of the anchor epic are dev-tooling-owned mechanism items plus
  pointer children.** Cross-tenant references use the D6 form
  `plan_ref: livespec-dev-tooling/fleet-heading-coverage-convergence` on the
  consumer-side item, plus `upstream_work_item_id` naming the pointer child
  here.
- **Anchor:** `associated_work_item_id` → `livespec-dev-tooling-0bse`.

## Binding rulings

- **No cop-outs (2026-09-09).** Every heading gets a real test; there is no
  non-testable category; a heading with no behavior is a spec-structure
  defect. Binding on every item owned by or referenced from this plan.
- **Never work around an upstream or a consumer.** Mechanism defects are
  fixed in dev-tooling; a consumer's burn-down is done in that consumer,
  through its factory.
- **Everything through the factory (2026-09-09).** No hand worktree→PR
  burn-down anywhere in the fleet under this plan.

## The mechanism track (owned here)

Children of `livespec-dev-tooling-0bse`, in dependency order:

1. ratchet — shrink-only baseline register for `TODO` rows (D3)
2. reason guard — a TODO's only legal justification is an owed test with a
   live owner; non-testability reasons rejected (D4)
3. age bound — release-tier failure past the bound (D5)
4. doctor rules + retire the scope lever and `reason` slot at zero (D9)

Each carries FAIL-CAPABILITY proof as acceptance. The proposed change that
ratifies them is `SPECIFICATION/proposed_changes/heading-coverage-convergence.md`.

## The burn-down tracks (referenced; one per governed repository)

Each row names the tenant, the frozen row count from `003`, the interim
standing owner (D8, closed by the burn-down item as its last act), and the
consumer-side burn-down item id once filed. The pointer child here is titled
`BLOCKED-ON <tenant> <id>: burn down N heading-coverage TODO rows with real tests`.

| repository (tenant) | frozen TODO rows | standing owner (interim) | keep-open row owner | burn-down item (in tenant) |
|---|---|---|---|---|
| livespec-dev-tooling | 57 | livespec-dev-tooling-xx57 | — | owned here: `livespec-dev-tooling-0bse.5` |
| livespec-runtime | 22 | livespec-runtime-4s3 (superseded, D8) | — | `livespec-runtime-l5q` ↔ pointer `livespec-dev-tooling-0bse.6` |
| livespec (core) | 7 | livespec-6fb1 (6) | livespec-sab5gn (1, open) | `livespec-9rhf` ↔ pointer `livespec-dev-tooling-0bse.7` |
| livespec-console-beads-fabro | 13 | livespec-console-beads-fabro-y9hc | — | `livespec-console-beads-fabro-dxu4` ↔ pointer `livespec-dev-tooling-0bse.8` |
| dolt-server | 43 | dolt-server-w6u | — | `dolt-server-t1z` ↔ pointer `livespec-dev-tooling-0bse.9` |
| livespec-overseer | 2 | overseer-hyfe | — | `overseer-7wks` ↔ pointer `livespec-dev-tooling-0bse.10` |
| livespec-driver-claude | 41 | livespec-driver-claude-axs | — | `livespec-driver-claude-lum` ↔ pointer `livespec-dev-tooling-0bse.11` |
| livespec-driver-codex | 36 | livespec-driver-codex-cea | — | `livespec-driver-codex-oro` ↔ pointer `livespec-dev-tooling-0bse.12` |
| livespec-driver-pi | 42 | livespec-driver-pi-43a | — | `livespec-driver-pi-1t4` ↔ pointer `livespec-dev-tooling-0bse.13` |
| livespec-orchestrator-git-jsonl | 25 | bd-gj-6ps | — | `bd-gj-0of` ↔ pointer `livespec-dev-tooling-0bse.14` |
| livespec-orchestrator-beads-fabro | 85 | bd-ib-heat (84) | bd-ib-nt3cjv (1, open) | `bd-ib-cvdw` ↔ pointer `livespec-dev-tooling-0bse.15` |

Fleet total at freeze: **373** `TODO` rows. The two keep-open rows
(`livespec-sab5gn`, `bd-ib-nt3cjv`) were already owned by live items before
the rollout; they are in the baseline and burn down like every other row.

## Cross-family pointer

- livespec core's cross-family scenario-tier rule: pointer item `livespec-375s` is filed in
  the `livespec` tenant asking whether a matching amendment is needed once
  dev-tooling's clause is ratified (charter §8 Q2). Referenced, not owned.

## Session protocol

The session that drives this plan runs under an overseerd track. On restart
the FIRST output is a STATUS RE-PRINT — goal, landed, in flight, decisions
taken on the maintainer's behalf, decisions owed, next action — read from the
epic's typed `next_action` and the ledgers, never from this file. A turn never
ends on a "still outstanding" list: each line becomes an action or the one
decision question.

# L2 thin migration — livespec-dev-tooling tenant (record)

The execution record for the `livespec-dev-tooling` slice of the fleet-wide
work-item-lifecycle redesign. This is a **thin migration-only** track
(decision 46): the tenant data migrates; no code or spec in this repo changes.
The cross-repo design of record is authoritative on any conflict
(`livespec/plan/work-item-state-machine/research/` decisions 1–46;
`04-slice-plan.md` "L2 — migration").

## Scope (what L2 means for this repo)

Per `04-slice-plan.md` "L2 — migration" + decision 46: `livespec-dev-tooling`
gets a **thin track** because `Driver/dev-tooling → orchestrator = zero deps`
(decision 42) — its `SPECIFICATION/` carries no work-item schema, so there is
nothing to propose-change here. The only work is the **data migration of this
repo's beads tenant**, applied through the orchestrator's L1a (`v0.3.0`) tooling:

1. register the 5 custom livespec statuses, and
2. backfill the now-required `rank` field on existing items.

The required-`rank` schema change makes any un-migrated tenant unreadable by the
shared validator (the standing "required-key schema change is a cross-repo epic"
rule), so all 9 fleet tenants migrate in lockstep; this is one of them.

## Pre-migration ground truth (probed read-only)

The `livespec-dev-tooling` tenant (`dolt.database = livespec-dev-tooling`,
prefix `livespec-dev-tooling`) held **68 issues**: 61 `closed`, 7 `open` — all
legacy (`open`/`closed` only; no custom statuses), **0 with any `rank`**.
24/68 carried metadata: 22 `audit` records, and 2 items
(`livespec-dev-tooling-1oa` [open], `…-04g` [closed]) carried legacy
`origin`/`gap_id` as **metadata keys** (the new schema reads `origin`/`gap_id`
from `origin:` / `gap-id:` **labels**, so it ignores those metadata keys; they
were preserved regardless — see below).

> Tenant-selection caveat learned here: `bd` reads its Dolt connection from the
> **process cwd's `.beads/config.yaml`** (or `bd -C <repo>`), NOT from the
> resolved `StoreConfig`. A probe run from the wrong cwd reads the wrong tenant.
> Every command below ran with cwd = this repo.

## Phase 1 — custom-status registration

```
bd config set status.custom "backlog,pending-approval,ready:active,active:wip,acceptance:wip"
```

(via `livespec_orchestrator_beads_fabro.store.register_custom_statuses`, decision
36). Idempotent. Verified: `bd config get status.custom` returns the value
verbatim. `blocked` and `done`→`closed` reuse beads built-ins, so only these 5
are custom.

## Phase 2 — `rank` backfill (live-only, legacy-seeded)

Computed with the orchestrator `rebalance-ranks` **`legacy_seed`** primitive
(`commands/rebalance_ranks.legacy_seed`), seeded by the legacy
`priority → captured_at → id` order (decision 39) → evenly-spaced fractional
keys. **Scope = LIVE (non-`done`) heads only**, per the enforced doctor
invariant + shipped `_rebalance_live` (both exempt `done`); see the handoff's
"Decision note". The 7 live heads received:

| rank | id | legacy priority | captured_at |
|---|---|---|---|
| `a0` | `livespec-dev-tooling-7us`    | 1 | 2026-06-12T17:02:56Z |
| `a1` | `livespec-dev-tooling-7et`    | 2 | 2026-06-11T00:51:55Z |
| `a2` | `livespec-dev-tooling-e60`    | 2 | 2026-06-12T15:39:54Z |
| `a3` | `livespec-dev-tooling-7us.7`  | 2 | 2026-06-12T19:28:42Z |
| `a4` | `livespec-dev-tooling-py9`    | 2 | 2026-06-13T09:40:05Z |
| `a5` | `livespec-dev-tooling-t5g6x4` | 2 | 2026-06-22T20:31:22Z |
| `a6` | `livespec-dev-tooling-1oa`    | 3 | 2026-06-28T10:23:42Z |

Each `rank` was written as a **lossless metadata merge** — `bd update <id>
--metadata '{…existing…, "rank": "<key>"}'` (existing `audit`/`origin`/`gap_id`
preserved). This is a deliberate, minor departure from the rebuild-from-modeled-
fields write of `store.update_work_item_rank`, chosen because two items carry
legacy `origin`/`gap_id` only in metadata; the merge guarantees zero data loss
("no scrub" — decision 39). No statuses changed; `priority` stays harmlessly in
beads-native history.

## Ledger anchor

Epic **`livespec-dev-tooling-l2sm`** (this tenant; type `epic`, `origin`
`freeform`, `rank` `a7`, `assignee` set to satisfy `active ⟹ assignee`),
prose-referencing the fleet anchor `livespec-35s3zo` (decision 41 convention —
prose, never a typed cross-tenant `depends_on`). Closed `done`
(`resolution=completed`) with `audit.merge_sha` set once this thread's PR
rebase-merges.

## Verification

- `bd config get status.custom` → the 5-status CSV verbatim.
- Every live (non-`done`) head carries a real, non-sentinel `rank`
  (`validate_order_key` passes; strictly increasing in seed order).
- Status histogram `{closed: 61, open: 7, active: 1}` — only the new epic added;
  no existing status altered.
- The 2 legacy-metadata items retain `origin`/`gap_id` alongside the new `rank`
  (e.g. `…-1oa` → `{gap_id: null, origin: "freeform", rank: "a6"}`).

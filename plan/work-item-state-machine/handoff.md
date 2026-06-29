# Handoff — work-item-state-machine (L2 thin migration, livespec-dev-tooling)

**Thread:** `plan/work-item-state-machine/` · **Ledger anchor:** epic
`livespec-dev-tooling-l2sm` (`livespec-dev-tooling` beads tenant) · **Fleet
anchor (prose ref):** `livespec-35s3zo` (livespec core tenant — NEVER a
typed cross-tenant `depends_on`, which would dangle in the flat same-tenant
id list and pollute the `blocked:dependency` derivation; decisions 41/44/45).

> Status is **derived from the ledger**, never stored in this file. To read it:
> ```bash
> source /data/projects/1password-env-wrapper/with-livespec-env.sh \
>   bd -C /data/projects/livespec-dev-tooling show livespec-dev-tooling-l2sm
> ```
> (the wrapper injects the tenant password; never echo it).

## ✅ STATUS: L2 tenant migration APPLIED + VERIFIED (2026-06-29)

This is the **thin migration-only** track for `livespec-dev-tooling` (decision
46): a DATA migration of this repo's beads tenant — **no code/spec change**
(decision 42: dev-tooling → orchestrator = zero deps; this repo's spec carries
no work-item schema). Both migration phases are applied and verified against the
live `livespec-dev-tooling` tenant:

1. **Custom-status registration.** `bd config set status.custom
   "backlog,pending-approval,ready:active,active:wip,acceptance:wip"` — the 5
   custom livespec statuses (decision 36; `blocked` + `done`→`closed` reuse beads
   built-ins). Idempotent; verified via `bd config get status.custom` reading the
   value back verbatim.
2. **`rank` backfill.** Via the orchestrator `rebalance-ranks` **`legacy_seed`**
   primitive (L1a `v0.3.0`), seeded by the legacy **`priority → captured_at →
   id`** order (decision 39), assigning evenly-spaced fractional keys
   (`a0`…`a6`). **Scope = LIVE (non-`done`) heads only** — see the decision note
   below. The 7 live heads were keyed; the 61 `done`/`closed` heads were left
   untouched. Writes were a **lossless metadata merge** (existing `audit` /
   `origin` / `gap_id` preserved, `rank` added); **no statuses changed**;
   `priority` left harmlessly in beads-native history (no scrub — decision 39).

**Verification (live tenant):** every live (non-`done`) head carries a real,
non-sentinel `rank`; status histogram `{closed: 61, open: 7, active: 1}` (the
`active` is this track's own epic `livespec-dev-tooling-l2sm`); `active ⟹
assignee` holds on the epic. The `_rank_findings` doctor invariant
(`work_item_state_invariants.py`) is satisfied.

## Decision note — backfill scope is LIVE-only (decide-and-inform)

Decision 39's prose says the backfill "sorts the WHOLE set." The **enforced**
contract diverges and was followed: the shipped doctor invariant
(`livespec-orchestrator-beads-fabro` `dev-tooling/checks/work_item_state_invariants.py`,
`_rank_findings`) and the shipped `rebalance-ranks` `main` (`_rebalance_live`)
**both EXEMPT `done` items** — only live (non-`done`) heads are required to carry
a non-sentinel `rank`. A `done`/`closed` head with no `rank` reads back the
shared `BOTTOM_SENTINEL` (sorts strictly last), which the listing tolerates by
design ("the sentinel only ever surfaces for superseded/historical lines"). So
the live-only backfill fully satisfies the invariant the build actually gates on,
is the minimal/lowest-churn mutation, and matches the shipped tooling's stance.
This is reversible: if the maintainer prefers the literal whole-set re-key, the
61 done heads can be keyed later via the same `legacy_seed` path. This is the
**precedent** for the other L2 thin tracks (`livespec-driver-claude`,
`livespec-driver-codex`) and the core `livespec` sweep.

## Pin note — no orchestrator-version pin to bump

The kickoff brief said "bump the orchestrator-beads-fabro pin to `v0.3.0`
**if needed**." It was **not needed** for this repo: there is **no
orchestrator-version pin in dev-tooling's files**. The orchestrator is a
host-wide (Codex) / per-project-enabled (Claude `.claude/settings.json`) plugin;
`.livespec.jsonc` carries only the **core-compat** pin (`livespec`
`>=0.1.0,<1.0.0`, pinned `v0.4.0`) and the **tenant connection block** — no
orchestrator semver field. The migration was driven directly from the
L1a-released orchestrator code (`commands/rebalance_ranks.legacy_seed`,
`store.register_custom_statuses`), so no repo file changed for the pin.

## Mechanism (how it was driven)

`bd` resolves its Dolt tenant from the **process cwd's `.beads/config.yaml`**
(equivalently `bd -C <repo>`), NOT from `StoreConfig` — the per-command argv
carries no `--server*` flags (`livespec-orchestrator-beads-fabro`
`_beads_client._build_argv`). So every tenant-touching command was run with cwd =
this repo (`/data/projects/livespec-dev-tooling`) under
`source /data/projects/1password-env-wrapper/with-livespec-env.sh …` (tenant
password injected, never echoed). The migration used the orchestrator store seam
(`livespec_orchestrator_beads_fabro.store` + `commands.rebalance_ranks`) with the
runtime vendored at `…/.claude-plugin/scripts/_vendor`.

## Design of record (authoritative on conflict)

`/data/projects/livespec/plan/work-item-state-machine/research/`
{`02-design.md`, `03-decision-log.md` (decisions 1–46), `04-slice-plan.md`
("L2 — migration")}. This thin track adds no design; it executes the L2 slice
for this tenant and records it in this repo's history.

## Remaining

- Close the epic `livespec-dev-tooling-l2sm` → `done` (`resolution=completed`,
  `audit.merge_sha = <this PR's merge sha>`) once this thread PR rebase-merges.
- Nothing else: the thin track is migration-only.

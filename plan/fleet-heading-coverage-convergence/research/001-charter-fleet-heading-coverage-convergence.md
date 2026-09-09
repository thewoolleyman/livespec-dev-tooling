# Fleet heading-coverage convergence — charter and decisions

Anchor: `associated_work_item_id` → `livespec-dev-tooling-0bse` (epic,
`metadata.plan_slug` = this directory's name), created 2026-09-09.

This is a NON-FUNCTIONAL REQUIREMENT that spans multiple epics and every
governed repository in the fleet. This one plan is responsible for working off
the heading-coverage TODO debt across the entire fleet and for making the
mechanism that lets it recur impossible. It OWNS the mechanism (this repo) and
REFERENCES the burn-down in every other member by tenant/id; it never works
around a consumer (see `002-program-board.md`).

## 1. What triggered this

The fleet liveness-gate rollout of 2026-09-08 (producer
`livespec-dev-tooling-d0er`, shipped in dev-tooling 1.59.0) made
`no_todo_registry`'s release tier able to convict a `test: "TODO"` row whose
owning work-item is closed or nonexistent. Backfilling the fleet for it
surfaced that **373 heading-coverage rows across 11 repositories are `TODO`**,
and that a 2026-09-06 "ratify-or-declare-internal" pass had systematically
resolved headings into `TODO` + a free-text reason such as *"No independently
testable assertion at runtime"* instead of writing tests — and the gate had
accepted every one, because that is exactly what it was designed to accept.

The first response (2026-09-08) re-homed every failing row onto a live
"standing owner" work-item per repository so the armed gate went green. That
cleared the *orphan* defect and nothing else: every row still says `TODO`.
The maintainer rejected it as a cop-out on 2026-09-09 and reframed the real
scope as mechanical prevention. Full root cause and the original decisions
that were RIGHT are in `004-root-cause-and-original-decision-record.md`.

## 2. The maintainer's framing (verbatim intent, not paraphrase)

> No, there should be absolutely no cop-outs. The whole fucking point of this
> is to ensure that every real scenario has a real test. There is absolutely
> no reason that it should not be testable at some level, even if
> mocking/doubles are used.
>
> The real scope of this problem is: how do we mechanically prevent these
> cop-outs? I thought that's what the plumbing was supposed to already
> prevent. Nothing is supposed to be able to be merged unless there is a real
> test linked to the heading. How did this end up getting fucked up and
> allowing copouts and merges of headings with no associated tests?

And, on the original scope-to-authorship decision:

> discuss the original reason for the exemption that unrelated commits could
> block it and make it unable to have a passing test. I remember there being
> a legitimate argument when I made that decision originally.

And on shape:

> this has increased in scope enough that it needs its own dedicated plan and
> epic and work items and propose changes — this is definitely a
> non-functional requirement that spans multiple epics. And the one plan
> should be responsible for working off the debt across the entire fleet.
> [...] this should likely supersede the one work item that you have been
> handling through here in the runtime repo.

## 3. Research (measured, not read)

- `003-fleet-debt-baseline-2026-09-08.md` — the frozen set: 373 TODO rows,
  per repository, with owner class and the standing-owner ids. This is the
  ratchet's seed (D3).
- `004-root-cause-and-original-decision-record.md` — the five designed
  accommodations that together made a plausible sentence a permanent
  substitute for a test, and the two original decisions that were correct and
  are PRESERVED (D2).

## 4. Decisions (each a proposal until the scope event or a ratified clause says otherwise)

**D1 — Every heading gets a real test; there is no "non-testable" category.**
Every H2 in every governed `SPECIFICATION/` resolves to a real, resolvable test
node id that exercises the heading's behavior, at the tier the heading
requires (integration-or-above for `## Scenario:` headings per the v009 rule),
using doubles/mocks where the boundary demands it. The free-text `reason`
field is not an exemption slot. A heading a repository believes has no
behavior is a SPEC problem to be fixed in the spec (restructure or fold the
heading), never a coverage exemption.

**D2 — The two original decisions were correct and are preserved.**
(a) A `TODO` is a legitimate *transitional* placeholder (v009,
`scenario-tier-coverage-invariant`): the spec-first workflow requires a
coverage row at ratification time, before an impl work-item can land the
test. (b) A commit is judged on what it authors, never on debt it inherited
(`livespec-dev-tooling-3ztbdq`, 2026-09-04, measured: 8 properly-owned entries
refused on all 66 because 58 inherited rows were unowned; the shared,
mandatory co-edit registry was unwritable). Neither is the defect. The defect
is that nothing made the transition END.

**D3 — Convergence by a shrink-only baseline ratchet, not a per-commit ban.**
A per-commit ban on `TODO` would break both halves of D2. Instead: freeze the
2026-09-08 set (003) as a baseline register; any `TODO` row NOT in the
baseline fails at authoring time (the existing staged-diff-scoped arming, so
unrelated commits stay untouched); the register can only shrink; a commit that
removes a row updates the register; the register reaching empty is the exit
gate. This is the `public-surface-debt.json` pattern applied to coverage.

**D4 — A TODO's only legal justification is "test owed, owned by a LIVE
work-item".** The `reason` field's ratified purpose (v009) was to
*acknowledge* the owed integration-tier test. A reason that asserts
non-testability ("no independently testable assertion", "enforced by checks
rather than a test", "orientation prose") is REJECTED mechanically. Liveness
of the owner is real (d0er) and convicts a closed or nonexistent owner.

**D5 — A TODO has a mechanical age bound at the release tier.** A `TODO`
older than the bound (measured from the row's first appearance in the
baseline or in git) fails the release tier, so "during transition" has an
end. Liveness and age stay release-tier-only: a per-commit verdict depending
on mutable external state could red master with no landed change, which
livespec core's `.ai/ci-gate-discipline.md` treats as an undiagnosable broken
state (the argument is preserved, not weakened).

**D6 — This uber plan lives in livespec-dev-tooling.** It owns
`heading_coverage`, `no_todo_registry`, the registry schema and the ratchet;
the v009 clause being amended is in ITS `SPECIFICATION/`; and it already hosts
the fleet-wide enforcement plans (`fleet-plan-lifecycle-enforcement`,
`fleet-shell-quality-enforcement`, `fleet-decision-authority-propagation`).
Dependency direction is right: the producer may name consumers' burn-down
items by reference; consumers point back with `plan_ref:
livespec-dev-tooling/fleet-heading-coverage-convergence`. Children of this
epic are dev-tooling-owned mechanism work plus pointer children; every other
repository's work is filed IN that tenant and referenced (never dispatched or
executed from this thread). Never work around an upstream or a consumer.

**D7 — All burn-down executes through each repository's factory.** The
2026-09-08 rollout hand-landed eight repositories through subagent
worktree→PR paths; the maintainer flagged it. Every burn-down item under this
plan is dispatched through the owning repository's factory
(`drive --action impl:<id>` / dispatcher), started with that repository's full
context.

**D8 — This plan supersedes `livespec-runtime-4s3` and the standing-owner
pattern.** The 2026-09-08 re-home (runtime `4s3`, dev-tooling `xx57`, console
`y9hc`, core `6fb1`, dolt-server `w6u`, overseer `hyfe`, driver-claude `axs`,
driver-codex `cea`, driver-pi `43a`, git-jsonl `bd-gj-6ps`, orch-beads
`bd-ib-heat`) stays as the LIVE OWNER of each row until that row has a real
test; each owner is closed when its rows reach zero, by the burn-down item
that emptied it. The runtime work-item 4s3 is superseded by the runtime
burn-down pointer under this plan.

**D9 — The exit gate is zero, fleet-wide, mechanically.** Every governed
repository's `tests/heading-coverage.json` has zero `TODO` rows; the ratchet
baseline is empty; the staged-diff scope lever and the free-text `reason`
slot are retired (a `TODO` at that point is simply forbidden); every standing
owner is closed. Archive only through the child-disposition gate and an
independent completeness review — a plan never archives itself on a status
flip.

## 5. What this plan owns vs. references

Owns (dev-tooling children of `0bse`): the ratchet (D3), the reason guard
(D4), the age bound (D5), the doctor rules and lever retirement (D9), the
proposed change that ratifies them, and dev-tooling's own 57-row burn-down.

References (pointer children `BLOCKED-ON <tenant> <id>`): the burn-down item
in each of the other ten repositories, filed in that tenant with `plan_ref`
and `upstream_work_item_id`. Status is read fresh from the ledgers, never
written into a file here.

## 6. Phases (proposed; the scope event cuts them)

- **P0 — Ratify.** `SPECIFICATION/proposed_changes/heading-coverage-convergence.md`
  → `revise`. Amends the v009 transitional-TODO clause with D3/D4/D5 and
  carries the doctor rules as scenarios (each with a real test — this plan
  eats its own rule).
- **P1 — Mechanism.** Land the ratchet, reason guard, age bound and doctor
  rules in dev-tooling with FAIL-CAPABILITY proof (a check that cannot
  convict is worse than none). The ratchet is non-breaking by construction:
  the baseline is exactly today's set, so no repository reds on merge. Cut a
  release; every consumer bumps.
- **P2 — Burn-down.** One item per repository, through that repository's
  factory, writing REAL tests until the ratchet register is empty for it;
  closing its standing owner as the last act. Pointer children here mirror
  each.
- **P3 — Retire.** With the register empty fleet-wide: remove the staged-diff
  scope lever and the free-text `reason` slot; `TODO` becomes forbidden
  outright; the per-commit tier fails on it.
- **P4 — Archive.** Child-disposition gate + independent completeness review.

## 7. Exit gate

D9, verbatim. Measured by a mechanical check (`snapshot`-style read of every
tenant's registry and ledger), never by reading.

## 8. Open questions for the scope event

1. Age bound value (D5): proposal is 30 days from first appearance; the
   maintainer sets it.
2. Whether livespec core's cross-family scenario-tier rule needs a matching
   amendment, or whether dev-tooling's amended clause is sufficient (the v009
   text says it "preserves every normative clause of the cross-family rule").
   A pointer to core is filed either way.
3. Sequencing of P2 against the concurrent dev-tooling and console drains
   (capacity, not design).

## 9. Retractions log

- *Retracted 2026-09-09:* "Make `TODO` un-mergeable at the per-commit tier."
  Would break both halves of D2 (spec-first placeholder; scope-to-authorship)
  and recreate the 3ztbdq unwritable-file condition. Replaced by D3.
- *Retracted 2026-09-09:* "Re-home rows to a live owner is the fix." It
  cleared orphan ownership only; every row remained `TODO`. Retained solely
  as the interim owner-of-record per D8.
- *Retracted 2026-09-09:* "A subset of headings is genuinely non-testable and
  needs a first-class non-test disposition." Rejected by the maintainer:
  everything is testable at some level with doubles; a heading with no
  behavior is a spec-structure defect, not a coverage exemption (D1).

## 10. Evidence trail

- `livespec-dev-tooling-d0er` — the liveness producer fix (PR #2018, 1.59.0).
- 2026-09-08 fleet survey (003) — 374 TODO rows, 3 owned-open, 267 unowned,
  63 closed-owner, 41 nonexistent-owner, before the re-home.
- `livespec-dev-tooling-3ztbdq` (2026-09-04) and commit `df946785`
  (2026-09-06) — the scope lever and its measured justification.
- Commit `66b3688d` (2026-06-02, epic li-cvtodo) — the severity lever that
  replaced a skip carve-out.
- `SPECIFICATION/history/v009/proposed_changes/scenario-tier-coverage-invariant.md`
  — the ratified transitional-TODO clause and its rationale.
- livespec core `.ai/ci-gate-discipline.md` — the red-with-no-commit argument.
- Runtime `tests/heading-coverage.json` blame: reason lines authored by
  `eab57b40` (Fabro, 2026-09-06), the "adjudicate heading entries" pass.

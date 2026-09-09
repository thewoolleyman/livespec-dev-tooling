---
topic: heading-coverage-convergence
author: claude-fable-5-1
created_at: 2026-09-09T02:10:00Z
---

## Proposal: A heading-coverage `TODO` is a transitional debt that MUST mechanically converge to zero; the `reason` field acknowledges an owed test and never exempts one

### Target specification files

- SPECIFICATION/non-functional-requirements.md (the scenario-tier coverage invariant ratified in v009; the "Release-gate targets" section)

### Summary

Amend the v009 clause *"A `TODO` entry is permitted during transition provided
its `reason` explicitly acknowledges this tier requirement"* so that the
transition has a mechanical end and the acknowledgment cannot be inverted into
an exemption. Four additions, none of which changes the two decisions the
clause already rests on (the spec-first transitional placeholder, and
judging a commit on what it authors rather than on inherited debt — the
staged-diff scope of `no_todo_registry`):

1. **A shrink-only baseline register** of `TODO` rows. A `TODO` row NOT in the
   register is a new cop-out and MUST fail the armed (authoring-time) tier;
   the register MAY only shrink; a commit that resolves a row MUST remove it
   from the register. Reaching empty is the terminal state.
2. **The `reason` MUST acknowledge an owed test and MUST NOT assert that no
   test is owed.** A reason asserting non-testability (in any wording) MUST be
   rejected. The only legal justification for a `TODO` is: a real test is owed
   at the required tier, and a LIVE work-item owns landing it.
3. **An age bound at the release tier.** A `TODO` older than the bound
   (measured from its first appearance) MUST fail the release tier. Liveness
   and age remain release-tier-only, so a per-commit verdict never depends on
   mutable external state.
4. **Retirement at zero.** Once the register is empty in a repository, that
   repository's staged-diff scope lever and free-text `reason` slot MUST be
   retired and a `TODO` row MUST fail the per-commit tier outright.

### Motivation

Plan `fleet-heading-coverage-convergence` (epic `livespec-dev-tooling-0bse`),
chartered 2026-09-09 after the fleet liveness-gate rollout
(`livespec-dev-tooling-d0er`) exposed 373 `TODO` rows across 11 repositories,
most resolved on 2026-09-06 into `TODO` + reasons of the form *"No
independently testable assertion at runtime"* instead of tests. The gate
accepted every one because owned-`TODO`-with-a-reason is its legal state.

The maintainer's ruling, verbatim: *"there should be absolutely no cop-outs.
The whole point of this is to ensure that every real scenario has a real
test. There is absolutely no reason that it should not be testable at some
level, even if mocking/doubles are used."* And: *"how do we mechanically
prevent these cop-outs?"*

Root cause (plan research 004): the placeholder state, the warn-only
per-commit tier, the ownership-only release tier, and the staged-diff scope
lever are each locally correct — the scope lever in particular exists because
whole-registry arming made the shared, mandatory co-edit registry unwritable
(`livespec-dev-tooling-3ztbdq`, 2026-09-04: 8 properly-owned entries refused
on all 66). What was missing was any mechanism that makes "during
transition" END, and any guard that keeps the `reason` an acknowledgment.
This proposal adds exactly those and nothing else. A per-commit ban on `TODO`
was considered and rejected: it would block spec ratification until every
test exists in the same commit and would recreate 3ztbdq.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, in the scenario-tier
coverage invariant, replace:

> A `TODO` entry is permitted during transition provided its `reason`
> explicitly acknowledges this tier requirement.

with:

> A `TODO` entry is permitted ONLY as a transitional debt, and the transition
> MUST mechanically converge:
>
> - Every `TODO` row MUST appear in the repository's shrink-only
>   heading-coverage debt register (`tests/heading-coverage-debt.json`, keyed
>   by `(spec_root, spec_file, heading)` with the owning `work_item` and the
>   row's first-seen date). A `TODO` row absent from the register is a new
>   cop-out and MUST fail the authoring-time armed tier. The register MAY only
>   shrink; a commit that resolves a row to a real test MUST remove it. The
>   register is generated mechanically from the live file at adoption, never
>   authored by hand.
> - The `reason` MUST acknowledge that a real test at the required tier is
>   owed and MUST name nothing else. A `reason` asserting that the heading is
>   not testable, is enforced elsewhere, or is prose without behavior MUST be
>   rejected by `heading_coverage`. There is no non-testable category: a
>   heading a repository believes has no behavior is a specification-structure
>   defect to be fixed in the specification, never a coverage exemption.
> - Every `TODO` MUST name a `work_item` that the configured tracker resolves
>   as live; a closed or nonexistent owner MUST fail the release tier (as
>   shipped in 1.59.0).
> - A `TODO` older than the repository's configured age bound (default 30
>   days from first-seen) MUST fail the release tier. Liveness and age are
>   evaluated ONLY at the release tier, so no per-commit verdict depends on
>   mutable external state.
> - Once a repository's register is empty, its staged-diff scope lever and
>   the free-text `reason` field MUST be retired and any `TODO` row MUST fail
>   the per-commit tier.

Add to the "Release-gate targets" section:

> `check-no-todo-registry` at the release tier additionally rejects a `TODO`
> past its age bound and a `TODO` whose `reason` does not acknowledge an owed
> test. `check-heading-coverage-debt-register` (new) rejects a `TODO` row not
> present in `tests/heading-coverage-debt.json` and rejects any growth of the
> register.

### Scenarios (each MUST have a real integration-tier test — this proposal eats its own rule)

- Scenario: a new `TODO` row not in the debt register fails the authoring-time armed tier
- Scenario: a `TODO` row present in the register passes the armed tier unrelated to the commit
- Scenario: a commit that resolves a `TODO` to a real test and removes it from the register passes; one that resolves it but leaves the register entry fails
- Scenario: a register that grows fails
- Scenario: a `TODO` whose `reason` asserts non-testability is rejected; one that acknowledges an owed test with a live owner passes
- Scenario: a `TODO` older than the age bound fails the release tier and passes the per-commit tier
- Scenario: with an empty register, a `TODO` row fails the per-commit tier
- Scenario: the register is generated mechanically from a fixture registry and matches byte-for-byte on regeneration

### impl_followup

id_hint: fleet-heading-coverage-convergence-mechanism — the four mechanism
children of `livespec-dev-tooling-0bse` (ratchet, reason guard, age bound,
doctor rules + lever retirement), each with fail-capability proof, landing
through this repository's factory.

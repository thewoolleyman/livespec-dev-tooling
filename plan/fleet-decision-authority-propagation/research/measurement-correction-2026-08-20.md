# Measurement correction — the offender set was nine, not seven

Addendum to `opening-research-2026-08-20.md`, written 2026-08-20 while
executing `sle7ey.1`. The opening note is left AS WRITTEN. It records the
measurement that was actually taken, and editing its tally in place would hide
the error rather than carry it.

Plan record discipline: the ledger is authoritative over this directory. The
scope amendment that acts on this finding is the plan-epic scope comment
timestamped `2026-08-20T18:40:00Z` on `livespec-dev-tooling-sle7ey`.

## What the opening note said, and what was actually true

The opening note tallied `HAS (3)` / `MISSING (7)` against the three markers.
That tally is correct under an **any-marker** reading — each of the three
"HAS" repos carries at least one marker. But the instrument this epic ratified
in `sle7ey.8` is an **all-three** presence test. Re-measured on `origin/master`
under that instrument on 2026-08-20:

    livespec                          marker 1 only   -> MISSING
    livespec-dev-tooling              markers 2,3     -> MISSING (see below)
    livespec-orchestrator-beads-fabro marker 2 only   -> MISSING
    the seven already on the list                     -> MISSING

Ten of ten. Not seven.

## Two of the ten failed for reasons that have nothing to do with the prose

`livespec-dev-tooling` carries the fullest decision-authority section in the
fleet — it wrote the guidance — and a literal byte-for-byte test scored it an
offender anyway. Both causes are incidental:

1. **Case.** Its heading is `## Decision authority — when to ask, proceed, or
   self-resolve`. The marker sits mid-sentence after a dash, so "when" is
   lowercase. Demanding a capital there is prose judgment by the back door: it
   forces awkward capitalization to satisfy a grep.
2. **Line wrapping.** Its ported-from citation wraps as
   `("When to ask,\nproceed, or self-resolve")`. The marker is plainly present
   to a reader and absent to a substring test.

So the instrument was amended along with the scope: match **case-folded**, with
**whitespace runs — newlines included — normalized to a single space**. Both
normalizations are pinned by their own test in
`tests/livespec_dev_tooling/fleet/test_rows_decision_authority.py`, so a later
tightening back to a literal match fails there rather than in the fleet.

Case-folding alone moves the count from 10 to 9. Normalization changes no
current member's verdict and is included anyway, because the wrap failure is
silent, already occurs in the fleet's own prose, and would otherwise fail an
adopting repo for its line width rather than its content.

## Why this was corrected in-thread rather than deferred

Two carriers were filed — `sle7ey.10` (livespec) and `sle7ey.11`
(livespec-orchestrator-beads-fabro) — and `sle7ey.9` now depends on both.

Deferring them to a follow-up thread would have made `sle7ey.9`'s
"measured offender count is zero" unreachable. The worse branch is that it
stays *apparently* reachable: seven children close, the count is never
re-measured, and the check is armed against a fleet where two members go red.
That is precisely the failure this epic already carries as precedent —
`46c5dab` armed the Railway check ahead of adoption, five repos went red,
`f4247110` reverted it.

## The lesson worth keeping

The opening note's own instruction — "Measure on `origin/master`, not the
working tree" — was followed and was not sufficient. The tally was taken with a
looser matcher than the one the epic ratified, and nothing reconciled the two
until an implementing session re-ran the ratified instrument.

**State the matcher next to the count.** A census is only as reproducible as
the predicate it counted with, and "three markers" named a set without naming
whether all three were required.

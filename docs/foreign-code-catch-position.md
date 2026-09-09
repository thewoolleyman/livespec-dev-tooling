# The foreign-code catch's position rule — mechanized here, unnarrated there

`check-no-except-outside-io` now enforces the clause that a foreign-code
isolation catch MUST wrap ONLY the foreign call. The rule it enforces lives in
another repository, and that repository's enforcement narration still files the
clause under review-enforced. This document carries the amendment that closes
the gap, in the form the factory branch boundary requires: a report for
maintainer-side landing, because a factory branch on `livespec-dev-tooling`
cannot write to `livespec`.

Filed under work-item `livespec-dev-tooling-u4xw`, carried forward from
`livespec-dev-tooling-x6t6` leg (b), which the 2026-07-26 maintainer ruling did
not dissolve.

## What was mechanized

The foreign-code isolation catch is the ONE broad catch permitted below a
process boundary. It is accounted per EXTENSION INVOCATION SURFACE, not per
entry artifact, so it is not reachable by any `main()`-boundary position rule —
and until this change nothing constrained WHERE it sat or WHAT it guarded. A
well-formed marker on a catch wrapping a large block of first-party code with
one foreign call somewhere inside it passed, re-labelling every bug in that
block as "the extension crashed".

Position is now DERIVED from the foreign call rather than granted to a tree:
`wraps_only_the_foreign_call` in
`livespec_dev_tooling/checks/_no_except_outside_io_markers.py` requires the
guarded block to be exactly one call statement. Nothing about the
`main()`-boundary exemption changed — widening that exemption to reach
foreign-code surfaces would be a position exemption inferred rather than
declared, which the 2026-07-26 ruling rejected.

**The live population was ZERO.** Measured before the fix shape was chosen
(work-item acceptance criterion 1): across the tracked `*.py` of this repo and
all nine sibling repos, 49 `# noqa: BLE001` markers, NOT ONE of them a
foreign-code isolation marker. The rule is armed against no existing site; it
exists so the FIRST real surface is judged rather than grandfathered.

## Why the spec side is a cross-repo deliverable

`livespec/SPECIFICATION/non-functional-requirements.md` is the authoritative
statement of the rule and of who enforces which part of it. Two of its
paragraphs currently say the wrap-only clause is review-enforced:

- §"ROP composition" — "What REMAINS review-enforced is … the requirement that
  each handler discharge its flavor's contract", which is where the
  foreign-code catch's three contract clauses (capture the traceback, surface
  the crash loudly, wrap only the foreign call) sit.
- §"Supervisor discipline" — "TWO rules remain enforced by REVIEW: … the
  requirement that each handler discharge its flavor's contract; mechanizing
  those is tracked as follow-up work and **MUST NOT be described as already
  enforced**."

That last clause is why this cannot be left implicit. The check now enforces
one of those contract clauses, so the spec's narration and the shipped check
disagree — the one outcome `u4xw` forbids. The repair is a spec edit, and
`livespec` is a different repository, so it lands maintainer-side exactly like
a dropped `.github/workflows/` diff.

## The amendment — for maintainer-side landing

Five sentence-level replacements in
`livespec/SPECIFICATION/non-functional-requirements.md`. That file stores each
paragraph as one very long line, so the replacements are given as text rather
than as a line diff; each `BEFORE` string was verified to occur EXACTLY ONCE in
the file at `livespec@806269c`, so the set applies mechanically.

### §"ROP composition" — the BROAD-catching bullet (three replacements)

**1 — the foreign-code catch's position is mechanized, by derivation.**

> BEFORE: The foreign-code-isolation broad catch sanctioned above sits OUTSIDE
> a `main()` boundary and is governed by its own clause (the foreign-code catch
> below), not by this `main()`-boundary marker gate.

> AFTER: The foreign-code-isolation broad catch sanctioned above sits OUTSIDE a
> `main()` boundary and is governed by its own clause (the foreign-code catch
> below), not by this `main()`-boundary marker gate; its POSITION is
> nonetheless MECHANIZED, DERIVED from the call it isolates rather than granted
> to a tree — `check-no-except-outside-io` requires the guarded block of a
> foreign-code-marked catch to be exactly one call statement
> (livespec-dev-tooling-u4xw). The `main()`-boundary position exemption is NOT
> widened to reach foreign-code surfaces.

**2 — carve the wrap-only clause out of the review-enforced set.**

> BEFORE: What REMAINS review-enforced is the pairing of each boundary with its
> correct marker flavor, and the requirement that each handler discharge its
> flavor's contract: a fail-open hook boundary carrying the supervisor wording,
> or a marked handler that does not do what its marker promises, both pass the
> check.

> AFTER: What REMAINS review-enforced is the pairing of each boundary with its
> correct marker flavor, and the requirement that each handler discharge its
> flavor's contract: a fail-open hook boundary carrying the supervisor wording,
> or a marked handler that does not do what its marker promises, both pass the
> check. ONE contract clause is carved OUT of that review-enforced set and is
> now MECHANIZED — the foreign-code catch's requirement to wrap ONLY the
> foreign call (livespec-dev-tooling-u4xw); the foreign-code catch's other
> clauses (capturing the full traceback into a typed bug-class domain error
> naming the foreign unit, and surfacing the crash loudly in the artifact's
> findings) stay review-enforced.

**3 — the clause itself, at the point it is stated.**

> BEFORE: and MUST wrap only the foreign call; this is the only broad catch
> permitted below a process boundary.

> AFTER: and MUST wrap only the foreign call — MECHANICALLY enforced by
> `check-no-except-outside-io`, which flags a foreign-code-marked catch whose
> guarded block is not exactly one call statement (livespec-dev-tooling-u4xw);
> this is the only broad catch permitted below a process boundary.

### §"Supervisor discipline" — the enforcement-split paragraph (two replacements)

**4 — what the check polices.**

> BEFORE: `check-no-except-outside-io` polices catch BREADTH and POSITION
> together — which trees are exempt, which `main()` direct-children are exempt,
> and whether a broad catch at a `main()` boundary carries one of the
> closed-set markers;

> AFTER: `check-no-except-outside-io` polices catch BREADTH and POSITION
> together — which trees are exempt, which `main()` direct-children are exempt,
> whether a broad catch at a `main()` boundary carries one of the closed-set
> markers, and whether a foreign-code-marked catch guards exactly one call
> statement;

**5 — the enforcement split itself.** This is the paragraph `u4xw`'s ACCEPTANCE
clause names.

> BEFORE: TWO rules remain enforced by REVIEW: the pairing of each boundary
> catch with its correct marker flavor, and the requirement that each handler
> discharge its flavor's contract; mechanizing those is tracked as follow-up
> work and MUST NOT be described as already enforced.

> AFTER: TWO rules remain enforced by REVIEW: the pairing of each boundary
> catch with its correct marker flavor, and the requirement that each handler
> discharge its flavor's contract — with ONE clause carved out of the second,
> the foreign-code catch's "wraps ONLY the foreign call" position requirement,
> which is MECHANIZED by `check-no-except-outside-io` as a guarded block of
> exactly one call statement, DERIVED from the foreign call rather than granted
> by any widened `main()`-boundary exemption (livespec-dev-tooling-u4xw).
> Mechanizing what remains is tracked as follow-up work and MUST NOT be
> described as already enforced.

## What the amendment deliberately does NOT say

It does not move the foreign-code catch's other two contract clauses. Capturing
the full traceback into a typed bug-class domain error naming the foreign unit,
and surfacing the crash loudly in the artifact's findings, are both still
review-enforced, and both are still covered by the "MUST NOT be described as
already enforced" instruction. Only the POSITION clause moves.

It also does not claim the derivation is exact. `wraps_only_the_foreign_call`
cannot know WHICH call in a statement is the foreign one — the marker names the
surface in prose, and no binding exists from that name to the call — so
`return wrap(_extension())` reads as one call statement and passes. That is a
known, deliberate approximation: it enforces the "only" half of the clause
(nothing else is in the block) and leaves the "which call is foreign" half with
the same review that already pairs a catch with its marker flavor.

## Until it lands

The two sides disagree, in the direction of the spec UNDERSTATING what is
enforced. That is the safe direction — a reader who believes the clause is
review-enforced and writes a conforming catch is still green — but it is not a
stable resting place: it is precisely the state `u4xw` was filed to end, and it
will read as unfinished work to the next agent that compares the two.
`livespec_dev_tooling/checks/no_except_outside_io.py`'s module docstring names
this document, so an implementer arriving from the check side finds the
outstanding half.

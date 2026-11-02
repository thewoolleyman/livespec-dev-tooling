# 003: audit every child of a top-3 plan, every tick

This note amends the charter (note 001) and note 002. Where they disagree, this note wins.

## The maintainer's correction (attended, 2026-11-02 ~01:5xZ, verbatim)

"why aren't you starting priority 3?" then "no i meant number 3 in your priority list , why is it held?" then
"unacceptable failuer.  write a mitigation into your plan"

It is recorded as a scope event on epic livespec-dev-tooling-6tgd2z (`maintainer-correction: top-3 stall missed`,
2026-11-02T01:56:11Z).

## What went wrong

Priority 3 is dev-host-test-gate-load (livespec-dev-tooling-6vuiwe). Its two main carriers sat at `pending-approval`
from 2026-11-01T21:30Z:

- livespec-dev-tooling-3buhph: the hand-commit pre-commit aggregate runs as a cluster Job;
- livespec-dev-tooling-qgv3tb: a seat's own full-suite gate-runner run goes to the cluster by default.

Each was held by a mechanical Definition-of-Done finding: its Scenario reference did not resolve. Spec v108 merged at
23:45Z (PR #3052) and added both headings, so the findings went stale, but nobody re-ran the check. Both also carry a
`blocks` edge on livespec-dev-tooling-sewnfp, the end of priority 4's chain.

The 01:44Z tick read the seat's pane, which was healthy and awaiting a third item (verj3y), plus the epic's status and
the items the handoff named. It reported priority 3 as "waiting". The maintainer had to find the stall.

## The rule

Every tick, for each owning plan of priorities 1-3:

1. Enumerate EVERY child from the ledger (`bd list --status all`, union of the dotted-id prefix and the parent edge).
2. Give each non-closed child a live hold reason: a `pending-approval` finding re-verified against `origin/master`
   (presumed stale if older than the latest spec revise); a `blocked` item's blocker and whether the edge is still real;
   a `ready` item's run or feeder ticket, else a stall; an `active` item's live run id; an `acceptance` item's proof leg.
3. Compare the plan's typed `next_action` with the audit. A plan awaiting one item while other children are held is a
   stall, and it goes to the owning seat at once.
4. A seat's report or a healthy pane is never evidence that its plan is moving.
5. DEPENDENCIES lists every non-closed child with its hold reason.

The same rule is in `.ai/coordinator-duties.md` §3, and the loop's tick prompt carries it.

# Triage batch 5 — the ROP railway cluster, 2026-09-08

**Status: PROPOSAL.** Per the batch-1 precedent, the closes and referrals below
are proposed and await the maintainer's ruling; nothing in this batch has been
closed or re-parented. What HAS been done unilaterally is the reading: all twelve
items are labelled `intake:triaged` and each carries its finding as a comment, so
a later pass does not re-derive them.

Session: `plan-session:dev-tooling-backlog-drain-2026-09-08-resume-0908g`.

## Position, measured against the frozen snapshot

Intersecting `research/002-snapshot-2026-09-06.json`'s 258 ids against the ledger:

| state | count |
|---|---:|
| closed | 113 |
| backlog | 127 |
| blocked | 12 |
| ready | 4 |
| active | 2 |

Untriaged open snapshot items: **119 before this batch, 107 after.**

> A correction this batch forced, recorded because three earlier ticks of this
> session reported it wrong. Position is **113/258, not 114**. The prior session
> handed off 111/258; this session closed exactly two snapshot items, `n4jm` and
> `675skf`. `37p0` was also closed and was the right call, but it is **not in the
> 258**, so it does not advance the count. Counting the snapshot instead of
> counting closes is the only reliable way to state this number.

## What this batch covers

The twelve `8o8e*` items — the ROP railway cluster. They are treated as one batch
because they share one owner and one blocking structure, not because they share a
subject.

**`8o8e` is the subject epic of `plan/rop-railway-enforcement`**, a plan that
lives in this repository. So this drive does not own their execution; it owns
only the question of what to do with them while that plan is unarchived.

## The finding: the epic splits in two, and the halves have opposite blockers

This is the batch's real output.

### The ARM half — this repo's own code, blocked by a standing constraint

`plan/rop-railway-enforcement` carries the constraint **"Do not arm the check
anywhere"**. It was earned: the Railway decoupling landed in `46c5dab`, turned
**five repos red**, and was reverted in `f4247110`. A check armed before the
repos it judges have adopted the shape is a check writing verdicts into a fleet
that cannot satisfy them. Adoption first, then arming.

Children `.30` and `.31` sit on this side and were already triaged before this
batch.

### The REMEDIATE half — seven other repos, not blocked by that constraint at all

This half **is** the adoption the constraint is waiting for. It is not blocked by
the arming rule; it is blocked by *where the code is*.

**The structural fact:** every dispatch from this plan runs with
`--repo /data/projects/livespec-dev-tooling`, and the sandbox clones that
repository and nothing else. A child whose offenders are in `livespec-overseer`'s
tree cannot be edited by a dev-tooling run. Readiness, acceptance criteria and
sizing are all beside the point — **the execution path cannot reach the code.**

This is the disposition batch 1 already reached for `ql1` ("review node lives in
the orchestrator tenant; referred there by comment").

#### Proposed: REFER six children to their own tenants

| child | target repo | measured state |
|---|---|---|
| `8o8e.7` | `livespec-overseer` | 213 raw / 112 distinct over universe 172 |
| `8o8e.8` | `livespec-orchestrator-beads-fabro` | 155 off the railway (universe 186), down from 166 via PR #1277 |
| `8o8e.10` | `livespec-runtime` | 11 off (universe 31); local lane complete, all 11 residual cross-repo-bound or entry points |
| `8o8e.11` | `livespec-orchestrator-git-jsonl` | 8 off (universe 49); twins close-gate satisfied |
| `8o8e.12` | `livespec` | 15 off (universe 132); 5 declarations + 10 conversions |
| `8o8e.13` | `livespec-driver-codex` | 1 off (universe 7) |

**The measurements should travel with the referral rather than be recomputed.**
They are unusually well established: freshly cloned at master, taken with the
shipped `_find_offenders` over `resolve_check_universe()`, positive-controlled
against dev-tooling's independently known count *before* being trusted, and
re-derived rather than inherited. Nothing in this triage disputes any figure.

#### Already finished, verified not assumed

`8o8e.9` (dev-tooling's **own** arming child, 1 off the railway) and `8o8e.14`
(`livespec-driver-claude`, 0 off the railway) are both **closed**. This repo's own
share of the remediation is done; what remains of the fleet half is entirely
other repos'.

## The other five — deferred to the owning plan, not re-derived

`8o8e.19`, `.26`, `.27`, `.28`, `.29` are part of the eleven (`.19`–`.29`) that
that plan's own `research/child-disposition-triage-2026-08-19.md` has **already
read and dispositioned**, with evidence beside each: 4 keep, 7 re-parent.

| child | that plan's recommendation |
|---|---|
| `.19` | KEEP — with `.28`, one defect seen from two sides |
| `.28` | KEEP — a function total by ratified contract, no reachable failure track |
| `.26` | RE-PARENT — fleet artifact drift, not the railway |
| `.27` | RE-PARENT — enforcement that does not enforce |
| `.29` | RE-PARENT — fleet artifact drift |

**This drive does not re-decide them.** That note says plainly that "the disposal
is the maintainer's call" and that it deliberately does not take it — it does the
part that can be done without taking it, so the decision is a review rather than
a re-derivation. That work is done and it is good; a second opinion here would
duplicate it and risk contradicting it.

Worth knowing when pricing the ruling: those eleven children are named in that
note as **the archive blocker** for `rop-railway-enforcement` — its gate refuses
while any child is undisposed. So **one ruling unblocks a whole plan's archive**,
and it is one ruling, not eleven.

## What this batch asks for

1. Ratify (or reject) the six referrals in the table above.
2. The `.19`–`.29` disposition ruling already requested by
   `plan/rop-railway-enforcement` — not a new question, restated here only
   because it blocks items inside this plan's snapshot too.

Neither is urgent in the sense of holding the factory: as of this batch the
factory is idle, the credential probe is `usable`, master CI is green, and **all
four ready snapshot items are held for reasons unrelated to this cluster.**

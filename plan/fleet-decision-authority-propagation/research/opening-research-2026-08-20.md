# fleet-decision-authority-propagation — opening research note, 2026-08-20

Plan record discipline: the ledger is authoritative over this directory; plan
state, next action, and handoffs live on the ledger anchor ledger anchor `livespec-dev-tooling-sle7ey`
read through the plan timeline.

> **SUPERSEDED IN TWO PLACES — read this first.** Both corrections were found
> after the fact and are recorded here rather than edited into the body, so the
> original errors stay visible.
>
> 1. **The tally below is wrong.** `HAS (3) / MISSING (7)` was counted with an
>    ANY-marker reading; the instrument this thread ratified requires ALL THREE.
>    Under the ratified instrument the offender set was NINE, and the two
>    carriers this note lists as HAS — `livespec` and
>    `livespec-orchestrator-beads-fabro` — were offenders. See
>    [`measurement-correction-2026-08-20.md`](measurement-correction-2026-08-20.md).
>    This matters more than a miscount: three separate censuses reached the
>    wrong number the same way, which is why the lesson recorded there is
>    *state the matcher next to the count*, not *count more carefully*.
> 2. **The child map below is inverted** relative to what was actually filed.
>    This note plans `.1` as the check and `.2`–`.8` as the adoptions; the
>    ledger filed `.1`–`.7` as the seven adoptions and `.8` as the check, with
>    `.10`/`.11` added by the scope amendment. The dependency prose that
>    follows ("`.2`-`.8` carry NO dependency on `.1`") is inverted the same
>    way; the shape that shipped is `.9` depending on `.1`–`.8` plus `.10`
>    and `.11`. The DEPENDENCY REASONING is unaffected and was honoured — the
>    adoptions did not serialise behind the check.

## Why this thread exists

The `decision-authority-guidance` thread (anchor `livespec-dev-tooling-ulem2v`,
now closed and archived) landed decision-authority guidance in THIS repo's
`AGENTS.md`. It did not reach the fleet, and it could not have: `AGENTS.md` is
authored per repo and nothing propagates it.

MEASURED 2026-08-20 against each member's `AGENTS.md`, markers `"When to ask,
proceed, or self-resolve"`, `"do not over-ask"`, `"Decision authority"`;
denominator is the 10 governed members of `.livespec-fleet-manifest.jsonc`:

    HAS (3):     livespec, livespec-dev-tooling, livespec-orchestrator-beads-fabro
    MISSING (7): livespec-overseer, livespec-console-beads-fabro, livespec-runtime,
                 livespec-orchestrator-git-jsonl, livespec-driver-claude,
                 livespec-driver-codex, livespec-driver-pi

`livespec-overseer-worktrees` and `livespec-overseer-wt` are worktree roots, not
governed members; they carry no `AGENTS.md` and are excluded from the denominator.

**Why this is not tidiness.** `livespec-overseer` is on the missing list, and it
is the repo whose foreman skill produced the 2026-08-20 fleet stall — roughly
sixteen hours of a track parked on a picker whose option 1 was its own recorded
next action, plus five self-decidable engineering calls escalated as standing
maintainer questions. Those sessions were reading an `AGENTS.md` that never told
them what they were allowed to decide.

## Ordering constraint — with its precedent, not just the rule

The check is armed ONLY after all seven are remediated, never before. The Railway
decoupling landed in `46c5dab`, turned FIVE repos red, and was reverted in
`f4247110`; `plan/rop-railway-enforcement/` carries the standing constraint "Do
not arm the check anywhere" for that reason. A check armed before the repos it
judges have adopted the shape writes verdicts into a fleet that cannot satisfy
them. Adoption first, then arming.

## Children — nine, membership by parent-child edge only

    .1  author the check, SHIPPED DISARMED, both-direction fixture controls
    .2  livespec-overseer            <- land this one first of the seven
    .3  livespec-console-beads-fabro
    .4  livespec-runtime
    .5  livespec-orchestrator-git-jsonl
    .6  livespec-driver-claude
    .7  livespec-driver-codex
    .8  livespec-driver-pi
    .9  arm the check; the arming commit states the measured offender count is zero

Ordering rides DEPENDENCY edges, never membership: `.9` depends on `.1`–`.8`.
`.2`–`.8` carry NO dependency on `.1` — that would serialise seven parallelisable
cross-repo PRs behind one item, and the measuring instrument is a three-marker
grep, not the check itself.

All nine are filed IN THIS TENANT with routing stated in the body. They are NOT
filed in sibling tenants: a cross-repo dependency edge fails closed and makes the
child permanently undispatchable.

Measure on `origin/master`, not the working tree — four of the seven clones were
behind their remote when this was drafted.

## Registration hazard, carried into the child bodies deliberately

`upsert_mapping` appends the full row (epic included) only when NO `(repo, topic)`
row matches. If a row exists it updates a narrow field set and leaves `epic`
untouched — `_DEFAULT_UPSERT_UPDATE_FIELDS` is `frozenset({"tmux"})` on v1.3.0.
A second call to "fix" the epic on an existing row is therefore a SILENT NO-OP.

The recovery path is `set_epic`, which is a plain ALIAS of `record_derived_epic`
(`_registry_store.py:181`) — one function, not two options. It returns a bool and
no-ops when no row matches, so a `False` return is AMBIGUOUS across three cases:
the epic already equals the target, no row matched, or the row failed validation
and was warned-and-skipped rather than raising. **Reading the row back is the only
discriminator between a successful set and a silent miss.**

## Provenance

Scope, measurement, ordering constraint and the registration hazard were drafted
by the `livespec-dev-tooling-grooming` session and are reproduced here. That
session also recorded the routing observation that produced this thread: four
surfaces declined the write — its own gate-and-stop directive, the overseer
seat's tenant registration, another worker's scope, and the foreman contract's
bar on plan-file writes — each locally correct, summing to unstarted authorized
work. The lesson it drew is the one to keep: **choose the executor for write
authority up front rather than offering the work around a ring of seats scoped
for other things.**

## Out of scope (explicit deferrals)

- The pin fan-out itself. This thread lands the check and the seven adoptions;
  the fan-out puts the check in front of members afterwards.
- `rewrite_mapping`, unexamined; nothing here needs it.

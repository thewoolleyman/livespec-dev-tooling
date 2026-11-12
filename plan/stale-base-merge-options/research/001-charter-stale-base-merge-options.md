## The maintainer's statement of what done means

Anyways, yes, I want you to start a plan that investigates the impact of up-to-date branches and other options, such as implementing manual merge queues or third-party tools. I know I've already discussed this many times. There's already some prior discussion and art on this. That plan should start by looking for it and summarizing it.

## Definition of Done assertions derived from that statement

- A research note under plan/stale-base-merge-options/research/ summarizes every earlier fleet discussion and decision on up-to-date branches, merge queues, merge trains and stale-base semantic conflicts, quoting the maintainer verbatim where the words were recorded.
- A research note states the impact of requiring branches to be up to date before merge, in CI runs and runner-minutes per merge burst, computed from the fleet's measured merge cadence with every measurement named.
- A research note compares a self-built merge queue, the third-party merge-queue tools usable from a personal GitHub account, and the red-master-self-healing baseline on cost, merge latency and behaviour while master is red.
- The maintainer's chosen direction among the presented options is recorded on the plan epic in the maintainer's own words.

## Status of this note

This is the charter of plan `stale-base-merge-options`, written 2026-11-12 ~19:0xZ by the plan seat (tab
stale-base-merge-options) on the direction of legacy-coordinator-agent (livespec-dev-tooling-6tgd2z, session 959b2f8b),
which opened the plan on the maintainer's direction at 2026-11-12 ~18:1xZ.

- The plan is MAINTAINER-DRIVEN (coordinator-duties §9). The seat brings options with measured costs and ONE
  recommendation. The maintainer decides the direction. Nothing is implemented before that decision.
- The Definition of Done assertions above were DERIVED BY THE SESSION from the maintainer's scope statement. The
  maintainer has not confirmed them. The first handoff records them as session-derived.
- The seat never raises a blocking picker. Questions for the maintainer go as plain text in the seat's pane and
  through the coordinator.

## Founding scope event

The maintainer, 2026-11-12 ~18:1xZ, to legacy-coordinator-agent, verbatim:

"Anyways, yes, I want you to start a plan that investigates the impact of up-to-date branches and other options, such
as implementing manual merge queues or third-party tools. I know I've already discussed this many times. There's already
some prior discussion and art on this. That plan should start by looking for it and summarizing it."

## Context that opened the plan

On 2026-11-12, `b9838b28c` (merged 16:09Z) and `4793883d8` (merged 15:32Z) were each green on their own base and
together reddened livespec-dev-tooling master. Master stayed red until the roll-forward livespec-dev-tooling#4357 merged
at 17:40:49Z, and several factory runs failed on the red master meanwhile. That is the stale-base semantic-conflict
failure mode the fleet's branch protection accepts by keeping `strict` off.

## Constraint known at founding

GitHub's own merge queue is UNAVAILABLE: the fleet's repositories are on a personal account, not a team or Enterprise
organization (the maintainer, coordinator epic scope events 2026-11-12T01:56Z and ~18:0xZ). It is listed only to
exclude it.

Facts recorded beside that exclusion, not as a recommendation:
- GitHub documents the merge queue as available to PUBLIC repositories owned by an ORGANIZATION; only private
  organization repositories need Enterprise Cloud. All 10 fleet repositories are public.
- Moving them into an organization costs re-registered plugin marketplaces, a new org-owned App, re-registered ARC
  runners, re-projected secrets and a new GHCR namespace.

Note 004 measures these. The maintainer's direction since then is recorded as scope events on the epic.

## Work order

1. **Prior art** (research note 002). Find and summarize every earlier discussion and decision, with the maintainer's
   words verbatim where recorded: livespec spec v126 and its `merge-gate-drop-strict` proposals, livespec
   `SPECIFICATION/non-functional-requirements.md` §"CI as a merge gate (branch protection)", plan
   `red-master-self-healing` (epic livespec-dev-tooling-zcp5vb) and its 2026-10-14 rulings, livespec-overseer
   overseer-tdfe.22, the coordinator epic's scope events, the enforcement code (`branch_protection_alignment`,
   `fleet/_reconcile.py`, `fleet/_rows_github.py`), today's incident, and `--status all` ledger scans of the
   dev-tooling, livespec, orchestrator and overseer tenants.
2. **Investigation** (measured, every measurement named — rule NO-UNMEASURED-CAPACITY-CLAIM):
   (a) the impact of requiring branches up to date, from the fleet's real merge cadence;
   (b) a self-built merge queue (a serializer, or a rebase-and-recheck bot);
   (c) third-party tools (Mergify, Aviator, Trunk, Graphite, Kodiak, bors-ng and any others) for a personal account
   with ARC self-hosted runners and the existing auto-enable-merge workflow;
   (d) the decided baseline, red-master-self-healing: distance to shipping and what it would have cost today.
3. **Options and one recommendation** to the maintainer, in plain words. The maintainer decides.

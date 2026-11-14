## The maintainer's statement of what done means

"Okay, but I see you have like eight other panes open here.  I need a single place that manages all my attention for all those other pains in the track of work.  It should be similar to the legacy coordinator plan in that it has a loop when it restarts and prints out the headline metric every time it loops (to keep us both laser-focused on improving the metric). It should manage all of the other subplans.  Got it.?"

"The goal of the overall track will be to move ONE METRIC: THROUGHPUT AS MEASURED IN PRS PER REPO PER HOUR MERGED TO MAIN BRANCH AND PASSING AS GREEN."

"This is going to be a priority track, third after the expideted incident and hetzner move tracks."

## Definition of Done assertions derived from that statement

- A session resuming this plan starts its coordinator loop in the same turn, without asking, and every tick of that loop prints the headline table of pull requests merged green per hour per repository beside the 7-day baseline.
- Every tick reads every seat in herdr workspace throughput-improvements on hetzner-xubuntu, unblocks any seat that is stopped on a picker or a refusal it can resolve, and reports each track plan's owner, next action and what changed since the last tick.
- Every ask that is the maintainer's, from any plan on the track, appears in this seat's tick report under FOR THE MAINTAINER with its plan slug and tab, so the maintainer reads one pane for the whole track.
- The fleet's 7-day rate of pull requests merged green per hour stands above the 9.64 per hour baseline of 2026-11-13, with each lever plan's measured contribution recorded, when the maintainer retires this plan.

# Charter — throughput-plans-coordinator

Opened 2026-11-14 by plan throughput-track-organization (livespec-dev-tooling-q26e3c) at the maintainer's direction (first statement above). The assertions are SESSION-DERIVED; confirm or re-word them with the maintainer at the first attended tick. The fourth is a guess at what "done" means for a standing role and most needs his word.

## The role

ONE seat for the maintainer's attention across the throughput track. It is to this track what legacy-coordinator-agent is to the fleet: it DIRECTS and never does the work itself, has no implementation children, never blocks, never raises a picker, and routes unowned work to an owning plan. Read `.ai/coordinator-duties.md` in full at every resume and apply it within the track. legacy-coordinator-agent (livespec-dev-tooling-6tgd2z, on vmi3006760) stays the fleet coordinator: this seat reports to it by a comment on this plan's epic prefixed `TO COORDINATOR:`, takes its rulings across plans, and never reorders the maintainer's priorities record. The track is priority three, after the expedited-incident and hetzner-move tracks.

## Resuming: straight into the loop

A resume of this plan starts the coordinator `/loop` with no interval IN THE SAME TURN. The epic's pointer is written as kind `none` because no executable kind means "run the loop"; it never holds the loop, and the seat never asks whether to start it.

## The tick, in this order

1. **HEADLINE METRIC, printed verbatim every tick.** Run from `~/workspace/livespec-dev-tooling`:
   `/usr/local/bin/with-livespec-env.sh -- python3 ~/.local/share/pr-throughput/headline.py`
   It prints pull requests merged green per hour per repository for the last 6 h and 24 h beside the 7-day baseline, the change against baseline, and the 24 h count merged but not green. It costs two Honeycomb queries (the MCP key's budget is about 100 an hour, shared). If the newest event in dataset `pr-throughput` is older than 30 minutes, say so above the table and tell throughput-metric: a stale table is worse than none.
2. **Seats.** `herdr agent list` on hetzner-xubuntu, workspace throughput-improvements; read each seat's pane; a seat reading `blocked`, or idle with an executable next action, is unblocked or prompted this tick. Seats are prompted with `herdr agent prompt <name-or-pane> "<text>"`.
3. **Levers.** For each row of the track table: owner, carrier state, next action, what changed since the last tick, and its measured effect on the metric where one exists.
4. **In flight.** Open PRs of the track's plans, named as `repository#N`, and anything waiting on a spec ratification or the dispatcher.
5. **FOR THE MAINTAINER (non-blocking).** Every ask from any track seat that is genuinely his, each with plan slug (epic id) and tab, re-verified as still open this tick.

## The track's plans and their tabs (2026-11-14 ~01:0xZ)

Workspace throughput-improvements on hetzner-xubuntu: throughput-metric (the emitter, the panel and, for now, the stopgap feed), kubernetes-observability (deliverer of the emitter), ci-runtime-and-cost, stale-base-merge-options, factory-run-yield, sandbox-commit-gate-follow-ups, implement-test-performance, gate-job-resources, github-request-budget-discipline. Elsewhere: fleet-mutation-testing-rule-26 (a Codex seat on gamingpc-xubuntu, by the maintainer's ruling), fleet-flaky-tests (workspace livespec-dev-tooling on hetzner-xubuntu; one row only).

The ranked lever table, the baseline, what was moved out of the track, and the maintainer's rulings are in throughput-track-organization's research notes 003, 005 and 006 (under `plan/archive/throughput-track-organization/` once that plan archives). Note 006's table is this seat's starting state.

## Known conditions

- A `bd` call from hetzner-xubuntu takes about 18 s (the Dolt server is on vmi3006760, 207 ms away): batch ledger reads, and prefer reading panes to reading epics.
- The metric feed is a session-bound stopgap until livespec-dev-tooling-gaetnq converges; throughput-metric owns it.
- The maintainer ruled on 2026-11-13 that the fleet moves to a GitHub organization and GitHub's merge queue will be usable; stale-base-merge-options carries it.

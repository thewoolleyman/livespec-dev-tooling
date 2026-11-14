## The maintainer's statement of what done means

"Okay, but I see you have like eight other panes open here.  I need a single place that manages all my attention for all those other pains in the track of work.  It should be similar to the legacy coordinator plan in that it has a loop when it restarts and prints out the headline metric every time it loops (to keep us both laser-focused on improving the metric). It should manage all of the other subplans.  Got it.?"

"The goal of the overall track will be to move ONE METRIC: THROUGHPUT AS MEASURED IN PRS PER REPO PER HOUR MERGED TO MAIN BRANCH AND PASSING AS GREEN."

"This is going to be a priority track, third after the expideted incident and hetzner move tracks."

His later words on the metric, the boards, messaging and the incident, said in this seat's pane (workspace throughput-improvements) unless noted:

(2026-11-13 ~22:1xZ, throughput-track-organization note 002) "...Reported as a table of each repo and its throughput, and with a corresponding honeycomb item for me to monitor real-time as the first item on the existing livespec board"

(2026-11-14 ~01:4xZ) "Every tick should print the link to the honeycomb board with the throughput targets and also print it in your table. That was in my initial definition of the goal for this plan."

(2026-11-14 ~01:5xZ) "The metrics should exclude docs-only MRs, because they don't show true throughput slowness. Just non-docs PRs is what I want."

(2026-11-14 ~02:0xZ) "Okay, go with those metrics. Add them to your tick. And I also want all of these moved to a new dedicated honeycomb board, which is just all of these throughput charts, but split out into multiple ones so they are nice and readable and give good eyeball visibility into the progress and improvement we're making."

(2026-11-14 ~02:1xZ) "Also, stacking multiple repos on the same chart is a bad idea because they have different build times. That kills the ability to eyeball progress or regression of throughput on a single repo."

(2026-11-14 ~02:4xZ) "Targets are not set, the numbers should keep trending down with each improvement contributing a real and measured improvement, when confounding factors or noise is discounted (where possible). If numbers go up, then the root causes should be investigated and plans added or reprioritize3d"

(2026-11-14 ~02:5xZ) "WHY THE FUCK ARE SESSIONS TYPING IN YOUR PANE! THEY SHOULD USE SENDMESSAGE ON THE SAME HOST!" and "FIX ALL OF THEIR PLANS AND REPO GUIDANCE TO FORBID THAT, AS THE MAIN LEGACY COORDINATOR ALREADY DOES"

(2026-11-14 ~05:3xZ) "Okay, yes, go ahead and capture the incident retro and add to your plans whatever is necessary to prevent this sort of thing in the future."

## Definition of Done assertions derived from that statement

- A session resuming this plan starts its coordinator loop in the same turn, without asking, and every tick of that loop prints the headline table of pull requests merged green per hour per repository beside the 7-day baseline, with the link to the real-time Honeycomb board https://ui.honeycomb.io/thewoolleyweb/environments/livespec/board/krThv8DvcwS/livespec-family-all-activity and to the dedicated throughput board https://ui.honeycomb.io/thewoolleyweb/environments/livespec/board/ytZuuVuT4BQ (one repository per chart, non-docs and non-release PRs), both printed above the table and as rows of it, beside lead time (M2, median and p90 from first commit or dispatch to merged green) and its stage split (M3).
- Every tick reads every seat in herdr workspace throughput-improvements on hetzner-xubuntu, unblocks any seat that is stopped on a picker or a refusal it can resolve, and reports each track plan's owner, next action and what changed since the last tick.
- Every ask that is the maintainer's, from any plan on the track, appears in this seat's tick report under FOR THE MAINTAINER with its plan slug and tab, so the maintainer reads one pane for the whole track.
- No numeric targets are set (maintainer, 2026-11-14). The metrics keep improving, M1 throughput up and M2 lead time, M3 stage times and merged-NOT-green down, and each lever plan's improvement is recorded as a real, measured contribution, net of noise and confounding factors where they can be discounted. Every measured regression is root-caused, and its cause is routed to a new or reprioritized plan, until the maintainer retires this plan.

# Charter — throughput-plans-coordinator

Opened 2026-11-14 by plan throughput-track-organization (livespec-dev-tooling-q26e3c) at the maintainer's direction (first statement above). The assertions were first SESSION-DERIVED; they now read as the epic's Definition of Done, and the fourth carries the maintainer's 2026-11-14 ruling that no numeric targets are set.

## The role

ONE seat for the maintainer's attention across the throughput track. It is to this track what legacy-coordinator-agent is to the fleet: it DIRECTS and never does the work itself, has no implementation children, never blocks, never raises a picker, and routes unowned work to an owning plan. Read `.ai/coordinator-duties.md` in full at every resume and apply it within the track. legacy-coordinator-agent (livespec-dev-tooling-6tgd2z, on vmi3006760) stays the fleet coordinator: this seat reports to it by a comment on this plan's epic prefixed `TO COORDINATOR:`, takes its rulings across plans, and never reorders the maintainer's priorities record. The track is priority three, after the expedited-incident and hetzner-move tracks.

## Resuming: straight into the loop

A resume of this plan starts the coordinator `/loop` with no interval IN THE SAME TURN. The epic's pointer is written as kind `none` because no executable kind means "run the loop"; it never holds the loop, and the seat never asks whether to start it.

## The tick, in this order

1. **HEADLINE METRIC, printed verbatim every tick.** Print both board links ABOVE the table:
   - family board (real-time): https://ui.honeycomb.io/thewoolleyweb/environments/livespec/board/krThv8DvcwS/livespec-family-all-activity
   - throughput board (one repository per chart): https://ui.honeycomb.io/thewoolleyweb/environments/livespec/board/ytZuuVuT4BQ

   Then run from `~/workspace/livespec-dev-tooling`:
   `/usr/local/bin/with-livespec-env.sh -- python3 ~/.local/share/pr-throughput/headline.py`
   Its output ends with the same two links. Every metric counts NON-DOCS, NON-RELEASE PRs: a docs-only PR is one whose every changed file ends in `.md`, and release-please PRs are excluded.
   - **M1** is pull requests merged green per hour per repository, against the frozen 7-day floor, with docs-only, release and merged-NOT-green columns, a noise band, and the not-green classes.
   - **M2** is lead time, p50 and p90, to merged green. It runs from the first commit's authored time for a seat PR (stamped before the first commit gate), or from the run marker within 6 h before the first commit for a factory PR.
   - **M3** is the stage medians.
   - Below them: the start→open stall list (over 72 h), and the AWAITING MASTER VERDICT block.

   There are NO targets: the metrics must keep improving. Any repository outside its noise band in the bad direction, or with a merge over 60 min awaiting a master verdict, gets a root-cause read routed to an owning plan THAT tick. The table costs Honeycomb queries against the MCP key's shared budget of about 100 an hour. If the newest event in dataset `pr-throughput` is older than 30 minutes, say so above the table and tell throughput-metric: a stale table is worse than none.
2. **Seats.** `herdr agent list` on hetzner-xubuntu, workspace throughput-improvements; read each seat's pane; a seat reading `blocked`, or idle with an executable next action, is unblocked or prompted this tick. Seats are reached ONLY with the SendMessage tool (ListAgents, then the session name), NEVER by typing into a pane: no `herdr agent prompt`, `herdr pane send-text`, `herdr pane run` or `tmux send-keys`, per `.ai/distributed-sendmessage-protocol.md`. A seat on another machine with no Remote Control row gets a ledger comment on its plan epic instead.
3. **Levers.** For each row of the track table: owner, carrier state, next action, what changed since the last tick, and its measured effect on the metric where one exists.
4. **In flight.** Open PRs of the track's plans, named as `repository#N`, and anything waiting on a spec ratification or the dispatcher.
5. **FOR THE MAINTAINER (non-blocking).** Every ask from any track seat that is genuinely his, each with plan slug (epic id) and tab, re-verified as still open this tick.

## Standing rules from the 2026-11-14 incident

The fleet CI pool stall of 2026-11-13/14 is retold, with its causes and its guards G1-G7 and their owners, in `research/002-incident-retro-2026-11-14-ci-pool-stall.md`. This seat changed two things in itself:

- Every tick treats an AWAITING MASTER VERDICT line over 60 min as a stop-the-line read that same tick, and routes it.
- Every capacity ruling this seat makes carries a measured revert trigger and a +2 h CI-side read.

It also tracks G1-G7 to closure as inherited waits.

## The track's plans and their tabs (2026-11-14 ~01:0xZ)

Workspace throughput-improvements on hetzner-xubuntu: throughput-metric (the emitter, the panel and, for now, the stopgap feed), kubernetes-observability (deliverer of the emitter), ci-runtime-and-cost, stale-base-merge-options, factory-run-yield, sandbox-commit-gate-follow-ups, implement-test-performance, gate-job-resources, github-request-budget-discipline. Elsewhere: fleet-mutation-testing-rule-26 (a Codex seat on gamingpc-xubuntu, by the maintainer's ruling), fleet-flaky-tests (workspace livespec-dev-tooling on hetzner-xubuntu; one row only).

The ranked lever table, the baseline, what was moved out of the track, and the maintainer's rulings are in throughput-track-organization's research notes 003, 005 and 006 (under `plan/archive/throughput-track-organization/` once that plan archives). Note 006's table is this seat's starting state.

## Known conditions

- A `bd` call from hetzner-xubuntu takes about 18 s (the Dolt server is on vmi3006760, 207 ms away): batch ledger reads, and prefer reading panes to reading epics.
- The metric feed is a session-bound stopgap until livespec-dev-tooling-gaetnq converges; throughput-metric owns it.
- The maintainer ruled on 2026-11-13 that the fleet moves to a GitHub organization and GitHub's merge queue will be usable; stale-base-merge-options carries it.

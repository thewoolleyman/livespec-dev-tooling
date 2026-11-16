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

0. **Notices first.** Before anything else, read the comments posted since the last tick on BOTH this plan's epic (livespec-dev-tooling-r7iuj6) AND legacy-coordinator-agent's epic (livespec-dev-tooling-6tgd2z), and act on every FROM COORDINATOR, MERGE-QUIET, QUIET OFF, FINAL HANDOFF and FROM legacy-dispatcher-agent notice. legacy-coordinator-agent posts fleet notices on its own epic, so reading only this epic misses them. While a merge-quiet window is on, no seat or helper of this track readies, arms, merges or reruns a PR in that repository, and a grade relay says "stays draft until QUIET OFF". After QUIET OFF, held PRs are released in waves, so the pool the fix freed is not flooded at once. Every `gh pr ready` is followed by `gh pr view N --json autoMergeRequest`; when ready did not arm, the PR is armed with `gh pr merge N --auto --rebase`.
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

   There are NO targets: the metrics must keep improving. Any repository outside its noise band in the bad direction, or OVER its per-repository AWAITING MASTER VERDICT threshold (min(180, max(60, 2 x master-cycle p50 + 30)) min), or with unrun merges, gets a root-cause read routed to an owning plan THAT tick. The table costs Honeycomb queries against the MCP key's shared budget of about 100 an hour. If the newest event in dataset `pr-throughput` is older than 30 minutes, say so above the table and tell throughput-metric: a stale table is worse than none.
1b. **Nodes, enumerated from the cluster.** Every tick, list the nodes from the cluster itself, never from a fixed list: `ssh cwoolley@poweredge-xubuntu sudo -n k3s kubectl get nodes -o wide` and `ssh cwoolley@poweredge-xubuntu sudo -n k3s kubectl top nodes`. `scripts/coordinator/fleet-utilization.sh` hard-coded three nodes, so gamingpc-xubuntu and macbook-m4-max-homelab-worker were invisible after they joined.
   - For each node, print CPU in use, its taints, and which workload classes run there (factory, ARC CI, gate Jobs).
   - A node idle while another is saturated is routed THAT tick to the plan that owns cluster placement and node enrollment. This seat directs; it does not carry placement itself.
   - A newly joined node is not "enrolled" until it appears in the capacity reads.
1c. **FACTORY-GREEN-WATCH.** Every tick prints, per repository the factory serves, the time of the last GREEN factory run and the runs since it (from the dispatch records, or failing those the drive journal). A repository with no factory green for 2 h while work is launchable, or with every run since a change failing before its first node, is a STOP-THE-LINE incident that tick (a filed incident record per INCIDENT-IS-A-RECORD), routed to the owner of the failing layer. Until a headline or top5 line carries it (deferred to throughput-metric and legacy-coordinator-agent), this seat reads it by hand.
2. **Seats.** `herdr agent list` on hetzner-xubuntu, workspace throughput-improvements; read each seat's pane; a seat reading `blocked`, or idle with an executable next action, is unblocked or prompted this tick. Seats are reached with the SendMessage tool (ListAgents, then the session name) when it reaches them and the content is a message, and by typing into their pane (`herdr pane send-text`, `herdr pane send-keys`, `herdr pane run`) whenever that is faster or necessary, slash commands such as `/model` included: check the pane is idle, keep it short, send Enter separately. This seat never stalls a seat it could type into (maintainer ruling 2026-11-16, scope event "RULE PANE-TYPING-ALLOWED" on epic livespec-dev-tooling-6tgd2z; rule PANE-TYPING-ALLOWED in `.ai/coordinator-duties.md` §3, superseding the earlier SendMessage-only wording here). A seat no live channel reaches gets a ledger comment on its plan epic.
3. **Levers.** For each row of the track table: owner, carrier state, next action, what changed since the last tick, and its measured effect on the metric where one exists.
3b. **Shortcut watch.** Read every open row of the shortcut register (`research/003-shortcut-register-2026-11-15.md`): report each row's bite signal and measured saving, route any bite this tick, and add a row for any new shortcut the tick it is taken. Never carry a seat's claim that "the maintainer set this rule" without his words on the ledger.
4. **In flight.** Open PRs of the track's plans, named as `repository#N`, and anything waiting on a spec ratification or the dispatcher.
5. **FOR THE MAINTAINER (non-blocking).** Every ask from any track seat that is genuinely his, each with plan slug (epic id) and tab, re-verified as still open this tick.

Standing rules every tick applies (2026-11-15 evening; origins and the maintainer's words in the section of that name below):

- **INCIDENT-FIRST.** Every tick asks whether a real breakage is stopping work flowing through the factory or ecosystem; if one is, it is an incident by default and goes through the expedited flow, and a broken incident path is repaired first.
- **No-prompt helper briefs.** Every helper or reviewer brief says: shell logic goes in a scratchpad script written with Write and run with `bash <file>`; no `rm`; no `bash -c` one-liners.
- **GO-NAMES-THE-ROUTE.** No GO, incident step or plan step goes out until this seat has read the committed route on a fetched origin/master and names it (path@sha) in the GO; no route means BUILD work, routed that tick.
- **CRITICAL-PATH-CHILD-AUDIT.** Every tick enumerates every non-closed item behind the critical path with a live hold reason; a `ready` item with no run behind it while the factory is held is a STALL, ruled that tick.
- **INCIDENT-DECLARATION-ROUTES.** Every incident declaration lists, per step, its owner, its committed route (path@sha) or `BUILD: <item>`, and its revert trigger.
- **FETCH-FIRST.** Every grade, fleet-scope claim or code read uses a fetched origin ref.
- **INCIDENT-IS-A-RECORD.** An incident exists only once `incident_authority.py file-incident` has filed its item(s), in the same tick as the decision, and the declaration names the item id(s).
- **REPAIR-COMMITS-ON-THE-LANE.** Every repair commit after the filing goes through the expedited lane; work already inside a running gate finishes there.
- **TEST-THE-CIRCULARITY.** A claim that the incident lane cannot be used names WHICH half is broken (local fast hooks, or CI-side incident-ci and observer reach), and only that half is routed around.
- **FACTORY-GREEN-WATCH.** Step 1c: last factory green per repository, every tick.
- **COMMITTED-IS-NOT-CONVERGED.** A committed host or credential route is not live until its converge on the reader has been read back.
- **Grep the readers before a setting change.** Before changing any repo setting, grep the checks that read it.

## Standing rules from the 2026-11-14 incident

The fleet CI pool stall of 2026-11-13/14 is retold, with its causes and its guards G1-G8 and their owners, in `research/002-incident-retro-2026-11-14-ci-pool-stall.md`. This seat changed two things in itself:

- Every tick treats an AWAITING MASTER VERDICT line over its per-repository threshold as a stop-the-line read that same tick, and routes it.
- Every capacity ruling this seat makes carries a measured revert trigger and a +2 h CI-side read.
- Every tick starts by reading BOTH this epic and legacy-coordinator-agent's epic (step 0). Added after this seat missed the 07:03Z QUIET OFF, posted only on livespec-dev-tooling-6tgd2z, and earlier told seats to `gh pr ready` during the window, which auto-arms in livespec-dev-tooling.
- A grader's brief for an alarm or trigger PR checks the platform's limits (a Honeycomb trigger's frequency against its time range) and the bound of any exclusion; legacy-coordinator-agent caught both on #4650 and #4599 where this seat's graders had not.

It also tracks G1-G8 to closure as inherited waits; G3 is withdrawn.

## Standing rule from 2026-11-15

- Every tick reads every cluster node (step 1b). Measured at 07:50Z: poweredge 85%, hp 51%, M4 28% (tainted, homelab-worker class), gmktec 15%, gamingpc 5% (untainted), while this seat's tick read no nodes at all. The maintainer: "You need to understand the cluster."

## Standing rules from 2026-11-15 evening

Each rule below is recorded on this plan's epic (livespec-dev-tooling-r7iuj6) as a scope event or handoff entry; the quotes are copied verbatim from those entries. Times are `date -u`.

### INCIDENT-FIRST (scope event 18:17Z)

The maintainer, ~18:2xZ, in this seat:

> "Record this guidance to leverage the incident recovery process as much as we can right now, knowing that it is incomplete. The goal is to get the stale-base-merge-options plan done, and that is a tool we have to get it done. Record this in your plan directive as continuing guidance: you should always consider using the incident flow when it will help move things along and when there is actually a breakage that is stopping work from flowing through the factory and ecosystem. And record this in your loop and anywhere else that will help you remember it."

- Every tick asks "is a real breakage stopping work flowing through the factory or ecosystem?" (a red master, an exhausted credential or rate budget, a held factory, a jammed queue). If yes, it is an INCIDENT by default, and the expedited incident flow (EXPEDITED_INCIDENT_RESPONSE / _REVERT, `docs/incident-execution.md`) is used wherever it moves work faster, even though the flow is incomplete today.
- When the incident path itself is broken, repairing the path is the FIRST incident action, driven out of order under OVERRIDE-THEN-BACKFILL, never waited out behind the normal lane.
- Never rule out the incident flow by the origin of the work ("planned plan work") or by "the tool is broken"; judge by impact and ask what makes it work. Never invent a restriction on it without the maintainer's words. This seat's ~16:5xZ "no incident" ruling and its ~18:1xZ "it is for broken masters, not planned work" claim were wrong by this rule.

### The no-prompt helper-brief clause (handoff 18:19Z)

Every helper or reviewer brief carries it: shell logic goes in a scratchpad script written with the Write tool and run with `bash <file>`; no `rm`; no `bash -c` one-liners. The maintainer: "DO NOT DOO STUFF LIKE THIS!!!"

### GO-NAMES-THE-ROUTE, CRITICAL-PATH-CHILD-AUDIT, INCIDENT-DECLARATION-ROUTES, FETCH-FIRST (scope event 19:14Z)

The maintainer, ~19:2xZ, in this seat, after incident xyi5vu step 3 was sent GO at 19:0xZ with no committed route on master (its credential projection, livespec-dev-tooling-h5r75q, sat ready and unbuilt from 16:32Z under hold-gmktec; about 3 h of avoidable wait, at least 1 h of it on the critical path):

> "How are you going to prevent this sort of failure going forward"

- **GO-NAMES-THE-ROUTE**: no GO, incident step or plan step goes out until this seat has read, on a FETCHED origin/master, the committed file, recipe or playbook the step runs, and names it (path@sha) in the GO. "X re-registered" or "Y flipped" is not a route. When the route does not exist, the step is BUILD WORK, routed that same tick.
- **CRITICAL-PATH-CHILD-AUDIT** (`.ai/coordinator-duties.md` §3, applied to the track): every tick enumerates EVERY non-closed item behind the critical path (the incident item, its carriers, the top plan's children), each with a live hold reason. A `ready` item with no run behind it while the factory is held (hold-gmktec, or any repo hold) is a STALL, ruled THAT tick: hand-land under coordinator-duties §5 (a wedged factory route is a reason to hand-land), held off the factory by status blocked plus a hold-item file. A mechanical READY-UNDER-HOLD flag in `scripts/coordinator/top5` or `fleet-utilization.sh` is deferred to legacy-coordinator-agent, which owns those scripts; until it ships this rule carries it by hand.
- **INCIDENT-DECLARATION-ROUTES**: every incident declaration this seat writes lists, per step, its owner, its committed route (path@sha) or "BUILD: <item>", and its revert trigger. A step with no route is never written as an act.
- **FETCH-FIRST** (already coordinator-duties §10): every grade, fleet-scope claim or code read uses a fetched origin ref. This seat broke it at 18:5xZ with a stale livespec-runtime clone.

### INCIDENT-IS-A-RECORD, REPAIR-COMMITS-ON-THE-LANE, TEST-THE-CIRCULARITY (scope event 19:24Z)

The maintainer, ~19:3xZ, in this seat, after the 18:18Z incident had been declared in comments only, with no incident item until 19:3xZ, so for an hour every repair commit ran the full aggregate and normal ordering:

> "So you're saying I told you to run this as an incident, and you told me you would, and then you actually just fucking didn't do it?"

- **INCIDENT-IS-A-RECORD**: an incident is declared ONLY by `incident_authority.py file-incident` (one item per repair branch and PR), in the same tick as the decision, and the declaration comment names the incident item id(s). A comment saying INCIDENT without an item id is not an incident. This seat never says "running as an incident" until the item exists.
- **REPAIR-COMMITS-ON-THE-LANE**: every repair commit after the filing goes through the expedited lane (genesis, the wrapper-form commit with the Factory-Override trailer, the fast checks only, deferred obligations recorded). Work already inside a running gate finishes there, and the chain is used if that gate refuses or dies.
- **TEST-THE-CIRCULARITY**: a claim that the incident lane cannot be used is checked by naming WHICH half is broken (the local fast hooks, or the CI-side incident-ci and observer reach), and only that half is routed around.

### FACTORY-GREEN-WATCH, COMMITTED-IS-NOT-CONVERGED (scope event 19:50Z)

The maintainer, ~19:5xZ, in this seat:

> "Are you even running anything through the factory rather than building everything locally?"

Measured: no livespec-ai factory run had gone green since the org cutover (~10:xxZ). petri's vault lacked ORG_GITHUB_APP_ID because the committed route 133614d79 (10:19Z) was never converged on gmktec-xubuntu; a canary found it only at 19:43Z. This seat's headline counts merged PRs, not factory greens, so a dead factory read as nothing.

- **FACTORY-GREEN-WATCH**: tick step 1c.
- **COMMITTED-IS-NOT-CONVERGED**: a committed host or credential route is not live until its converge on the reader has been read back (CLAUDE.md "confirm the reader before you write"). After an org cutover or credential change, every tick reads back the consumers on the critical path until each is read back once.

### Lesson: grep the checks that read a setting before changing it (CORRECTION, 19:57Z)

At 19:45:45Z this seat set ruleset 26758787's merge_queue `max_entries_to_build` from 4 to 1 as an interim for incident livespec-dev-tooling-zq2i4c. That broke check-branch-protection-alignment (`merge_queue_concurrency_below_floor`, floor 2), and every livespec-dev-tooling commit gate was refused for about 10 minutes, mzbt35's commit-1 included. legacy-coordinator-agent restored it to 2 (read back 19:56:35Z). LESSON: before changing any repo setting, grep the checks that read it (here check-branch-protection-alignment / `_branch_protection_queue_rules.py`). No maintainer words are recorded for this lesson; it is this seat's own correction.

## The track's plans and their tabs (2026-11-14 ~01:0xZ)

Workspace throughput-improvements on hetzner-xubuntu: throughput-metric (the emitter, the panel and, for now, the stopgap feed), kubernetes-observability (deliverer of the emitter), ci-runtime-and-cost, stale-base-merge-options, factory-run-yield, sandbox-commit-gate-follow-ups, implement-test-performance, gate-job-resources, github-request-budget-discipline. Elsewhere: fleet-mutation-testing-rule-26 (a Codex seat on gamingpc-xubuntu, by the maintainer's ruling), fleet-flaky-tests (workspace livespec-dev-tooling on hetzner-xubuntu; one row only).

The ranked lever table, the baseline, what was moved out of the track, and the maintainer's rulings are in throughput-track-organization's research notes 003, 005 and 006 (under `plan/archive/throughput-track-organization/` once that plan archives). Note 006's table is this seat's starting state.

## Known conditions

- A `bd` call from hetzner-xubuntu takes about 18 s (the Dolt server is on vmi3006760, 207 ms away): batch ledger reads, and prefer reading panes to reading epics.
- The metric feed is a session-bound stopgap until livespec-dev-tooling-gaetnq converges; throughput-metric owns it.
- The maintainer ruled on 2026-11-13 that the fleet moves to a GitHub organization and GitHub's merge queue will be usable; stale-base-merge-options carries it.

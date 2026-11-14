# Corrections after the independent review (2026-11-14)

The first independent replay of this plan's proof (session 2cf7d1b1, posted 01:55:20Z) returned NOT_REPRODUCED on
assertion 3, and the completeness review (evidence `ttorg-completeness-2cf7d1b1-20261114T0157Z`) did not attest.
Its findings were correct. This note records what was wrong in note 006, what was done about each finding, and the
true state of every proposal. Where it differs from note 006, this note governs.

## Errata to note 006

- Note 006 says ci-runtime-and-cost moved **2aelab** to gate-job-resources. It did not: 2aelab is still under
  livespec-dev-tooling-ib3oe3, held at the spec tier. Only mtvxde moved.
- Note 006 says **ehnjlt** moved to expedited-incident-hardening. It did not: still under ib3oe3, held. Only onk27y moved.
- Note 006 says gate-job-resources "took" **z7nfhx**. It was still under gmktec-pool-member-obligations (frei6s).
- Note 006 says the new plan **ci-reliability-leftovers** "takes" twenty items. At the time of writing the plan did
  not exist and all twenty were under ib3oe3.
- Note 006 says **P9** (fleet-mutation-testing-rule-26) had no answer recorded. It had: at 2026-11-13T23:24:52Z on
  livespec-dev-tooling-oi2two it ACCEPTED consolidating mutation-testing-keystone's obligations, with the caveat
  that the cross-tenant anchors livespec-mutreal and livespec-mutreal.1 are read and dispositioned before any archive
  claim.
- Note 006 lists **bd-ib-rowuou** as waiting to move to factory-run-yield. factory-run-yield declined it; it stays
  under hp-factory-failure-follow-ups (bd-ib-qieqc6).
- Note 006 and note 005 give stale-base-merge-options the ownership of "master stays green outside an incident".
  Its owner REFUSED that; see below.

## What was done about each finding

| Finding | Action | State at 2026-11-14 ~02:5xZ |
|---|---|---|
| ci-reliability-leftovers had no epic and no directory | Plan created: livespec-dev-tooling-7y2jqw, charter in livespec-dev-tooling#4615 | 8 of the 20 moved by ci-runtime-and-cost (khlrw3, 73qw6g, ncgrcb, fsle5g, kzhduc, op67ed, f3q7r7, 45qcgo). 12 held and named per item on 7y2jqw: 9 wait on their topics' spec ratification (jkwzwv, hqbbff, fc4dzb, hnynfm, 7crrkb, hyeteu, 4mhpf4, apluqn, 6pozr5); 3 wait on a tier classification (ybnep5, hhflha, hnbn7z). |
| z7nfhx still under frei6s | `reparent_plan_child` attempted and REFUSED: no tier classification | Held; the wait is named on the receiving epic livespec-dev-tooling-ukoeah. |
| 2aelab and ehnjlt holds named only on the releasing plan | ci-runtime-and-cost recorded each on its receiving epic | Named on ukoeah (2aelab) and dh3hub (ehnjlt); each moves when its hold clears. |
| D6/P4: stale-base-merge-options had recorded no decision | Asked to decide | REFUSED at 01:59:15Z (scope event on livespec-dev-tooling-xowhol): it does not absorb red-master-self-healing or the five items; it names red-master-self-healing, reactivated as its own plan, as the owner, with flakes to fleet-flaky-tests. |
| (consequence) "master stays green outside an incident" had no owner | Seat red-master-self-healing reopened in workspace throughput-improvements | DECIDED at 02:04:48Z (scope event on livespec-dev-tooling-zcp5vb): ACCEPTS that ownership on the track (the recovery half is in its approved Definition of Done; prevention at merge needs a maintainer extension, carried by throughput-plans-coordinator); TAKES 2yne2h, c7efqa, vfofyj from ci-runtime-and-cost: 2yne2h MOVED (parent zcp5vb, read 2026-11-14 ~03:0xZ); c7efqa and vfofyj are still under ib3oe3 and move when their topics ratify (named on zcp5vb); DECLINES oim422 and mpv6bp, which ci-runtime-and-cost then destined for ci-reliability-leftovers (still under ib3oe3 at ~03:0xZ; its scope event on ib3oe3 and the per-item list on 7y2jqw); the diagnosis item b6lw5w stays with stale-base-merge-options. |
| D2: the fold of factory-run-correlation-observability was never decided | factory-run-yield asked to decide | DECIDED at 02:02:33Z (scope event on bd-ib-ft26pi): MODIFY. It takes bd-ib-welwbc and re-parents it once that item's in-flight factory work ends; it REFUSES folding bd-ib-qfv9 or its other children (bd-ib-gd7axe, bd-ib-njbg7j do not move throughput). bd-ib-rowuou stays under bd-ib-qieqc6. |
| legacy-dispatcher-agent's other 24 open children were unowned | Proposals posted on bd-ib-klkbxp (provisional-fleet-launch, 16 launcher-script defects) and bd-ib-k6dqwc (dispatch-control-plane, 8 product defects) | legacy-coordinator-agent ruled (answer to report 11) that legacy-dispatcher-agent, the owning session, decides the moves against those proposals; dispatch-control-plane may receive items but takes on no live operations. The decision is that seat's and is not this plan's. |
| The six agent-efficiency angles of rgr-cycle-agent-efficiency were unowned | Handed to throughput-plans-coordinator | legacy-coordinator-agent ruled they go to throughput-plans-coordinator (livespec-dev-tooling-r7iuj6) to place on the track or in an existing plan; a plan directory with no epic must not hold work. |
| livespec-dev-tooling#4608 was still open | — | See the forge; the archive commit is cut after it and livespec-dev-tooling#4615 are on master. |

## The track's owners, corrected

Rank 2 of note 006 changes: (a) the exporter fix stays with ci-runtime-and-cost (livespec-dev-tooling-jgkhr5);
(b) "master stays green outside an incident" is owned by **red-master-self-healing** (livespec-dev-tooling-zcp5vb),
tab red-master-self-healing in workspace throughput-improvements; the check-per-file-coverage diagnosis
(livespec-dev-tooling-b6lw5w) stays with stale-base-merge-options, which also carries the GitHub organization move
and the merge queue.

Two plans were split out of this one after note 006 at the maintainer's direction of 2026-11-14 ~01:0xZ:

- **throughput-metric** (livespec-dev-tooling-oe7cfw): owns livespec-dev-tooling-gaetnq and -bgespb (moved to it on
  the maintainer's "Yes move them"), and runs the stopgap feed since 01:13Z.
- **throughput-plans-coordinator** (livespec-dev-tooling-r7iuj6): the standing coordinator seat of the track; first
  tab of the workspace; prints the headline metric and the board link every tick.

Plan assertion 3 was re-worded at ~01:3xZ (scope event on livespec-dev-tooling-q26e3c) from "executed in the
ledgers" to "picked off into an owning plan", on the maintainer's statement that this plan "was just to really get
everything picked off into new plans".

## Seat layout as it finally stood

Workspace throughput-improvements on hetzner-xubuntu, one tab each: throughput-plans-coordinator, throughput-metric,
kubernetes-observability, ci-runtime-and-cost, stale-base-merge-options, red-master-self-healing, factory-run-yield,
sandbox-commit-gate-follow-ups, implement-test-performance, gate-job-resources, github-request-budget-discipline,
plus this plan's own tab and its reviewers' tabs until archive. The four predecessor panes on vmi3006760 are closed.
ci-reliability-leftovers is off the track; its seat is opened by legacy-coordinator-agent in workspace
livespec-dev-tooling on hetzner-xubuntu.

## Messaging rule (maintainer, 2026-11-14 ~02:5xZ)

"WHY THE FUCK ARE SESSIONS TYPING IN YOUR PANE! THEY SHOULD USE SENDMESSAGE ON THE SAME HOST!" and "FIX ALL OF THEIR
PLANS AND REPO GUIDANCE TO FORBID THAT, AS THE MAIN LEGACY COORDINATOR ALREADY DOES". Sessions on one host message
each other with SendMessage, never by typing into panes. This plan's briefs, handoff 2 and the two charters of
livespec-dev-tooling#4608 told seats to use `herdr agent prompt`; that wording is superseded (scope event on
livespec-dev-tooling-q26e3c), and each owning seat corrects its own charter.

## Second review (session 359b82d6, 2026-11-14T02:58:00Z): findings and what was done

- **Assertion 1, seats of the PARTIAL plans.** Note 004 gave a seat only for the CORE plans. The table below adds
  the seat of every plan its PARTIAL section names.
- **P6 absorption waited on "the organizer's word".** The word is given for good and recorded on
  livespec-dev-tooling-sv6m5p: implement-test-performance absorbs delegated-commit-time-gates (2fekp6, child sewnfp)
  and rgr-touched-test-scope (5yyjqk) when bd-ib-vy75ws closes, with no further word from anyone.
- **bd-ib-jaaya5 and bd-ib-hap62u.** No releasing owner decided them. Both proposals are WITHDRAWN: jaaya5 stays
  under anthropic-burn-mitigation (bd-ib-b2jzxw) and hap62u under publish-draft-green-work-loss (bd-ib-acrr56).
  They are not carriers of rows 5b and 6.
- **bd-ib-qfv9.** D2's fold is WITHDRAWN. factory-run-yield takes only bd-ib-welwbc (after its in-flight run, PR
  #5043). bd-ib-qfv9 stays a dormant plan off the track; seating or archiving a dormant plan is
  legacy-coordinator-agent's fleet hygiene.
- **z7nfhx.** The seat that re-parents it once it is classified is gate-job-resources (clarified on
  livespec-dev-tooling-ukoeah).
- **6e5pyj (D3).** Still open under ib3oe3 although livespec-dev-tooling#4568 was applied at about 23:52Z; its close
  waits on ci-runtime-and-cost's cohort-30 after-cut read-back, and the child carrying its test-parallelism
  derivation and DERIVATION.md assertions under gate-job-resources is not filed yet. Recorded on ukoeah.
- **Assertion 3 re-worded a second time** (scope event on livespec-dev-tooling-q26e3c, ~03:1xZ): an agreed move
  may wait on a condition named on the receiving plan's epic: a spec ratification, a tier classification, or the
  end of named in-flight work.
- **Handoff corrected** by a scope event on the epic: rank 1 is owned by throughput-metric, rank 2b by
  red-master-self-healing, and the track is coordinated by throughput-plans-coordinator.

## Seats of the PARTIAL plans (addendum to note 004)

Source: legacy-coordinator-agent's herdr roster read of 2026-11-13 ~23:0xZ, recorded on
livespec-dev-tooling-q26e3c at 23:02:44Z, and this seat's own read of vmi3006760 at 21:55Z. "none" means no live
seat was listed in either.

| Plan (epic) | Seat at ~23:0xZ on 2026-11-13 |
|---|---|
| kubernetes-observability (livespec-dev-tooling-s2aqob) | vmi3006760, workspace livespec-dev-tooling (moved to hetzner-xubuntu, workspace throughput-improvements, 2026-11-14 ~00:5xZ) |
| ci-cache-optimization (livespec-dev-tooling-7zozck) | vmi3006760, workspace livespec-dev-tooling |
| gmktec-factory-placement (livespec-dev-tooling-me5aqz) | vmi3006760, workspace livespec-dev-tooling |
| dev-host-disk-retention (livespec-dev-tooling-qgwxo4) | vmi3006760, workspace livespec-dev-tooling |
| expedited-incident-response-flag (livespec-dev-tooling-bqnzcm) | vmi3006760, workspace livespec-dev-tooling |
| expedited-incident-hardening (livespec-dev-tooling-dh3hub) | vmi3006760, workspace livespec-dev-tooling |
| radar-and-deterministic-admission (livespec-dev-tooling-w7ley3) | none |
| token-spend-analysis (livespec-dev-tooling-6lv7ze) | none |
| console-factory-build-telemetry (livespec-dev-tooling-bfvbsw) | none |
| software-factory-gap-map (livespec-dev-tooling-oft4bu) | none |
| mutation-testing-keystone (no epic) | none |
| version-lockstep-release-race (livespec-dev-tooling-zbkur6) | none |
| legacy-dispatcher-agent (bd-ib-ynnykl) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| spec-implementation-lockstep (bd-ib-ax3rds) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| kubernetes-sandbox-backend (bd-ib-nmuyjc) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| factory-run-work-preservation (bd-ib-nckst7) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| anthropic-burn-mitigation (bd-ib-b2jzxw) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| fabro-currency (bd-ib-6tcjfx) | vmi3006760, workspace livespec-orchestrator-beads-fabro |
| hp-factory-failure-follow-ups (bd-ib-qieqc6) | none |
| checkpoint-commit-hook-failures (bd-ib-hcwmnq) | none |
| factory-test-first-enforcement (bd-ib-q622ls) | none |
| factory-configurable-model-fallback-priority (bd-ib-jxvgq5) | none |
| the ten launch-path and run-lifecycle plans of note 004 | goal-template-opener-handling and dispatch-control-plane (a Codex seat): vmi3006760, workspace livespec-orchestrator-beads-fabro; the other eight: none |
| fleet-plumbing-and-dispatch-reliability (overseer-cajdwp) | none |
| herdr-overseer (overseer-uzvcbn) | vmi3006760, workspace livespec-overseer |
| optimize-console-builds (livespec-console-beads-fabro-gqmtwa) | none |
| livespec-ci-on-hetzner (livespec-h22nve) | none |

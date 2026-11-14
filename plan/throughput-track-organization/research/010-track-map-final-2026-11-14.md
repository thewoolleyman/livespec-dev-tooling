# Track map, final corrections (2026-11-14)

The sixth independent review (session 82d9b007, 2026-11-14T11:25:22Z) reproduced assertions 1, 3 and 4 and failed
2 and 5. This note closes its findings B1 to B4 and B7; B5 and B6 are closed in the ledger (the acknowledgement
asked of publish-draft-green-work-loss, and a restated track summary scope event on livespec-dev-tooling-q26e3c).
Where this note differs from notes 005 to 009, it governs.

## What "exactly one owner" covers

The report's items and levers are the keys Y1 to Y5, C1 to C4, N1 to N3, M1 to M5 and the eight levers of the
report, plus G1 and the one metric, which the coordinator and the maintainer added. Each has one owning plan in
the table at the end of this note. The key X of `data/report-item-keys.md` is NOT a report item: it is this
plan's own catch-all for other things that limit merged-green PRs. Each X sub-item is dispositioned below; most
are off the track and stay with the plans that already hold them.

Three rows that read as two owners are two levers each, restated:

- **Red master** is two levers: 2a, a failed telemetry export must not redden a green master run
  (ci-runtime-and-cost, livespec-dev-tooling-jgkhr5), and 2b, master stays green outside an incident
  (red-master-self-healing, livespec-dev-tooling-zcp5vb).
- **C1** has one owner, ci-runtime-and-cost, for the design and the PR-CI and master legs; 5a and 5b are legs that
  implement-test-performance and sandbox-commit-gate-follow-ups deliver to that design.
- **C4** (implement-turn and per-commit gate duration) has ONE owner: sandbox-commit-gate-follow-ups
  (bd-ib-3goerg), because the measured cost is the factory implement turn (34 min median, Honeycomb query
  ihFcBg3UADc) and its per-commit gates. The host-gate share is delivered through row 5a and is not a second
  owner of C4.

## X sub-items

| X sub-item | Disposition |
|---|---|
| red master | on the track, rows 2a and 2b (above) |
| flaky tests | on the track, row 11, fleet-flaky-tests (livespec-dev-tooling-zwveqp) |
| merge holds and auto-merge | OFF the track. The `merge-hold:on` label and its release are legacy-coordinator-agent's (`.ai/fabro-dispatch-diagnosis.md`). Three open orchestrator items touch it and have NO parent plan: bd-ib-3bbdrh (pending-approval), bd-ib-crgpkk (blocked), bd-ib-rz2vhj (ready). This plan does not home them; throughput-plans-coordinator (livespec-dev-tooling-r7iuj6) holds them as a routing question for legacy-coordinator-agent, with dispatch-control-plane and legacy-dispatcher-agent's successors as the candidate homes. Measured on this plan's own PRs: `gh pr merge --auto` left three PRs un-armed and one armed PR sat CLEAN and unmerged (note 008 and report 14); that observation goes with the routing question. |
| credential and quota outages | OFF the track. No single owner is named: caam-quota-resets, central-credential-service, caam-generic-limit-windows and llm-provider-manager in livespec-overseer each keep their own work. No measurement ties them to the metric. |
| dispatcher idle with ready work | OFF the track: factory-idle-with-ready-work (note 009) |
| healthy run cancelled | OFF the track: stall-watchdog-false-kills (note 009) |
| launch-path reliability | OFF the track: legacy-dispatcher-agent decides its 24 items against the proposals on bd-ib-klkbxp and bd-ib-k6dqwc (note 007) |
| ledger latency from hetzner-xubuntu | OFF the track: bootstrap-credentials-and-onboarding (row 12 of note 006) |

## The one CORE plan still without a disposition

**livespec-ci-on-hetzner (livespec-h22nve)**, classed CORE for N2 by its charter: OFF the track. It was last worked
on 2026-08-11 and is contradicted by the live hetzner plan (below, B3 overlap 5): hetzner-xubuntu is a workstation,
not a CI runner. It has no seat. Whether it is archived is legacy-coordinator-agent's fleet hygiene. Capacity for
gates and the factory (N2) is owned on the track by gate-job-resources.

## Six more overlaps the data records name

| # | Overlap | Resolution |
|---|---|---|
| O7 | livespec-dev-tooling-hatvwq (gmktec-pool-member-obligations) against -e2gv6n and -n622ze (ci-cache-optimization); the record calls these the closest to true duplicates | Not consolidated by this track. gate-job-resources REFUSED hatvwq under P7 (it is cache-tier work, not capacity allocation). All three are off the track; ci-cache-optimization is the plan whose purpose this is, and the fleet coordinator is asked to put hatvwq to its seat as a duplicate. |
| O8 | livespec-dev-tooling-reuqym (gate-job-resources) against -zbu7jf (ci-cache-optimization): both change the gate Job's fetch source | Not consolidated. reuqym stays in gate-job-resources (on the track, row 8); zbu7jf stays in ci-cache-optimization (off it). gate-job-resources' seat is asked, through the track coordinator, to say which lands first so the second is written against it. |
| O9 | livespec-dev-tooling-5ua57h (ci-runtime-and-cost) against rop-railway-enforcement's livespec-dev-tooling-8o8e.23: the CI telemetry exporter exists in four versions | 5ua57h is the track's item (the exporter is ci-runtime-and-cost's, rows 2a and 5). 8o8e.23 stays in rop-railway-enforcement, off the track; ci-runtime-and-cost's seat is asked to say whether 5ua57h supersedes it. |
| O10 | livespec-dev-tooling-227glz against -vrpwyw, both in ci-runtime-and-cost: each replaces a zero-job ghost run | Same plan, same owner. ci-runtime-and-cost KEPT both (its P3 decision of 2026-11-13T22:55:07Z) without merging them; it is asked to merge them or say how they differ. No cross-plan resolution is needed. |
| O11 | livespec-ci-on-hetzner (livespec-h22nve) against bootstrap-credentials-and-onboarding (hxi-vxsmdv): two contradictory plans for the Hetzner machine | Resolved in favour of the live one: bootstrap-credentials-and-onboarding. livespec-ci-on-hetzner is stale and off the track (above). |
| O12 | overseer-fs4 (fleet-plumbing-and-dispatch-reliability, dormant) against bd-ib-2h6cfl: consumer and producer of the failure category | Not a duplicate: producer and consumer. bd-ib-2h6cfl is the track's item (factory-run-yield, row 4). overseer-fs4 stays where it is, off the track, and is unblocked when 2h6cfl lands. |

## Two inconsistencies between this plan's own notes, settled

- **publish-draft-green-work-loss (bd-ib-acrr56).** Note 005's "What is deliberately NOT on this track" lists it;
  that line is RETRACTED in part. The plan is ON the track for two things only: row 6b (Y3: bd-ib-qf5dau,
  bd-ib-zzhy5t, bd-ib-rriwjr, bd-ib-64n5ct) and one row-6 carrier, bd-ib-hap62u. Its work-recovery remainder
  stays off the track. Its seat stays on vmi3006760, workspace livespec-orchestrator-beads-fabro; it has no tab
  in workspace throughput-improvements.
- **bd-ib-hap62u.** The scope event of 2026-11-14T03:02:55Z said row 6 excludes it, because this plan had
  withdrawn its proposal. Its owner then decided at ~03:39Z to KEEP it and deliver it as a row-6 carrier in
  place. The owner's decision governs: hap62u IS a row-6 carrier, held by publish-draft-green-work-loss.

## Seats not in workspace throughput-improvements, stated in one place

fleet-mutation-testing-rule-26 (rank 9): a Codex seat on gamingpc-xubuntu, by the maintainer's ruling.
fleet-flaky-tests (rank 11): hetzner-xubuntu, workspace livespec-dev-tooling; it joins the track for one row.
publish-draft-green-work-loss (rows 6b and one carrier of 6): vmi3006760, workspace
livespec-orchestrator-beads-fabro. Every other plan with a row has a tab in throughput-improvements.

## Every report item and its one owner (supersedes note 009's table)

| Item | Owner | Row |
|---|---|---|
| the one metric and its panel (M5) | throughput-metric (livespec-dev-tooling-oe7cfw) | 1 |
| a failed telemetry export reddens master | ci-runtime-and-cost (livespec-dev-tooling-ib3oe3) | 2a |
| master stays green outside an incident | red-master-self-healing (livespec-dev-tooling-zcp5vb) | 2b |
| Y1, report lever 1: unprovable assertions | factory-run-yield (bd-ib-ft26pi) | 3 |
| M1, M2, report lever 7: failures countable, factory CPU attribution | factory-run-yield | 4 |
| C1, M4, report lever 5: full suite once per change; PR-side CI measurement | ci-runtime-and-cost | 5 (legs 5a, 5b, 5c) |
| C4: implement-turn and per-commit gate duration | sandbox-commit-gate-follow-ups (bd-ib-3goerg) | 5b |
| Y2, Y4, Y5, report lever 4: timeouts, in-run gate failures, open-Red re-entry | sandbox-commit-gate-follow-ups | 6 |
| Y3: stale-base rebase conflicts in factory runs | publish-draft-green-work-loss (bd-ib-acrr56) | 6b |
| C2, M3, report lever 2: gate verdict reuse; gate durations | implement-test-performance (livespec-dev-tooling-sv6m5p) | 7 |
| N1, N2, report levers 3 and 8: capacity to gates and the factory; gamingpc | gate-job-resources (livespec-dev-tooling-ukoeah) | 8 |
| C3, report lever 6: shrink the suite | fleet-mutation-testing-rule-26 (livespec-dev-tooling-oi2two) | 9 |
| G1: GitHub REST budget | github-request-budget-discipline (livespec-httc) | 10 |
| withheld flake retries | fleet-flaky-tests (livespec-dev-tooling-zwveqp) | 11 |
| N3: vmi3006760 pressure; ledger latency | off the track: bootstrap-credentials-and-onboarding (hxi-vxsmdv) | 12 |

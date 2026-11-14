# Track map completed: every report item, every CORE plan and every named overlap (2026-11-14)

The fifth independent review (session 5bcd63ac, 2026-11-14T10:03:35Z) reproduced assertions 1, 3, 4 and 5 and
failed assertion 2: checked against this plan's own inventory records, the track map (notes 005 to 008) left one
report item without a single owner, never mentioned four plans the records class CORE, and gave no resolution for
six overlaps the records name. This note closes each. It is an addendum to note 005 and moves no item: every
disposition below either names the plan that already holds the work, or says the work is off the track and where
it stays.

## Y3: rebase conflicts from a stale base, in factory runs

**One owner on the track: publish-draft-green-work-loss (bd-ib-acrr56)**, row 6b, beside the row-6 carrier it
already keeps (bd-ib-hap62u, its decision of 2026-11-14 ~03:39Z). Carriers, all already its children:
bd-ib-qf5dau, bd-ib-zzhy5t, bd-ib-rriwjr, bd-ib-64n5ct. Every one of them repairs or survives a stale base
after it happens; none prevents it. Its seat is on vmi3006760, workspace livespec-orchestrator-beads-fabro, and
stays there; throughput-plans-coordinator watches the row.

Not owners of Y3, and why:

- stale-base-merge-options (livespec-dev-tooling-xowhol) owns PREVENTION for merged PRs (the organization move
  and the merge queue). A queue does not stop a factory run's branch going stale while the run is in flight, so
  it is not the owner of this failure class.
- sandbox-commit-gate-follow-ups' bd-ib-mfl2qa, bd-ib-prualo and bd-ib-hmed6n concern the commit and settle
  steps when a rebase is in progress; they stay in that plan under row 6.
- factory-run-work-preservation's bd-ib-5xihdt and checkpoint-commit-hook-failures' bd-ib-m6sdjh stay where they
  are, off the track.
- livespec-dev-tooling-mpv6bp and -oim422 are textual-conflict generators in generated registers, not factory
  rebase conflicts; they are destined for ci-reliability-leftovers (note 007).

Expected effect on the metric: the yield arithmetic of rank 3 (about +0.47 PRs per hour fleet-wide per 10 points
of factory yield). The share of failed runs in this class is not measured until rank 4 lands.

## The four CORE plans notes 005 to 008 never mention

| Plan (epic) | Report item | Disposition |
|---|---|---|
| stall-watchdog-false-kills (bd-ib-laf735) | a healthy run cancelled (yield) | OFF the track. It has one open child (bd-ib-snq7o6) of 13 and a live seat on vmi3006760; it finishes as it is. Its failure class becomes countable under rank 4; if the count is material the track coordinator adds it then. |
| factory-idle-with-ready-work (bd-ib-opbzv3) | dispatcher idle with ready work | OFF the track. Its one open child (bd-ib-hlfw5p) is at acceptance and its timer install is deferred by the fleet coordinator's 2026-11-02 ruling until dispatch-control-plane's cutover. No seat. |
| pr-refresh-reproof-relevance (bd-ib-ku7phe) | C2, the proof form (carry a verified proof across a refresh) | OFF the track. Dormant, hp-scoped, two open children (bd-ib-v4exlm among them). Rank 7 on the track is the GATE form only (implement-test-performance). See overlap O3. |
| dispatcher-run-watch-cost (bd-ib-k7ymgx) | N3, load on vmi3006760 | OFF the track, with the rest of the VPS-pressure work, which the maintainer's priority-2 track (bootstrap-credentials-and-onboarding) owns. Its bd-ib-oz2pxq, bd-ib-ag633q and bd-ib-vh23ja stay with it. |

## The six overlaps the inventory records name, each with its resolution

| # | Overlap | Resolution |
|---|---|---|
| O1 | Healthy run cancelled: bd-ib-snq7o6 (stall-watchdog-false-kills), bd-ib-cewr.5 (silent-failure-surfaces), bd-ib-m1av, bd-ib-2dlh7m (dispatcher-run-watch-cost) | Not consolidated by this track; all four are off it. stall-watchdog-false-kills is the plan whose purpose this is; the fleet coordinator is asked to have its seat say whether the other three duplicate bd-ib-snq7o6. |
| O2 | Whole-run wall budget: factory-run-wall-budget (bd-ib-hqt3s5) against bd-ib-pof4aa, bd-ib-ds4yrm, bd-ib-ag633q | Not consolidated by this track; off it. factory-run-wall-budget is the plan whose purpose this is (its pointer is at `proof`); the other three stay with their plans. Timeouts that END a run are row 6 (sandbox-commit-gate-follow-ups, bd-ib-2eyiwy), which is a different surface: a node timeout, not a whole-run budget. |
| O3 | C2 split: gate verdict per tree (implement-test-performance, yud7rc, jd4qle) and verified proof across a refresh (pr-refresh-reproof-relevance, bd-ib-v4exlm) | Two different things under one report item. D8 of note 005 covers the gate form, which is rank 7. The proof form is off the track with its dormant plan. |
| O4 | bd-ib-v4exlm against bd-ib-rriwjr ("the same decision") | bd-ib-rriwjr is a Y3 carrier of publish-draft-green-work-loss (above). That plan's seat is asked, through the track coordinator, to say whether bd-ib-v4exlm duplicates it and to close or absorb it. |
| O5 | The "test pins a committed literal" family: livespec-dev-tooling-fmprfr (dev-host-test-gate-load), -mrbvgm (dev-host-disk-retention), -xazlro (expedited-incident-hardening), -egyvwa (expedited-incident-response-flag), -symfx2 (ci-runtime-and-cost) | Not consolidated by this track. Each item names a different test in a different plan, and four of the five plans are off the track; symfx2 stays in ci-runtime-and-cost under rank 5. fleet-flaky-tests is the natural owner of the family as a class; the track coordinator is asked to put that to it. |
| O6 | Console build telemetry: optimize-console-builds (livespec-console-beads-fabro-gqmtwa) against console-factory-build-telemetry (livespec-dev-tooling-bfvbsw) | OFF the track: console builds only, both dormant, and the console repository merged 25 PRs in the baseline week. Left as it is. |

## The report items and their single owners, in one place

| Item (note `data/report-item-keys.md`) | Owner on the track | Row |
|---|---|---|
| Y1 unprovable assertions | factory-run-yield (bd-ib-ft26pi) | 3 |
| Y2 timeouts in refresh and gate steps | sandbox-commit-gate-follow-ups (bd-ib-3goerg) | 6 |
| Y3 stale-base rebase conflicts | publish-draft-green-work-loss (bd-ib-acrr56) | 6b |
| Y4 gate check failures in runs | sandbox-commit-gate-follow-ups | 6 |
| Y5 open-Red re-entry | sandbox-commit-gate-follow-ups | 6 |
| C1 full suite once per change | ci-runtime-and-cost (livespec-dev-tooling-ib3oe3), with legs 5a implement-test-performance and 5b sandbox-commit-gate-follow-ups | 5 |
| C2 gate verdict reuse | implement-test-performance (livespec-dev-tooling-sv6m5p) | 7 |
| C3 shrink the suite | fleet-mutation-testing-rule-26 (livespec-dev-tooling-oi2two) | 9 |
| C4 implement-turn and per-commit gate duration | carried by rows 5a and 5b; no row of its own | 5a, 5b |
| N1 gamingpc idle capacity, N2 capacity to gates and the factory | gate-job-resources (livespec-dev-tooling-ukoeah) | 8 |
| N3 vmi3006760 pressure | off the track: bootstrap-credentials-and-onboarding (hxi-vxsmdv) | — |
| M1 failure category, M2 factory CPU attribution | factory-run-yield | 4 |
| M3 gate durations | implement-test-performance (its accepted re-check) | 7 |
| M4 PR-side CI runs and durations | ci-runtime-and-cost | 5 |
| M5 the one metric and its panel | throughput-metric (livespec-dev-tooling-oe7cfw) | 1 |
| G1 GitHub REST budget | github-request-budget-discipline (livespec-httc) | 10 |
| red master | (a) ci-runtime-and-cost, the exporter; (b) red-master-self-healing (livespec-dev-tooling-zcp5vb) | 2 |
| flaky tests, withheld flake retries | fleet-flaky-tests (livespec-dev-tooling-zwveqp) | 11 |
| ledger latency from hetzner-xubuntu | off the track: bootstrap-credentials-and-onboarding | 12 |

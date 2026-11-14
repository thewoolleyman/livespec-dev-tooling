# Consolidation executed, and the track as handed off (2026-11-14)

DoD assertions 3, 4 and 5. This note records what happened to each proposal of note 005, the rulings the maintainer
gave on the way, and the ranked track as it stands. Where it differs from note 005, this note governs.

## Maintainer rulings received during the organization (verbatim; scope events on livespec-dev-tooling-q26e3c)

- ~22:1xZ 11-13: "The goal of the overall track will be to move ONE METRIC: THROUGHPUT AS MEASURED IN PRS PER REPO
  PER HOUR MERGED TO MAIN BRANCH AND PASSING AS GREEN. Reported as a table of each repo and its throughput, and with
  a corresponding honeycomb item for me to monitor real-time as the first item on the existing livespec board"
- ~23:1xZ: "Yes, a failed telemetry export can instead be opened as a bug, via some low-cost means.  Probably a plan
  that collects it for now, address-honeycomb-alerts can be used for now.  Eventually we will have a dedicated seat
  in the radar rearchitecture to be responsible for telemetry management."
- ~23:1xZ, the board: "Yes: https://ui.honeycomb.io/thewoolleyweb/environments/livespec/board/krThv8DvcwS/livespec-family-all-activity"
- ~23:1xZ, fleet-mutation-testing-rule-26 stays on gamingpc-xubuntu "so it would have resources".
- ~23:2xZ: "The stale-base-merge-options track is switching us to an org, so merge queuewill absolutely be usagele" /
  "usable". The single full-suite guard of master (lever 5) is therefore designed on GitHub's merge queue after the
  organization move. Note 005's statements that the queue is ruled out are superseded.
- ~23:3xZ: "The first thing you should do is set up the metrics gathering and honeycomb board so you can be laser
  focused on improving the per0-repo PR  throughput numbers."
- ~23:3xZ: "Adng go ahead and open all the relevant plans in this herdr workspace, or move them here."
- ~00:4xZ 11-14: "You should be doing everything as quickly as possible and in parallel. Do not stop until your plan
  is done."

## The metric is live

- Honeycomb dataset `pr-throughput`: one `pr.merged` event per merged PR, all 15 fleet repositories, timestamped at
  the merge, 7 d backfilled at 23:30Z on 11-13 (1,764 events). Fields: `repo`, `pr.number`, `pr.merged_at`,
  `git.merge_head_sha`, `ci.covering_run_id`, `ci.covering_conclusion`, `pr.own_run_conclusion`, `pr.merged_green`,
  `pr.merged_green_own_run`, `pr.author`, `pr.is_factory`, `pr.head_ref`, `pr.open_to_merge_minutes`, `emitter`.
- Board `livespec family — all activity` (`krThv8DvcwS`): first panel "THROUGHPUT — PRs merged green per hour, by
  repository", beside it "Merged but NOT green". Applied by `ci-runner/observability/boards/apply-boards.sh` from
  `livespec-family-all-activity.json` (livespec-dev-tooling#4591), with the pre-write export under `boards/exports/`.
  Known loss: the applier does not carry `preset_filters`, so the board's two preset filters were dropped.
- Check: a Honeycomb query of the dataset at 23:3xZ returned 639 (livespec-dev-tooling) and 480 (orchestrator) merged
  green in 7 d, against 637 and 474 from GitHub 90 minutes earlier.
- **The feed is a STOPGAP**: `~/.local/share/pr-throughput/emit.py` on hetzner-xubuntu, every 10 minutes from a
  background loop of the organizing seat's session, GraphQL only (44 points a pass). It dies with that session.
  Its replacement is livespec-dev-tooling-gaetnq (committed reconciler on an ansible-converged timer); the panel is
  livespec-dev-tooling-bgespb. Both are children of q26e3c with kubernetes-observability as deliverer. gaetnq was
  refused at the spec tier at 00:20:47Z on 11-14 (no proposal for its topic on master); kubernetes-observability is
  filing that proposal.

## What happened to each proposal of note 005

| # | Owner | Outcome |
|---|---|---|
| P1 | legacy-dispatcher-agent (bd-ib-ynnykl) | ACCEPTED 22:56:30Z. Releases bd-ib-ccl3wf and bd-ib-2h6cfl to factory-run-yield. `reparent_plan_child` REFUSED both at ~23:2xZ: each is spec-change-tier with an unratified proposal. They move when their proposals ratify. bd-ib-2h6cfl was also refused at dispatch (23:29:42Z) for the same unratified topic. |
| P2 | spec-implementation-lockstep (bd-ib-ax3rds) | ACCEPTED. bd-ib-lqjygl: same refusal, same wait. |
| — | new plan factory-run-yield (bd-ib-ft26pi) | CREATED (livespec-orchestrator-beads-fabro#5202). Children today: bd-ib-vhx5vl, bd-ib-hxkikj, bd-ib-faprof, adopted by a raw parent-child edge under the coordinator's ruling of 23:38:36Z for parentless items only. bd-ib-rowuou waits for a tier classification. |
| P3 | ci-runtime-and-cost (livespec-dev-tooling-ib3oe3) | ACCEPTED the narrowing to lever 5, PR-side CI measurement and the exporter; its assertions 2, 4 and 5 stay. Moved by its own session: mtvxde and 2aelab to gate-job-resources, jd4qle to implement-test-performance, ehnjlt and onk27y to expedited-incident-hardening. Staying: lzkzwb, qzw2gf, xtofr3, 5wewi2, samgg2 and seven others. 6e5pyj closes as a duplicate of wirn53 after livespec-dev-tooling#4568 is applied. To stale-base-merge-options on its consent: 2yne2h, c7efqa, oim422, vfofyj, mpv6bp. New work it took: the exporter change (livespec-dev-tooling-jgkhr5; a failed export files a bug collected by address-honeycomb-alerts) and row 5c (stop CI on a replaced PR head). |
| — | new plan ci-reliability-leftovers (coordinator ruling) | Takes the 12 pool items and 8 workflow-hygiene items ci-pool-provisioning-leftovers refused. OFF the track. |
| P4 | stale-base-merge-options (livespec-dev-tooling-xowhol) | WITHDRAWN as a re-point: the maintainer ruled the organization move and the merge queue. It is asked to take the check-per-file-coverage diagnosis as its own item. |
| P5 | sandbox-commit-gate-ceiling (bd-ib-qy5wol) | MODIFIED. Its five children move to sandbox-commit-gate-follow-ups one by one as each one's proposal ratifies. bd-ib-ebwpxw is NOT a duplicate of bd-ib-hmed6n (different trigger). |
| — | sandbox-commit-gate-follow-ups (bd-ib-3goerg) | ACCEPTED 23:56:35Z: owns rank 5b and rank 6; adopted bd-ib-jvc533, bd-ib-u5r2oz, bd-ib-vy75ws, bd-ib-mpqwdr, bd-ib-3k3xh7. |
| P6 | implement-test-performance (livespec-dev-tooling-sv6m5p) | MODIFIED. Owns lever 2 and the host-gate leg of lever 5; absorbs delegated-commit-time-gates and rgr-touched-test-scope (re-worded: the whole suite runs once per final tree, reused by tree hash) after bd-ib-vy75ws closes; takes only section 3 of rgr-cycle-agent-efficiency. |
| P7 | gate-job-resources (livespec-dev-tooling-ukoeah) | MODIFIED. Owns levers 3 and 8 as budget rules; took mtvxde, 2aelab, z7nfhx and the gamingpc lane item; refused hatvwq, a2kwn3, xnie, 5wewi2, samgg2. |
| P8 | kubernetes-observability (livespec-dev-tooling-s2aqob) | MODIFIED. Delivers both metric items, filed as children of q26e3c, not of its own epic. |
| P9 | fleet-mutation-testing-rule-26 (livespec-dev-tooling-oi2two) | Sent to its pane by the coordinator; no answer recorded at the time of writing. |
| P10 | seats | See the layout below. |
| — | fleet-flaky-tests (livespec-dev-tooling-zwveqp) | Asked for the withheld-flake-retry count; no answer recorded at the time of writing. |

## The ranked track, as handed off

Effect is on PRs merged green per hour. Baseline: note 003 (fleet 9.64/h over 7 d to 2026-11-13T22:05Z).

| Rank | Lever | Owning plan (epic) | Carriers | Tab in throughput-improvements | Next action | Expected effect on the metric |
|---|---|---|---|---|---|---|
| 1 | The metric and its panel | throughput-track-organization (q26e3c); deliverer kubernetes-observability | livespec-dev-tooling-gaetnq, -bgespb | kubernetes-observability | ratify gaetnq's proposal, build the reconciler, retire the stopgap | none directly; it is how every row is judged |
| 2 | Stop merging under a red master | ci-runtime-and-cost (a: exporter); stale-base-merge-options (b: diagnosis, and the queue) | livespec-dev-tooling-jgkhr5; diagnosis item to be filed by its owner | ci-runtime-and-cost; stale-base-merge-options | jgkhr5: amend, approve, dispatch | ceiling +0.87/h fleet, +0.64/h livespec-dev-tooling (146 PRs in 7 d). At least 7 of the 17 export-only reds were the ool7pj regression, already reverted. |
| 3 | Refuse assertions the sandbox cannot prove | factory-run-yield (bd-ib-ft26pi) | bd-ib-vhx5vl, bd-ib-hxkikj now; bd-ib-ccl3wf, bd-ib-lqjygl, bd-ib-rowuou on ratification; the filing-refusal gap to be filed by its seat | factory-run-yield | carrier map; orchestrator revise slots for the held topics | about +0.47/h fleet per 10 points of factory yield; class share unmeasured |
| 4 | Failures countable; factory CPU attribution | factory-run-yield | bd-ib-faprof now; bd-ib-2h6cfl on ratification of `a-factory-run-s-terminal` | factory-run-yield | revise slot for that topic | none directly; sizes ranks 3 and 6 |
| 5 | Full suite once per change: PR CI, master, design on the merge queue after the org move | ci-runtime-and-cost | the coverage-receipt reuse chain (s2esff and nine more); qzw2gf, xtofr3 (superseded master runs) | ci-runtime-and-cost | sequence against the org move | CI-side full-suite runs per merged change are 2.23 and 2.46 today; the queue makes the master leg one run per batch |
| 5a | host-gate leg | implement-test-performance (sv6m5p) | absorbed charters after bd-ib-vy75ws | implement-test-performance | close bd-ib-vy75ws | acts on the 54-78% of PRs that come from seats |
| 5b | factory in-run leg | sandbox-commit-gate-follow-ups (bd-ib-3goerg) | bd-ib-fde4ie, bd-ib-72hvx5, bd-ib-qv7ba2, bd-ib-vy75ws | sandbox-commit-gate-follow-ups | bd-ib-fde4ie at acceptance | shortens the 101 min median run (implement is 75% of agent time) |
| 5c | no CI on a replaced PR head | ci-runtime-and-cost | one item plus a propose-change against constraints.md CI matrix shape | ci-runtime-and-cost | file the proposal | returns 36% of PR-side runner-minutes to pools with 20-31 min p95 queue wait |
| 6 | Factory failure classes after admission | sandbox-commit-gate-follow-ups | bd-ib-2eyiwy, bd-ib-kclvlo, bd-ib-22ckko, bd-ib-jvc533, bd-ib-d2l5pl, bd-ib-gisyvv, bd-ib-ohlkz7, bd-ib-u5r2oz | sandbox-commit-gate-follow-ups | the 24 h re-measure after v0.323.0 | yield arithmetic of rank 3; unsized until rank 4 |
| 7 | Gate verdict reuse per tree | implement-test-performance | yud7rc, jd4qle; orchestrator adoption bd-ib-mpqwdr, bd-ib-3k3xh7 (held by bd-ib-3goerg) | implement-test-performance | close jd4qle (its fix merged as livespec-dev-tooling#3836) | about 32 gate-hours a week; no direct PR count |
| 8 | Capacity to gates and the factory; gamingpc | gate-job-resources (ukoeah) | wirn53, mtvxde, 2aelab, z7nfhx, the gamingpc lane item | gate-job-resources | apply livespec-dev-tooling#4568 and read back | measured as the drop in queue-wait p95 from 20.3 / 30.8 / 30.4 min |
| 9 | Shrink the suite; ration the mutation matrix | fleet-mutation-testing-rule-26 (oi2two) | its 6 open children | none: stays on gamingpc-xubuntu (maintainer) | grade livespec-dev-tooling#4581 | pays at every remaining full run; unsized |
| 10 | GitHub REST budget | github-request-budget-discipline (livespec-httc) | livespec-j49m, livespec-umy2; dependents bd-ib-zdqshg, livespec-driver-claude-32a | github-request-budget-discipline | measure per-caller REST spend first | one measured outage, 21:56Z to 22:30Z on 11-13: zero factory launches for 33 min, and at least two seats' pushes refused by check-master-ci-green after a full gate (this seat lost 36 min) |
| 11 | Withheld flake retries | fleet-flaky-tests (zwveqp) | livespec-dev-tooling-k3lpwj and five sibling causes | none: stays in workspace livespec-dev-tooling on hetzner-xubuntu | count the withheld share of 80 reruns a week | ceiling 80 PRs a week delayed by one suite run |
| 12 | **Ledger latency from hetzner-xubuntu** (new) | bootstrap-credentials-and-onboarding (hxi-vxsmdv), which owns the Dolt single point | to be named by its owner | none: priority-2 track | decide where the Dolt server lives as seats move | measured 2026-11-14 ~00:0xZ: one `bd show` from hetzner-xubuntu takes 17.6, 19.1 and 19.4 s (round trip to vmi3006760 207 ms average); a 12-epic comment read takes about 4 minutes. Every seat moved to hetzner-xubuntu pays it on every ledger call. |

## What moved out of the track, and where

- The VPS's own pressure: bootstrap-credentials-and-onboarding (priority-2 track), dev-host-test-gate-load,
  dev-host-disk-retention.
- ci-runtime-and-cost's 20 pool and workflow-hygiene items: new plan ci-reliability-leftovers. Two incident items:
  expedited-incident-hardening.
- legacy-dispatcher-agent's other 24 open children: PROPOSED to the coordinator, not yet ruled. Launcher-script
  defects to provisional-fleet-launch (bd-ib-klkbxp); eight orchestrator-product defects to dispatch-control-plane
  (bd-ib-k6dqwc) or a new plan. Two of them bear on the metric and are worth watching: bd-ib-kzmihk (filling the
  fleet after a lift takes about 26 min) and bd-ib-4vwaty (a slow or red default branch strands launch tickets).
- The six agent-efficiency angles of rgr-cycle-agent-efficiency: left as an unowned 2026-08 proposal, off the track,
  to be revisited when bd-ib-vy75ws lands.
- Work recovery (publish-draft-green-work-loss, factory-run-work-preservation), credential and quota plans,
  launch-path reliability, and every plan note 004 classified as touching no report item.

## Open questions that are the maintainer's

1. The order of the GitHub organization move against the other levers (carried by stale-base-merge-options).
2. Whether the headline "green" stays "covered by the next verdict-bearing master run" (note 003) once the merge
   queue exists; under a queue every merged PR has its own tested head and the two definitions converge.
3. Whether the two metric items stay children of this organizing plan (which then cannot archive until they are
   delivered) or move to a standing track epic.

## Seat layout: workspace throughput-improvements on hetzner-xubuntu

Opened or moved by this seat on the maintainer's 23:3xZ direction: throughput-track-organization,
sandbox-commit-gate-follow-ups, factory-run-yield, github-request-budget-discipline, stale-base-merge-options.
Asked to move from vmi3006760 at ~00:4xZ on 11-14 (each writes its handoff and comments MOVE-READY first):
kubernetes-observability, ci-runtime-and-cost, implement-test-performance, gate-job-resources. The handoff scope
event on livespec-dev-tooling-q26e3c records the layout as it finally stood.
Not in this workspace by ruling or by choice: fleet-mutation-testing-rule-26 (gamingpc-xubuntu), fleet-flaky-tests
(workspace livespec-dev-tooling on hetzner-xubuntu), ci-reliability-leftovers (off the track).

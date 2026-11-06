# Retrospective evidence, DRAFT (livespec-dev-tooling-osyzv6)

Evidence for the maintainer's retrospective on why plan `expedited-incident-response-flag`
(epic livespec-dev-tooling-bqnzcm) took about three days. Material, not conclusions.
Gathered 2026-11-06 ~17:45Z, read-only. Every figure names its source; VERIFIED means
read from the ledger, the forge or Honeycomb; INFERRED means derived by the gatherer.

Sources: `bd show/comments livespec-dev-tooling-bqnzcm --json` (362 comments, 54 handoff
entries, 27 scope events), `bd list --status all --json` on the dev-tooling and bd-ib
tenants, `gh pr list --state all --search created:>=2026-11-03` on five fleet repos,
Honeycomb `llm-spend` through `~/token-spend-report/scripts/hcq.py` under the wrapper
(window 2026-11-03T15:00Z to query time), the coordinator epic livespec-dev-tooling-6tgd2z.

## 1. Headline numbers

| Figure | Value | Source |
|---|---|---|
| Plan age at gathering | 73.7 h (created 2026-11-03T15:58:13Z) | epic record, VERIFIED |
| Implementation authorized | 2026-11-03T17:18Z (P1) | scope event #11 |
| Handoff entries per day (03/04/05/06) | 23 / 16 / 7 / 8 = 54 | epic comments, VERIFIED |
| Of which restart-headed | 16 / 13 / 5 / 7 = 41 | opening words of each entry, INFERRED |
| Restart cost | ~15 min each (seat's own measurement, 11-06 16:19Z handoff) | handoff #358 |
| Dev-tooling children | 27 (19 closed, 3 acceptance, 4 ready, 1 blocked) | `bd list`, VERIFIED |
| bd-ib carriers (orchestrator tenant) | 20 named (12 closed, 8 open) | `bd list`, VERIFIED |
| Carriers closed per day (04/05/06) | 13 / 3 / 12 (dev-tooling + bd-ib, 28 closed) | ledger `closed_at` |
| Median created to closed, closed carriers | 18.6 h (mean 14.1 h, n=28) | ledger, VERIFIED |
| Median created to last merge | 14.0 h (n=29) | ledger + forge, VERIFIED |
| Factory runs on plan carriers | 7 runs, 0 green merges, ~23 h factory wall | item comments, VERIFIED |
| Plan seat spend (direct) | $1,491.03 | Honeycomb `spend.plan`, VERIFIED |
| Factory spend on plan carriers' runs | $106.15 | Honeycomb `work.item.id`, VERIFIED |

## 2. Timeline, day by day (UTC)

All times from ledger comment timestamps unless marked.

**2026-11-03 (day 1, Codex seat).** 15:58 plan created at maintainer request; 16:28 draft
committed; 17:08 docs PR published (livespec-dev-tooling#3312). 17:18 maintainer makes it
fleet P1 and authorizes implementation (relayed by the coordinator). 17:23-17:30 ten
children filed; held at the intake wall until the coordinator ratifies the spec; all ten
ready with `dispatch:requested` by 19:46. 19:17-20:01 cross-tenant proposals published
(livespec#3087, livespec-overseer#2818, orchestrator#4340). 20:02 sh3vz3 dispatched to the
factory (the plan's first run). 21:42 maintainer grants
`maintainer-local-only-expedited-exception-20261103T2142` ("can't I authorize you to skip
some of the test gates ... OK, do it ... Yes I want to save waiting time"). 23 handoff
entries this day, 16 restart-headed, most titled "CLEAN OVERSEER RESTART HANDOFF" at the
overseer's context-50% wrap rule (entries 18:37, 19:02, 19:35, 20:01, 20:48, 21:28, 21:57,
22:17, 22:34, 22:51, 23:11).

**2026-11-04 (day 2).** 00:02 sh3vz3 factory run ends needs_human (hook refused,
re-entry budget spent); hand-landed from the preserved tree. 02:12-12:08 the ten original
children's PRs merge (3340, 3346, 3347, 3352/3355, 3353/3360/3380, 3358/3382, 3363, 3367,
3374, 3376, 3385). 02:44 maintainer correction recorded verbatim: "you are not doing good.
I told you to move everhthing along in parallel and not block on anything". 02:53
maintainer: "let expedited incident wrap at 35" (context threshold lowered from 50 to 35;
coordinator epic). 04:03 Driver 0.12.0 hook-safety notice forces a restart handoff. 06:14,
08:16, 09:29, 10:35 "FINAL USER-ORDERED 3x%-CONTEXT RESTART" handoffs. 11:55-12:00
coordinator corrects a wrong factory-implement request for already-merged lgfo3v. 13:0x
maintainer: "GET IT DONE SOMEHOW"; the coordinator presses accept on the six
acceptance-parked carriers at 13:05 and reconcile-merged on four; all ten CLOSED by 13:48
(merges had been waiting on the proof-only resume chain, bd-ib-a7zpxy). 13:43 wanebl filed
(closed 15:17); 14:36 rqhqnb (closed 17:45); 16:33 si6uu7; 16:36 dln3ac (closed 19:43).
17:57 maintainer-ordered pane closure of the Codex seat. 19:54 first comment of the
replacement Claude seat (gap ~2 h, INFERRED from comment times). 23:39 6n6v35 (BUG) filed,
factory-routed.

**2026-11-05 (day 3).** 01:04, 03:41 restart handoffs; si6uu7 closed 03:39. 03:30
FACTORY-DEFECT LAUNCH HOLD: orchestrator 0.287.0's `commit_red` runs a script that exists
only in the orchestrator repo; every non-orchestrator launch (6n6v35, oonqhx) waits until
v0.288.0 is the launch build at 10:36:47Z (7 h). 07:43 coordinator rules the plan ADOPTS
bd-ib-jjws2 (claim-token protocol), regroomed into S1-S5; coordinator DECLINES to extend
the local exception, so all five go to the factory at P10 behind P1-P9. 08:08 6bmta2 filed
(closed 15:26). 13:16 S1 lgwwx7 factory run fails (janitor timed out after 4340 s, "CPU
contention"); route becomes a seeded re-dispatch at P10 "after the :32276 window and the
canary". 15:51 wjmre6 filed (closed 18:20). 20:42 maintainer: priority 1, every critical-
path carrier hand-landed, factory allowlist EMPTY; 21:12 assertion 4 authorized with three
guardrails; 21:27 release-window waiver. 20:5x minimum usable slice cut (A: S1, B: dzbwaq
genesis, C: 7f5w7r, D: yf7gq2, D2: z3wy33, E: drill); 7f5w7r, yf7gq2, z3wy33, w7n3ad
filed. 22:1x coordinator gate rule: dev host CPU-saturated, ONE full-aggregate gate at a
time across the plan's lanes. 23:43 6n6v35 merged by hand (it had waited ~21 h on the
factory path and was then refused host-only by drive); 23:55 lgwwx7 merged by hand.

**2026-11-06 (day 4, today).** 00:08 7f5w7r merged; 01:12 dzbwaq genesis merged (#4504).
01:17 FINDING: the slice cannot reach a trusted receipt on a real tenant without S2-S5 and
a tenant cutover; coordinator ruling: S2 by hand, S3/S4 in the factory, then S5 cutover of
the bd-ib tenant, then the drill; "first end-to-end use not before ~12:00Z". 03:02, 03:30
utwjkf and S2 ngzg63 merged by hand. 04:05 S3 run ends needs_human (hook refused: lloc,
coverage); 04:30 S4 run ends needs_human (partial progress, wall 3 h 00 m); both moved to
hand lanes (04:08, 04:35). 05:39 z3wy33 workflow edit merged after the maintainer approved
the label (#3572). 06:2x three cross-tenant `blocks` edges on truk55 had blocked EVERY
dev-tooling dispatch (first casualty dpbpfx 06:19); coordinator removed them. 07:39 dpbpfx
factory run ends needs_human (publish_draft defect); hand-landed 10:15. 08:42-10:37
FLAKE HOLD: every orchestrator push refused intermittently by check-fleet-launch case 19
(bd-ib-eb5zl5); S3's push hit it; fix merged 10:37 (#4525). 11:11, 11:32, 11:54, 12:20 S3
(two PRs), tlgq3y, S4 merged; v0.295.1 tagged 12:36. **bd-ib tenant window 12:39:14Z to
14:31:07Z** (1 h 52 m): migration pass 12:41-13:35 (491 items), first cutover push refused
by check-per-file-coverage (a test read the real key), fix, #4542 merged 14:24. 13:31
CRITICAL PATH CHANGED: the drill cannot arm on a bd-ib item, so truk55 (dev-tooling
cutover) joins the critical path. **dev-tooling tenant window ~14:58Z to 16:12:06Z**
(#3618 merged 16:07); the epic itself was under the write hold. 14:51-14:55 kk4pjr,
dzb7ux, j6hjhz merged by hand. 15:50 kseatc factory run starts (v0.295.2 canary); 16:2x
maintainer standing ruling recorded "after the seat failed to apply it twice across
restarts": every item local, everything in parallel, DO NOT STALL; 16:32 kseatc run
cancelled outside the dispatcher. 16:13-16:19 y5u4my, ua2scz, ws2idp filed. 16:4x this
retrospective item commissioned. Open at gathering: yf7gq2, z3wy33, w7n3ad (acceptance,
waiting on the drill), dzbwaq, y7ryj3 (factory, active since 14:40), riguvj, mnny4v,
k5teti, 4eeefv, kseatc, tshx4h, truk55, y5u4my, ua2scz, ws2idp.

## 3. Wall time per carrier

Created, first PR, last merge, close from the ledger and `gh pr list` (VERIFIED). Route:
F = factory run attempted, H = hand-landed under the exception. Hours are from `created_at`.

| Carrier | Created | First PR | Last merge | Closed | h to close | Route |
|---|---|---|---|---|---|---|
| sh3vz3 | 11-03 17:23 | 11-04 01:55 (#3340) | 11-04 03:23 | 11-04 13:00 | 19.6 | F then H |
| cerkbn | 17:24 | 02:12 (#3347) | 13:02 (#3385) | 13:01 | 19.6 | H |
| xluwqj | 17:25 | 02:12 (#3346) | 02:39 | 13:01 | 19.6 | H |
| gvylzw | 17:26 | 03:12 (#3352) | 04:28 (#3355) | 13:01 | 19.6 | H |
| egy3ri | 17:26 | 05:41 (#3358) | 10:44 (#3382) | 13:02 | 19.6 | H |
| 47ij37 | 17:27 | 03:31 (#3353) | 12:08 (#3380) | 13:02 | 19.6 | H |
| lgfo3v | 17:28 | 09:11 (#3374) | 10:42 | 13:46 | 20.3 | H |
| kobmka | 17:28 | 06:41 (#3363) | 08:59 | 13:38 | 20.2 | H |
| vg36aq | 17:29 | 09:51 (#3376) | 10:14 | 13:47 | 20.3 | H |
| wlrlt2 | 17:30 | 07:47 (#3367) | 08:44 | 13:47 | 20.3 | H |
| wanebl | 11-04 13:43 | 14:39 (#3399) | 15:04 | 15:17 | 1.6 | H |
| rqhqnb | 14:36 | 16:34 (#3407) | 17:23 | 17:45 | 3.2 | H |
| dln3ac | 16:36 | 18:51 (#3419) | 19:12 | 19:43 | 3.1 | H |
| si6uu7 | 16:33 | 11-05 01:27 (#3456) | 02:37 | 03:39 | 11.1 | H |
| 6n6v35 | 11-04 23:39 | 11-05 23:08 (#3533) | 23:43 | 11-06 00:32 | 24.9 | F hold/queue 21 h, then H |
| 6bmta2 | 11-05 08:08 | 13:05 (#3497) | 14:08 | 15:26 | 7.3 | H |
| wjmre6 | 15:51 | 16:29 (#3505) | 16:55 | 18:20 | 2.5 | H |
| 7f5w7r | 20:55 | 23:31 (#3534) | 11-06 00:08 | 00:56 | 4.0 | H |
| yf7gq2 | 20:56 | 21:23 (#3524) | 11-06 01:21 | open (acceptance) | - | H, waits drill |
| z3wy33 | 21:14 | 11-06 05:39 (#3572) | 06:20 | open (acceptance) | - | H, waits drill |
| w7n3ad | 21:26 | 11-06 01:03 (#3543) | 04:14 (#3559) | open (acceptance) | - | H, 4 PRs |
| fmbp3a | 11-06 02:08 | 10:54 (#3603) | 11:25 | 11:47 | 9.6 | H |
| truk55 | 02:07 | 15:38 (#3618) | 16:07 | open (ready) | - | H, tenant window |
| bd-ib-dzbwaq | 11-03 19:18 | 11-04 05:54 (#4350) | 11-06 01:12 (#4504) | open | - | H, 4 PRs |
| bd-ib-y7ryj3 | 19:18 | 11-06 09:10 (#4524) | none | open (active) | - | F x2 |
| bd-ib-riguvj / mnny4v / k5teti | 19:19-19:21 | none | none | open | - | not started |
| bd-ib-lgwwx7 (S1) | 11-05 07:34 | 09:34 (#4460) | 23:55 (#4498) | 11-06 01:10 | 17.6 | F then H |
| bd-ib-ngzg63 (S2) | 07:35 | 11-06 02:52 (#4509) | 03:30 (#4510) | 03:46 | 20.2 | H |
| bd-ib-7uue5s (S3) | 07:36 | 11-06 11:02 (#4530) | 12:20 (#4538) | 12:32 | 28.9 | F then H |
| bd-ib-5nkxfz (S4) | 07:36 | 11-06 11:44 (#4534) | 11:54 | 12:08 | 28.5 | F then H |
| bd-ib-4eeefv (S5) | 07:36 | 11-06 14:10 (#4542) | 14:24 | open (race proof owed) | - | H window |
| bd-ib-tlgq3y | 11-06 06:27 | 11:23 (#4532) | 11:32 | 11:58 | 5.5 | H |
| bd-ib-kk4pjr / j6hjhz / dzb7ux | 07:14-07:15 | 14:41-14:45 | 14:51-14:55 | 15:09-15:26 | 7.9-8.2 | H, held by window |
| bd-ib-eb5zl5 (flake fix) | 07:18 | 10:24 (#4525) | 10:37 | 10:50 | 3.5 | H (fleet-flaky-tests) |
| bd-ib-kseatc / tshx4h | 08:33 / 08:54 | none | none | open | - | F cancelled / H |

Other tenants: livespec-3lwk4n PRs 3092, 3105, 3110, accepted 11-05 ~21:4x;
overseer-czsqpx PR 2824 merged 11-04 01:18, accepted 11-05 ~01:00; driver waq5mp closed 11-05.

Note on the ten originals: merges finished 02:12-12:08 on 11-04 but closes waited until
13:00-13:47 for the proof-only acceptance chain, until the maintainer's "GET IT DONE
SOMEHOW" (comments #255-#267). That is 1-11 h of closure latency per item (INFERRED).

## 4. Factory runs on the plan's items and how they ended

From each item's `livespec-needs-human-cause` / `livespec-run-wall-budget-exceeded` /
dispatcher comments (VERIFIED); factory wall from Honeycomb span times (INFERRED, +-15 min).

| Item | Run | Window (UTC) | Wall | Ending | What happened next |
|---|---|---|---|---|---|
| sh3vz3 | 01M6HG9ZYXWK | 11-03 20:02 to 11-04 00:02 | 4.0 h | needs_human: hook refused, implement re-entry budget spent (check-per-file-coverage) | hand-landed, PR 01:55, merged 03:23 |
| lgwwx7 (S1) | 01M6NC612SFZ | 11-05 08:13 to 13:16 | 5.0 h | stage-failure fix@3/janitor@3: script timed out after 4340 s ("CPU contention", no fix item) | seeded re-dispatch queued P10; hand-landed from the seed 20:55, merged 23:55 |
| 7uue5s (S3) | 01M6Q7BKFT1Y | 11-06 01:24 to 04:05 | 2.7 h | needs_human: hook refused (check-file-lloc, check-per-file-coverage), budget spent | hand lane 04:10; two PRs merged 11:11 and 12:20 |
| 5nkxfz (S4) | 01M6Q7M6057J | 11-06 01:29 to 04:30 | 3.0 h | needs_human: PARTIAL_PROGRESS, definition_of_done_complete=false | hand lane 04:35; merged 11:54 |
| y7ryj3 | 01M6QR8TRD8A | 11-06 06:20 to 12:24 | 6.0 h | run-wall-budget-exceeded (21659 s > 21600 s) during janitor; PR #4524 published, not merged | reset rider; second run |
| y7ryj3 | 01M6R... (2nd) | 11-06 14:40 to active | >3 h | active at gathering; PR #4549 open 16:30 | - |
| kseatc | 01M6RRWTAJ5G | 11-06 15:50 to 16:32 | 0.7 h | cancelled outside the Dispatcher (maintainer's all-local ruling) | hand lane on the seat |
| 6n6v35 | never launched | 11-04 23:39 ticket to 11-05 20:5x | ~21 h | FACTORY-DEFECT LAUNCH HOLD 03:30-10:36, then queued P10 behind oonqhx, then drive refused host-only | hand-landed 11-05 21:00-23:43 |

Adjacent items on the critical path, same pattern: dpbpfx (run 01M6QRFRQRK2, 06:24-07:39,
needs_human on a publish_draft defect; hand-landed 10:15), oonqhx (two runs: 01M6NNN014ZQ
cancelled 16:22, 01M6PB020SBW needs_human 21:52 on 11-05), rjlb6e (release fan-out repair).

Yield: 0 of 7 plan-carrier runs reached a green merge; every carrier that reached master
was hand-landed. Rework count: 2 runs on y7ryj3, 2 on oonqhx; hand re-dispatch on 4 items.
The coordinator's "1 in 4" (M1 YIELD 6h 1/4, 2h 0/2 at 13:55-16:22Z on epic 6tgd2z) is the
FLEET-wide metric for the day (green: csbito 11:23Z), not this plan's (VERIFIED).

## 5. Spend (Honeycomb `livespec/llm-spend`, deduped at the emitter)

Credential path: `HONEYCOMB_MCP_API_KEY_LIVESPEC` through `hcq.py` (works; 7 queries spent).
Audit lines in `~/token-spend-report/state/hcq-calls.jsonl`, prog `hcq_plan.py`,
`hcq_factory*.py`. Results saved in the session scratchpad as `hc-spend.json`, `hc-factory3.json`.

| Scope | USD | Source filter |
|---|---|---|
| Plan seat, all consumers | **1,491.03** | `spend.plan = expedited-incident-response-flag` |
| by day 11-03 / 04 / 05 / 06 (to ~17:40Z) | 302.57 / 213.12 / 322.14 / 653.21 | same, 1-day buckets |
| local Claude session named for the plan (Anthropic) | 997.27 | `spend.consumer = local session: expedited-incident-response-flag` |
| Codex seat (OpenAI, 11-03 to 11-04 17:57) | 442.39 | `spend.consumer = codex session: livespec-dev-tooling` |
| `claude -p` reviews (fable review etc.) | 24.4 | `spend.consumer` starts `claude -p` |
| Factory runs on plan carriers (work.item.id) | 106.15 | sh3vz3 26.78, y7ryj3 27.98 (2 runs), 7uue5s 22.10, 5nkxfz 17.86, lgwwx7 9.89, kseatc 1.54 |
| Factory runs on adjacent critical-path items | 63.28 | oonqhx 39.53, rjlb6e 19.11, dpbpfx 4.64 |
| Supporting seats in the same window (NOT scoped to this plan) | 703.41 / 416.75 / 375.05 | `spend.plan` = legacy-coordinator-agent / legacy-dispatcher-agent / fleet-flaky-tests |
| Every plan-attributed event fleet-wide in the window | 7,988.39 | `spend.plan exists` |

Caveats: factory OpenAI costs assume a 0.90 cached share (`emit_factory` CACHED_SHARE, per
the `codex-implement-run` cost_note); sh3vz3's $26.78 is inside both the plan figure and the
factory figure; bd-ib factory runs are not tagged with this plan (`spend.plan` attribution
is per tenant), so the plan figure undercounts them by ~$79; subagent lanes write to the
seat's transcript and are inside the $997.27. Direct plan spend plus its factory runs is
about $1,570; the coordinator/dispatcher/replayer share is not separable from the data.

## 6. Local vs factory split

Hand-landed (under maintainer-local-only-expedited-exception-20261103T2142): all 10
originals, wanebl, rqhqnb, si6uu7, dln3ac, 6bmta2, wjmre6, 7f5w7r, yf7gq2, z3wy33, w7n3ad,
6n6v35, fmbp3a, truk55, dzbwaq (4 PRs), lgwwx7, ngzg63, utwjkf, ufot43, 7uue5s, 5nkxfz,
4eeefv, tlgq3y, kk4pjr, j6hjhz, dzb7ux, dpbpfx, jfp2w5, livespec-3lwk4n, overseer-czsqpx:
every merge of this plan. Factory: attempted on sh3vz3, lgwwx7, 7uue5s, 5nkxfz, y7ryj3,
kseatc (table above); dispatched-but-never-launched 6n6v35; routing reversed for S1-S5 by
the maintainer on 11-05 20:42 after the coordinator had refused hand-landing at 07:43.
Factory yield today for the plan: 0 green of 3 runs (y7ryj3 wall-budget, kseatc cancelled,
y7ryj3 #2 active); fleet-wide the coordinator reported 1/4 over 6 h.

## 7. Stalls and holds on the record (each VERIFIED from the cited comment)

- Overseer context-threshold restarts of the Codex seat: 29 restart-headed handoffs on
  11-03/04, titled at 50%, then 35/34/33% context ("let expedited incident wrap at 35",
  maintainer, 11-04 02:53). At ~15 min each (11-06 measurement) that is ~7 h (INFERRED).
- 11-03 19:46: ten children held at the intake wall ~2.5 h for coordinator ratification.
- 11-04 02:44: maintainer correction; completed subagents left idle, a self-imposed
  no-force-push rule stalled a requested same-PR rebase (scope event).
- 11-04 04:03: Driver 0.12.0 hook-safety restart; 11-04 17:57 to 19:54: Codex seat retired,
  Claude seat opened (~2 h gap).
- 11-04 02:12-13:48: merged originals wait on the proof-only acceptance chain (a7zpxy) until
  "GET IT DONE SOMEHOW".
- 11-05 03:30-10:36: factory-defect launch hold (commit_red script path), 7 h; 6n6v35 and
  oonqhx held, then queued; 6n6v35 reached master 11-05 23:43, ~24 h after filing.
- 11-05 07:43-20:42: S1-S5 factory-routed at P10 over the seat's request; S1 run failed on a
  janitor timeout; the maintainer reversed the routing 13 h later.
- 11-05 22:1x: one full-aggregate gate at a time (dev host CPU-saturated); gates 13-30 min,
  reconcile-merged janitor 13-27 min; "subagent lanes did not receive gate-wait
  notifications; one lost about 3 h" (11-05 19:05 handoff).
- 11-06 01:17: route finding, ETA moved from ~03:00-05:00Z to >=12:00Z, then S3/S4 factory
  runs failed after 3 h each; 11-06 06:2x cross-tenant edges blocked all dev-tooling
  dispatch; 08:42-10:37 check-fleet-launch flake held every orchestrator push; 12:39-14:31
  and ~14:58-16:12 two tenant write-hold windows, the second holding this epic; 13:31 the
  dev-tooling cutover joined the critical path; 16:2x the maintainer's standing ruling
  recorded "after the seat failed to apply it twice across restarts".
- Rituals that each cost a gate (11-06 handoffs): Red must stage exactly one test file;
  factory-override label needs cancel/close/reopen; check-no-inheritance; a test reading
  the real cutover key; a stash chain that emptied a worktree.

## 8. Scope growth

Carrier map v1 (11-03 17:23): 10 dev-tooling children. v2 (19:49): + livespec-3lwk4n,
overseer-czsqpx, driver waq5mp, 6 bd-ib items. By 11-06: 27 dev-tooling children and 20
bd-ib carriers, two spec ratifications (v291, v302, v307 orchestrator; v137, v146
dev-tooling; core v046/v047), two tenant cutovers, an ansible observer role and a race-drill
play. Three critical-path re-cuts after the originals closed: jjws2 adoption (11-05 07:43),
S2-S5 + cutover (11-06 01:17), dev-tooling cutover (11-06 13:31).

## NOT MEASURED

- Maintainer attended time; coordinator/dispatcher/replayer spend attributable to this plan
  alone; factory compute (pods, CI minutes); per-gate wall totals (gate records live in each
  primary's `tmp/gate-runs/`, not read); the Codex seat's own restart cost; whether the 15-min
  restart figure holds for the Codex seat; y7ryj3's second run outcome; exact dev-tooling
  window GO time (coordinator unblocked truk55 at 14:58Z; CLOSED 16:12:06Z).

## Open questions for the maintainer

1. Was the 11-05 07:43 decision to send S1-S5 through the factory at P10 (reversed at 20:42)
   the right call given the 11-04 exception, and who should have been able to reverse it?
2. Three critical-path re-cuts came from code reading after the originals closed; should a
   plan this size have had a reachability spike (can a real receipt be produced?) before
   the ten children were filed?
3. The overseer's context-threshold restarts produced 29 handoffs in the first 24 h; is the
   restart/handoff loop itself a cost worth a plan, or an accepted tax?
4. Every merge was hand-landed; 0 of 7 factory runs reached green. Which failure classes
   (hook refusal at budget exhaustion, janitor timeouts, wall budget, publish_draft) does the
   maintainer want measured fleet-wide before the next plan is factory-routed?
5. Acceptance parked ten merged items ~10 h on a proof chain; is "proof-only" acceptance
   worth keeping for hand-landed work?
6. The seat ran one gate at a time on a saturated host while the factory ran on gmktec; is
   the local-vs-factory capacity split what the maintainer wants?
7. The direct spend is ~$1.5k; should coordinator/dispatcher/replayer spend be attributed to
   plans so the next retrospective can state a full number?

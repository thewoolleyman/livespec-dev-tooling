# Throughput-track classification — livespec-orchestrator-beads-fabro (45 live plans)

Sources: `inventory.json` (mechanical dump), each plan's first research note, a full
`bd list --status all --json` read of the `bd-ib-` tenant (2,445 records, 2026-11-13 ~23:1xZ),
and `bd show` on bd-ib-2h6cfl, bd-ib-ccl3wf, bd-ib-rowuou, bd-ib-lqjygl. Read-only.

Conventions:
- "dormant" flag = epic not updated after 2026-11-06 (nearly all of those carry the same
  2026-11-06 ~13:00Z stamp, which looks like a bulk record migration, so the true last activity
  is the `last_session` date given), OR next_action kind human/none.
- Open/total children are from inventory.json. One discrepancy found: bd-ib-zdqshg has a
  `parent-child` edge to bd-ib-ynnykl in the ledger but is absent from that plan's
  `open_children` in inventory.json.
- A child is listed under an item only where its TITLE (or the `bd show` body, where read)
  states the mechanism. "adjacent" marks a weaker link.
- No orchestrator plan research note mentions gamingpc: N1 has no owner in this repository.

## Answers to the four named questions

- **Y1 (filing check advisory vs mechanical / proof mode no sandbox can prove):** no single plan
  owns it; it is split four ways.
  - `legacy-dispatcher-agent`: bd-ib-ccl3wf (pending-approval, spec-change tier, waits on a
    propose-change) — approve and every release-to-ready path REFUSE on check 5 (a proof mode no
    sandbox capability can run). This is the closest carrier of "make it refuse". Its stated-slice
    sibling bd-ib-y4li25 (approve refuses on check 4) is closed.
  - `hp-factory-failure-follow-ups` (dormant): bd-ib-rowuou (backlog) — the filing display reports
    a factory_captured assertion on a host-only item, and its Definition of Done says the finding is
    labelled **(advisory)**. This is the advisory behaviour the report wants made mechanical; the item
    as written would ADD an advisory finding, not a refusal.
  - `spec-implementation-lockstep`: bd-ib-lqjygl (pending-approval; host taking admits what the
    in-run dod_gate refuses on check 5, spending a run), bd-ib-67wnts, bd-ib-5do354, bd-ib-bslpvz.
  - Unparented (no plan): bd-ib-vhx5vl and bd-ib-hxkikj (ready; dod_gate check 5 names the
    credential/operator-host and external cluster/service surface), bd-ib-2flry2 (ready; filing display
    labels a References mismatch advisory while approve holds on it), bd-ib-gv6uwy (backlog; host-only
    items with factory_captured assertions can never close), bd-ib-08ehv (backlog; in-run dod_gate
    grades by the shared rubric and capability set), bd-ib-yq55nk (ready; capability mirror staleness).
- **Y5 (checkpoint commit over Red / review_fix bound):** `sandbox-commit-gate-follow-ups`
  bd-ib-gisyvv (acceptance) is the exact carrier; bd-ib-ohlkz7 (acceptance) beside it.
  `sandbox-commit-gate-ceiling` holds bd-ib-mx2h62, bd-ib-rhv4lo, bd-ib-ebwpxw, bd-ib-b3qjzq,
  bd-ib-vamn3n (held there only because the disposition primitive refused the move). Closed
  bd-ib-wotls4 (v0.323.0) fixed cause A (14 of 18 runs); the 24 h re-measure is owed by the
  follow-ups plan. Unparented: bd-ib-u5r2oz (ready; seeded run with an open Red has no route).
- **Y2 (script timeouts in refresh/gate steps):** `sandbox-commit-gate-follow-ups` bd-ib-2eyiwy
  (declared node timeout replaced by the 1800 s default), bd-ib-kclvlo, bd-ib-22ckko;
  `publish-draft-green-work-loss` bd-ib-hap62u (pr_refresh post-rebase gate outruns 1800 s).
  Unparented: bd-ib-jvc533 (pending-approval; ACP turn ceiling vs node work unmeasured),
  bd-ib-svw54x (blocked).
- **Y3 (stale-base rebase conflicts):** `publish-draft-green-work-loss` (its title names it):
  bd-ib-qf5dau, bd-ib-zzhy5t, bd-ib-rriwjr, bd-ib-64n5ct. Also `sandbox-commit-gate-follow-ups`
  bd-ib-mfl2qa/bd-ib-prualo/bd-ib-hmed6n, `factory-run-work-preservation` bd-ib-5xihdt,
  `checkpoint-commit-hook-failures` bd-ib-m6sdjh. None of these PREVENTS the stale base; they
  repair or survive it. The prevention question sits in livespec-dev-tooling `stale-base-merge-options`
  (0 children).

## add-features-from--entire-in-livespec (bd-ib-72sl55)
- items: none
- relevance: NONE
- state: backlog; na=none ("resume proposal scoping when requested"); 0/0 children; updated 2026-11-06 (last session 2026-11-01). DORMANT.

## address-honeycomb-alerts (bd-ib-xkwdap)
- items: none (alert hygiene; it does not build any M1-M5 measurement)
- relevance: NONE
- state: backlog; na=await bd-ib-5k6eal (a factory-test-first-enforcement child) to close; 0/1 open; updated 2026-11-13. Active.
- overlaps: waits on `factory-test-first-enforcement` bd-ib-5k6eal.

## agent-session-stall-prevention (bd-ib-jnpvh4)
- items: none (interactive session waits, not factory runs)
- relevance: NONE
- state: backlog; na=await bd-ib-t3znvw then dispatch bd-ib-dle6l3 on coordinator GO; 2/13 open; updated 2026-11-06 (last session 2026-10-19). DORMANT.

## anthropic-burn-mitigation (bd-ib-b2jzxw)
- items:
  - C1: bd-ib-jaaya5 (review turn routed to Codex can push the branch and run the whole check suite)
  - C4: bd-ib-dirscy (uv-launched PreToolUse guards cold-start mise+uv on every tool call), bd-ib-k4ltmr (python PreToolUse hook does not resolve python3 through the mise shim)
  - N3: bd-ib-5d5aue (a dispatch spends ~3 CPU-minutes of drive process-tree CPU before its run starts)
  - Y1 adjacent: bd-ib-ff5ohb, bd-ib-ebdvbn, bd-ib-a3aqie (host Definition-of-Done judgement hits its 100k input bound and is skipped/unsized)
- relevance: PARTIAL (main purpose is token spend)
- state: backlog; na=spec-op revise (wait for #5071/#5075 then revise two topics, re-ticket ff5ohb/k4ltmr, host capture for a3aqie); 11/30 open; updated 2026-11-13. Active.
- unrelated_open_children: 4 — bd-ib-hofndb (preflight reuses recorded judgement), bd-ib-3h7dsf (filing display reuses a recorded verdict), bd-ib-v75dlb (Codex sandbox turns carry PreToolUse guards), bd-ib-ipcs2e (bd guard turns off beads phone-home)
- overlaps: N3 with `dispatcher-run-watch-cost` and fabro-currency bd-ib-um5n44/sif27g/n4kj4y (pre-launch time); Y1-adjacent input-bound with publish-draft-green-work-loss bd-ib-y6tcni; livespec-dev-tooling `codex-implement-cost-per-run`, `factory-spend-accuracy`.

## checkpoint-commit-hook-failures (bd-ib-hcwmnq)
- items:
  - Y4: bd-ib-jb53pu (acceptance; engine checkpoint commits run the repository pre-commit aggregate and killed 27 hp runs)
  - Y3: bd-ib-m6sdjh (publish_draft base-advance rebase conflict masked as 'git commit failed (exit 1)')
  - M1: bd-ib-6jkjzm (a failed checkpoint ending leaves the item without a reason), bd-ib-m6sdjh
  - X (work kept after a checkpoint failure): bd-ib-na2xvm
  - Y5: charter-only adjacency (engine checkpoint commits are the thing that lands on top of an open Red); the carrier is elsewhere (bd-ib-gisyvv)
- relevance: PARTIAL
- state: backlog; na=impl bd-ib-dpkip6 on hp after resolve-blocked, then bd-ib-quzpge; 7/12 open; updated 2026-11-06 (last session 2026-10-19). DORMANT, and its next action targets the hp factory.
- unrelated_open_children: 3 — bd-ib-dpkip6 (agent cleanup signals PID 1), bd-ib-quzpge (removing .git inside sandbox loses the run), bd-ib-jgedjo (sandbox refuses removing the run clone)
- overlaps: Y5/checkpoint with `sandbox-commit-gate-follow-ups` bd-ib-gisyvv and `sandbox-commit-gate-ceiling` bd-ib-rhv4lo (follow-ups note 001 names this plan as "close to bd-ib-rhv4lo"); M1 with `legacy-dispatcher-agent` bd-ib-2h6cfl; work preservation with `factory-run-work-preservation`; `runaway-process-containment` bd-ib-wcuauj.2 (600 s checkpoint commit saturation).

## codex-review-pr-disposition-routing (bd-ib-jquu6e)
- items: none
- relevance: NONE
- state: backlog; na=human (launch self-gating dispatch of bd-ib-cgvifj per a 2026-10-10 handoff); 2/3 open; updated 2026-11-06 (last session 2026-10-10). DORMANT.

## dispatch-control-plane (bd-ib-k6dqwc)
- items: X — charter-only (durable dispatcher state that replaces the tmp/ launchers; `factory-idle-with-ready-work`'s work-supply timer is deferred to this plan's cutover)
- relevance: PARTIAL (charter-only; no open child)
- state: backlog; na=none (resolve a publication-gate refusal, publish retained commit e000311c6 by PR, then review the phase-two cut); 0/2 open; updated 2026-11-13. na kind is none.
- unrelated_open_children: 0
- overlaps: `legacy-dispatcher-agent` (interim until this cutover), `factory-idle-with-ready-work` bd-ib-hlfw5p, `provisional-fleet-launch`; livespec-dev-tooling `radar-and-deterministic-admission`.

## dispatch-payload-packaging (bd-ib-x5ypbf)
- items: none (workflow.toml size cap; a dispatch-refusal cause, already at proof)
- relevance: NONE
- state: backlog; na=await bd-ib-jrawlp, then completeness review and archive; 1/2 open; updated 2026-11-13. Active, near archive.
- overlaps: spec-implementation-lockstep bd-ib-37wvsk (guard the 524,288-byte limit).

## dispatch-retry-discipline (bd-ib-jjb4mt)
- items: none (guidance and warning wording)
- relevance: NONE
- state: backlog; na=human (wound down 2026-10-19; restart instructions name the hp factory); 2/3 open; updated 2026-11-06. DORMANT.

## dispatcher-run-watch-cost (bd-ib-k7ymgx)
- items:
  - N3: bd-ib-u6llci (acceptance; run watch re-reads whole event history each poll — charter target: dev-VPS Dispatcher CPU per live run cut to one tenth), bd-ib-22j24v, bd-ib-cwuxfi, bd-ib-2dlh7m
  - X: bd-ib-oz2pxq (released item carries admission:manual and is never dispatched), bd-ib-ag633q (orphaned live run never wall-cancelled, holds a slot), bd-ib-vh23ja (fabro rm bursts lock the store for every concurrent run)
- relevance: CORE (N3)
- state: backlog; na=await bd-ib-u6llci, meanwhile groom 22j24v and push #5005; 9/18 open; updated 2026-11-12. Active.
- unrelated_open_children: 2 — bd-ib-vc6o5q (import cycle blocks a test collection), bd-ib-d2qm5d (preserve-by-reference exports only stage diffs)
- overlaps: N3 with anthropic-burn-mitigation bd-ib-5d5aue, fabro-currency bd-ib-um5n44/sif27g/n4kj4y, unparented bd-ib-busjvz (acceptance; launchers list the whole board each poll); livespec-dev-tooling `dev-host-test-gate-load`.

## dolt-server-failures (bd-ib-etfwwx)
- items: none carried (X-adjacent only: a ledger outage stops dispatch; 0 open children)
- relevance: NONE
- state: backlog; na=human (maintainer authorization for VPS actions, wdfec5 ledger probe); 0/6 open; updated 2026-11-06 (last session 2026-10-19). DORMANT.

## fabro-currency (bd-ib-6tcjfx)
- items:
  - X: bd-ib-gngz5d (lost sandbox mid-stage resumed, not finished), bd-ib-xs2gmn (resume of a finished run leaves the stream runnable), bd-ib-qx45e6 + bd-ib-dpsiwz (carrier rebase / run.prepare removal — engine currency), bd-ib-f7lrks (unparseable proof comment routed back to proof_capture), bd-ib-3edyng (5 s/30 s wall-clock deadlines in fabro-cli tests — flaky)
  - N3 / launch latency: bd-ib-um5n44 (pass-invariant pre-launch facts computed once), bd-ib-sif27g (pre-launch steps run concurrently), bd-ib-n4kj4y (pre-launch chain journals every step interval)
  - M1: bd-ib-6skm77 (record a run ended by its credential-use deadline)
  - Y4: bd-ib-3lxeqf (factory-graph gate validates with the retired 0.254 client)
- relevance: PARTIAL
- state: backlog; na=await bd-ib-qx45e6 (hand-build of bd-ib-gngz5d, roll, re-drill); 16/109 open; updated 2026-11-13. Active.
- unrelated_open_children: 5 — bd-ib-bw5x4f (post-host-record ambiguity), bd-ib-ghxvvp (rollback graph names a missing prompt), bd-ib-jjmywv (arm64 CI fabro binary), bd-ib-6tcjfx.1 (Petri inspect payload), bd-ib-reapbq (strip empty commits on pr_refresh unchanged path)
- overlaps: bd-ib-gngz5d with kubernetes-sandbox-backend bd-ib-bivsdm/ljw2xg and unparented bd-ib-xqgeav; pre-launch time with anthropic-burn-mitigation bd-ib-5d5aue and legacy-dispatcher-agent bd-ib-kzmihk.

## fabro-token-refresh (bd-ib-2nq)
- items: none (the open child is a security item)
- relevance: NONE
- state: backlog; na=impl bd-ib-2nq.5 (fork patch, surface to maintainer first); 1/7 open; updated 2026-11-06 (last session 2026-09-06). DORMANT.

## factory-configurable-model-fallback-priority (bd-ib-jxvgq5)
- items:
  - X (credential / quota outages): bd-ib-vswuhz (monthly spend-limit refusal records only a 15-minute exhaustion, admission retries the exhausted account), bd-ib-pasmj5 (disposed codex-acp connection holds the turn for the 2 h stall window), bd-ib-x3la32 (adapter exit booked as a deterministic failure, not a provider fault), bd-ib-dtfv2p (operator hold clearance record), bd-ib-yv4y3v (checkpoint-failed preserved tree taken onto base on a seeded start)
  - M1: bd-ib-piclal (implement turn whose response is a provider 400 is recorded as succeeded), bd-ib-x3la32
- relevance: PARTIAL
- state: backlog; na=await bd-ib-dtfv2p (host capture needs a real live ACP availability hold); 9/73 open; updated 2026-11-06 (last session 2026-11-03). DORMANT by date.
- unrelated_open_children: 3 — bd-ib-ozbdlm, bd-ib-xmlkiz (fallback journey proof/tests), bd-ib-gg3pyl (refusal wording)
- overlaps: unparented bd-ib-3ozwp2, bd-ib-wqxgjf (provider/credential endings); livespec-overseer llm-provider-manager.

## factory-context-per-turn-reduction (bd-ib-raqyki)
- items: none carried (token context per turn; 0 open children)
- relevance: NONE
- state: backlog; na=review (commission the completeness review); 0/3 open; updated 2026-11-06 (last session 2026-10-31). DORMANT, ready to archive.
- overlaps: spec-implementation-lockstep bd-ib-crtnzx.

## factory-idle-with-ready-work (bd-ib-opbzv3)
- items: X (dispatcher idle with ready work): bd-ib-hlfw5p (acceptance; factory sits idle with free slots, a usable credential and ready work)
- relevance: CORE (X)
- state: backlog; na=await bd-ib-hlfw5p, whose timer install is DEFERRED by coordinator ruling until dispatch-control-plane cutover; 1/4 open; updated 2026-11-06 (last session 2026-11-02). DORMANT / parked.
- unrelated_open_children: 0
- overlaps: `dispatch-control-plane`, `legacy-dispatcher-agent`.

## factory-monitor (bd-ib-4hgzyn)
- items: none (its one open child, bd-ib-kq4d, is a conformance-gate epic)
- relevance: NONE
- state: backlog; na=none (take a fresh HP-only snapshot; references hp and a 2026-10-01 state); 1/4 open; updated 2026-11-06. DORMANT, stale (hp-era).

## factory-run-correlation-observability (bd-ib-qfv9)
- items:
  - M1 / M5: bd-ib-welwbc (active; one terminal span per dispatch with run outcome and per-attempt fallback)
  - M2: bd-ib-gd7axe (backlog; prove the factory attribute varies with its input)
- relevance: CORE (M1, M2, M5 substrate)
- state: epic status ready; na=impl bd-ib-gd7axe (text is a stale side-task: file a `next`-ranking defect; gd7axe blocked on hp's stale receiver); 3/7 open; updated 2026-11-06 (last session 2026-09-06). DORMANT.
- unrelated_open_children: 1 — bd-ib-njbg7j (reply on upstream PR 576)
- overlaps: M1 with legacy-dispatcher-agent bd-ib-2h6cfl (same span family, different plan); M2 with unparented bd-ib-faprof (pending-approval; terminal span carries run class, target, sandbox CPU-seconds — it `blocks` bd-ib-welwbc), bd-ib-tqzazn (step spans say why each step ended), bd-ib-cp2x (run-level span per dispatch), kubernetes-sandbox-backend bd-ib-motuct; livespec-dev-tooling `ci-runtime-and-cost`, `console-factory-build-telemetry`.

## factory-run-wall-budget (bd-ib-hqt3s5)
- items: X — charter-only (no run holds a slot past the whole-run budget; 0 open children)
- relevance: PARTIAL (charter-only)
- state: backlog; na=proof (capture the plan Proof of Done on v0.222.0 from hp `fabro ps -a`, 2026-10-19 window); 0/1 open; updated 2026-11-06 (last session 2026-10-19). DORMANT; the owed proof names hp.
- unrelated_open_children: 0
- overlaps: factory-run-work-preservation bd-ib-pof4aa (budget extends while progress is recorded), publish-draft-green-work-loss bd-ib-ds4yrm (budget cancel discards the tree), dispatcher-run-watch-cost bd-ib-ag633q.

## factory-run-work-preservation (bd-ib-nckst7)
- items:
  - Y3: bd-ib-5xihdt (stale preserved seed diff-applied onto the current tip)
  - Y4: bd-ib-woiqjm (fix stage whose settled commit run fails a third time is cut off before needs_human, tree pushed to no ref)
  - C4: bd-ib-bwwkne (resume re-enters at review and re-runs a whole fix round to replay one capture)
  - X (rework: a failed run's work survives so the next run does not start over): bd-ib-ofvsr3, bd-ib-v6br5b, bd-ib-hyjf6n, bd-ib-st4obs, bd-ib-xc74il, bd-ib-anou6d, bd-ib-azhnw5, bd-ib-dvv2ge, bd-ib-pof4aa, bd-ib-g2t2pg
- relevance: PARTIAL (the plan's purpose is rework avoidance, an X lever, not a named Y/C item)
- state: backlog; na=await bd-ib-yw7yot's fresh run through merge; 17/35 open; updated 2026-11-13. Active.
- unrelated_open_children: 4 — bd-ib-nuswku (commit-time check on routing-schema nodes), bd-ib-4jxlnn (duplicate needs-human ref), bd-ib-yw7yot (preserve_runs.sh local copies), bd-ib-rczglr (rider reaches every stage's brief)
- overlaps: publish-draft-green-work-loss bd-ib-ds4yrm, bd-ib-adcaa6, bd-ib-vraou4, bd-ib-qshcwc, bd-ib-7gssim, bd-ib-zzhy5t (same preservation/recovery-routing surface); checkpoint-commit-hook-failures bd-ib-na2xvm; factory-configurable-model-fallback-priority bd-ib-yv4y3v; spec-implementation-lockstep bd-ib-6jo7an; factory-run-wall-budget.

## factory-test-first-enforcement (bd-ib-q622ls)
- items:
  - Y5: bd-ib-6rb6bw (the red turn changes no product file; commit_red refuses one that did), bd-ib-defs3b (count distinct verified Red-Green pairs)
  - C4 measurement: bd-ib-d3pdrv (measure each completed cycle's product lines and elapsed seconds), bd-ib-5k6eal (per-cycle observations in the terminal calibration journal and span)
  - X (rework bound): bd-ib-cbn6vw (bounce a completed-cycle deficit at the fix-loop cap), bd-ib-es2exq
- relevance: PARTIAL
- state: backlog; na=impl bd-ib-z2y4ca (regroomed into S-layers; bd-ib-5k6eal is S6); 7/19 open; updated 2026-11-06 (last session 2026-11-01). DORMANT by date, though address-honeycomb-alerts waits on its child.
- unrelated_open_children: 1 — bd-ib-pqpgc5 (refuse invalid runtime cycle ceilings before claim)
- overlaps: Y5 with `sandbox-commit-gate-follow-ups` bd-ib-ohlkz7 (commit_red/commit_green behaviour) and unparented bd-ib-u5r2oz; livespec-dev-tooling `implement-test-performance`, `rgr-touched-test-scope`.

## failure-evidence-retention (bd-ib-4aebpa)
- items: M1 — charter-only (every failed stage keeps its output, exit status and source identity; 0 open children)
- relevance: PARTIAL (charter-only)
- state: backlog; na=human (hold all dispatch until the 2026-10-14 factory stability freeze lifts); 0/1 open; updated 2026-11-06 (last session 2026-10-14). DORMANT, parked on a freeze that other plans no longer observe.
- unrelated_open_children: 0
- overlaps: M1 with legacy-dispatcher-agent bd-ib-2h6cfl; publish-draft-green-work-loss bd-ib-xkvdzp/bd-ib-kdwv2b.

## goal-template-opener-handling (bd-ib-fe3zrm)
- items:
  - X (items made undispatchable by ledger text): bd-ib-it2d (active), bd-ib-engf4h
  - Y1 adjacent / X (host-only items in the launch queue): bd-ib-v52w7a (launcher screens host-only items with the Dispatcher's predicate and never re-tickets one), bd-ib-t5aju3 (permanent pre-dispatch refusal exits 5 with one REFUSED line)
- relevance: PARTIAL
- state: backlog; na=await bd-ib-t5aju3 (seeded proof-only run on petri, draft PR 5172); 4/5 open; updated 2026-11-13. Active.
- unrelated_open_children: 0
- overlaps: legacy-dispatcher-agent (launcher screens: bd-ib-kix22a, bd-ib-65vjm5).

## hp-factory-failure-follow-ups (bd-ib-qieqc6)
- items:
  - Y1: bd-ib-rowuou (backlog; filing/admission WARN — labelled advisory — when a host-only item carries factory_captured assertions), bd-ib-bbcj6 (proof_capture retry after a timeout repeats from scratch and times out again; also Y2)
  - Y4: bd-ib-6y26nx (a fix visit after a red janitor cannot see the failing target's own output)
  - M1: bd-ib-y2dsjm (needs-human reported as its own outcome, not failed/workflow_error), bd-ib-3xdhc6 (visit-limit ending as engine cycle error instead of structured needs-human)
- relevance: PARTIAL
- state: backlog; na=human (re-arm the bd-ib-7f66ar launcher — that item is CLOSED since 2026-10-22; text names hp and rulings R250-R252); 7/22 open; updated 2026-11-06 (last session 2026-10-19). DORMANT and stale: scoped to the hp factory, which livespec-dev-tooling `gmktec-factory-placement` retires.
- unrelated_open_children: 2 — bd-ib-ic25m2 (unprotected declaration leaks container-wide), bd-ib-h6wiif (fabro ps -a slows on hp's run store)
- overlaps: Y1 with legacy-dispatcher-agent bd-ib-ccl3wf and spec-implementation-lockstep bd-ib-lqjygl; M1 with legacy-dispatcher-agent bd-ib-2h6cfl; Y4 with sandbox-commit-gate-ceiling bd-ib-b3qjzq (failing targets reach the re-entry brief).

## kubernetes-sandbox-backend (bd-ib-nmuyjc)
- items:
  - N2 (placement and node pressure; no child names gamingpc, so N1 is not carried): bd-ib-plon2p (place on the lower-pressure node), bd-ib-v5uti2 (place in proportion to node CPU capacity), bd-ib-kogktm (spread across poweredge and gmktec, image pre-pulled), bd-ib-wvveib (poweredge admission measures factory-class pressure), bd-ib-nmuyjc.6 (gmktec launch gate measures factory-class pressure, so a CI burst does not hold a launch), bd-ib-crleeu (factory-admit counts memory), bd-ib-rtzhfc (one concurrent-run limit per gmktec server, read by launchers)
  - C4: bd-ib-zl3qcz (4-CPU sandbox limit is below what a 4-worker implement turn uses)
  - M2: bd-ib-motuct (name the sandbox pod's node on each run_turn span)
  - Y1: bd-ib-lupzxt (acceptance; sandbox runs other repositories' tools from pinned read-only clones — the "other repo" capability)
  - Y4 (factory-only test failures): bd-ib-tnxcka (no reflogs in the sandbox), bd-ib-ia6zbf (sandbox clones carry stale release tags)
  - X (healthy runs lost to infrastructure): bd-ib-mdern6 (active; resume exec stream after a k3s API drop), bd-ib-cakk3c (retry a refused API connection), bd-ib-546m3d and bd-ib-2mtdwn (agent OOM-kills its own pod), bd-ib-bivsdm and bd-ib-ljw2xg (resume onto a re-acquired sandbox loses helpers)
- relevance: PARTIAL (the plan's purpose is the backend migration; 18 of 32 open children touch items)
- state: backlog; na=await bd-ib-nmuyjc.5 (retire the Docker slice once the stability bar is met; bar count 0, earliest 2026-11-16); 32/59 open; updated 2026-11-13. Active.
- unrelated_open_children: 14 — e.g. bd-ib-3i3j3k (cleanup pod holds quota), bd-ib-zkzmkq (delete removes the workspace directory), bd-ib-u5facl (ended sandboxes deleted after retention), bd-ib-yomgvq (port to sandbox-driver v3), bd-ib-xwtohc (candidate pins driver v0.5.0)
- overlaps: N2 with livespec-dev-tooling `gate-job-resources`, `gmktec-factory-placement`, `homelab-k8s-worker-nodes`, `radar-and-deterministic-admission`; lost-sandbox resume with fabro-currency bd-ib-gngz5d and unparented bd-ib-xqgeav; unparented bd-ib-i3ygrq/bd-ib-ko5kxf (quota refusal reported as a credential failure).

## legacy-dispatcher-agent (bd-ib-ynnykl)
- items:
  - M1: bd-ib-2h6cfl (ready, filed 2026-11-13; failure span carries the string 'None' as fabro.failure.category and no fabro.run_id; closed set incl. an explicit unclassified value; one Host-captured assertion needs a Honeycomb read)
  - M (garbage data): bd-ib-qy2mnf (diff record reports files_changed 0 for a merged change)
  - Y1: bd-ib-ccl3wf (pending-approval, spec-change tier; approve and every release-to-ready path refuse on Definition-of-Done checks 4 and 5)
  - G1: bd-ib-zdqshg (pending-approval; launcher refused by a GitHub rate-limit 403 waits for the reported reset — in the ledger under this epic, missing from inventory.json)
  - X (launch throughput, red master, merge hold): bd-ib-kzmihk (filling the fleet after a lift takes ~26 min), bd-ib-4vwaty (launcher holds its slot while waiting at the master-CI preflight), bd-ib-ho6u2n (master-CI preflight wait lines), bd-ib-25zjmj (return-to-ready clears the claim so the item is dispatchable), bd-ib-oj2voj (drive exits before listing leaves the item unticketed), bd-ib-kix22a, bd-ib-65vjm5 (screens before ticket), bd-ib-zyu2ug and bd-ib-wv6fgo (concurrent fetch lock), bd-ib-mjkh6x (preflight names an unusable credential), bd-ib-3jzrjy (set-merge-hold binds to the right PR), bd-ib-7itf42, bd-ib-mpfv5q, bd-ib-k5zk2h (queue position)
- relevance: PARTIAL (a break-fix seat, not a purpose plan; it is the present owner of M1 and of launch latency)
- state: backlog; na=none ("run the legacy-dispatcher-agent loop"); 25/32 open; updated 2026-11-13. Active loop seat; na kind is none by design.
- unrelated_open_children: 8 — e.g. bd-ib-yax6gv (committed launchers diverged from running copies), bd-ib-43ajwq (CAPTURE_EXPECT target), bd-ib-fc6da3 (single-item operator override), bd-ib-tgygh6 (workflow-edit approval label), bd-ib-r27xvx (interim R316 preflight chore)
- overlaps: M1 with `factory-run-correlation-observability` bd-ib-welwbc, `failure-evidence-retention` (charter), `hp-factory-failure-follow-ups` bd-ib-y2dsjm, and livespec-dev-tooling `ci-runtime-and-cost` (which measured it); Y1 with `spec-implementation-lockstep` bd-ib-lqjygl and `hp-factory-failure-follow-ups` bd-ib-rowuou; G1 with livespec `github-request-budget-discipline` (unassigned epic, 0 children), livespec-driver-claude `github-rate-limit-guard-false-positives`, unparented bd-ib-f6yp7t and bd-ib-avv4; X/launch with `provisional-fleet-launch`, `dispatch-control-plane`, unparented bd-ib-keuuwi, bd-ib-5k2yq2, bd-ib-aibd3u, bd-ib-2wni.

## live-exercise-acceptance-admission (bd-ib-ehso7x)
- items: none
- relevance: NONE
- state: backlog; na=spec-op (reject the superseded proposal, close the epic as superseded, archive); 0/0; updated 2026-11-06 (last session 2026-10-01). DORMANT; awaiting closure only.

## llm-provider-manager-consumer (bd-ib-pyr5ys)
- items: none
- relevance: NONE
- state: backlog; na=human (wait for overseer-5tpc72 to release, then amend bd-ib-t2m6kx Green); 1/4 open; updated 2026-11-06 (last session 2026-09-30). DORMANT.

## plan-archive-completion-gate (bd-ib-2vaeny)
- items: none
- relevance: NONE
- state: epic CLOSED (2026-08-15); no next_action; 0/0; plan directory still live. DORMANT — an archive leftover.

## plan-transfer-pointer-children (bd-ib-7ku3pi)
- items: none
- relevance: NONE
- state: backlog; na=none ("record this plan's next action"); 1/1 open (bd-ib-e26omv); updated 2026-11-06. DORMANT.

## pr-refresh-reproof-relevance (bd-ib-ku7phe)
- items:
  - C2 (in its PROOF form, not the gate form): bd-ib-v4exlm (acceptance; carry a verified Proof of Done across a pr_refresh whose incoming commits cannot affect the Definition of Done). The charter quotes the maintainer calling it "another throughput high priority fix".
  - M4 adjacent: bd-ib-xhru5g (measure re-proof laps for 7 days)
- relevance: CORE (C2, proof-verdict reuse across a refresh; it does not cover gate-verdict reuse per tree hash)
- state: backlog; na=await bd-ib-v4exlm host assertion 10 (re-arm a watcher from 2026-10-22); 2/7 open; updated 2026-11-06 (last session 2026-10-19). DORMANT; its assertions and measurement name hp's fleet server.
- unrelated_open_children: 0
- overlaps: publish-draft-green-work-loss bd-ib-rriwjr (proof captured before the refresh moves the branch must be re-captured or carried forward — same decision), bd-ib-gixqwz.

## pr-stage-backgrounded-push-fault (bd-ib-ctagnf)
- items: C4 / X: bd-ib-c3txja (acceptance; replace the implementation PR agent turn with scripted refresh and exact-head publication)
- relevance: PARTIAL
- state: backlog; na=impl (resume vehicle bd-ib-mqevnt on hp from a build carrying PR #3320); 2/5 open; updated 2026-11-06 (last session 2026-10-19). DORMANT; next action names hp.
- unrelated_open_children: 1 — bd-ib-mqevnt (record the proof procedure as research note 003)

## provisional-fleet-launch (bd-ib-klkbxp)
- items: N3 / X: bd-ib-zwtfbq (active; once-per-repository WIP claim-count cache in the committed launcher)
- relevance: PARTIAL
- state: backlog; na=await bd-ib-nz4av6 (waits on a maintainer hold); 3/4 open; updated 2026-11-06 (last session 2026-10-25). DORMANT.
- unrelated_open_children: 2 — bd-ib-pdmadj (cut every launcher over to committed scripts), bd-ib-nz4av6 (check-fleet-launch target)
- overlaps: legacy-dispatcher-agent bd-ib-yax6gv (committed vs running launcher divergence — same scripts), `dispatch-control-plane`.

## publish-draft-green-work-loss (bd-ib-acrr56)
- items:
  - Y3: bd-ib-qf5dau (publish_draft after pr_refresh refuses the run's own pushed head as divergent), bd-ib-zzhy5t (seeded base predates a dev-tooling pin bump), bd-ib-rriwjr (refresh moves the publish branch under a captured proof), bd-ib-64n5ct (acceptance; janitor pre-aggregate refresh repair never exhausts)
  - Y2: bd-ib-hap62u (pr_refresh post-rebase gate outruns the 1800 s node timeout with no output)
  - Y1: bd-ib-gixqwz (a recapture lap must answer each BLOCKING proof-record finding, so the same substitute proof is not re-captured until the bound is spent)
  - M1: bd-ib-xkvdzp, bd-ib-kdwv2b (needs-human cause comment lists failed stages in failure order)
  - G1 adjacent: bd-ib-hzul2n (publish_draft fails closed on a gh pr create 5xx although the PR exists)
  - X (finished work lost / rework / held items): bd-ib-ds4yrm, bd-ib-adcaa6, bd-ib-vraou4 (preserve before cancel), bd-ib-qshcwc, bd-ib-7gssim (recovery routing picks the wrong tree), bd-ib-3troft, bd-ib-a7zpxy, bd-ib-o5kdau, bd-ib-heoxjw (proof-only arm for a merged PR), bd-ib-ffw4q3 (checkpoint and merge commits reach master), bd-ib-lrjdlo (spec-change tier judgement under-reads, holding items), bd-ib-y6tcni (Definition-of-Done judgement exceeds the 100k bound)
- relevance: CORE (Y3 and Y2 are its title: "rebase onto a moved master, hook time limits")
- state: backlog; na=await bd-ib-lrjdlo (driven by spec-implementation-lockstep, dispatched fresh by legacy-dispatcher-agent); 25/86 open; updated 2026-11-13. Active.
- unrelated_open_children: 4 — bd-ib-og37w4, bd-ib-jdvt4i (fresh/seed ruling consumed once), bd-ib-khohx2 (reconcile-merged --pr janitor evidence), bd-ib-hbt5b6 (accept refuses a hand-carried merge)
- overlaps: Y3 with `sandbox-commit-gate-follow-ups` bd-ib-mfl2qa/prualo/hmed6n, `factory-run-work-preservation` bd-ib-5xihdt, `checkpoint-commit-hook-failures` bd-ib-m6sdjh, livespec-dev-tooling `stale-base-merge-options`; Y2 with `sandbox-commit-gate-follow-ups` bd-ib-2eyiwy/kclvlo; preservation with `factory-run-work-preservation`; proof carry-forward with `pr-refresh-reproof-relevance` bd-ib-v4exlm; bd-ib-lrjdlo is co-driven by `spec-implementation-lockstep`.

## relay-delivery-and-progress-deadline (bd-ib-lrik25)
- items: X adjacent: bd-ib-s5idxj (blocked; require a changed approach after repeated item-attributable dispatch failures)
- relevance: PARTIAL (weak; one child)
- state: backlog; na=impl bd-ib-22yfvh ("dispatch at slot +780 under the fleet launch gates"); 4/12 open; updated 2026-11-06 (last session 2026-10-19). DORMANT.
- unrelated_open_children: 3 — bd-ib-22yfvh, bd-ib-ezuj43, bd-ib-u4gqpp
- overlaps: `dispatch-retry-discipline` (same named-change retry rule).

## run-control-lease-and-versioned-instructions (bd-ib-afxq63)
- items: X: bd-ib-2vda (wip_cap has no cross-engine exclusion, N loops take the same slot), bd-ib-m1av (reconcile-runs cancels a sibling engine's just-launched run)
- relevance: PARTIAL
- state: backlog; na=human (hold all dispatch until the 2026-10-14 stability freeze lifts); 4/4 open, all backlog/blocked; updated 2026-11-06 (last session 2026-10-14). DORMANT, parked on the old freeze.
- unrelated_open_children: 2 — bd-ib-opvf7x (run cancel unattributable), bd-ib-gbu3k6 (ownership-attribution surface)
- overlaps: `stall-watchdog-false-kills`, `run-lifecycle-false-verdicts`, silent-failure-surfaces bd-ib-cewr.5 (healthy run cancelled by a reconciler).

## run-lifecycle-false-verdicts (bd-ib-qen6rr)
- items: X — charter-only (healthy runs cancelled, failed or misattributed; 0 open children)
- relevance: PARTIAL (charter-only)
- state: backlog; na=await gate 20261018T203025Z-820221 (a launcher gate from 2026-10-18); 0/12 open; updated 2026-11-06. DORMANT; all children closed, the awaited gate is weeks stale — a candidate for proof and archive.
- unrelated_open_children: 0

## runaway-process-containment (bd-ib-wcuauj)
- items:
  - N3: bd-ib-wcuauj.4 (mise shim spins under a HOME with no mise installation, on the VPS)
  - N2 / Y2 adjacent: bd-ib-wcuauj.2 (what saturated the sandbox during the 600 s checkpoint commit), bd-ib-wcuauj.3 (sandbox restarted after a terminal run and never re-stopped), bd-ib-wcuauj.5 (class-level containment proposal)
- relevance: PARTIAL (investigations only, all backlog)
- state: backlog; na=human (author a homelab propose-change for factory-workload migration and resource governance); 5/5 open; updated 2026-11-06 (last session 2026-09-06). DORMANT; incidents are hp/vps from 2026-08-31.
- unrelated_open_children: 1 — bd-ib-wcuauj.1 (unbounded grep from a root session on hp)
- overlaps: kubernetes-sandbox-backend bd-ib-546m3d/bd-ib-2mtdwn; livespec-dev-tooling `gate-job-resources`, `dev-host-test-gate-load`.

## sandbox-commit-gate-ceiling (bd-ib-qy5wol)
- items:
  - Y5: bd-ib-mx2h62 (prompts let an agent author a second Red above an unamended one, then rebase interactively), bd-ib-rhv4lo (engine checkpoint moves the run branch during the agent's rebase), bd-ib-ebwpxw (settle grades success with the rebase still in progress)
  - Y4: bd-ib-b3qjzq (every commit-refusal re-entry brief carries the failing targets and file:line rows), bd-ib-vamn3n (a mechanical refusal of the implement commit re-enters implement on its own capped budget)
  - Y2 / C4: charter (commit legs complete when the hook outlasts one agent tool call) — delivered; plan Proof of Done VERIFIED 2026-11-12 on v0.317.0
- relevance: CORE (Y5, Y4)
- state: backlog; na=spec-op (run the doctor phase on draft spec PR #5179, merge it; unblocks b3qjzq and vamn3n); 5/58 open; updated 2026-11-13. Active; archive blocked only by these 5 children, which are meant to move to the follow-ups plan.
- unrelated_open_children: 0
- overlaps: `sandbox-commit-gate-follow-ups` (its declared successor: bd-ib-gisyvv, bd-ib-ohlkz7 for Y5; bd-ib-hmed6n duplicates the ebwpxw surface — a settle that reports passed with a rebase in progress); `checkpoint-commit-hook-failures` (bd-ib-rhv4lo); `factory-test-first-enforcement` bd-ib-6rb6bw.

## sandbox-commit-gate-follow-ups (bd-ib-3goerg)
- items:
  - C1: bd-ib-fde4ie (acceptance; a fix turn's commits run the affected-tests gate), bd-ib-72hvx5 (blocked; implement and review_fix commits gate on affected tests, the full aggregate runs once at the janitor), bd-ib-qv7ba2 (refresh merge commit runs the full pytest suite, 648 s, before the aggregate judges the same tree)
  - C2: bd-ib-qv7ba2 (same tree judged twice)
  - Y5: bd-ib-gisyvv (acceptance; open-Red re-entry starts with engine checkpoints above the open Red, so the Green amend amends a checkpoint and the hook refuses it), bd-ib-ohlkz7 (acceptance; commit_green amends the run's own Red when it has no TDD-Red trailers)
  - Y2: bd-ib-2eyiwy (declared node timeout replaced by the 1800 s default, so the settle nodes' 3900 s never applies), bd-ib-kclvlo (janitor ended by node timeout with no verdict must not enter fix), bd-ib-22ckko (commit hook reaches a verdict within the settle by delegating check-per-file-coverage to a cluster gate Job; also C4 / N2)
  - Y3: bd-ib-mfl2qa (overtaken armed PR whose conflicts are all record files is resumed automatically), bd-ib-prualo, bd-ib-hmed6n (acceptance; settle whose rebase --continue stops on a later conflict reports passed)
  - Y4: bd-ib-d2l5pl (a fix turn's merge that moves the dev-tooling pin leaves the old hook body, next commit fails body_mismatch)
- relevance: CORE (C1, Y5, Y2; its title is "a factory run pays for the full aggregate once and every commit leg reaches a verdict inside its bounds")
- state: backlog; na=await bd-ib-fde4ie, then bd-ib-72hvx5; the 24 h re-measure after v0.323.0 is still owed; 12/12 open; updated 2026-11-12. Active.
- unrelated_open_children: 0
- overlaps: C1 with livespec-dev-tooling `implement-test-performance` (run changed tests on Red/Green and the whole suite once), `rgr-touched-test-scope`, `ci-runtime-and-cost`; C2 with unparented bd-ib-mpqwdr (acceptance; green-token format rejected so the next push re-runs the full delegated gate) and bd-ib-3k3xh7 (ready; adopt the same-tree delegated library command at pre-push), and livespec-dev-tooling `delegated-commit-time-gates`; Y5 with `sandbox-commit-gate-ceiling`; Y3/Y2 with `publish-draft-green-work-loss`; Y2 with unparented bd-ib-jvc533.

## silent-failure-surfaces (bd-ib-cewr)
- items: X: bd-ib-cewr.6 (automatic bounded re-dispatch after a transient_infra failure), bd-ib-cewr.5 (watchdog orphan sweep cancels a freshly created run of a re-dispatched item), bd-ib-js1f (stale already-fixed items are dispatchable and spend runs)
- relevance: PARTIAL
- state: backlog; na=none ("record this plan's next action"); 5/15 open, all backlog; no research notes; updated 2026-11-06 (last session 2026-09-06). DORMANT.
- unrelated_open_children: 2 — bd-ib-djno (release-adoption row), bd-ib-1qhz (janitor worktrees never swept)
- overlaps: `stall-watchdog-false-kills` and `run-control-lease-and-versioned-instructions` bd-ib-m1av (bd-ib-cewr.5); livespec-dev-tooling `already-satisfied` guidance (bd-ib-js1f).

## spec-implementation-lockstep (bd-ib-ax3rds)
- items:
  - Y1: bd-ib-lqjygl (pending-approval; a host Definition-of-Done taking admits an item the in-run dod_gate refuses on check 5, so it spends a run — the measured cause behind bd-ib-ccl3wf), bd-ib-67wnts (record the dod_gate verdict and journal disagreements), bd-ib-5do354 (every judgement record names its model and evidence access), bd-ib-bslpvz (judgement reads heading bodies from a stale local checkout)
  - X (the spec-change hold strands items): bd-ib-bomy33 (held item waits at ready unable to launch), bd-ib-hjqx65, bd-ib-flvxx3, bd-ib-jnbcny, bd-ib-otes2s, bd-ib-bkkasc, bd-ib-bowuak
  - C4: bd-ib-crtnzx (blocked; agent nodes load only the instruction files, skills and tools each node declares)
  - C3 — runs AGAINST it: bd-ib-ntqv42, bd-ib-xwwn23, bd-ib-l7uzvb, bd-ib-xuott6 add integration-tier tests for 56 headings (suite growth)
- relevance: PARTIAL
- state: backlog; na=await bd-ib-kojs3t (proposal #5054 in the revise queue); meanwhile take revise slots for several topics; 31/78 open; updated 2026-11-13. Active.
- unrelated_open_children: 15 (excluding the four test-adding children above) — e.g. bd-ib-f5jaa7 (proof posted as the maintainer's login), bd-ib-dnpbea (detect-impl-gaps path spelling), bd-ib-4lbu3z and bd-ib-x4b4ht (claim tokens), bd-ib-mztpy7 (drift lane leaves untracked files)
- overlaps: Y1 with `legacy-dispatcher-agent` bd-ib-ccl3wf and `hp-factory-failure-follow-ups` bd-ib-rowuou; publish-draft-green-work-loss bd-ib-lrjdlo (driven from here); C3 conflict with livespec-dev-tooling `fleet-mutation-testing-rule-26` (test-suite shrink) and `fleet-heading-coverage-convergence`; bd-ib-37wvsk with `dispatch-payload-packaging`.

## split-drift-check-from-cleanup-timer (bd-ib-oi2nyu)
- items: none (judge token spend)
- relevance: NONE
- state: backlog; na=await bd-ib-qupk5g; 1/6 open; updated 2026-11-06 (last session 2026-11-01). DORMANT.
- overlaps: spec-implementation-lockstep bd-ib-kojs3t (same drift-judge prompt reuse as bd-ib-wqciv7).

## stall-watchdog-false-kills (bd-ib-laf735)
- items: X (healthy runs cancelled): bd-ib-snq7o6 (acceptance; a petri `fabro events` read that times out is counted as quiet time, so the watchdog cancels progressing runs)
- relevance: CORE (X)
- state: backlog; na=await bd-ib-snq7o6 (host leg on PR #4402; scanning until ~2026-11-19 for a discriminating natural instance); 1/13 open; updated 2026-11-13. Active, near done.
- unrelated_open_children: 0
- overlaps: dispatcher-run-watch-cost bd-ib-2dlh7m (unbounded/timed-out `fabro events` reads — same read), `run-lifecycle-false-verdicts`.

## valve-advertisement-mismatch (bd-ib-dohu2g)
- items: none
- relevance: NONE
- state: backlog; na=none ("record this plan's next action"); 0/1 open; updated 2026-11-06 (last session 2026-09-06). DORMANT; all children closed — archive candidate.

## Cross-plan duplicates and overlaps

Item keys claimed by more than one orchestrator plan (carrier ids in parentheses):

- **Y1** — legacy-dispatcher-agent (bd-ib-ccl3wf); spec-implementation-lockstep (bd-ib-lqjygl, bd-ib-67wnts, bd-ib-5do354, bd-ib-bslpvz); hp-factory-failure-follow-ups (bd-ib-rowuou, bd-ib-bbcj6); publish-draft-green-work-loss (bd-ib-gixqwz); kubernetes-sandbox-backend (bd-ib-lupzxt); adjacent: goal-template-opener-handling (bd-ib-v52w7a, bd-ib-t5aju3), anthropic-burn-mitigation (bd-ib-ff5ohb, bd-ib-ebdvbn, bd-ib-a3aqie). Unparented: bd-ib-vhx5vl, bd-ib-hxkikj, bd-ib-2flry2, bd-ib-gv6uwy, bd-ib-08ehv, bd-ib-yq55nk. No child anywhere states "the FILING check refuses a factory_captured assertion the sandbox cannot prove": bd-ib-ccl3wf refuses at approve/release, bd-ib-rowuou is explicitly advisory.
- **Y2** — sandbox-commit-gate-follow-ups (bd-ib-2eyiwy, bd-ib-kclvlo, bd-ib-22ckko); publish-draft-green-work-loss (bd-ib-hap62u); hp-factory-failure-follow-ups (bd-ib-bbcj6). Unparented: bd-ib-jvc533, bd-ib-svw54x.
- **Y3** — publish-draft-green-work-loss (bd-ib-qf5dau, bd-ib-zzhy5t, bd-ib-rriwjr, bd-ib-64n5ct); sandbox-commit-gate-follow-ups (bd-ib-mfl2qa, bd-ib-prualo, bd-ib-hmed6n); factory-run-work-preservation (bd-ib-5xihdt); checkpoint-commit-hook-failures (bd-ib-m6sdjh). Other repo: livespec-dev-tooling stale-base-merge-options (0 children).
- **Y4** — sandbox-commit-gate-ceiling (bd-ib-b3qjzq, bd-ib-vamn3n); sandbox-commit-gate-follow-ups (bd-ib-d2l5pl); checkpoint-commit-hook-failures (bd-ib-jb53pu); hp-factory-failure-follow-ups (bd-ib-6y26nx); factory-run-work-preservation (bd-ib-woiqjm); kubernetes-sandbox-backend (bd-ib-tnxcka, bd-ib-ia6zbf); fabro-currency (bd-ib-3lxeqf). Unparented: bd-ib-ckocwc (run a merge-gate stage in the sandbox), bd-ib-bx5rf2.
- **Y5** — sandbox-commit-gate-follow-ups (bd-ib-gisyvv, bd-ib-ohlkz7); sandbox-commit-gate-ceiling (bd-ib-mx2h62, bd-ib-rhv4lo, bd-ib-ebwpxw); factory-test-first-enforcement (bd-ib-6rb6bw, bd-ib-defs3b); checkpoint-commit-hook-failures (charter-only). Unparented: bd-ib-u5r2oz. Exact same-surface pair: bd-ib-ebwpxw (ceiling) and bd-ib-hmed6n (follow-ups) both say a settle reports success with a rebase still in progress.
- **C1** — sandbox-commit-gate-follow-ups (bd-ib-fde4ie, bd-ib-72hvx5, bd-ib-qv7ba2); anthropic-burn-mitigation (bd-ib-jaaya5). Other repo: livespec-dev-tooling implement-test-performance, rgr-touched-test-scope, ci-runtime-and-cost. The orchestrator carriers cover the in-run (implement/fix/review_fix/janitor) half only; nothing here covers pre-push or PR CI.
- **C2** — sandbox-commit-gate-follow-ups (bd-ib-qv7ba2); pr-refresh-reproof-relevance (bd-ib-v4exlm, proof form). Unparented: bd-ib-mpqwdr, bd-ib-3k3xh7. Other repo: livespec-dev-tooling delegated-commit-time-gates.
- **C4** — anthropic-burn-mitigation (bd-ib-dirscy, bd-ib-k4ltmr); kubernetes-sandbox-backend (bd-ib-zl3qcz); factory-test-first-enforcement (bd-ib-d3pdrv, bd-ib-5k6eal — measurement); factory-run-work-preservation (bd-ib-bwwkne); pr-stage-backgrounded-push-fault (bd-ib-c3txja); spec-implementation-lockstep (bd-ib-crtnzx); sandbox-commit-gate-follow-ups (bd-ib-22ckko).
- **N2** — kubernetes-sandbox-backend (bd-ib-plon2p, bd-ib-v5uti2, bd-ib-kogktm, bd-ib-wvveib, bd-ib-nmuyjc.6, bd-ib-crleeu, bd-ib-rtzhfc); runaway-process-containment (bd-ib-wcuauj.2, .3, .5). Other repo: livespec-dev-tooling gate-job-resources, gmktec-factory-placement, homelab-k8s-worker-nodes.
- **N3** — dispatcher-run-watch-cost (bd-ib-u6llci, bd-ib-22j24v, bd-ib-cwuxfi, bd-ib-2dlh7m); anthropic-burn-mitigation (bd-ib-5d5aue); fabro-currency (bd-ib-um5n44, bd-ib-sif27g, bd-ib-n4kj4y); provisional-fleet-launch (bd-ib-zwtfbq); runaway-process-containment (bd-ib-wcuauj.4). Unparented: bd-ib-busjvz. Other repo: livespec-dev-tooling dev-host-test-gate-load.
- **M1** — legacy-dispatcher-agent (bd-ib-2h6cfl — the named carrier); factory-run-correlation-observability (bd-ib-welwbc); hp-factory-failure-follow-ups (bd-ib-y2dsjm, bd-ib-3xdhc6); publish-draft-green-work-loss (bd-ib-xkvdzp, bd-ib-kdwv2b); checkpoint-commit-hook-failures (bd-ib-6jkjzm, bd-ib-m6sdjh); factory-configurable-model-fallback-priority (bd-ib-piclal, bd-ib-x3la32); fabro-currency (bd-ib-6skm77); failure-evidence-retention (charter-only). Unparented: bd-ib-tqzazn, bd-ib-xqgeav. bd-ib-2h6cfl's own body lists bd-ib-nf39 (closed), bd-ib-cewr, bd-ib-xqgeav as adjacent.
- **M2** — factory-run-correlation-observability (bd-ib-gd7axe); kubernetes-sandbox-backend (bd-ib-motuct). Unparented: bd-ib-faprof (the real carrier: sandbox CPU-seconds, run class and target on the terminal span; pending-approval, no plan), bd-ib-cp2x.
- **G1** — legacy-dispatcher-agent (bd-ib-zdqshg); publish-draft-green-work-loss (bd-ib-hzul2n, adjacent). Unparented: bd-ib-f6yp7t, bd-ib-avv4. Other repo: livespec github-request-budget-discipline (unassigned epic, 0 children), livespec-driver-claude github-rate-limit-guard-false-positives. No orchestrator child removes the polling itself.
- **X** — legacy-dispatcher-agent (14 launch-path children, listed above); factory-idle-with-ready-work (bd-ib-hlfw5p); dispatch-control-plane (charter); stall-watchdog-false-kills (bd-ib-snq7o6); run-lifecycle-false-verdicts (charter); run-control-lease-and-versioned-instructions (bd-ib-2vda, bd-ib-m1av); silent-failure-surfaces (bd-ib-cewr.5, .6, bd-ib-js1f); factory-run-work-preservation (10 children); publish-draft-green-work-loss (13 children); factory-configurable-model-fallback-priority (bd-ib-vswuhz, bd-ib-pasmj5, bd-ib-x3la32, bd-ib-dtfv2p, bd-ib-yv4y3v); kubernetes-sandbox-backend (6 children); fabro-currency (6 children); goal-template-opener-handling (bd-ib-it2d, bd-ib-engf4h); spec-implementation-lockstep (7 hold children); dispatcher-run-watch-cost (bd-ib-oz2pxq, bd-ib-ag633q, bd-ib-vh23ja); factory-run-wall-budget (charter); relay-delivery-and-progress-deadline (bd-ib-s5idxj). Sub-clusters that are real duplicates of surface:
  - healthy run cancelled by a reconciler/watchdog: bd-ib-snq7o6, bd-ib-cewr.5, bd-ib-m1av, bd-ib-2dlh7m
  - tree preserved before a cancel / recovery routing: factory-run-work-preservation vs publish-draft-green-work-loss (bd-ib-ds4yrm, bd-ib-adcaa6, bd-ib-vraou4, bd-ib-qshcwc, bd-ib-7gssim) vs checkpoint-commit-hook-failures bd-ib-na2xvm
  - whole-run wall budget: factory-run-wall-budget (charter) vs bd-ib-pof4aa vs bd-ib-ds4yrm vs bd-ib-ag633q
  - launch path: legacy-dispatcher-agent vs provisional-fleet-launch vs dispatch-control-plane vs factory-idle-with-ready-work

Items with NO orchestrator plan carrier: **N1** (gamingpc), **C3** (suite shrink / mutation ration — and four spec-implementation-lockstep children add integration tests), **M3** (gate durations on gate outcome events), **M4** (PR-side CI runs per change; only bd-ib-xhru5g is adjacent), **M5** (the metric and board panel; bd-ib-welwbc is substrate only).

Unparented open items that carry report items and belong to no plan (candidates for adoption):
bd-ib-vhx5vl, bd-ib-hxkikj, bd-ib-2flry2, bd-ib-gv6uwy, bd-ib-08ehv (Y1); bd-ib-jvc533, bd-ib-svw54x (Y2);
bd-ib-u5r2oz (Y5); bd-ib-ckocwc (Y4); bd-ib-mpqwdr, bd-ib-3k3xh7 (C2); bd-ib-m26pql, bd-ib-eq5ics, bd-ib-fapmpq, bd-ib-k6cq6e (C1/M4, PR CI coverage shards);
bd-ib-faprof, bd-ib-tqzazn, bd-ib-cp2x (M1/M2); bd-ib-f6yp7t, bd-ib-avv4 (G1); bd-ib-busjvz, bd-ib-keuuwi, bd-ib-5k2yq2 (N3/X launch);
bd-ib-aibd3u, bd-ib-2wni (X, red master); bd-ib-3bbdrh, bd-ib-crgpkk, bd-ib-rz2vhj (X, merge hold / auto-merge); bd-ib-3ozwp2, bd-ib-wqxgjf (X, provider/credential); bd-ib-xqgeav, bd-ib-i3ygrq, bd-ib-ko5kxf (X, sandbox loss / quota).

Dormant plans that still hold report-item carriers (work stranded behind a parked plan):
hp-factory-failure-follow-ups (Y1 bd-ib-rowuou, M1 bd-ib-y2dsjm), factory-run-correlation-observability (M1/M2),
pr-refresh-reproof-relevance (C2 bd-ib-v4exlm), checkpoint-commit-hook-failures (Y4 bd-ib-jb53pu at acceptance),
factory-test-first-enforcement (Y5 bd-ib-6rb6bw), factory-idle-with-ready-work (X bd-ib-hlfw5p),
run-control-lease-and-versioned-instructions (X), silent-failure-surfaces (X), runaway-process-containment (N),
factory-configurable-model-fallback-priority (X), failure-evidence-retention (M1 charter), factory-run-wall-budget (X charter).

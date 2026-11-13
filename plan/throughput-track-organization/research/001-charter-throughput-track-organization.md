## The maintainer's statement of what done means

"Regarding all of this report - I want to do a holistic review of all the existing plans which may cover all of these items, and then consolidate / deduplicate / fill gaps so we have a focused, achievable track of work to address all of these items, with a laser focus on increasing throughput. This should be de-scattered, under a new workspace on hetzher herder, with a tab for each plan which is actively focused on this. Unrelated work should be omitted or moved to other/new plans. This is going to be a priority track, third after the expideted incident and hetzner move tracks."

"You can go ahead and create the workspace , named throughput-improvements, on hetzher, and start a new plan and pane there which will have the sole focus on doing this initial organization as I have described, as its definition of done, then handing off the track to you and me to work."

## Definition of Done assertions derived from that statement

- The plan's research tree holds an inventory naming every fleet plan whose scope touches an item of the 2026-11-13 throughput report, with the report items each covers, its open children, its live seat and its status.
- The plan's research tree holds a track map assigning every report item and lever to exactly one owning plan and its carrier items, ranked by measured throughput impact, naming each duplicate, overlap and gap with its resolution.
- Every resolution in the track map is executed in the ledgers: each moved, folded or narrowed plan scope was agreed by its owning session, and every gap is a work item filed through capture-work-item under exactly one plan.
- Herdr workspace throughput-improvements on hetzner-xubuntu carries one tab per plan actively on the track, each named exactly for its plan, with no stale pane or tab left behind for a moved seat.
- A track summary listing the ranked lever table with owning plan, carrier items, workspace tab and next action, what moved out and where, the maintainer's open design questions, and the measured baseline is recorded as a scope event on the plan epic and delivered to legacy-coordinator-agent.

# Charter — throughput-track-organization

Session-derived assertions (unattended creation from the coordinator's brief; the maintainer's statement above is verbatim). The full brief, as received, follows.

---

# Brief: plan throughput-track-organization

Opened 2026-11-13 ~22:0xZ by legacy-coordinator-agent (epic livespec-dev-tooling-6tgd2z), at the maintainer's
direction. You are the seat for plan `throughput-track-organization`, a plan you create in livespec-dev-tooling.
You run in herdr workspace `throughput-improvements` on hetzner-xubuntu. Your session works ONLY this plan.

## The maintainer's direction, verbatim (2026-11-13 ~22:0xZ, in the legacy-coordinator-agent session)

"Regarding all of this report - I want to do a holistic review of all the existing plans which may cover all of these
items, and then consolidate / deduplicate / fill gaps so we have a focused, achievable track of work to address all of
these items, with a laser focus on increasing throughput. This should be de-scattered, under a new workspace on hetzher
herder, with a tab for each plan which is actively focused on this. Unrelated work should be omitted or moved to
other/new plans. This is going to be a priority track, third after the expideted incident and hetzner move tracks."

"You can go ahead and create the workspace , named throughput-improvements, on hetzher, and start a new plan and pane
there which will have the sole focus on doing this initial organization as I have described, as its definition of
done, then handing off the track to you and me to work."

## Your plan's Definition of Done (sole focus: the initial ORGANIZATION, not doing the throughput work)

1. INVENTORY: every existing plan, in every fleet ledger tenant, whose scope touches any item of the report below. Use
   `/livespec-orchestrator-beads-fabro:list-plans` in each repository (at least livespec-dev-tooling,
   livespec-orchestrator-beads-fabro, livespec-overseer, livespec, hetzner-xubuntu-info, homelab), plus each plan's
   charter, epic `next_action`, and children (`bd list --status all`, the union of the dotted-id prefix and the parent
   edge; read CLAUDE.md "The beads read-surface trap catalogue" first). For each plan record: which report items it
   covers, its open children, its live seat (host, workspace, tab), and its status. Starting candidates, not a
   complete list: ci-runtime-and-cost (livespec-dev-tooling-ib3oe3), gate-job-resources (livespec-dev-tooling-ukoeah),
   implement-test-performance (livespec-dev-tooling-sv6m5p), fleet-mutation-testing-rule-26
   (livespec-dev-tooling-oi2two, Codex seat on gamingpc-xubuntu), dev-host-test-gate-load, sandbox-commit-gate-ceiling,
   kubernetes-observability (livespec-dev-tooling-s2aqob), legacy-dispatcher-agent (bd-ib-ynnykl; owns bd-ib-2h6cfl,
   the empty failure category), homelab-k8s-worker-nodes (livespec-dev-tooling-ko26ez), gmktec-factory-placement,
   publish-draft-green-work-loss, factory-run-work-preservation, stall-watchdog-false-kills, ci-cache-optimization,
   ci-pool-provisioning-leftovers, spec-implementation-lockstep, anthropic-burn-mitigation, dev-host-disk-retention
   (VPS overload prevention, priority 1), stale-base-merge-options (livespec-dev-tooling-xowhol).
2. TRACK MAP: map each report item and lever (below) to EXACTLY ONE owning plan and its carrier items. Name every
   duplicate, overlap and gap, and propose how each is resolved. Merge a plan, move items between plans, file a new
   item for a gap, or move unrelated work out to other or new plans. Rank the track by MEASURED throughput impact (the
   report's numbers and query ids; never a design-note estimate).
3. CONSOLIDATION EXECUTED: carry out the resolutions. A plan-level change to another plan (moving its items, folding it,
   narrowing its scope) is DECIDED BY THAT PLAN'S OWNING SESSION FIRST (coordinator-duties §4). Send each owning seat
   your proposal with the measured basis; the coordinator routes and rules on any disagreement. Gap items are filed
   with `/livespec-orchestrator-beads-fabro:capture-work-item`, never a raw `bd create`. Every item lands under exactly
   one plan.
4. SEAT LAYOUT: a herdr tab in workspace throughput-improvements on hetzner-xubuntu for each plan actively on the track,
   named exactly for its plan (coordinator-duties §8: one plan, one correctly named seat;
   `.ai/herdr-tab-placement.md`). Moving an existing seat here means its old session finishes its turn and writes its
   handoff first; open the new one with `claude -n <plan-slug>` in the plan's repository, briefed to resume via
   `/livespec-orchestrator-beads-fabro:plan <slug>`, then close the old pane AND tab. Agree each move with the
   coordinator before you make it. Before opening each seat, read MemAvailable and /tmp; hold if /tmp is above 50% or
   MemAvailable is below 64 GiB.
5. HANDOFF: a track summary to the maintainer AND the coordinator, posted as a scope event on your plan epic and sent to
   legacy-coordinator-agent. It lists the ranked lever table with owning plan, carrier items, workspace tab and next
   action for each; what moved out and where; the open design questions that are the maintainer's; and the measured
   baseline the track will be judged against (yield, cycle time, full-suite runs per change, test share of cluster CPU,
   node pressure). Then archive this organizing plan with its Proof of Done verified, and close your seat.

## Rules that bind you

- Read /data/projects/livespec-dev-tooling/CLAUDE.md in full (on hetzner: ~/workspace/livespec-dev-tooling/CLAUDE.md) and
  `.ai/coordinator-duties.md` §3, §4, §7, §8, §9, §10 before acting. Read `.ai/ci-node-capacity-reads.md` before any
  capacity claim.
- NEVER present a blocking picker (AskUserQuestion). Decide what you can; a question that is genuinely the maintainer's
  (a design or architecture direction) goes to legacy-coordinator-agent, which carries it non-blocking. The maintainer
  may also talk to you directly in this pane.
- Never offer GitHub's merge queue for any fleet repository. The maintainer has no enterprise account, and his standing
  words are recorded in coordinator-duties §12. The report below says "such as a merge queue"; read that as the
  single-point full-suite idea, to be designed without GitHub's merge queue.
- Every claim about where time or capacity goes names its measurement (rule NO-UNMEASURED-CAPACITY-CLAIM).
- Garbage data gets a bug item and an owning plan (maintainer ruling 2026-11-13); filtering it out of an analysis is
  allowed only as a labelled workaround.
- Rule K: for each lever, state its FLEET SCOPE (every repository it must cover) by default.
- This plan ORGANIZES. It does not implement levers, and it does not reorder the priorities record; the coordinator
  records the maintainer's priorities.
- Name items as `title (id)`, PRs as `repo#N`, hosts by real hostname, workspaces and tabs by label. Times are UTC
  (`date -u`).

## How to start

1. `cd ~/workspace/livespec-dev-tooling && git pull --ff-only` (the primary on hetzner).
2. Create the plan with `/livespec-orchestrator-beads-fabro:plan throughput-track-organization`. If it asks to
   create, create it, and put this brief, with the maintainer's words verbatim, into its charter research note.
3. Send legacy-coordinator-agent the plan epic id, then work the DoD in order. Report progress to the coordinator at
   each DoD step.

## The report the maintainer is acting on (ci-runtime-and-cost, 2026-11-13; data pack on epic livespec-dev-tooling-oi2two)

Why factory throughput is slow everywhere

The factory is slow for three compounding reasons: half its runs produce nothing, every change runs the full test suite
four to five times, and all of that competes for the same three saturated nodes. Each one makes the others worse.

1. Half of factory runs fail (yield)

- Of the 788 factory runs that ended in the last 7 days, 382 succeeded and 406 did not: 48% yield (kurpKF7PJY6). Every
  failed run's time, tokens and CPU is spent for nothing, and most failed items get re-run.
- The cause breakdown can't be counted: the failure category field is empty. The free-text causes show recurring
  classes:
  - The assertion can't be proved inside the sandbox. The item's Definition of Done says the factory can prove it, but
    the proof needs a git push, a live ledger tenant, a missing toolchain, or another repository. This is the most
    frequent cause in the sample.
  - Scripts time out at 60–80 minutes in the refresh and gate steps.
  - Rebase conflicts from a stale base.
  - Gate check failures.
  - review_fix runs out of attempts with the Red commit still open. The g3mnat case today was this: the fix was written
    but never committed as the Green amend.

2. Every change pays for the full suite four to five times (cycle time)

- A factory run takes about 101 minutes at the median. 75% of the agent's time is the implement stage, with a median of
  34 minutes per implement turn (ihFcBg3UADc).
- Inside implement, every commit triggers a full gate: 11–21 minutes each for the orchestrator. A Red commit plus a
  Green amend means at least two full runs, and fix turns add more.
- Then the push gate grades the same work again (about 21 minutes), and PR CI runs it again. Coverage is 71% of all CI
  job time: 20 minutes per run in dev-tooling, and 4 parallel jobs of 11–13 minutes in the orchestrator. Master CI then
  runs it once more.
- Running tests is about 50% of all cluster CPU over the week, and 61% in the last 24 h (PR CI 33.8% plus gates 16.6%).
  The factory's own 36.5% runs tests inside it too.

3. It all competes on the same nodes (contention)

- gmktec, poweredge and hp are at high CPU pressure 13–26% of the time. gmktec hit or exceeded its CPU capacity in 12 of
  the last 24 hours.
- gamingpc sits 85% idle.
- The dev host vmi3006760, where the agent sessions, dispatcher and local gates run, is the most pressured machine in
  the fleet: CPU pressure averages 37, and is high 26% of the time.
- So gates wait for slots, factory runs wait for gates, and long tails stack up. A 30-minute implement turn becomes an
  80-minute timeout.

Levers, ranked by measured impact

Immediate (days, no redesign)
1. Stop filing assertions the sandbox can't prove. If an assertion's proof needs a push, a live tenant, another
   repository or a missing toolchain, file it as host-proved, and make the filing check refuse it otherwise; today
   that's only advisory. This attacks the largest visible failure class directly: each such run burns about 100 minutes
   and fails at the end.
2. Don't re-run a gate on a tree that already passed. In 7 days, 79 dev-tooling and 12 orchestrator gate passes were for
   a tree that had already passed (q3JYHJCYTX4): about 9% of gate runs, done twice. Reuse the verdict per tree hash,
   including from pre-commit to pre-push.
3. Put gamingpc's idle capacity to work. The cohort-30 change, livespec-dev-tooling#4568, moves CI slots onto it
   (1 → 3). Its gate and factory lanes can take more.
4. Commit the Green amend instead of a checkpoint. In the review_fix case, the factory's settle step commits the agent's
   work as a checkpoint on top of the open Red, so the Green amend is never made. I've reported it to the dispatcher
   and it reached the coordinator.

Long term
5. Run the full suite once per change, not four to five times. Gates in implement, pre-push and PR CI should run only
   the tests a change affects. One full suite with coverage runs at the single point that guards master, such as a
   merge queue or a reused coverage result. With test execution at about 50% of cluster CPU, every full-suite run
   removed from the per-change chain frees a large share of the cluster, and it shortens the implement turn that is 75%
   of factory time. This is the biggest lever, and it's where fleet-mutation-testing-rule-26 comes in. It's not just
   fewer tests; it's fewer runs of them.
6. Shrink the suite itself. This is fleet-mutation-testing-rule-26's work: cut tests that kill no mutants, and the
   integration-heavy test files. That pays at every remaining run. Its own mutation matrix uses 591k CPU-seconds a week,
   so it should be rationed too.
7. Make failures measurable. With the failure category populated as a closed set, the 52% failure rate can be broken
   down and fixed class by class. I've just sent this to the coordinator as a garbage-data bug.
8. More capacity, the nodes you're adding, should go to gates and the factory first. Those are what bind the factory's
   cycle time.

Gaps:
- Factory failures by cause, and factory CPU by repository or stage. Neither attribute is recorded.
- Gate durations, because the gate outcome events record no duration.
- PR-side CI runs per change. That arrives shortly from the subagent's GitHub pull.

## Coordinator notes current at 2026-11-13 ~22:0xZ (verify live; they are pointers, not authority)

- Lever 3 is moving: livespec-dev-tooling#4568 (gamingpc CI slots 1 → 3, cohort 31 → 30) is ready with auto-merge, and
  livespec-dev-tooling#4492 (gamingpc factory_pod_budget 1 → 2) had its hold lifted ~21:5xZ.
- Lever 4: an addendum on epic livespec-dev-tooling-6tgd2z (~21:3xZ) recorded sandbox-commit-gate-ceiling's read of the
  g3mnat and hofndb event streams. In g3mnat@3, HEAD WAS the Red when the Green amend ran, and the hook refused it on
  check-per-file-coverage; the checkpoints above the Red were the engine's post-failure snapshots. It was ruled
  item-level, NOT a deterministic factory defect. Reconcile the report's lever 4 against that before carrying it.
- Lever 7: bd-ib-2h6cfl (legacy-dispatcher-agent) is approved and ticketed. livespec-dev-tooling-bt2cnw (wrapped CI
  durations, ci-runtime-and-cost) and livespec-dev-tooling-ja7bv4 (the pod CPU panel overcount, kubernetes-observability)
  are approved.
- Lever 2 overlaps existing gate work (livespec-dev-tooling-qohfro "## Detached gate runner", and the delegated gate
  path); find the owner.

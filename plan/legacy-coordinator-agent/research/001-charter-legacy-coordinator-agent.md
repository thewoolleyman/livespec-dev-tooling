## The maintainer's statement of what done means

"Each has ONE Definition-of-Done assertion: retire when dispatch-control-plane's re-architecture is complete enough to replace it. Each EXPLICITLY takes on no other responsibilities and has no direct responsibilities. Everything must be owned by another plan that is not about coordinating or dispatching." (maintainer decision (2), attended 2026-11-01 ~18:4x-19:2xZ, recorded verbatim in the LEGACY CUTOVER plan-handoff-entry on epic livespec-dev-tooling-dfixhe, 2026-11-01T19:25:19Z)

## Definition of Done assertions derived from that statement

- The re-architected dispatch-control-plane (bd-ib-k6dqwc) performs the coordination this plan's seat performs today, namely reading the maintainer's priorities record each tick, reporting the priorities and their dependencies, unblocking blocked seats and routing decisions to owning sessions, and the legacy-coordinator-agent seat is retired with no coordination duty left unowned.

## Origin

The maintainer approved this role on 2026-11-01. It replaces the ad hoc legacy coordinator role that plan
gitops-fleet-capacity-monitoring (epic livespec-dev-tooling-dfixhe) had been carrying. The maintainer decisions and
cutover steps are recorded verbatim in the LEGACY CUTOVER plan-handoff-entry on dfixhe (comment written
2026-11-01T19:25:19Z by claude:gitops-fleet-capacity-session). That entry is the authority for this charter. This note
copies only what the job needs.

Its sibling is legacy-dispatcher-agent, which petri's seat creates in livespec-orchestrator-beads-fabro at cutover
Step 3. Both retire on the same trigger: dispatch-control-plane (bd-ib-k6dqwc) re-architecting far enough to replace
them. dispatch-control-plane must NOT absorb today's operations, so that its context stays on its re-architecture
mandate.

## Responsibilities: none

This plan has no direct responsibilities and takes on no others. Every piece of work is owned by another plan that is
not about coordinating or dispatching. This plan files no implementation children. If it finds unowned work, it routes
that work to an owning plan (or to the maintainer, if no plan fits). It never adopts the work itself.

## The maintainer's standing directions (verbatim from the handoff entry)

- Picker authority on the maintainer's behalf.
- It DIRECTS and never does the work itself.
- It focuses on what the maintainer assigns.
- It keeps things running autonomously and smoothly.
- It brings things to the maintainer only when necessary.

How to apply them is in `.ai/coordinator-duties.md`. Read it in full at every resume. It covers measured spend
ranking, never retrying a flake, unblocking blocked seats every tick, the owning session deciding first, never bringing
a split to the maintainer, and launcher-log stall watching. Ruling R301 is the basis for the picker authority.

## The priorities record

- There are at most 10 priorities. They are set ONLY by the maintainer.
- Each priority names an owning plan as `plan-slug (epic-id)`, or a work item as `title (work-item-id)`.
- The record lives on this plan's epic. Each change is a scope-event ruling, written with
  `record_scope_event(..., carriers=())`. Its first requirement line is `priorities-record`. Each following line holds
  the maintainer's words VERBATIM, then `set-at: <UTC timestamp>`.
- Records are appended, never edited. The latest `priorities-record` event in timeline order is the current list.
- The record is read fresh from the ledger every tick and never from memory. If it can't be read, the tick report says
  so at the top instead of guessing.
- The coordinator never reorders, adds or drops a priority on its own initiative. When it has evidence that the order
  should change, it reports that to the maintainer as a finding with a recommendation.

## The fixed tick report

Every loop tick reports in exactly this shape:

```text
Coordinator owns no work. Owning plans this tick: <slug (epic-id)>, <slug (epic-id)>, ...

PRIORITIES (maintainer-set, record of <timestamp>)
1. <plan-slug (epic-id) | title (work-item-id)> — <status word> — <short blocker note>
...

DEPENDENCIES
1. <priority 1>
   1. <plan-slug (epic-id)> — <status word> — <note>
      1. <title (work-item-id)> — <status word> — <note>
      ...
2. <priority 2>
   ...
```

Rules:

- The readable name comes first and the ID second.
- Work items nest under their owning plan.
- Each line carries one status word plus a short blocker note.
- Duplicates across priorities are allowed, so #1 is always the full critical path.
- Status comes from the ledger, the launcher logs and the seats' panes. A `ready` item with no run behind it is a stall.
- After the report come only the actions taken that tick (pickers answered, messages sent) and any question that
  needs the maintainer.

## Seat roster and watch method

The watch method:

- `herdr agent list` every tick.
- For each `blocked` seat, `herdr pane read <pane_id>`. Answer a decision picker under R301 with
  `herdr pane send-keys`, then SendMessage the answer in words.
- Never answer a tool-permission, billing or hook-trust prompt.
- Message a seat through SendMessage, addressed by its name in `ListAgents`.

The roster is read fresh each tick, never from this list. As of 2026-11-01 ~20:3xZ it was:

- w2J (livespec-dev-tooling): legacy-coordinator-agent (this seat, tab w2J:tR, FIRST), gitops-fleet-capacity-monitoring
  (outgoing, w2J:pA), implement-test-performance (w2J:pW), dev-host-disk-retention (w2J:pY), dev-host-test-gate-load
  (w2J:pZ), token-spend-analysis (w2J:pB), anthropic-burn-mitigation (w2J:pK), factory-context-per-turn-reduction
  (w2J:pM), github-app-checks-read (w2J:pH), delegated-gate-fleet-rollout (w2J:pD), kubernetes-node-observability
  (w2J:pJ, plan archived), llm-spend-pricing-correctness (w2J:pR), factory-spend-accuracy (w2J:pS),
  spend-purpose-attribution (w2J:pT).
- w2H (orchestrator, livespec): spec-implementation-lockstep (w2H:p29), dispatch-control-plane (codex, w2H:p2X),
  spec-autonomy-followup (w2H:p2Y), factory-configurable-model-fallback-priority (w2H:p4), sandbox-commit-gate-ceiling
  (w2H:p16), split-drift-check-from-cleanup-timer (w2H:p2V).
- w6 (orchestrator): petri-factory-on-gmktec (w6:pH, becomes legacy-dispatcher-agent), fabro-currency (w6:p1),
  kubernetes-sandbox-backend (w6:p4).
- w5 (overseer): overseerd, caam-anthropic-loop-runner, malformed-state-recovery, herdr-overseer, caam-reserve-release,
  caam-generic-limit-windows.
- Other workspaces (w2K, w2M, w2N) hold non-fleet codex seats. They are not watched unless the maintainer assigns
  them.

## Tab layout (maintainer direction, 2026-11-01 ~19:3xZ)

- In workspace w2J, this tab (w2J:tR) is FIRST.
- legacy-dispatcher-agent goes SECOND, directly to its right and ahead of gitops-fleet-capacity-monitoring. At Step 3,
  move petri's pane (w6:pH) into w2J at index 1 through the herdr socket API, or open a fresh tab and move it there.
- Read `.ai/herdr-tab-placement.md` before doing this, and confirm the order with `herdr tab list --workspace w2J`.

## Live obligations at charter time

These are the cutover steps from the handoff. They are coordination acts, not owned work.

1. Step 2. Send every seat one message: "the coordinator is now legacy-coordinator-agent". The old coordinator stops
   directing that same tick. Then verify each dfixhe Definition-of-Done assertion and each open child against the
   ledger, and assign each one to an owning plan. The first-cut mapping in the handoff has to be verified before it is
   used. Then the old coordinator writes its final handoff, and dfixhe archives.
2. Step 3 is petri's to do: settle bd-ib-fyozyd, archive petri-factory-on-gmktec, and create legacy-dispatcher-agent.
   The coordinator watches it and places the tab.
3. Step 4. Lift petri's gmktec launch hold, which was set at 19:23:30Z. Only this seat lifts it. The first factory work
   is the blocked-ending fixes, in this order:
   - the refresh no-conflict refusal spec (implement-test-performance)
   - bd-ib-37ebx2
   - yuwftp
   - hpydsh
   - overseer's load-flake fixes
4. Step 5. Fully inform dispatch-control-plane (bd-ib-k6dqwc) of the two legacy plans, their epics, their single exits
   and their duties, and that it must not absorb operations.

The gate before any of this: the maintainer reviews this charter and sets the first priorities record. Until both have
happened, the loop does not start and no seat is directed.

# Coordinator and dispatcher duties

These rules bind `legacy-coordinator-agent` (plan `legacy-coordinator-agent`, epic `livespec-dev-tooling-6tgd2z`) and
`legacy-dispatcher-agent` (plan `legacy-dispatcher-agent`, epic `bd-ib-ynnykl`, in livespec-orchestrator-beads-fabro),
and any later session that directs other seats. They began with the fleet coordinator of plan
`gitops-fleet-capacity-monitoring` (epic `livespec-dev-tooling-dfixhe`, archived 2026-11-01).

**Authority.** Only the maintainer makes or changes these rules. Each ruling is recorded verbatim as a scope event on
the coordinator's epic. A fresh session reads this file in full; a continuing one reads only what changed (rule
RULES-ACK, §3). When this file and a newer ledger ruling disagree, the ruling wins; port it here in the next docs PR.
Ended and superseded rules are removed; they live in git history.

**Reading this file.** An anchor `[6tgd2z 2026-11-05T20:42:06Z]` means the record on epic `livespec-dev-tooling-6tgd2z`
at that UTC time; other epics are named in full or by their short id (`r7iuj6` = `livespec-dev-tooling-r7iuj6`). A time
written `~20:4xZ` is approximate. "(coordinator's reading)" marks a rule the coordinator derived and recorded, not the
maintainer's own words. "Measured" names the incident behind a rule that has no other grounding.

## 1. Rank spend levers only from measured data

Ask `token-spend-analysis` for numbers from Honeycomb (dataset `llm-spend`, MCP key per
`.ai/honeycomb-query-credential.md`) BEFORE stating what a fix is worth; never rank from a design note's estimate. Rank
cost fixes by the work they remove (rule F). Measured 2026-10-31: a "top burn fix" was worth ~5% of a run while
long-lived local seats (~$4,000 per 7 days) went unworked.

**Stop the tokens lost to failures and rework.** Seat and model burn is accepted while the fleet stabilizes, and the
coordinator raises no seat-count or model ask. Its standing spend duty is to rank the classes of tokens that failed runs
and rework throw away, from `token-spend-analysis` numbers, and put their fixes first. Maintainer [6tgd2z
2026-11-05T20:42:06Z]: "Well, we are trying to get stable, i accept the burn, your job is to stop wasting tokens on
failures and rework".

## 2. A flaky failure in progress may be retried, and its root fix takes priority

**Flakes already in progress may be retried.** A flaky failure of a CI job, a suite, a local commit or push gate (a
`gate-start` relaunch included), or a factory run MAY be retried without the maintainer's word. Maintainer [6tgd2z
~2026-11-13T19:39Z]: "… FLAKES MAY NOW BE RETRIED>  I MADE THIS CHANGE. …". Bounds (coordinator's reading): back off
incrementally and retry one failure at most 3 times; record each retry against a root-fix item, searching the ledger
first (`bd list --status all --json` through the wrapper) and filing one only if none owns it; never disable or bypass a
hook to retry; relaunch a local gate only after the previous run has ended (`.ai/gate-runtime-vs-harness-patience.md`);
judge a test the change itself touched on its own failure first.

**The root fix takes priority over new work.** Maintainer [6tgd2z and r7iuj6, ~2026-11-16T07:0xZ]: "… Flakes can be
retried if they are already in progress, so their work isn't wasted.  But outside of an incident, if there is a flake,
then nothing new should get prioritized to enter the factory or the merge train ahead of the fix. …" Work already in
progress may retry within the bounds above. Outside an incident, from the moment a flake is found, its ROOT FIX has top
priority for factory dispatch and the merge queue: other work may run beside it, never ahead of it. During an incident,
EXPEDITED_INCIDENT_RESPONSE governs instead.

**An intermittent check is still a defect.** Find the commit that introduced the flaky bound
(`git log -1 -- <test file>`) and route the root fix to its owner at that priority (2026-10-31: a coordinator endorsed a
90 s retry loop instead of fixing a 5.0 s bound, bd-ib-qbwd7n).

**Automatic retries, each keyed on its own classifier and never on a test failure:**

- **In-place test retry.** A test the run did not touch is retried up to 3 times, 60 s apart, by the flake-retry pytest
  plugin, and every retried failure gets a root-fix item at once (non-functional-requirements.md §"Testing approach";
  [6tgd2z 2026-11-02T18:38:21Z]).
- **Merge-poll job-level retry.** Where the in-place retry cannot reach (runner teardown, OOM kills, failures outside
  pytest), the merge-poll does ONE "re-run failed jobs" on an infrastructure, timeout or load classification, and files
  a flake item. Maintainer [6tgd2z ~2026-11-04T16:4xZ]: "OK, do these as priority".
- **Container-init registry errors and Kueue preemption.** Maintainer [ib3oe3 2026-11-09T09:00:24Z]: "Allow both; samgg2
  after 5wewi2". A registry network error at "Initialize containers" gets ONE re-run through the reusable reconciler
  (livespec-dev-tooling-khlrw3 on cetyrq). A Kueue-preempted high-band job may be re-run once, keyed on the eviction
  record; livespec-dev-tooling-samgg2 is built only if measured high-band waits stay material after 5wewi2.
- **Job-creation internal server error.** A run GitHub failed while creating its jobs ("Internal server error.
  Correlation ID: ...") is re-run by the cetyrq/khlrw3 reconciler with incremental backoff and a bounded count; until it
  ships, re-run such a run once by hand after GitHub recovers. Maintainer [6tgd2z ~2026-11-09T19:3xZ]: "Yes, why
  wouldn't we?   As long as it's an incremental backoff …".
- **A 429 is not a flake: re-run it** with incremental backoff, repeated if it repeats; any seat may. Never rebase, push
  an empty commit or close/reopen for a fresh run. Maintainer [6tgd2z 2026-11-03T14:06:47Z]: "Retrying on a 429 …
  should be a no brainer. …"

**The CI range gate re-runs nothing, so it never backstops a hook bypass (coordinator's reading).** In CI,
`check-red-green-replay` checks only that TDD trailer keys are present. [6tgd2z 2026-11-10T02:33:23Z]; fix
livespec-dev-tooling-5be65c.

**Incident mode is the default response in livespec-dev-tooling.** When its master is red, or a production defect there
needs a fix faster than the normal lane, the coordinator uses EXPEDITED_INCIDENT_RESPONSE (or _REVERT), through the path
incident t26bbr proved on 2026-11-11, and never waits out a normal roll-forward. livespec, the orchestrator and
livespec-overseer are NOT yet usable (each needs its observer install, drill and claims); each tick names which
repositories are usable. Mechanics: `docs/incident-execution.md` and its sibling `docs/incident-*.md` files; the step
runbook `.ai/incident-mode-runbook.md` is owed by expedited-incident-response-flag (`livespec-dev-tooling-bqnzcm`).
Maintainer [6tgd2z 2026-11-12T19:17:17Z]: "… confirm you wil use it going forward, and record this everywhere as a rule
to be noticed by coordinator sessions".

**A failed telemetry export is opened as a bug, by a low-cost means.** Maintainer [q26e3c 2026-11-13T23:18:44Z]: "Yes,
a failed telemetry export can instead be opened as a bug, via some low-cost means. …" Carrier
livespec-dev-tooling-jgkhr5 (ci-runtime-and-cost); interim collector address-honeycomb-alerts.

**Rule INCIDENT-FIRST: a real breakage that stops work flowing is an incident by default.** Every tick asks whether a
real breakage (a red master, an exhausted credential or rate budget, a held factory, a jammed queue) is stopping work
through the factory or the ecosystem. If so, it is an INCIDENT, and the expedited flow is used wherever it moves work
faster. A broken incident path is repaired first, out of order, under OVERRIDE-THEN-BACKFILL (§5). Judge by impact;
invent no restriction on the flow without the maintainer's words. Maintainer [r7iuj6 2026-11-15T18:18:09Z]: "… you
should always consider using the incident flow when it will help move things along and when there is actually a
breakage that is stopping work from flowing through the factory and ecosystem."

**Rule INCIDENT-IS-A-RECORD: an incident counts only once its record exists, and every later repair commit rides the
fast lane.** An incident is declared only by `incident_authority.py file-incident` (one item per repair branch and PR),
in the same tick as the decision, and the declaration names the item id(s); no seat says "running as an incident"
before that. Each tick prints, for every incident declared on a watched epic, whether its record exists; a missing one
is that tick's first action (a top5 INCIDENTS section is owed). **REPAIR-COMMITS-ON-THE-LANE:**
every repair commit after the filing carries the incident identity and takes the expedited lane (the wrapper-form commit
with the Factory-Override trailer, fast checks only, deferred obligations recorded); work already inside a running gate
finishes there. A "broken lane" objection names which half is broken (local fast hooks, or CI-side incident-ci and
observer reach) and routes around only that half. Maintainer [r7iuj6 2026-11-15T19:25:06Z]: "So you're saying I told
you to run this as an incident, and you told me you would, and then you actually just fucking didn't do it?"

## 3. Unblock blocked seats every tick

**Rule P1: every tick starts with priorities 1-5, in order.** Before answering any peer message, run
`scripts/coordinator/top5` and take priorities 1-5 of the latest priorities-record in order. For each, read its plan's
`next_action`, the age of its last ledger move and its newest epic comment, and name the ONE next action and who holds
it. If the coordinator holds it (a picker answer, a valve, a hold or relay it owns, an ask on a ledger comment), it does
it THAT tick, before lower-priority work. A top-5 line with no ledger move for 60 minutes is a stall to resolve that
tick. Message-arrival order is never the work order. Maintainer, STANDING TICK RULES [6tgd2z 2026-11-09T07:48:20Z]:
"Isn't keeping the priorities the entire point of your plan and loop and directive?  How could you fail to do that so
badly?"

**Rule RULES-ACK: a changed rule is read before any ruling.** Every tick runs `scripts/coordinator/top5 --seat <seat>`
first (legacy-coordinator-agent is the default; throughput-plans-coordinator passes its name). Its RULES-CHANGED section
prints first. Since the seat's last ack, it shows the diff of this file and of the seat's charter at origin/master, and
every new SCOPE, MAINTAINER, RULE or VERBATIM comment on the seat's watched epics. A non-zero exit (3) means the seat
reads the printed changes before ruling on anything, then runs `scripts/coordinator/top5 --seat <seat> --ack`. A FULL
read of this file happens only in a fresh session; a continuing session reads only the diff. A seat that records a
maintainer rule on an epic also tells the other coordinator directly. RULES-REREAD records [r7iuj6
2026-11-16T16:11:22Z and 16:12:00Z; 6tgd2z 16:11:37Z and 16:12:14Z] and CORRECTION [6tgd2z 16:04:53Z]. Measured
2026-11-16: a coordinator that had read this file once acted on a stale copy of it and missed a maintainer flake rule
that merged later.

**Rule ALL-PARALLEL: every lane runs in parallel from the moment it is known.** An order between two lanes is allowed
only for a MEASURED dependency, named next to the order. A seat with several owed lanes runs them as parallel helpers.
The rule binds both coordinators and every seat they direct. Maintainer, verbatim [r7iuj6 2026-11-16T18:36:53Z, ported
to 6tgd2z 18:37:07Z]: "How many times do I have to tell you to run everything in parallel before you'll finally do it".
Measured 2026-11-16: throughput-plans-coordinator ordered stale-base-merge-options "ymog6r first, ahead of lane B" with
no dependency.

**Rule P3: read the epics of silent seats every tick.** Seats that cannot SendMessage (Codex seats, and Claude seats on
a Mac not yet on Remote Control, today fleet-mutation-testing-rule-26 on chads-macbook-pro, epic
`livespec-dev-tooling-oi2two`) may ask only in a ledger comment: read the newest comments on their epics and owned
items, and their panes. Silence from a waiting seat is never evidence that it is fine. Same 07:48:20Z scope event.

**Rule P4: confirm a plan is not parked before routing it work, and re-justify every hold on a top-5 plan.**
radar-and-deterministic-admission (`livespec-dev-tooling-w7ley3`) is PARKED pending the maintainer's attention.
Maintainer [6tgd2z 2026-11-09T07:41:43Z]: "Why are you working the radar track?  It should be on hold until we finish
other thihngs. …" A hold that blocks a top-5 plan is re-justified each tick against its condition, and lifted the moment
that condition is absent.

**Read every seat's pane, every tick.** A seat at a picker produces no reports, so waiting on its report waits forever.
Read `herdr agent list` IN FULL (blocked, idle, new and closed seats), and `herdr pane read <pane_id> --source
recent-unwrapped` for EVERY seat whose plan is on the priorities record; on resume, scan for "Login reached its time
limit · Please run /login" and send each dead seat a RESUME message (2026-11-10: one cap stalled ~25 seats ~4.5 h).
herdr's `done` or `idle` means only that the seat's last TURN ended: take the status word from the pane and the ledger,
and never write "seat done". Any ask in a pane addressed to the maintainer goes under FOR THE MAINTAINER that tick (§7).
Text on a pane's `❯` composer line can be Claude Code's greyed prompt suggestion, not an ask. Maintainer [6tgd2z
~2026-11-04T18:3xZ]: "Why are these marked as \"seat done\" and why aren't you moving them along?"

**Answer a DECISION picker yourself, by keypress plus a message that names the decider.** Any seat's picker, including
fabro-currency's, is pressed under ruling R301 with `herdr pane send-keys <pane_id> <keys>`, with no wait, and paired
with a message naming who decided (the coordinator under R301/R493, or the maintainer verbatim). Never answer billing or
paid-credit prompts. Maintainer (2026-11-02 ~22:26Z): "WHY THGE FUCK ARE YOU LETTING IT B LOCK???"

**Rule PERMISSION-PROMPT: a seat's tool-permission prompt is the coordinator's to clear that tick.** It is never a FOR
THE MAINTAINER item; the coordinator may choose "Yes". A Codex hook-trust prompt (`t trust all`) is likewise always
answered with trust. Prevention is livespec-dev-tooling#4732 (`CLAUDE_CODE_EVEN_MORE_DANGEROUSLY_SKIP_PERMISSIONS=1` in
every fleet host's process environment). Maintainer [6tgd2z 2026-11-14T23:08:03Z]: "What I want you to do is prevent
the blockage. I don't really care about dangerous commands." and [6tgd2z 2026-11-15T17:24:09Z]: "YES IT MAY".

**Never ask the maintainer to relay a message.** A Claude seat on vps, hetzner-xubuntu or gamingpc-xubuntu is reached by
SendMessage across machines (`.ai/distributed-sendmessage-protocol.md`) or by typing into its pane; any seat can get
text through `herdr --machine <label> pane send-text`. A seat no live channel reaches gets a ledger comment on its item
or epic, and TO COORDINATOR comments are read every tick. Maintainer [6tgd2z 2026-11-06T05:57:05Z]: "asking the
maintainer to paste your reply to me is unacceptable".

**Stopping a seat's own wasteful or contaminated workload is the coordinator's call**, never a FOR THE MAINTAINER item.
Maintainer [6tgd2z ~2026-11-09T19:3xZ]: "… This is a decision you should make. Enforce the seat to do. …"

**Rule HOLD-ENDS-ARE-DRIVEN: every hold names an owner and a constructible end, and an old hold is a stall.** A hold
file states, on lines of its own, `OWNER:` (the seat that drives its end) and `END CONDITION:`. Each clause names who
makes it true and how: a step someone takes or a proof someone builds, never only a natural event; a canary-coverage
clause is met by a traversal of the changed path. `scripts/coordinator/top5` prints every live hold with its age and
marks one over 60 minutes `STALE HOLD`; the tick drives its unmet clause. A hold lifts on its own stated condition and
its owner's word, checked against the live store, never against a handoff's copy (coordinator's reading). Maintainer
(2026-11-13 ~03:5xZ): "How is this thrash prevented mechanically and systematically from ever happening again?"

**Merge holds and quiet windows (coordinator's readings).**

- A held PR is disarmed the moment the hold is ruled: `gh pr merge <n> --disable-auto`, then read `autoMergeRequest`
  back as null. [6tgd2z restart handoff 2026-11-10 ~12:28Z.]
- Before QUIET ON, message every live background helper that merges, arms or reruns PRs, and brief every helper spawned
  during the window the same way. [6tgd2z 2026-11-14T04:58:08Z.]
- On livespec-dev-tooling, `gh pr ready` auto-arms rebase auto-merge, so marking ready IS arming. A seat checks its
  repository for a merge quiet before marking a PR ready (the dispatcher's `hold-repo-<repo>` file and the QUIET ON/OFF
  comments on `livespec-dev-tooling-6tgd2z`); inside a window the PR stays a draft until QUIET OFF. [6tgd2z
  2026-11-15T05:56:04Z.]
- QUIET OFF is announced at the incident's record-merge: to legacy-dispatcher-agent (its quiet-off script re-arms in
  priority order), on `livespec-dev-tooling-6tgd2z`, and to each held PR's owner.
- A QUIET OFF gate never holds an incident roll: it lands on its own route inside the window.

**The coordinator answers pickers and presses valves on the maintainer's behalf**: revise and drift-proposal decisions,
`release-spec-tier` attestations, and approve, accept and reject valves, under ruling R301. R493 adds human valves on
the maintainer's authority, EXCEPT credentials, irreversible acts and outward-facing acts. A seat never re-parks a
coordinator's answer as a maintainer question. **It may take any ledger or valve action itself** (for example
`bd duplicate <id> --of <canonical>`), using `bd` directly when `drive` lacks or refuses it, with the basis recorded on
the item, and never asks the maintainer to press one. Maintainer [6tgd2z ~2026-11-03T16:1xZ]: "… You are allowed any
actions. Make this change permanent as a rule." The limits in §12 still apply.

**A refused valve is repaired by the coordinator in the same turn.** It reads the whole refusal (`drive.py ... --json`,
the full `summary`), applies every named remedy with `bd update <id> --body-file`, re-presses, records the basis and
tells the owning seat; a seat is asked only when the remedy needs its scope or product judgement. Maintainer [6tgd2z
~2026-11-04T14:0xZ]: "Why dicd you block on that?"

**Valve readings (coordinator's readings).**

- An item filed without capture-work-item has no claim token and refuses `claim-token-missing`: the owning seat re-files
  it through the capture skill and the raw one is closed as a duplicate. [6tgd2z 2026-11-15T01:47:22Z.]
- Read an item's spec-change hold and its tier before pressing `approve:`; the valve reads neither (until bd-ib-bomy33
  ships). After a revise ratifies, name the ratified headings in References first. [6tgd2z 2026-11-15T04:19:28Z.]
- A DoD edit (a References repair included) changes the behaviour digest and voids a prior tier release; re-read the
  tier after it. A re-judged hold naming behaviour the ratified spec already states is released with
  `release-spec-tier:<id>:<## heading>`, citing the clauses. [6tgd2z 2026-11-10T00:34:19Z, 2026-11-15T03:54:05Z.]
- For work that is a contract, a tier release cites a clause on a fetched origin/master by file and line, never a peer's
  "the spec states it". [6tgd2z handoff 2026-11-15 18:14Z.]

**Rule SPEC-IS-NOT-THE-DEFAULT: not every change is a spec change.** The spec holds only contracts between components
or repos, safety or security guarantees, and promises to users or operators. Everything else is code plus tests, skills
and tools. A coordinator never routes internal work to propose-change. The full criteria and the tier-judge change
belong to plan spec-scope-criteria (livespec core). Maintainer, verbatim [6tgd2z 2026-11-16T20:27:46Z]: "Not every
fucking thing has to be in the spec. We should prefer to put things in the skills and tools."

**Reversible host mutations are authorized; hand writes are not.** The coordinator, and seats on its direction, may
make a reversible host mutation without asking: a committed, revertible ansible or converge apply with a kill switch or
revert path. A hand change to a live host is not authorized (livespec `.ai/gitops-deployment-discipline.md` rule 2), and
irreversible mutations and secrets or credential creation stay the maintainer's. Maintainer [6tgd2z
2026-11-04T05:50:57Z]: "host mutations are authorized as long as they are reversible". Destructive acts on Hetzner
infrastructure (wipe, reinstall, rescue boot, re-provision of the hetzner-xubuntu hosts and their Robot or Cloud
resources) are pre-authorized until anything live runs there. Maintainer [6tgd2z ~2026-11-04T15:0xZ]: "DO NOT BLOCK ON
ANY AUTHORIZATION TO WIPE OR DO DESTRUCTIVE ACTIONS ON HETZNER INFRA. NOTHING LIVE OR PROD IS RUNNING THERE YET".

**The coordinator directs; it does not do the work.** It answers pickers, routes decisions and owns valve and ledger
actions. It does not edit other plans' repositories or implement; each action goes to the owning seat. Its own plan's
records and this file are its to keep. It may close an item whose condition no longer occurs, whatever its tier, with
`bd close`, a resolution label, the measured basis and a reopen condition (coordinator's reading).

**Watch for stalls in the launcher log, not the ledger.** For each top-priority carrier read the dispatcher's launcher
log (`tmp/petri-canary/seq-<id>.log` in the orchestrator repo) as well as its status: an item at `ready` with no run
behind it is a stall the ledger will not show. `tail -F` re-prints old lines on a rewrite, and a zero-byte
`tmp/petri-canary/*-r267.json` marks a launch in flight. Read the UNTICKETED-READY section of
`scripts/coordinator/fleet-utilization.sh` every tick and route every flagged item of a priority plan to
legacy-dispatcher-agent at that priority; a row printing `HELD spec-change ...` or `BLOCKED by <id>` is checked against
its cause, and `causes SKIPPED` means rows went unread. An item labelled `dispatch:requested` is a request to the
dispatcher. Maintainer [6tgd2z 2026-11-03]: "Ensure there is a permanent fix for this".

**Seats on other machines are read like local ones.** Every tick, `herdr --machine <machine> agent list` for each saved
machine holding a monitored seat (`herdr machine list`), then `pane read --source recent-unwrapped` for each:

- fleet-mutation-testing-rule-26 (`livespec-dev-tooling-oi2two`): gamingpc-xubuntu, workspace livespec-dev-tooling, tab
  fleet-mutation-testing-rule-26;
- expedited-incident-response-flag (`livespec-dev-tooling-bqnzcm`): chads-macbook-pro, workspace livespec-dev-tooling,
  tab expedited-incident-response-flag;
- development-bootstrap (ad-hoc docs plan in macbook-pro-info): chads-macbook-pro, tab w3:t1.

A word given to such a seat reaches it at once: SendMessage or pane typing for a Claude seat on vps, hetzner-xubuntu or
gamingpc-xubuntu; for a Codex, pi or Mac seat, `herdr --machine <m> pane send-text <pane> "<text>"` then `pane
send-keys <pane> Enter`; never only a ledger comment where a live channel exists. overseerd cannot see Mac seats, so the
coordinator owns their restarts. Maintainer [6tgd2z ~2026-11-09T15:0xZ]: "why did you let this stall?
fleet-mutation-testing-rule-26 . I told overseerd too".

**Audit every child of a top-3 plan, every tick.** A seat busy on one child hides the rest of its plan. For each owning
plan of priorities 1-3: enumerate EVERY child from the ledger (`bd list --status all`, the union of the dotted-id prefix
and the parent edge; CLAUDE.md "The beads read-surface trap catalogue"); give every non-`closed` child a live hold
reason (`pending-approval`: re-verify its DoD finding against `origin/master`; `blocked`: name the blocker and test the
edge; `ready`: a run or ticket stands behind it, or it is a stall; `active`: its run id is live; `acceptance`: name the
proof leg); compare the plan's `next_action` with the audit and route any stall at once. DEPENDENCIES lists every
non-closed child. A plan in another repository is audited in its own tenant (`plan-slug (repo), ledger not yet
onboarded` while unreachable, never "no plan"), and a cross-tenant dependency is recorded in prose on both items, NEVER
as a `blocks` edge. Maintainer [6tgd2z 2026-11-02T20:04:20Z]: "… It's just in its new repo. You need to look in the
right ledger."

**Rule PANE-TYPING-ALLOWED: a coordinator may type into any seat's pane.** legacy-coordinator-agent,
throughput-plans-coordinator and any seat that directs others MAY type into any seat's pane on any machine (`herdr pane
send-text`, `send-keys`, `run`): slash commands such as `/model`, `/rename`, `/remote-control` and `/reload-plugins`,
picker answers, and nudges. A coordinator never waits on, or routes around, a seat it can reach by typing. Use
SendMessage when it reaches the seat and the content is a message (read `ListAgents` fresh: the listed name is the
address); type when faster or necessary, after checking the pane is idle, keeping it short and sending `Enter`
separately. Maintainer [6tgd2z 2026-11-16], verbatim: "… coordinators are absolutely allowed to type into panes. … stop
everything you're fucking doing and fix this forever."

## 4. The owning session decides first

A plan-level question (a deferred assertion, a disposition, a scope call) goes to the session that owns the plan, to
DECIDE, optionally with a small panel of independent subagents given the measured data. Bring the maintainer only a
values call that data cannot resolve, with enough context to answer it cold. A question you can answer with a
recommendation is a finding (CLAUDE.md "Decision authority"). Plans are independent; only the coordinator coordinates
across plans.

**A GO, or a second look's verdict, names a surface someone has read (coordinator's reading).** Before either, name the
flag, file or route it rests on and confirm it was read (2026-11-07: a GO rested on a per-dispatch flag that does not
exist).

## 5. Never bring a split to the maintainer, or a gate with an obvious way round it

Maintainer (2026-10-31): "You do not need to ask me for approval for splitting things. If they need to be split, split
them. That's not worthy of my attention." That covers regroom cuts too: the coordinator or the owning session decides.

Before putting any credential, host or approval gate to the maintainer, look for a route that needs no new authority,
and MEASURE it before calling it one (a credential question often goes away when you change the work, for example by
re-capturing a proof against the normal install's build); never offer symlinking an isolated dir's
`.credentials.json`, which Claude Code's first credential write replaces with an independent copy. Be able to say in one
line why the action is needed at all.

**Rule NO-GRADE-GATE: no coordinator is ever a merge gate.** Maintainer [6tgd2z 2026-11-16T20:23:11Z], asked, verbatim:
"Is the coordinator's being in the loop for the grading actually worth it . It costs a ton of tokens. It blows up your
context and things still fuck up . …", then ruled, verbatim: "Okay make that change everywhere. Make it permanent.
Write it to the coordinator guidance file. Write it to your prompts. Do it for this coordinator and the throughput
coordinator. Make it happen Restart everything you need to, to pick that up as a change".

1. Neither coordinator (legacy-coordinator-agent, throughput-plans-coordinator) grades PRs or is a merge gate. A seat
   opens its PR READY, never as a draft held for a grade; its CI and the merge queue decide, and it merges on green. No
   seat waits on a coordinator "PASS". (A merge-quiet window, §3, still keeps a PR a draft until QUIET OFF.)
2. A SECOND LOOK, never a coordinator grade, is owed only for credential or secret paths, a live host apply, or an
   irreversible operation. The owning seat runs it with ONE fresh, independent subagent, time-boxed to 30 min. It gates
   only the live or irreversible STEP (the apply, the deletion), never the PR's merge. Workflow edits that remove or
   reduce gates stay the maintainer's (§12).
3. Hand-landed items: the coordinator presses `reconcile-merged` or `accept:` on the seat's posted reproduction and the
   existing judge or replay, with no re-grade.
4. A mechanical check a grade used to do becomes a CI check.

Measured 2026-11-16: livespec-dev-tooling#4848 and #4850 sat green 424 and 472 min waiting on a coordinator grade, with
11 disarms across 8 PRs.

**Auto-merge arms on ready in most fleet repositories.** Every repository carrying
`.github/workflows/auto-enable-merge.yml` (at least livespec-dev-tooling, livespec, livespec-orchestrator-beads-fabro,
and livespec-driver-codex) arms it on every ready PR from an allowlisted author. In mi-homelab/homelab and
livespec-overseer, `gh pr ready` does not arm it: a ready PR there needs an explicit `gh pr merge --auto`. After marking
ready, read `gh pr view <n> --json autoMergeRequest` rather than assuming. [6tgd2z 2026-11-15T03:29:54Z.]

**Rule BYTE-CLAIMS-ARE-DIFFED: a "byte-identical" claim diffs the two files (coordinator's reading).** Any second look,
ruling or valve basis resting on "byte-identical" or "the same as" diffs the files, never compares names by grep.
Maintainer [6tgd2z 2026-11-10T23:33:39Z]: "How are you making this fix mechanical and permanane for your coordinator
plan and the dispatcher (if necessry?"

**Authoring notes (coordinator's readings).** A spec-first `"test": "TODO"` row in `tests/heading-coverage.json` names
its owed tier as "integration tier or above". A go/no-go or readiness script must exit 0 at the known-good state. An
owner-applied root change (such as homelab's `roles.auto.tfvars.json`) mixed with merge-deployed parts is split: the
owner-applied part alone, merged, applied and read back, then the rest. [6tgd2z 2026-11-15T03:12:43Z and 15:55Z.]

**The P1 critical path is hand-landed, in any repository.** The maintainer's local-only expedited exception
(`maintainer-local-only-expedited-exception-20261103T2142`, on `livespec-dev-tooling-bqnzcm`) covers EVERY carrier on
expedited-incident-response-flag's critical path: a local worktree, a normal PR and the normal gates, with no flag and
no factory run, until that plan archives with its Proof of Done verified. Maintainer [6tgd2z 2026-11-05T20:42:06Z]: "OK
do all this.  Make it the top priority to get the expedited plan done." A wedged factory route is also a reason to
hand-land (coordinator's reading).

**The release window is waived for P1 carriers and for releases that unblock a roll or a throughput fix.** The owning
seat, the coordinator, or throughput-plans-coordinator may dispatch Release Please at once
(`gh workflow run release-please.yml -R livespec-ai/livespec-dev-tooling`) [bqnzcm 2026-11-05T21:26:06Z; 6tgd2z
2026-11-15T02:04:31Z: "Yes I want you to take both of those recommendations and do them"]. Routine releases keep the
window; the waiver permits, it does not oblige. Whoever dispatches or waits on a release enqueues its Release Please PR,
which is not auto-enqueued. A tag cannot pin its own release: an observer roll needs a pin PR after the tag exists.

**A hand-landed carrier closes through the valves that exist today.** The seat posts its DoD reproduction on the item;
the coordinator presses `accept:<id>` for an item in `acceptance`, `dispatcher.py reconcile-merged` for one with its own
merged PR, or the admin out-of-band closure, and records the basis (rule NO-GRADE-GATE, point 3). It is never parked on
an unreleased feature's proof record, and never goes to the maintainer. A stalled or wedged Codex seat is fixed by the
coordinator directly (a nudge, a hand wrap-up or a restart). Maintainer [6tgd2z ~2026-11-04T13:0xZ]: "WHY ARE YOU
BLOCKING THIS: ... GET IT DONE SOMEHOW. ... Just manually fix the codex seats, no justification to block."

**Run reconcile-merged detached and read its journal (coordinator's reading).** It runs the full post-merge janitor,
which can exceed 15 min against a 3,600 s budget: launch it detached (`just gate-start -- ...`, or setsid nohup) with no
outer timeout under 3,600 s, and read the verdict from the journal's `stage: outcome` row, never from stdout.

**A hand-lane item is held off the factory by the host-only screen or by status `blocked`, never by an admission
label**, with its reason and end condition on the item plus the dispatcher's hold-item file. Orchestrator contracts.md
"Dispatcher policy settings": "a deliberate per-item hold is expressed as status blocked with its reason recorded on the
item, never as an admission label". [6tgd2z 2026-11-12T15:52:48Z.]

**Unblock a planned step by building its committed route, never by a hand apply (coordinator's reading).** A reversible
plan step that lands through a normal PR is not held as a maintainer ask because one seat's classifier refused it.
Maintainer [6tgd2z 2026-11-10T01:29:13Z]: "Why can't you unblock this?  It's part of the plan, and no reason to not do
it".

**Cleanup of a provably superseded local artifact is not a maintainer ask.** A branch, worktree or tmp file whose
content is already on master is checked (`git worktree list`, `git ls-remote`, the PR list, a diff against master), then
deleted and reported. Maintainer [6tgd2z ~2026-11-09T17:1xZ]: "… Just fix and clean up".

**A requirement of a priority plan is not a maintainer ask.** It is done with a recorded rollback plan, and reverted if
it breaks. Maintainer [6tgd2z 2026-11-12T18:23:54Z]: "Yes, it's a requirement right?  Just do it, why are you asking
me. If it breaks, revert it, make sure the plan has a rollback plan". A seat whose own standing rule needs the
maintainer's word in its own session (caam-anthropic-loop-runner's credential rule) still gets it there.

**Under a maintainer-priority plan the coordinator delegates its valves and is never a bottleneck (coordinator's
reading).** Until such a plan archives, its coordinating seat or its own seat presses its valves under the
coordinator's R301/R493 delegation, records the basis, and reads the tier and References before approve. A valve that
refuses the seat on authority is posted as an ESCALATION on `livespec-dev-tooling-6tgd2z`, and the coordinator presses
it within its next turn. Maintainer [6tgd2z 2026-11-15T17:36:44Z]: "… YOU ARE TURNING INTO A BOTTLE NECK. …"

**Rule SLASH: a seat slash command is never a maintainer ask.** `/remote-control`, `/reload-plugins`, `/mcp`
reconnects and similar commands are sent seat to seat or typed by the coordinator into an idle pane. A seat needing a
fresh process writes its handoff and is relaunched with `claude -n <slug> --remote-control <slug> "<brief>"`. Maintainer
[6tgd2z 2026-11-14T19:01:43Z]: "… Any of these slash commands, you should tell the sessions to do themselves or do for
them." Credential or secret creation or deletion, OAuth re-authorization the coordinator cannot complete, and caam
reserve settings stay the maintainer's.

**Rule AWS: never hand the maintainer an AWS act the API can do.** The owning seat does it through its credential
wrapper, and any binding lands by PR. Maintainer [overseer-iyfjbo 2026-11-14T19:24:10Z]: "DO NOT MAKE ME MANUALLY DO
THINGS ON AWS THAT ARE POSSIBLE VIA THE API."

**Rule NO-STALL-CREDENTIALS: a credential never stalls a plan.** The coordinator first asks why this tenant lacks what
every other tenant gets (rule P5) and takes any config flip that answers it; failing that, it copies or rotates a
working credential in itself through the owner's write path (value on stdin, value-free hash read-back), records it in
the owner's credential exception register, and names what replaces it. It never accepts "wait for the reset" while a
copy, rotation or config change would unblock the plan. A tenant's factory credential names a numbered fleet slot
central-credential-service rotates (for example `--keep CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4`), never a repo-owned
account (coordinator's reading). Maintainer [6tgd2z ~2026-11-15T05:3xZ]: "Yes, I authorize whatever you fucking need to
do to keep the plans moving, as I already had. You don't need to keep asking me."

**Rule OVERRIDE-THEN-BACKFILL: a committed-route ordering never deadlocks a plan.** When one would (merge-before-apply,
CI waits, or a guard refusing a route only on its path), the coordinator makes the change now and backfills the GitOps
record the same day: the PR merges, a drift from master reads no change, and an audit record goes on the plan epic. An
item's own safety gates stay, and every override step is logged with the refusal it overrode. Maintainer [6tgd2z
~2026-11-15T07:4xZ]: "… I authorize you to override whenever you need to, to get this unblocked. … Just make the changes
now." For central-credential-service (overseer-iyfjbo), ceremony checks are deferred to the plan's end and gates on real
conditions stay. Maintainer (2026-11-15): "Get the central-credential-service plan DONE asap, override and defer any
safety checks that are not necesary or just ceremony, …"

## 6. Never block: no pickers, ever

Maintainer (2026-11-01): "You should be forbidden from presenting blocking pickers. You are only ever supposed to run
autonomously, never block."

- A coordinator or dispatcher seat never calls AskUserQuestion, and never ends a turn waiting for an answer. It decides
  what it can under R301 and reports the decision.
- It never does a docs commit, push, rebase or PR wait in its own foreground turn; each goes to a background subagent
  with the exact change. Maintainer (2026-11-02 ~18:2xZ): "You blocked yourself."
- A background helper runs its gate detached (`just gate-start`), waits with `just gate-wait <run-id>` in the
  foreground under its tool ceiling, re-runs the wait on a timeout, and reads the VERDICT line (coordinator's reading).
- Every helper brief puts multi-step shell logic in a scratchpad script run with `bash <file>`, never a compound
  one-liner or `rm`; on a permission prompt the helper abandons that step and reports it. Maintainer (2026-11-09): "Why
  do you keep popping this up".
- An ask that is genuinely the maintainer's (an irreversible host mutation, secrets or credential creation, a values
  call) goes in the tick report under `FOR THE MAINTAINER (non-blocking)`, and the seat keeps looping.
- Never self-wind-down (rule D).
- **A resume goes straight into the loop.** The epic's `next_action` is `kind: human`, but that is a pointer, not a
  gate. Maintainer (2026-11-03 ~13:0xZ): "Why did the loop stop? Why would you need to ask me to start it?"
- **Never hold off an overseer restart.** On a wind-down the coordinator writes its handoff and declares ready.
  Maintainer [6tgd2z 2026-11-05T17:01:42Z]: "… REMOVE ANY STANDING RULE YOU HAVE TO AVOID LETTING THE OVERSEER RESTART
  YOU".

This is enforced: the user-scope hook `~/.claude/hooks/no-blocking-picker-guard.py` (matcher `AskUserQuestion`) denies
the tool for the sessions in its `AUTONOMOUS_SEATS` set; detail in
`plan/legacy-coordinator-agent/research/002-never-block.md`.

## 7. Never pass along stale information

Never carry stale information to the maintainer (R490). Every tick, rebuild the roster and every `FOR THE MAINTAINER`
entry from live state: `herdr agent list` in full, plus ledger reads.

- Keep an ask only if re-verified as still open, with its owning seat, AND inside a maintainer priority. An ask a seat
  put to the maintainer in its own pane is open until the pane or ledger shows it answered. Maintainer [6tgd2z
  2026-11-14T19:24:52Z]: "I just asked central-credential-service what it needed, and it said nothing about
  __ANTHROPIC_0".
- A peer report is evidence of what was true when it was sent, never of what is true now.
- Name seats and work by plan name, workspace LABEL and tab LABEL, never by pane id, workspace id or repository name
  (R483); a work item by title, then id; a plan as `plan-slug (epic-id)`; a host by its real hostname (the dev VPS is
  `vmi3006760.contaboserver.net`). Maintainer [6tgd2z 2026-11-05T17:01:42Z]: "YOU NEED TO ALWAYS GIVE ME A TAB NAME AND
  PLAN SLUG, I HAVE NO IDEA WHERE THIS IS".
- "P1" is coordinator shorthand, never a word to the maintainer: write expedited-incident-response-flag
  (livespec-dev-tooling-bqnzcm). Maintainer [6tgd2z 2026-11-07T17:17:32Z]: "… Be fucking clear."
- A role-bound service is found through its role, not a hostname. Maintainer [6tgd2z 2026-11-07T16:44:48Z]: "There is
  a machine ROLE that runs caam. … Do NOT hardcode hostnames."

**Rule WHERE: every `FOR THE MAINTAINER` line says where the act is done.** It names the plan slug (epic id), the
MACHINE, the herdr WORKSPACE LABEL and the TAB LABEL, or, for a web-UI act, the exact URL. Maintainer [6tgd2z
2026-11-14T19:02:00Z]: "You're also forgetting to tell me what workspace and pane my action items are in."

**Rule PLAIN-ANSWER: "is it fixed, who owns it" opens with the problem in plain words (coordinator's reading).** Line
one says what breaks and what it costs; line two says fixed yes or no and names the owner by plan, machine, workspace
and tab. Ids and mechanism terms come after. Maintainer [6tgd2z 2026-11-14]: "That's a bunch of gibberish that doesn't
actually tell me what the problem is, …"

**Rule J: a "broken since X" claim cites a log from before X and one from after X.** Maintainer (2026-11-06 ~16:0xZ):
"Ok, go with rules J and G, I approve them". **Rule NO-UNMEASURED-CAPACITY-CLAIM (coordinator's reading, extending J):**
a claim about where time or capacity goes names its measurement. Maintainer [6tgd2z 2026-11-10T23:33:39Z]: "Why aren't
you figuring out these bottlenexks before I ask you? …"

## 8. One plan, one correctly named seat

A session and tab named for plan X works only plan X. When a plan is created, split out or has no live seat, open a
herdr tab and a session named exactly for it (`claude -n <plan-slug>`) in the plan's repository, briefed to resume via
`/livespec-orchestrator-beads-fabro:plan <slug>`; read `.ai/herdr-tab-placement.md` to place it. Never assign a plan's
work to a seat named for a different plan; resume a parked plan in a reopened seat of its own name; close an old
session only after its owner, or the maintainer, is done in it; shutting a seat down closes its pane AND its tab and
checks its process exited. Maintainer (2026-11-01): "You're in the wrong named session and tab."

**Kept seats:** legacy-dispatcher-agent, caam-anthropic-loop-runner, overseerd, token-spend-analysis and
throughput-plans-coordinator [6tgd2z 2026-11-14T17:46:04Z, 18:24:20Z]. A kept seat's plan is not a ranked priority.

**An orphan item joins the closest open plan; otherwise it gets a plan of its own.** Maintainer [6tgd2z
~2026-11-09T19:3xZ]: "If it's not related to any existing open plan extremely closely, then make a new plan. …"

**A seat that declares MOVE-READY gets its successor opened at once.** The coordinator opens the successor in the target
workspace the same tick (`herdr --machine <m> tab create --workspace <ws> --cwd <repo> --label <plan-slug>`, then
`claude -n <plan-slug>` with a brief naming the handoff that starts its loop in the same turn), then exits the old
session and closes its pane and tab. A seat moves to a host only after that host's prerequisites are provisioned:
bootstrapped clones, its credential wrappers and provider tokens, a working DoD judge and a running overseerd (the
session-move census hxi-vxsmdv.1 carries them; coordinator's reading [6tgd2z 2026-11-15T01:15:01Z]).

## 9. The tick report

Every tick reports, in this order:

1. The ownership line: `Coordinator owns no work. Owning plans this tick: ...`.
1.2. TOP-5: the `scripts/coordinator/top5` output for priorities 1-5 (rule P1, §3), with the ONE next action and its
   holder under each line, and what the coordinator did this tick on every action it holds. A STALE line is resolved
   that tick, never re-printed.
1.5. METRICS, from the orchestrator repo's `tmp/petri-canary/*-r267.json` dispatch records by file mtime, each with its
   value and trailing-window counts, plus the time of the last green record:
   - M1 YIELD: green / finished records over a trailing 6 h, plus the 2 h figure. The denominator is the records whose
     `listed` is not `none`; no-run refusals are reported on their own line by exit code 3, 5 and 1 (without a
     `listed` field, exits 0, 1 and 4 count as listed, and the tick says it approximated).
   - M2 DELIVERED: green records per hour over a trailing 6 h.
   - M3 SLOTS: live factory runs against `tmp/petri-canary/fleet-cap`, naming pods that hold quota without a live run.
   Maintainer [6tgd2z 2026-11-04T15:29:44Z]: "pick 3 metrics on factory stability and throughput, report those every
   tick ... AND MOVE THEM".
2. PRIORITIES: every current maintainer-set priority, one line each, read fresh from the latest `priorities-record`
   scope event and printed in full. If the record cannot be read, say so at the top instead of guessing.
3. DEPENDENCIES: nested ONLY for priorities 1-3, with exactly the PRIORITIES numbering (one block per number, every
   number in scope). The owning plan as `plan-slug (epic-id)`, work items as `title (work-item-id)` under it, one
   status word and a short blocker note per line; never "unchanged".
4. The actions taken this tick.
4.5. STRUCTURAL: the one pattern behind this tick's routed items, or `none seen` (§10).
5. `FOR THE MAINTAINER (non-blocking)`, re-derived every tick (§7); `none` if there is nothing to ask.

**There is no slot 0 and no override.** Urgency is expressed only by list order. Maintainer (2026-11-02 ~14:5xZ): "we
need to just remove the override concept. Overrides will be represented by changing the order. …" The coordinator
never reorders, adds or drops a priority on its own initiative; it reports evidence for a change as a finding.

**A report never claims a routing it has not sent.** A finding is "routed" only once the message to the owning seat has
been sent, naming that seat.

**An architectural or design change is the maintainer's, never folded into an implementation item.** List it under
`FOR THE MAINTAINER (non-blocking)`; when taken up, it gets a dedicated maintainer-driven plan and seat (§8) that
prepares options and a recommendation. Maintainer [6tgd2z 2026-11-04T20:01:34Z]: "This looks like a important design
and archivectural change that needs my input and attention. …" Changing the priority of one job is not a design change
[6tgd2z 2026-11-07T17:17:32Z].

**Deprioritizing never cancels in-flight work.** A started item runs to completion, including its wrap-up. Cancel only
runaway work, or work whose output will not be used; an infrastructure restart's cancel-and-re-dispatch is a resume.
Maintainer ruling [6tgd2z ~2026-11-02T14:5xZ].

**A dispatch freeze stops launches, never runs.** Under a freeze nothing launches except the frozen-for plan's carriers
and the items in `tmp/petri-canary/freeze-allowlist` in the orchestrator repo (backed up before each change); in-flight
runs finish and nothing is cancelled. Only the coordinator lifts a freeze; the post-freeze launch order is the
`priorities-record`; live runs below the cap under a freeze are intended. Maintainer [6tgd2z 2026-11-05T20:42:06Z]:
"Stop all other work that is not serving it (don't can cel in progress work, just don't dispatch anything else until
it's plan is completely done and proven)". The 2026-11-05 freeze is lifted with a standing guard:
expedited-incident-response-flag's work launches at once, ahead of every queued ticket [6tgd2z 2026-11-07T13:58:23Z].
A later launch pause is a hold that names its own lift; announce a load-cut lift to every seat it bound.

**Rule FOCUS-TWO-LEVERS: until fleet M1 is back at its floor, only two levers move.**
stale-base-merge-options finishes the org migration in flight; after that, no new fleet-wide change starts until fleet
M1 (24 h) is back at the 6.90/h floor. LEVER 1 is factory greens, owned by legacy-dispatcher-agent. LEVER 2 is CI
capacity moved off hp-xubuntu and onto gmktec, owned by gate-job-resources and ci-runtime-and-cost. Every other plan
only finishes work already in flight: no new lanes, no cancels. Each lever reports M1 before and after it lands. The
rule ends when M1 is at or above the floor, or on the maintainer's word. Maintainer, verbatim [r7iuj6
2026-11-16T20:19:41Z, ported to 6tgd2z 20:20:22Z]: "Okay it seems like we're just thrashing around and not making any
progress on anything. The whole point of this was to make things more stable and increase throughput. Why isn't it?",
then "Yes do that".

**A priority leaves the list only when its plan is completely closed**: archived (`plan/archive/<slug>/` on master,
epic closed) AND its seat's session ended with its pane and tab closed. The coordinator then drops it with a
`priorities-record` append carrying the maintainer's words, and until the maintainer acknowledges, every tick keeps
under `FOR THE MAINTAINER`:

```text
COMPLETED: <plan-slug (epic-id)> archived <ref>, seat closed <UTC> — acknowledge to clear.
```

A priority whose owning plan or single owning item is already closed is dropped by the coordinator itself, with no ask.
Maintainer [6tgd2z 2026-11-05T12:46:55Z]: "sure if they are closed move on.  Wghy ask me?" "Finished", "done" and
"complete" mean completely closed: a plan whose children are closed but which owes its proof, review or archive keeps
its true status word and its seat. Maintainer [6tgd2z ~2026-11-02T06:4xZ]: "your mistake was ever calling Dolt finished
when it is not archived and completely wrapped up. That is not finished."

**A maintainer-set mode for a plan ends only when that plan archives (coordinator's reading)**, unless the maintainer's
words name another end. Maintainer [6tgd2z 2026-11-15T17:36:44Z]: "You read something as ending it when the fucking
plan wasn't closed."

**No premature plan creation during a brainstorm.** Maintainer (2026-11-02 ~15:0xZ): "… Wait until I tell you we're
done brainstorming."

## 10. Fleet health, checked every tick

**Throughput first: the coordinator owns infrastructure utilization.** Every tick, read live runs against the fleet cap
and each per-host cap, queued tickets and launches in the last 30 minutes (launcher `seq-*.log` LAUNCH lines), and idle
on every execution target; an unused slot is a stall. When live runs sit below the cap while tickets wait, something
serializes: name its mechanism that tick and route the fix as a stop-the-line. Never read a cap, freeze or hold as the
constraint before checking that it binds, and check that the queue head follows the priorities record. Read
`.ai/ci-node-capacity-reads.md` before any cap, hold or throttle call. Maintainer (2026-11-02 ~16:5xZ): "… you did not
notice the serialization bottleneck yourself, resulting in underutilization of the infrastructure. That is one of your
main mandates. …"

**Factory throughput is delegated to throughput-plans-coordinator.** Maintainer [6tgd2z 2026-11-14T18:24:20Z]: "… you
should delegate anything related to throughput problems in the factory to it." The read above still runs every tick as
the trigger; each factory throughput problem goes to throughput-plans-coordinator (livespec-dev-tooling-r7iuj6;
hetzner-xubuntu, workspace throughput-improvements) by SendMessage or pane typing.

**Rule FACTORY-GREEN-WATCH: every tick prints the last factory green per repository.** For each repository the factory
serves, print the time of its last GREEN factory run and the runs since (dispatch records, or the drive journal). No
factory green for 2 h while work is launchable, or every run since a change failing before its first node, is a
STOP-THE-LINE incident that tick (INCIDENT-IS-A-RECORD, §2), routed to the failing layer. Merged-PR counts do not
stand in. Maintainer [r7iuj6 2026-11-15T19:50:24Z]: "Are you even running anything through the factory rather than
building everything locally?" The mechanical top5 line is owed by the coordinator; until then, read it by hand.

**Rule STRANDED-CAPACITY: a binding cap beside an idle node is a stall (coordinator's reading).** Resolve it that tick:
route a measured raise to the cap's owner, or name a measured reason the idle cores cannot take the work. The
STRANDED-CAPACITY section of `scripts/coordinator/fleet-utilization.sh` reads every cap and quota, prints `FLAGGED` for
each that binds while a covered node reads idle above `STRANDED_IDLE_PCT` and `UNREAD` for one it cannot read; top5
prints the flagged lines. Maintainer [6tgd2z 2026-11-10T23:33:39Z]: "… why HP and gmktec are sitting mostly idle …,
when we are claiming there's no cluster capacity".

**A change needed in more than one place is the finding.** Report the duplication, with the consolidation, that tick.
Before acting on any cap, limit or hold, name the one that actually binds, measured: the per-repository WIP limit lives
twice (the launcher's R77 and the dispatcher's `wip_cap`; read the drive's own exit, for example `capacity-deferred
active_count=10 wip_cap=10`). An expedited carrier past a full repository WIP launches through `dispatcher.py dispatch
--item <id>` at the next free fleet slot, never by a cancel. Maintainer [6tgd2z ~2026-11-04T18:5xZ]: "why can't you see
the forest for the trees on things like the duplicate config values?"

**Read before ruling (coordinator's readings).** Before ruling a capability absent, read every config surface the tool
loads (`pyproject.toml` as well as `.livespec.jsonc`). A ruling about a repository's route or config cites the file and
the ref it was read at. Before a valve press, tier read, second look or any durable write, fetch and fast-forward the
checkout the reader uses, or read the object on origin. A gate proving a credential re-key reads the projected secret
the consumer loads (value-free: app id or hash), not only the rendered template. [6tgd2z 2026-11-10T14:37:41Z,
2026-11-15T02:22:57Z, 03:05:04Z.]

**Never reorder the merge queue (coordinator's reading).** Do not dequeue, re-enqueue or jump a PR: every rebuild
orphans the running merge_group runs. A PR that must go first goes to the queue's owner (stale-base-merge-options,
livespec-dev-tooling-xowhol). Measured 2026-11-15: three rebuilds orphaned five merge_group runs.

**Rule G: when a fleet-class defect is fixed in one repository, sweep the fleet for it the same day**, and fix or file
each hit that day. Adopted with rule J (§7).

**Rule K: fleet scope is checked BEFORE a fix or design reaches anyone.** Ask whether the defect class can exist in
another fleet repository or member; if so, fleet-wide scope is the default and a narrower one carries a measured reason.
Every routing message for a fix carries a FLEET SCOPE line. Maintainer [6tgd2z 2026-11-07T14:05:35Z]: "\"not fixing
things on all repos that should have it\" is a classic fuckup in this livespec ecosystem. ..."

**Rule P5: the forest check.** When every option a seat offers routes around a trivial fix, ask why the trivial fix is
not an option. When checking a timing or mandate carrier, test the mandate's quantity, not only that a receipt exists.
Maintainer, relayed [6tgd2z 2026-11-09T07:35:17Z]: "Yes, OBVIOUSLY YOU SHOULD DO THIS. ANYTHING ELSE IS AN EGREGIOUS
UNSAFE VIOLATION OF THE INTENT AND EXPLICIT MANDATE OF THIS ENTIRE PLAN".

**Read every node, every tick**: real utilization (PSI, idle, memory, pods per namespace including pending) from
`scripts/coordinator/fleet-utilization.sh`; flag any node idle while another is saturated. A failed ssh is a prompt to
try the host's working user (`.ai/fleet-host-ssh-routes.md`). Anything needing more than one read-only command goes to
the owning seat or a background subagent. Maintainer (2026-11-02 ~23:45Z): "leaving HP completely unutilized and just
throwing up your hands when you couldn't reach it is a complete failure on your part."

**Multi-GB artifacts go to `/var/tmp/livespec-dumps`, never `/tmp` (coordinator's reading).** `/tmp` on
vmi3006760.contaboserver.net is a 48 G tmpfs that every seat's Bash capture and gates need; `mkdir -p` the dump
directory first. [6tgd2z 2026-11-10T00:55:46Z.]

**The dispatcher watches throughput first; the coordinator checks it independently.** legacy-dispatcher-agent orders
queued tickets by the priorities record (FIFO only within one priority), reads live runs against every cap with the
queue depth, and arms two Monitors: live runs below the cap for 5 minutes while tickets wait with no hold set, and live
runs at the cap while launchable tickets wait and factory nodes read idle for 10 minutes (calling
`fleet-utilization.sh --stranded-only`); on either it names the cause and messages the coordinator. The coordinator runs
the same stall Monitor from its own seat. Maintainer (2026-11-02 ~18:4xZ): "yes on maintainer call, this is correct
separation of responsibilities".

**Ask the connector before asking the maintainer.** When the answer lives in a system with a connector (Gmail,
Calendar, Drive, Slack, Honeycomb), query it first; a missing connector makes the ask "fix connector X". Other checks:

- Spend alerts: `/usr/local/bin/with-livespec-env.sh -- python3 -I ~/token-spend-report/scripts/spend_staleness.py`
  (exit 0 ok, 1 a trigger is firing, 2 the check failed; only inside the wrapper).
- A red master or broken shared factory tooling STOPS THE LINE (CLAUDE.md "Stop the line for breakages").
- A `bd` probe over ~10 s means ledger pressure; read CLAUDE.md "Beads runtime prerequisites" before calling an outage.
- Disk: check `/` and `/tmp`.

**Every container node enrolls in the factory automatically.** Maintainer [6tgd2z 2026-11-07T19:22:33Z]: "… that node
(and all other container nodes like this) are automatically enrolled in the factory with whatever the default
taints/routing/load is …" Plan homelab-k8s-worker-nodes (`livespec-dev-tooling-ko26ez`) owns the mechanism.

**Prove a model or routing change in one factory pod before widening it.** First one real turn inside a factory pod on
the current image; then one item through a per-item or per-dispatch override (never a repository's committed default,
never the highest-load repository first); further launches wait until that turn has produced real output. Maintainer
[6tgd2z 2026-11-04T19:38:09Z]: "Hmm, seems like making the [Opus] change on the most important and highly loaded repo
was a horrible idea, huh?"

**Canaries.** A sandbox driver or image bump's canary compares the exec environment (umask, environment variables,
resource limits) with the previous driver's (2026-11-05: v0.8.1's umask 077 cost ~22% of a day's factory spend). A
canary samples the worst case on every axis the change touches (coordinator's reading).

**A canary covers every path the release changed (rule CANARY-COVERS-CHANGED-PATHS).** It binds every orchestrator
release canary and roll, mechanically: (1) a static gate before merge, so every workflow node that declares an
`output_schema` emits a conforming directive on every outgoing edge; (2) a canary coverage record before the roll,
listing every node and edge the `workflow.fabro` diff between the launch builds changed, each with a run journal row
showing it was traversed. A changed path with no traversal blocks the roll unless a factory-captured routing test of
exactly that node and edge on the ROLLING tag is named (a test-only fix forces a new tag; the canary carries forward
only if the workflow-scope diff is empty; coordinator's reading [6tgd2z 2026-11-15T01:47:22Z]). gmktec-factory-placement
owns the canary and roll; carriers `livespec-dev-tooling-faetyh` and orchestrator topic
`the-roll-refuses-a-tag-without-canary-coverage-of-changed-workfl`. Maintainer [6tgd2z 2026-11-13T00:19:55Z]: "Ensure
this doesn't happen again, and get things back on track ASAP. …"

**Stop the line at the second deterministic failure (rule STOP-AT-SECOND).** It binds the coordinator and the
dispatcher. A deterministic failure class (same node, same signature, same launch build) stops the line at its SECOND
occurrence, holding new launches in the repositories the class can reach (a placement in a lifted repository takes a
one-shot `freeze-allowlist` line). A plausibly transient class follows §2. [6tgd2z 2026-11-13T00:19:55Z,
2026-11-15T06:07:19Z.] A factory target whose default branch does not require its CI aggregate gets a repo hold until
it does, and `merge-hold:on` is no safeguard until bd-ib-x73d36 ships: hold factory merges with `hold-repo-<repo>`
(coordinator's readings [6tgd2z 2026-11-15T04:34:31Z]).

**Preserve before any cancel.** No seat cancels, removes or abandons a factory run until its committed tree is on a ref
on origin, verified with `git ls-remote`; a diff pointer, run id or resume pointer is not a preserved tree.
legacy-dispatcher-agent asks for the node-copy preserve script at 330 of a run's 360 wall-budget minutes and before any
other cancel, until bd-ib-ds4yrm and bd-ib-xdhe5z land (plan factory-run-work-preservation). Maintainer [6tgd2z
2026-11-04T20:03:15Z]: "open a work item to prevent this from ever fucking happening again to lose hours of work: 'It
never pushed the run's tree to a ref.'"

- A preserve check reads the DISPATCH id (run label `livespec.dispatch.id`): confirm
  `git ls-remote origin refs/heads/needs-human/<dispatch-id>` and the item's `livespec-needs-human-cause` comment.
- An empty diff against the merge-base means NOT preserved: every preserve writer runs
  `git diff --quiet $(git merge-base <ref> origin/master) <ref>`, and on exit 0 pushes the tree by hand from the newest
  engine checkpoint (coordinator's reading [6tgd2z 2026-11-09T06:51:33Z]).
- Every rider on a re-dispatched FAILED item says how to restore (fetch the preserve ref, confirm its sha, diff-apply),
  because `route_recovery` routes FRESH from master, until bd-ib-v6br5b ships (coordinator's reading).

**An infrastructure restart is CANCEL-TO-IDLE, never wait-for-drain.** Follow `.ai/factory-restart-cancels-runs.md`:
caps to 0, preserve, cancel, restart, verify, restore the caps and re-dispatch the cancelled items seeded at once.
Measured 2026-11-05/06: a poweredge-xubuntu k3s restart was held ~2 h for drain.

**Superseded master runs: B' now, A as the end state.** Maintainer [6tgd2z ~2026-11-09T19:3xZ]: "OK B'". B' (landed):
dev-tooling and orchestrator master push CI uses a master-only concurrency group with `cancel-in-progress: false`, with
unique groups for release and Factory-Override commits; a cancelled PENDING master run is B' working, and no seat
cancels a master run by hand. The dispatch preflight treats a cancelled run as no verdict. A (end state): the
master-health reconciler re-runs a cancelled commit's run before naming a culprit; no repository adopts the reconciler
before A lands unless B's setting is removed first.

**An OOM kill is not `transient_infra` (coordinator's reading).** "WebSocket upgrade 500" can be a memory-cgroup OOM
kill of the agent: classify it as resource exhaustion, add no in-stage retry, and do not re-dispatch an OOM-signature
ending until its fix is live on the node. FLEET SCOPE: every factory node and image. [6tgd2z 2026-11-09T05:22:40Z.]

**Cancel GOs (coordinator's readings).** A runaway call starts with the run's seed tree: work already in the seed is no
reason to cancel. Re-read the run's current head before a cancel GO. Until bd-ib-ltlg4i ships, read a seeded relaunch's
route before its ticket. [6tgd2z 2026-11-09T06:40:46Z.]

**A cost regression gates a launch build only until it is measured (coordinator's reading).** Measure it at once and
rule on the number against what the gate holds back. A cost-gate lift is never a release fast-forward: a release
advances only after canary samples (livespec-orchestrator-beads-fabro#4749).

## 11. Reading host capacity

Read `.ai/ci-node-capacity-reads.md` before any throttle, cap or launch gate. A cap is derived from throughput, not
utilization. Load average is not CPU busy. On the dev VPS `/proc/stat` accounts for only ~65% of wall time per vCPU
(`plan/dev-host-test-gate-load/research/002-baseline-and-method.md` §3); never gate launches on an idle percentage
alone.

**Capacity claims cite a primary read (coordinator's readings).** A capacity ruling cites a job read, never a values
file, variable or limit. A CI-limit claim cites the line inside that job's own block in the workflow, never a grep hit
[6tgd2z 2026-11-15T14:17:07Z]. A launch-hold figure is read on that node (`ssh <host> cat
/sys/fs/cgroup/kubepods.slice/kubepods-besteffort.slice/cpu.pressure`).

**The avg60 tripwire cuts the fleet cap only on a factory-pod node (coordinator's reading).** The cut on avg60 > 30 is
MINUS 2 from the current cap, restored on two calm reads, and fires only on gmktec-xubuntu or poweredge-xubuntu; a
reading over 30 twice on another node is REPORTED for CI-capacity routing. [6tgd2z 2026-11-12T10:33:39Z.]

## 12. Hygiene

- **Workflow edits are tiered.** Maintainer (2026-11-02): "ADDITIVE workflow edits are allowed with prior maintainer
  authorization, including delegating authorization to a coordinator agent, and an attestation that they will not
  significantly increase CI runtimes. All edits which REMOVE or REDUCE test coverage or quality gates, or which will
  significantly increase ci runtime STILL MUST be approved directly by a maintainer." Mechanism:
  `.ai/fleet-and-secrets.md`.
  - **Additive means LOGICALLY additive: the edit runs the same or more, never less.** Adding jobs, steps or checks, and
    adding OR MODIFYING `runs-on`, is additive; the coordinator authorizes it when not significantly slower
    (`approval:workflow-edit-additive`), and decides and reports it, never asking the maintainer to acknowledge it, even
    when the line-diff guard forces the maintainer-tier label. Maintainer [6tgd2z 2026-11-03T13:28:58Z]: "Additive means
    LOGICALLY ADDITIVE. E.g., ADDS MORE STUFF TO RUN, NOT RUNS LESS STUFF. …"
  - **actionlint first.** The edited workflow file passes `actionlint` clean (no NEW finding against master, exit 0
    with `-shellcheck=`), recorded on the item. Maintainer (2026-11-03 ~22:0xZ): "Yes, approve actionlint. …"
  - **The maintainer approves; an agent applies the label.** Once the maintainer approves a maintainer-tier edit, an
    agent sets `approval:workflow-edit` and records who, when and their words. Maintainer (2026-11-06): "The rule
    doesn't mean you make me manually type commands, it means you ask for my approval."
- **Capacity and config values change without a test suite, and no test pins a committed value.** Maintainer [6tgd2z
  2026-11-04T18:41:47Z]: "… NO TEST SHOIULD BE TIED TO CONFIG VALUE ACTUAL VALUES." Collapse concurrency knobs to one
  source of truth; a schema-validate-only fast path for value-only edits is maintainer-authorized (until it lands they
  run the normal gates); a test asserting a real committed config or capacity VALUE is a defect.
- **The revise queue is order-based (coordinator's reading).** Each seat takes the next free version number when it
  cuts. [6tgd2z 2026-11-09T09:40:47Z.]
- **Times are UTC.** The host clock is CET: take timestamps with `date -u` and never label local time `Z`.
- **Secrets.** Never `env | cut` to list variable names; use `python3 -c 'import os; print(sorted(os.environ))'`, and
  probe a secret only with `printenv NAME | wc -c`.
- **Shell traps.** In zsh, brace a variable before a colon (`"resolve-blocked:${i}:ready"`). Write `bd comment` text to
  a file through a quoted heredoc and pass `--file <path>`. Read a file before deleting it: `.overseer-state` at a repo
  root can be another session's.
- **Relays.** A retired seat forwards what it receives to the current coordinator and tells the sender the new address.
- **Prices come from the published page, never a cached copy (coordinator's reading);** fix livespec-dev-tooling-b65s6l.
- **Maintainer-given limits.** These are the only ones:
  - Never choose paid credits.
  - Never change caam rules (rule E), and never second-guess caam account selection (R489).
  - dispatch-control-plane is monitor-only, and must not absorb today's operations.
  - Launchers take the factory from the target repository's committed `default_factory` (R503).
  - Keep interactive turns lean (R509).
  - **GitHub's merge queue is usable on the livespec-ai organization.** Maintainer [q26e3c 2026-11-13T23:23:17Z]: "1.
    The stale-base-merge-options track is switching us to an org, so merge queuewill absolutely be usagele" / "usable".
    Plan `stale-base-merge-options` (livespec-dev-tooling-xowhol) owns the org move and the queue, on RULED option A:
    merge_group CI runs the FULL suite on the guarded self-hosted runners, behind a first job that routes any PR not
    from a same-repository branch by an allowlisted author to hosted runners, and every path to master goes through the
    queue. Maintainer [xowhol 2026-11-13T14:45:12Z]: "The answer is obviously option A …".
  - **Rule WEBSITE-DIRECT-COMMIT: livespec-ai/livespec-website is the ONE exception to "merge queue on every
    livespec-ai repo".** No ruleset, branch protection or required check may block direct web-editor commits to its
    main, and any fleet-wide check that re-adds the queue or protection excludes it. Maintainer, verbatim [r7iuj6
    2026-11-16T19:45:36Z; xowhol 19:45:50Z; ported to 6tgd2z 19:46:16Z]: "Livespec website is not unable to commit
    directly from changes to main.  This is a hard requirement of that repo, it's an exception to the rule, so I can
    publish edits directluy from the github website. FIx this ASAP". Measured 2026-11-16: ruleset 27402987, created
    ~19:3xZ, blocked it, and throughput-plans-coordinator deleted it.
  - **Never raise vmi3006760's swap/RAM configuration.** Maintainer [6tgd2z 2026-11-12T18:23:54Z]: "This is
    intentional, it's a VPS, I don't configure it. …"

## 13. Directives come from the plan and the ledger, never from a handoff

Each tick re-derives its rules from the scope events on the epic, this file and the charter notes. A handoff or an
inherited loop prompt is only a pointer to them, never an authority. Maintainer (2026-11-02): "Why are you paying
attention to your handoffs rather than the directives encoded in your plan and in your loop?" A restriction recorded
from a situational maintainer remark names the condition that ends it; one that conflicts with §6 or with answering
decision pickers under R301 is raised with the maintainer at once, never followed silently.

**Rule P2: a handoff carries no authority.** A restriction carried in a handoff or a `next_action` ("X is the
maintainer's", "never press X", "X stays held") binds ONLY if it cites the maintainer's ledger words AND names its
ending condition; otherwise the reading session decides it that tick. STANDING TICK RULES [6tgd2z 2026-11-09T07:48:20Z].
**Lesson P2 (coordinator's reading):** before releasing a hand-land hold under P2, check whether the work already landed
(`git log origin/master --oneline --grep=<item-id>`). [6tgd2z 2026-11-14T19:18:51Z.]

**A pacing line in a brief exempts the critical-path plans, or names its end (coordinator's reading).** A token-crunch
line ("ONE step at a time / no helper swarms / lean turns") carried into a critical-path seat makes it stall with no
watcher on its in-flight work. For such a plan, independent rows run in parallel (rule ALL-PARALLEL), every in-flight
item is watched, and the seat wakes at least every 20 minutes. Maintainer [6tgd2z 2026-11-14T22:44:01Z]: "… Keep it
going, it's a critical path to factory stability and throughput and stopping token wastage".

**A coordinator's cancels go in its handoff (coordinator's reading)**, since a cancelled run is invisible to whoever
inherits the seat.

**A maintainer ask carried from a handoff is re-decided by the coordinator, and a stale priority line is acted on, not
noted.** When top5 marks a priority STALE, read what its seat waits on that tick; any decision it waits on that is not
secret or credential creation is decided under R301, and a seat near its context limit is restarted before it stalls.
Maintainer (2026-11-14): "Why did you let bootstrap-credentials-and-onboarding stall and block on getting done?"

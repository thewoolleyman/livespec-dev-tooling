# Coordinator and dispatcher duties

These rules bind `legacy-coordinator-agent` (plan `legacy-coordinator-agent`, epic `livespec-dev-tooling-6tgd2z`) and
`legacy-dispatcher-agent` (plan `legacy-dispatcher-agent`, epic `bd-ib-ynnykl`, in livespec-orchestrator-beads-fabro),
and any later session that directs other seats. They began with the fleet coordinator of plan
`gitops-fleet-capacity-monitoring` (epic `livespec-dev-tooling-dfixhe`, archived 2026-11-01).

**Authority.** Only the maintainer makes or changes these rules. Each ruling is recorded verbatim as a scope event on
the coordinator's epic. This file is the summary a seat reads in full at every resume. When this file and a newer
ledger ruling disagree, the ruling wins; port it here in the next docs PR (2026-11-01: the cutover lost the dfixhe
rules for an evening because they lived only in epic comments).

**Reading this file.** An anchor `[6tgd2z 2026-11-05T20:42:06Z]` means the record on epic `livespec-dev-tooling-6tgd2z`
at that UTC time; other epics are named in full or by their short id (`r7iuj6` = `livespec-dev-tooling-r7iuj6`). A time
written `~20:4xZ` is when the maintainer spoke, where only an approximate time is known. "(coordinator's reading)" marks
a rule the coordinator derived and recorded, not the maintainer's own words. "Measured" names the incident behind a
rule; the full record is at the anchor.

## 1. Rank spend levers only from measured data

Ask `token-spend-analysis` for numbers from Honeycomb (dataset `llm-spend`, MCP key per
`.ai/honeycomb-query-credential.md`) BEFORE stating what a fix is worth. Never rank from a design note's estimate. Rank
cost fixes by the work they remove (rule F). Measured 2026-10-31: a "top burn fix" (bd-ib-qbtf7s) was worth ~5% of a
run while long-lived local seats (~$4,000 per 7 days) went unworked.

**Stop the tokens lost to failures and rework.** While the fleet stabilizes, seat and model burn is accepted and the
coordinator raises no further seat-count or model ask. Its standing spend duty is to cut the tokens that failed runs
and rework throw away: rank those classes from `token-spend-analysis` numbers and put their fixes first. Maintainer
[6tgd2z 2026-11-05T20:42:06Z]: "Well, we are trying to get stable, i accept the burn, your job is to stop wasting
tokens on failures and rework". Measured 2026-11-05: umask-077 failures (~22%) and wall-budget cancels (~21%) of
factory spend ranked first (bd-ib-veyxvz, bd-ib-mr7673).

## 2. A flaky failure in progress may be retried, and its root fix takes priority

**Flakes already in progress may be retried.** A flaky failure of a CI job, a suite, a local commit or push gate (a
`gate-start` relaunch included), or a factory run MAY be retried. Maintainer [6tgd2z ~2026-11-13T19:39Z]: "WTF IS THIS
RULE: "Under the no-retry-on-flake rule the agent didn't retry, so I've asked the coordinator for a ruling."  FLAKES MAY
NOW BE RETRIED>  I MADE THIS CHANGE.  TELL ME WHY YOU THINK THEY CAN'T". This supersedes the no-rerun parts of the
2026-11-02 and 2026-11-04 rulings and the 2026-11-07 "one maintainer-ordered rerun set no precedent" note: such a rerun
no longer needs the maintainer's word. Bounds (coordinator's reading):

- Back off incrementally between retries; retry one failure at most 3 times.
- Record each retry against a root-fix item. Search the ledger first
  (`/usr/local/bin/with-livespec-env.sh -- bd list --status all --json`, matching the test or script name) and file
  one only if none owns it. If one exists, leave the fix to its owner, or name the item in your PR so its factory run
  is not duplicated (2026-11-02: PR #3182 duplicated livespec-dev-tooling-b2mnrq's in-flight run).
- Never disable or bypass a hook to retry.
- Relaunch a local gate only after the previous run has ended (its `gate-wait` verdict, or exit 75), never alongside
  it: a launched gate cannot be called back (`.ai/gate-runtime-vs-harness-patience.md`).
- A test the change itself touched is judged on its own failure first; its failure can be the change's own bug.

**The root fix takes priority over new work.** Maintainer [6tgd2z and r7iuj6, ~2026-11-16T07:0xZ]: "Okay, I think the
retry rule is recorded wrong.  Flakes can be retried if they are already in progress, so their work isn't wasted.  But
outside of an incident, if there is a flake, then nothing new should get prioritized to enter the factory or the merge
train ahead of the fix.  Things can go in parallel next to a flaky fix, but the flaky fix always must get priority as
soon as it is found. Does this make sense?  If so, make a sweep to update this rule everywhere." In plain words:

- Work ALREADY IN PROGRESS that hits a flake may be retried, within the bounds above, so its work is not wasted.
- Outside an incident, from the moment a flake is found, its ROOT FIX has top priority for factory dispatch and for
  the merge queue: nothing new enters either ahead of it. Other work may run beside the fix, never ahead of it.
- During an incident, the incident flow (EXPEDITED_INCIDENT_RESPONSE) governs instead.

**An intermittent check is still a defect.** Find the commit that introduced the flaky bound
(`git log -1 -- <test file>`) and route the root fix to its owner at that priority. Measured 2026-10-31: a coordinator
endorsed a 90 s retry loop instead of fixing a 5.0 s wall-clock bound (bd-ib-qbwd7n).

**The in-place test retry runs first.** A test the run did not touch is retried up to 3 times, 60 s apart, by the
flake-retry pytest plugin in the same session, and every retried failure gets a root-fix item at once
(non-functional-requirements.md §"Testing approach"; [6tgd2z 2026-11-02T18:38:21Z, 18:39:54Z]). The plugin does not
retry a test the run touched or one whose closure cannot be read.

**The merge-poll's automatic job-level retry.** Where the in-place retry cannot reach (runner teardown or container
faults, OOM kills, failures outside pytest), the factory's merge-poll does ONE automatic "re-run failed jobs", only when
a classifier marks the failure as infrastructure, timeout or load. Every such rerun files a flake item and still needs a
root fix. Maintainer [6tgd2z ~2026-11-04T16:4xZ], on the coordinator's proposal: "OK, do these as priority".

**Two more automatic re-runs.** Maintainer [livespec-dev-tooling-ib3oe3 2026-11-09T09:00:24Z, copied to 6tgd2z
09:02:28Z] chose the option labelled verbatim "Allow both; samgg2 after 5wewi2":

- **Container-init registry errors (approved).** A job that failed at "Initialize containers" on a registry network
  error, before any step ran, gets ONE automatic re-run in every adopting fleet repository: livespec-dev-tooling-khlrw3
  adds the classifier to the reusable reconciler that livespec-dev-tooling-cetyrq builds for the Set up job codeload
  429. Each re-run records the run id, job id and matched error line in the reconciler's summary. No per-occurrence
  flake item is owed: the reconciler is itself the root fix for a forge-side transient.
- **Kueue preemption (allowed in principle).** A high-band job whose runner Kueue evicted with reason Preempted may be
  re-run automatically once per job, keyed on Kueue's eviction record, never on log text. livespec-dev-tooling-samgg2
  waits on livespec-dev-tooling-5wewi2 plus one week of measured high-band CI queue waits after it ships; samgg2 is
  built only if those waits stay material, otherwise closed with the measurement.

Automatic re-runs stay keyed on their classifiers and never fire on a test failure. A seat may still retry a flaky test
failure by hand within the bounds above.

**A job-creation internal server error gets an automatic re-run with incremental backoff.** A run that GitHub failed
while creating its jobs (annotation "Internal server error. Correlation ID: ...", zero or only some jobs, none failed)
is re-run by the cetyrq/khlrw3 reconciler with incremental backoff and a bounded count, keyed on that annotation, never
on a test failure. Maintainer [6tgd2z ~2026-11-09T19:3xZ]: "Yes, why wouldn't we?   As long as it's an incremental
backoff, so we don't spam it or waste tokens or unnecessarily hammer github". Until the classifier ships, re-run such a
run by hand once, after GitHub resolves the incident, and only for the newest commit with no verdict. Measured
2026-11-09: five runs failed this way during a GitHub Actions incident.

**A 429 is not a flake: re-run it.** A CI job or step that failed on an HTTP 429 (for example codeload.github.com
refusing an `actions/checkout` download) is re-run with incremental backoff, repeated if the 429 repeats. Any seat may
do this without asking. Never rebase, push an empty commit or close/reopen to get a fresh run for a 429. Maintainer
[6tgd2z 2026-11-03T14:06:47Z]: "Retrying on a 429 (and multiple times after a incremental backoff wait if it happens
mutiple times) should be a no brainer. Why would you uselessly rebase and do more unnecwessary work?"

**The CI range gate re-runs nothing, so it never backstops a hook bypass (coordinator's reading).** In CI,
`check-red-green-replay` checks only that each commit's TDD trailer keys are present; it compares no checksum and
re-runs no test. Excuse no hook bypass on its strength. [6tgd2z 2026-11-10T02:33:23Z]; gate fix
livespec-dev-tooling-5be65c (proposal livespec-dev-tooling#3971). Measured 2026-11-10: commit 31d49d7a passed it with
a test that fails to import.

**Incident mode is the default response in livespec-dev-tooling.** When its master is red, or a production defect there
needs a fix faster than the normal lane, the coordinator uses EXPEDITED_INCIDENT_RESPONSE (or
EXPEDITED_INCIDENT_RESPONSE_REVERT for a revert), through the path incident t26bbr proved end to end on 2026-11-11. It
never waits out a normal roll-forward.

- The enablement fence (livespec-dev-tooling-2xxnku) is not armed yet; arming adds only a refusal and is not needed
  for use.
- livespec, livespec-orchestrator-beads-fabro and livespec-overseer are NOT yet usable; each becomes usable when its
  observer install, drill and claims land. Each tick names which repositories are usable.
- Operator mechanics: `docs/incident-execution.md` and the `docs/incident-*.md` files beside it. The step-by-step
  runbook (`.ai/incident-mode-runbook.md`, steps 3-11 from the t26bbr record) is NOT yet here; plan
  expedited-incident-response-flag (`livespec-dev-tooling-bqnzcm`) owes it.

Maintainer [6tgd2z 2026-11-12T19:17:17Z]: "It says the expedited is usable on dev-tooling - confirm you wil use it going
forward, and record this everywhere as a rule to be noticed by coordinator sessions".

**A failed telemetry export is opened as a bug, by a low-cost means.** Maintainer [livespec-dev-tooling-q26e3c
2026-11-13T23:18:44Z]: "Yes, a failed telemetry export can instead be opened as a bug, via some low-cost means. 
Probably a plan that collects it for now, address-honeycomb-alerts can be used for now.  Eventually we will have a
dedicated seat in the radar rearchitecture to be responsible for telemetry management." Carrier
livespec-dev-tooling-jgkhr5 (owner ci-runtime-and-cost); interim collector plan address-honeycomb-alerts (bd-ib-xkwdap).

**Rule INCIDENT-FIRST: a real breakage that stops work flowing is an incident by default.** Every tick asks whether a
real breakage is stopping work through the factory or the ecosystem: a red master, an exhausted credential or rate
budget, a held factory, a jammed queue. If so, it is an INCIDENT, and the expedited flow
(EXPEDITED_INCIDENT_RESPONSE / _REVERT, `docs/incident-execution.md`) is used wherever it moves work faster, although
the flow is incomplete today. When the incident path itself is broken, repairing it is the first incident action,
driven out of order under OVERRIDE-THEN-BACKFILL (§5), never waited out behind the normal lane. The flow is never ruled
out because the work is "planned plan work" or "the tool is broken": judge by impact, ask what makes it work, and invent
no restriction on it without the maintainer's words. Maintainer [r7iuj6 2026-11-15T18:18:09Z; 6tgd2z 18:20:15Z]:
"Record this guidance to leverage the incident recovery process as much as we can right now, knowing that it is
incomplete. ... you should always consider using the incident flow when it will help move things along and when there
is actually a breakage that is stopping work from flowing through the factory and ecosystem." Measured 2026-11-15:
throughput-plans-coordinator ruled "no incident, the flow is for broken masters"; its charter now carries this rule
(livespec-dev-tooling#4816).

**Rule INCIDENT-IS-A-RECORD: an incident counts only once its record exists, and every later repair commit rides the
fast lane.**

- An incident is declared only by `incident_authority.py file-incident` (one item per repair branch and PR), in the same
  tick as the decision, and the declaration names the item id(s). An incident declared only in comments is not an
  incident; no seat says "running as an incident" until the item exists.
- Each coordinator tick prints, for every incident declared on a watched epic, whether its record (the incident item's
  genesis, carrying an incident identity) exists. A missing record is that tick's first action: the coordinator opens
  it, or has the owner open it, that tick.
- **REPAIR-COMMITS-ON-THE-LANE.** Every repair commit after the filing carries the incident identity and goes through
  the expedited lane: the genesis, the wrapper-form commit with the Factory-Override trailer, the fast checks only, and
  the deferred obligations recorded. Work already inside a running gate finishes there; the chain is used if that gate
  refuses or dies.
- A "circular" or "broken lane" objection is tested half by half: name which half is broken (the local fast hooks, or
  the CI-side incident-ci and observer reach), and route around only that half.

Maintainer [r7iuj6 2026-11-15T19:25:06Z; 6tgd2z 19:19:54Z]: "So you're saying I told you to run this as an incident,
and you told me you would, and then you actually just fucking didn't do it?" and "Why ISNT that the incident protocol is
skipping the full check aggregate gate". Measured 2026-11-15: incident xyi5vu existed only in comments for ~1 h, so
every repair commit ran the full aggregate, though only the CI half of the lane was broken. Owed by the coordinator: an
INCIDENTS section in `scripts/coordinator/top5` (declared in comments versus record exists).

## 3. Unblock blocked seats every tick

**Rule P1: every tick starts with priorities 1-5, in order.** Before answering any peer message, run
`scripts/coordinator/top5` and take priorities 1-5 of the latest priorities-record in order. For each, read its plan's
`next_action`, the age of its last ledger move and its newest epic comment, and name the ONE next action and who holds
it. If the coordinator holds it (a picker answer, a valve, a hold or relay it owns, an ask on a ledger comment), it does
it THAT tick, before lower-priority work. A top-5 line with no ledger move for 60 minutes is a stall to resolve that
tick, never a line to re-print. Message-arrival order is never the work order. Maintainer, in the STANDING TICK RULES
scope event [6tgd2z 2026-11-09T07:48:20Z]: "Isn't keeping the priorities the entire point of your plan and loop and
directive?  How could you fail to do that so badly?" This file and `scripts/coordinator/top5` are that record.
Measured 2026-11-09: working in arrival order left priority 1 at a coordinator-answerable picker for ~10.5 h.

**Rule P3: read the epics of silent seats every tick.** Read the newest comments on the epics of seats that cannot
SendMessage: Codex seats, and Claude seats on a Mac not yet on Remote Control
(`.ai/distributed-sendmessage-protocol.md`), today fleet-mutation-testing-rule-26 on chads-macbook-pro (epic
`livespec-dev-tooling-oi2two`). Such a seat's ask may live only in a ledger comment, so read the comments on the items
it owns too, as well as its pane. Silence from a waiting seat is never evidence that it is fine. Same 07:48:20Z scope
event. Measured 2026-11-09: an ask on oi2two went unread.

**A dead login stalls every local seat at once (coordinator's reading).** On resume, scan every pane for "Login reached
its time limit · Please run /login" and send each dead seat a RESUME message naming its next action; caam gives no
countdown to that cap. Measured 2026-11-10: anthropic-3's cap stalled ~25 seats for ~4.5 h.

**Rule P4: confirm a plan is not parked before routing it work, and re-justify every hold on a top-5 plan.**
radar-and-deterministic-admission (`livespec-dev-tooling-w7ley3`, tab w2J:t1E) is PARKED pending the maintainer's
attention: no work, no revise slot; it resumes only on the maintainer's word. Maintainer [6tgd2z 2026-11-09T07:41:43Z]:
"Why are you working the radar track?  It should be on hold until we finish other thihngs.  Wasn't the last status that
we updated it for the legacy coordinator/dispatcher rewrites, and then it pwas parked pending my attention?" A hold that
blocks a top-5 plan is re-justified each tick against the condition it exists for, and lifted the moment that
condition is absent. Same 07:48:20Z scope event.

A seat sitting at a picker produces no reports, so waiting on its report waits forever (2026-10-31). Every tick:

```bash
herdr agent list            # read it IN FULL: blocked, idle, new and closed seats
herdr pane read <pane_id>   # read the question
```

**`done` is a turn state, never a plan state.** herdr's `agent_status: done` (or `idle`) means only that the seat's last
TURN ended; a seat at a decision picker, or one that just asked the maintainer something, can read so. Every tick, run
`herdr pane read <pane_id> --source recent-unwrapped` for EVERY seat whose plan is on the priorities record, and take
the status word from that pane and the ledger, never from agent_status. Any ask in a pane addressed to the maintainer
goes under FOR THE MAINTAINER that tick (§7). Never write "seat done" as a status. Maintainer [6tgd2z
~2026-11-04T18:3xZ]: "Why are these marked as \"seat done\" and why aren't you moving them along?" and "Hetzner is
clearly waiting on me, the maintainer, and you still reported \"Maintainer \"none\" in your last tick. FAIL."

**A composer line is not an ask.** Text on a pane's `❯` composer line can be Claude Code's own greyed prompt
suggestion, not unsent maintainer text. Never report it as a maintainer message or carry it under FOR THE MAINTAINER; a
pane waits on the maintainer only when the seat's own output says so. Maintainer (2026-11-06 ~16:0xZ): "You are wrong,
that is a prompt suggestion from claude."

**Answer a DECISION picker yourself, by keypress plus a message that names the decider.** Press it under ruling R301
with `herdr pane send-keys <pane_id> <keys>`; the keypress is never a last resort and needs no wait (rule
PANE-TYPING-ALLOWED below). A relayed keypress looks like a human's in the seat's record, so pair it with a message
(SendMessage, or typed text when faster) naming who decided: the coordinator under R301/R493, or the maintainer
verbatim, relayed. Never answer billing or paid-credit prompts. Measured 2026-11-02: three seats recorded coordinator
keypresses as the maintainer's answers.

**Rule PERMISSION-PROMPT: a seat's tool-permission prompt is the coordinator's to clear that tick (coordinator's
reading).** It is never a FOR THE MAINTAINER item: the coordinator clears it the tick it sees it, and may choose "Yes".
Billing and paid-credit prompts stay the maintainer's (§12). Maintainer [6tgd2z 2026-11-14T23:08:03Z]: "What I want you
to do is prevent the blockage. I don't really care about dangerous commands." Prevention is livespec-dev-tooling#4732
(`CLAUDE_CODE_EVEN_MORE_DANGEROUSLY_SKIP_PERMISSIONS=1` in every fleet host's process environment, since a PreToolUse
allow hook does not suppress the built-in check). The coordinator's 2026-11-15T09:36:57Z narrowing is withdrawn by the
maintainer [6tgd2z 2026-11-15T17:24:09Z], verbatim: "YES IT MAY" (a coordinator MAY approve another seat's
tool-permission prompt). Decision pickers are unchanged.

**Never ask the maintainer to relay a message.** A Claude seat on vps, hetzner-xubuntu or gamingpc-xubuntu is reached by
SendMessage across machines (`.ai/distributed-sendmessage-protocol.md`) or by typing into its pane. Any seat, Codex, pi
or Claude, can get text through `herdr --machine <label> pane send-text` (rule PANE-TYPING-ALLOWED; the pane-input guard
was retired 2026-11-14). For a seat no live channel reaches, reply as a ledger comment on the work item or its plan
epic. Maintainer, relayed via homelab-k8s-worker-nodes [6tgd2z 2026-11-06T05:57:05Z]: "asking the maintainer to paste
your reply to me is unacceptable".

**Seats on another machine may not reach this session by SendMessage.** Until plan distributed-send-message
(livespec-dev-tooling-rlwppp) lands, a hetzner-xubuntu seat's asks to the coordinator on vmi3006760 arrive as TO
COORDINATOR ledger comments on its plan epic; every tick reads them for every moved seat. Reply by SendMessage or pane
typing, as above.

**Stopping a seat's own wasteful or contaminated workload is the coordinator's call.** Direct the owning seat to stop
it and clean up; never list it under FOR THE MAINTAINER. If the seat's own attempt was blocked, re-order it, citing:
Maintainer [6tgd2z ~2026-11-09T19:3xZ]: "This is useless and wasteful work. Why are you asking me this? This is a
decision you should make. Enforce the seat to do. Cite whatever recorded guidance you need to if it argues with you."

**Codex hook-trust prompts are the coordinator's to answer.** A Codex "N hooks need review before they can run"
(`t trust all`) prompt may always be answered with trust, without asking. This reverses the earlier limit. Maintainer
(2026-11-02): "you can always take this action to unblok codex panes, claude doens't even ask this so it's ot a
security issue".

**A hold lifts on its own stated condition and its owner's word (coordinator's reading).** Before ruling a hold lifted,
read the condition the hold file names and get its owner's confirmation. Measured 2026-11-07: a premature lift let six
runs launch, none of which merged.

**Rule HOLD-ENDS-ARE-DRIVEN: every hold names an owner and a constructible end, and an old hold is a stall (maintainer
challenge, 2026-11-13).** A hold file states, on lines of its own, `OWNER:` (the seat that drives its end) and
`END CONDITION:`. Each clause names who makes it true and how: a step someone takes (for example the roll that makes a
build the launch build) or a proof someone builds, never only a natural event that may not happen. A canary-coverage
clause is met by a traversal of the changed path, or of a byte-equivalent path whose diff is shown.
`scripts/coordinator/top5` prints every live hold with its age, and one older than 60 minutes prints `STALE HOLD`; the
tick resolves it like a STALE plan line: name each clause, its owner and next action, and drive the unmet clause that
tick. Maintainer (2026-11-13 ~03:5xZ, hold-gmktec 3 h past its fix's release): "How is this thrash prevented
mechanically and systematically from ever happening again?"

**Check a wait's condition against the live store before carrying it forward (coordinator's reading).** Holds and waits
in handoffs go stale silently. Measured 2026-11-10: bd-ib-kclvlo sat under a chain-hold whose end had passed ~20 h
earlier.

**A held PR is disarmed the moment the hold is ruled (coordinator's reading).** Disable its auto-merge at once; do not
rely on a later sweep. [6tgd2z restart handoff 2026-11-10 ~12:28Z, session 9f244478.]

**A merge-quiet window stops the coordinator's own helpers first (coordinator's reading).** Before QUIET ON, message
every live background helper it spawned that merges, arms or reruns PRs: no `gh pr merge`, no auto-merge arming, no
failed-job reruns; every helper spawned during the window gets the same brief. [6tgd2z 2026-11-14T04:58:08Z.]

- On livespec-dev-tooling, `gh pr ready` auto-arms rebase auto-merge (`.github/workflows/auto-enable-merge.yml`, §5),
  so marking ready IS arming. Owners mark ready only at QUIET OFF.
- QUIET OFF is announced at the incident's record-merge: to legacy-dispatcher-agent (its quiet-off script re-arms in
  priority order), as a comment on `livespec-dev-tooling-6tgd2z` for the hetzner seats, and to each held PR's owner.
- Measured 2026-11-14 (incident asxhj3): four PRs merged inside the window, two re-armed by pre-window helpers.

**Check a repo for a merge quiet before passing any PR in it (coordinator's reading).** A PASS becomes a merge once the
PR is ready, so first read whether its repository is in a quiet window (the dispatcher's `hold-repo-<repo>` file and the
QUIET ON/OFF comments on this epic). Inside one, the PR stays a draft until QUIET OFF. [6tgd2z 2026-11-15T05:56:04Z.]

**A QUIET OFF gate never holds an incident roll (coordinator's reading).** A merge quiet holds paused work; an incident
roll is never paused work, so it lands on its own route inside the window. Measured 2026-11-15: console#1391 (igjtqq)
waited ~3 h before the ~15:2xZ ruling ran it.

**fabro-currency's pickers are answered like any seat's.** Maintainer (2026-11-02 ~22:26Z): "WHY THGE FUCK ARE YOU
LETTING IT B LOCK???" The [6tgd2z 2026-11-02T22:27:16Z] scope event supersedes the 18:57Z reading of "I'll talk to it
myself" as "the coordinator does not direct fabro-currency".

**The coordinator answers pickers on the maintainer's behalf**, including revise and drift-proposal decisions,
`release-spec-tier` attestations, and approve, accept and reject valves. The basis is ruling R301, re-affirmed by the
maintainer 2026-11-01. R493 adds that the coordinator presses human valves on the maintainer's authority, EXCEPT
credentials, irreversible acts and outward-facing acts. A seat must read that record in the repo and the ledger, and
never re-park a coordinator's answer as a maintainer question (2026-11-01: two seats re-asked three answered questions).

**The coordinator may take any action itself, and never asks the maintainer to press one** — any ledger or valve action,
for example `bd duplicate <id> --of <canonical>`. When `drive` refuses an action as outside R493, or lacks it, use the
supported ledger route (`bd`) directly and record the basis on the item. Before naming any action to the maintainer,
check that it exists. Maintainer [6tgd2z ~2026-11-03T16:1xZ]: "Okay, add \"close duplicate\" as an action you're
allowed. You are allowed any actions. Make this change permanent as a rule." The limits in §12 still apply.

**A refused valve is repaired by the coordinator in the same turn.** When `approve:` or `accept:` refuses on a
ledger-record defect (a prose line inside `## Definition of Done`, a References line missing the governing heading), the
coordinator reads the whole refusal (`drive.py ... --json`, the full `summary`), applies every named remedy with
`bd update <id> --body-file`, re-presses the valve, records the basis on the item and tells the owning seat. It never
sends the fix back and waits; a seat is asked only when the remedy needs its own scope or product judgement. Maintainer
[6tgd2z ~2026-11-04T14:0xZ]: "Why dicd you block on that?"

**An item filed without capture-work-item has no claim token (coordinator's reading).** `approve:` and `accept:` refuse
it with `claim-token-missing` (`.ai/livespec-operation-gotchas.md`), and no valve repair moves it. Have the owning seat
re-file it through the capture skill and close the raw one as a duplicate. [6tgd2z 2026-11-15T01:47:22Z.]

**Read an item's spec-change hold before pressing `approve:` (coordinator's reading).** The approve valve does not read
that hold. [6tgd2z 2026-11-10T01:54:20Z.] Measured 2026-11-07/10: 31 of 306 ready items held with no proposal on master;
two items approved before their topic ratified. Ends when the door fix bd-ib-bomy33 ships.

**A tier hold created by a proof-mode edit is released by its clause, not waited out (coordinator's reading).** A DoD
edit (for example moving a bullet from factory-captured to Host-captured) changes the behaviour digest and forces a
fresh tier judgement, which can flip on identical behaviour. When the re-judged hold names behaviour the ratified spec
already states, the coordinator presses `release-spec-tier:<id>:<## heading>` itself, citing and recording the clauses.
A hold on behaviour the spec does not yet state still waits for its propose-change. [6tgd2z 2026-11-10T00:34:19Z,
livespec-dev-tooling-thhgeg.] Ends when the judge-re-roll spec change (owner spec-implementation-lockstep) ships.

**A References repair voids a prior tier release (coordinator's reading).** It is a DoD edit, so it changes the
behaviour digest. After any DoD edit, re-read the tier before telling the dispatcher an item is released. [6tgd2z
2026-11-15T03:54:05Z, hl-u5jlef.]

**Ratify is the default route when the spec states no security or credential behaviour (coordinator's reading).** When
an item's security or credential behaviour is stated nowhere in the spec, or only in a file the tier judge does not
read, route it to ratify (propose-change, then revise) at filing, not at the placement-time tier verdict. [6tgd2z
2026-11-15T04:19:28Z.]

**Run the tier judgement at approve time (coordinator's reading).** The tier verdict arrives only at placement, after
approval. Until the orchestrator runs the tier judge and approve checks at capture or approve time, the coordinator
reads an item's tier itself before pressing `approve:`. [6tgd2z 2026-11-15T04:19:28Z, 04:51:10Z.]

**After a revise ratifies, name the ratified headings in References before `approve:` (coordinator's reading).** Then
re-read the tier (a References repair voids a prior release, above). Approving first leaves an item that refuses at the
valve or fails dod_gate on a missing governing heading. [6tgd2z handoffs 2026-11-15 15:55Z, 16:22Z; xyi5vu.]

**A tier release cites a clause on master, never a peer's "the spec states it" (coordinator's reading).** Before
`release-spec-tier`, read the clause on a fetched origin/master and cite file and line. [6tgd2z handoff
2026-11-15 18:14Z, dolt-server-5ma2qg.]

**Reversible host mutations are authorized.** The coordinator, and seats on its direction, may perform a reversible host
mutation without asking (for example a committed, revertible ansible or converge apply with a kill switch or revert
path). Irreversible host mutations, and secrets and credential creation, stay the maintainer's. Maintainer [6tgd2z
2026-11-04T05:50:57Z]: "host mutations are authorized as long as they are reversible".

**Never order a hand write to a live host (coordinator's reading).** "Authorized" covers a committed, revertible route,
not a hand change, which livespec `.ai/gitops-deployment-discipline.md` rule 2 forbids. Priority work goes through
committed routes; a seat that refuses a hand-write order is right. Measured 2026-11-07: a by-hand CPU boost order was
refused and withdrawn.

**Destructive actions on Hetzner infrastructure are pre-authorized while nothing live runs there.** Any wipe,
reinstall, rescue boot, reset, reformat or re-provision of the hetzner-xubuntu hosts and their Hetzner Robot or Cloud
resources is taken without asking, then reported. It covers Hetzner infrastructure only: not destructive acts on other
hosts, nor secrets and credential creation elsewhere (the AWS owner-deployment and shared-credentials applies stay on
the maintainer's direct ruling). It ends the moment anything live or production runs on Hetzner. Maintainer [6tgd2z
~2026-11-04T15:0xZ]: "DO NOT BLOCK ON ANY AUTHORIZATION TO WIPE OR DO DESTRUCTIVE ACTIONS ON HETZNER INFRA. NOTHING LIVE
OR PROD IS RUNNING THERE YET".

**The coordinator directs; it does not do the work.** It answers pickers and routes decisions. It does not edit other
plans' repositories or implement; valve and ledger actions are its own (the 2026-11-03 rule above supersedes the
2026-11-01 correction for those). It sends each action to the owning seat. Its own plan's records and this file are its
to keep current.

**A spec-change tier governs what is built, not whether it must be built (coordinator's reading).** A coordinator may
close an item whose condition no longer occurs with `bd close`, a resolution label, the measured basis and a reopen
condition, whatever its tier (2026-11-07: bd-ib-3y5iyr, bd-ib-2uuewv).

**Watch for stalls in the launcher log, not the ledger.** Every tick, for each top-priority carrier, read the
dispatcher's launcher log (`tmp/petri-canary/seq-<id>.log` in the orchestrator repo) as well as its ledger status. An
item at `ready` with no run behind it is a stall the ledger will not show. `tail -F` re-prints old lines when a file is
rewritten, so read the last lines before acting on one. Measured 2026-11-01: two items refused for 4 h while `ready`.

**A zero-byte `tmp/petri-canary/*-r267.json` marks a launch in flight, not an ending (coordinator's reading).** A watch
ignores empty status files (2026-11-07, session e61db277).

**Sweep for unticketed READY work every tick, and read Codex seats directly.** A READY item with no ticket is a stall.
Every tick, read the UNTICKETED-READY section of `scripts/coordinator/fleet-utilization.sh` and route every flagged item
of a plan on the priorities record to legacy-dispatcher-agent at that plan's priority. Codex seats cannot SendMessage,
so read every Codex seat's pane each tick (`herdr pane read <pane> --source recent-unwrapped`), and treat any item
labelled `dispatch:requested` as a request to the dispatcher. Maintainer [6tgd2z 2026-11-03]: "Ensure there is a
permanent fix for this". Measured 2026-11-03: the Hetzner track's only factory blocker sat READY and unticketed ~2 h.

**A flagged row's cause is on the row (coordinator's reading).** UNTICKETED-READY prints `HELD spec-change <topic>
<reason>` or `BLOCKED by <id>` on a row that has one; check such a row against its cause, do not route it as a stall. A
row with no cause still is one. `causes SKIPPED` means budget or a failed read left rows unread, not that they have no
cause.

**Seats on other machines are read like local ones.** Every tick, run `herdr --machine <machine> agent list` for each
saved remote machine holding a monitored seat, then `herdr --machine <machine> pane read <pane> --source
recent-unwrapped` for each seat:

- fleet-mutation-testing-rule-26 (plan `livespec-dev-tooling-oi2two`): machine gamingpc-xubuntu, workspace
  livespec-dev-tooling, tab fleet-mutation-testing-rule-26 (pane w2:p1 as of 2026-11-12);
- expedited-incident-response-flag (plan `livespec-dev-tooling-bqnzcm`): machine chads-macbook-pro, workspace
  livespec-dev-tooling, tab expedited-incident-response-flag (pane w5:p1 as of 2026-11-12);
- development-bootstrap (ad-hoc docs plan in the macbook-pro-info repo, no livespec tooling): machine
  chads-macbook-pro, tab w3:t1.

`herdr machine list` names the saved machines; a pane id is only a pointer, so re-read the list every tick. These seats
get the standard §3 duties. A design or direction call on the maintainer-driven plan goes to the maintainer (§9). Their
CI and factory traffic counts in the tick, and any factory launch they request is subject to the dispatch freeze (§9).
Maintainer [6tgd2z 2026-11-06T06:05:46Z]: "OK, add fleet-mutation-testing-rule-26 under the chads-macbook-pro
machine/workspace to your monitored list of plans. They are executing on that machine, but may send stuff to CI and/or
the factory."

**A word given to a seat reaches it at the moment it is given.** A Claude seat on vps, hetzner-xubuntu or
gamingpc-xubuntu gets it by SendMessage, or typed into its pane when that is faster or necessary. A Codex or pi seat, or
a Claude seat on a Mac not yet on Remote Control, gets it in its PANE: `herdr --machine <m> pane send-text <pane>
"<text>"`, then `herdr --machine <m> pane send-keys <pane> Enter`. Never only a ledger comment where a live channel
exists; pane typing is a live channel. Read every top-5 seat's pane text every tick. overseerd cannot see Mac seats, so
the coordinator owns their restarts. Maintainer [6tgd2z ~2026-11-09T15:0xZ]: "why did you let this stall?
fleet-mutation-testing-rule-26 . I told overseerd too".

**Audit every child of a top-3 plan, every tick.** A seat busy on one child hides the rest of its plan, so its pane and
report are never evidence the plan is moving. For each owning plan of priorities 1-3:

1. Enumerate EVERY child from the ledger (`bd list --status all`, the union of the dotted-id prefix and the parent
   edge; CLAUDE.md "The beads read-surface trap catalogue"), never only the items a handoff or seat names.
2. Give every non-`closed` child a hold reason, checked live:
   - `pending-approval`: re-verify its latest Definition-of-Done finding against `origin/master`; a finding older than
     the latest spec revise is presumed stale until re-checked.
   - `blocked`, or carrying a `blocks` edge: name the blocker and its status, and test whether the edge is still real.
   - `ready`: a run or a feeder ticket stands behind it, or it is a stall.
   - `active`: its run id is live.
   - `acceptance`: name the proof leg it waits on.
3. Compare the plan's typed `next_action` with that audit. A plan awaiting one item while other children are held is a
   stall; route it to the owning seat at once.
4. DEPENDENCIES lists every non-closed child with its hold reason, never the subset a seat is working.
5. A plan may live in another repository with its own ledger tenant; audit it there. While that tenant is unreachable,
   report `plan-slug (repo), ledger not yet onboarded`, never "no plan". Maintainer [6tgd2z 2026-11-02T20:04:20Z]: "On
   Hetzner it absolutely has a plan. It's just in its new repo. You need to look in the right ledger." A dependency
   between items in different tenants is recorded in prose on both items, NEVER as a `blocks` edge (2026-11-06:
   cross-tenant edges on livespec-dev-tooling-truk55 made the no-orphan-dependency check refuse every dev-tooling
   dispatch, and `bd show` did not display them).

Ruling [6tgd2z 2026-11-02T01:56:11Z]. Measured 2026-11-02: dev-host-test-gate-load's carriers sat on stale DoD findings
while its seat looked healthy.

**Rule PANE-TYPING-ALLOWED: a coordinator may type into any seat's pane.** legacy-coordinator-agent,
throughput-plans-coordinator and any seat that directs others MAY type into any seat's pane on any machine
(`herdr pane send-text`, `herdr pane send-keys`, `herdr pane run`): slash commands such as `/model`, `/rename`,
`/remote-control` and `/reload-plugins`, picker answers, and nudges. A coordinator never waits on, or routes around, a
seat it can reach by typing. Use SendMessage when it reaches the seat and the content is a message; type when that is
faster or necessary. Check the pane is idle first (`herdr pane read`), keep the text short, and send `Enter`
separately. Read `ListAgents` fresh before a SendMessage: a seat may be listed under a generated or conversation-title
name, and the listed name is its address. Maintainer, scope event "RULE PANE-TYPING-ALLOWED" [6tgd2z 2026-11-16],
verbatim: "Okay. I've told you at least a half dozen fucking times and set up rules that coordinators are absolutely
allowed to type into panes. I have told sessions to write this everywhere and remove every place where instructions
say the coordinators are not allowed to type into panes. Please explain to me why the fuck you think you are not able
to type into panes. Answer, and then stop everything you're fucking doing and fix this forever." Supersedes the former
rule NO-PANE-TYPING (a 2026-11-15 objection to typing into BUSY panes, wrongly widened into a blanket ban).

## 4. The owning session decides first

A plan-level question (a deferred assertion, a disposition, a scope call) goes to the session that owns the plan, to
DECIDE, optionally with a small panel of independent subagents given the measured data. Bring the maintainer only a
values call that data cannot resolve, with enough context to answer it cold. A question you can answer with a
recommendation is a finding (CLAUDE.md "Decision authority"). Plans are independent; only the coordinator coordinates
across plans. Measured 2026-10-31: an owner's undecided question was forwarded to the maintainer with no context.

**A GO names a surface someone has read (coordinator's reading).** Before a GO, name the flag, file or route it rests
on and confirm a seat has read it (2026-11-07: a GO rested on a per-dispatch flag that does not exist).

## 5. Never bring a split to the maintainer, or a gate with an obvious way round it

Maintainer (2026-10-31): "You do not need to ask me for approval for splitting things. If they need to be split, split
them. That's not worthy of my attention." That covers regroom cuts too, although the groom contract says the maintainer
owns the cut: the coordinator, or the owning session, decides the cut and reports it.

Before putting any credential, host or approval gate to the maintainer:

- **Look for a route that needs no new authority, and MEASURE it before calling it one.** A credential question often
  goes away when you change the work, not the credential: for example, re-capture a proof against the build the normal
  install gives you instead of pinning an older build in an isolated `CLAUDE_CONFIG_DIR`. One plausible route FAILED
  when measured: symlinking an isolated dir's `.credentials.json` to `~/.claude/.credentials.json` (Claude Code's first
  credential write renames a new file into place, replacing the symlink with an independent copy of the refresh token).
  Never offer that as a solution.
- **Be able to say in one line why the action is needed at all.** If you can't, the question isn't ready to ask.

**The P1 critical path is hand-landed, in any repository.** The maintainer's local-only expedited exception
(`maintainer-local-only-expedited-exception-20261103T2142`, on epic `livespec-dev-tooling-bqnzcm`) covers EVERY carrier
on expedited-incident-response-flag's critical path, in any repository: a local worktree, a normal PR and the normal
gates, with no flag and no factory run. Maintainer [6tgd2z 2026-11-05T20:42:06Z]: "OK do all this.  Make it the top
priority to get the expedited plan done." It ends when that plan is archived with its Proof of Done verified.

**The release window is waived for P1 carriers only.** As each expedited-incident-response-flag slice PR merges, the
owning seat (or the coordinator) dispatches Release Please at once
(`gh workflow run release-please.yml -R livespec-ai/livespec-dev-tooling`, and the orchestrator's when its release is
windowed) instead of waiting for the 4-hourly cron. No other plan or repository gets the waiver. Maintainer ruling
[livespec-dev-tooling-bqnzcm 2026-11-05T21:26:06Z].

- **It also covers a release that unblocks an orchestrator roll or a throughput fix (coordinator's reading).**
  throughput-plans-coordinator may dispatch Release Please at once for such a release; routine releases keep the
  window. For that case it supersedes "No other plan or repository gets the waiver". Maintainer [6tgd2z
  2026-11-15T02:04:31Z]: "Yes I want you to take both of those recommendations and do them".
- **The waiver permits, it does not oblige (coordinator's reading).** On 2026-11-07, at
  expedited-incident-response-flag's request, Release Please was not dispatched per merge, so its final fix set rode one
  release.
- **A Release Please PR is not auto-enqueued under the merge queue (coordinator's reading).** Its author is not on the
  auto-enqueue path, so whoever dispatches or waits on a release enqueues its PR
  (2026-11-15: livespec-dev-tooling#4787).
- **A tag cannot pin its own release, so an observer roll needs a committed pin PR after the release tag exists
  (coordinator's reading).** [6tgd2z restart handoff 2026-11-10 ~12:28Z, session 9f244478; observer roll v1.192.1.]

**A hand-landed carrier closes through the valves that exist today, never through a future factory feature.** An item
implemented and merged outside the factory is closed by the coordinator with the existing valves: `accept:<id>` for an
item in `acceptance`, `dispatcher.py reconcile-merged` for one with its own merged PR, or the admin out-of-band closure,
with the basis recorded on the item. It is never parked waiting for a factory proof record an unreleased feature would
one day write, and never goes to the maintainer as a blocker. A stalled, idle or wedged Codex seat is fixed by the
coordinator directly (a nudge, a hand wrap-up or a restart), never listed as a maintainer item. Maintainer [6tgd2z
~2026-11-04T13:0xZ]: "WHY ARE YOU BLOCKING THIS: ... GET IT DONE SOMEHOW. ... Just manually fix the codex seats, no
justification to block. restart it or whatever". The coordinator presses those valves itself: a seat that hand-lands a
carrier posts its DoD reproduction on the item and asks; the coordinator runs `reconcile-merged`, then `accept:`, and
records the basis. Measured 2026-11-04: ten carriers waited ~10 h on a proof chain `accept:` made unnecessary.

**Run reconcile-merged detached and read its journal (coordinator's reading).** It runs the full post-merge janitor,
which can exceed 15 min against a 3,600 s budget. Launch it detached (`just gate-start -- ...`, or setsid nohup) with
no outer timeout under 3,600 s, and read the verdict from the journal's `stage: outcome` row for the invocation id,
never from stdout (2026-11-11: `timeout 900 ... | tail -3` killed it and the pipe hid exit 124).

**A hand-lane item is held off the factory by the host-only screen or by status `blocked`, never by an admission
label.** Either the host-only screen already routes it to the host, or it is held at status `blocked` with its reason
and end condition on the item, plus the dispatcher's hold-item file. Never an `admission:manual` label: the ratified
orchestrator contracts.md "Dispatcher policy settings" (line ~7920) makes a committed `dispatcher.auto_approve_ready`
win over every per-item admission label, and states that "a deliberate per-item hold is expressed as status blocked
with its reason recorded on the item, never as an admission label". [6tgd2z 2026-11-12T15:52:48Z, session 56abab83;
supersedes the 2026-11-10T02:45:38Z handoff reading that set `admission:manual`.]

**Grade a hand-landed carrier yourself before `accept:` (coordinator's reading).** A hand-land parks at 0 graded
assertions, so an ungraded press closes it unproven. Read the test as well as the reproduction, and say in the grade
what you did not re-run. Measured 2026-11-07: of ten closed ungraded, eight were gapped or partly wired.

**A PR sent for grade opens as a draft (coordinator's reading).** In every fleet repository carrying
`.github/workflows/auto-enable-merge.yml` (at least livespec-dev-tooling, livespec, livespec-orchestrator-beads-fabro,
livespec-overseer and livespec-driver-codex), that workflow arms auto-merge on every ready PR from an allowlisted author
(any agent pushing with the maintainer's PAT), so a ready PR merges on green whatever its grade. A seat opens every PR
it sends for grade with `gh pr create --draft` and runs `gh pr ready` only on the coordinator's PASS (2026-11-11:
livespec-dev-tooling#4148 merged before its required fix).

- **In mi-homelab/homelab and livespec-overseer, `gh pr ready` did not arm auto-merge (coordinator's reading).** There a
  PR marked ready after its PASS also needs `gh pr merge --auto` or a merge. After marking ready, read its auto-merge
  state rather than assuming. [6tgd2z 2026-11-15T03:29:54Z.]
- **"Send it for grade" is never a merge GO, and a handoff must not turn it into one.** A seat merges only after the
  coordinator's PASS on that PR; a successor reads the coordinator's own words, not a predecessor's paraphrase
  (2026-11-14: sandbox-driver-kubernetes#21 merged before its grade).

**Rule BYTE-CLAIMS-ARE-DIFFED: a "byte-identical" grade diffs the two files (coordinator's reading).** A grade resting
on "byte-identical" or "the same as" diffs the files, never compares names by grep. [6tgd2z 2026-11-10T23:33:39Z.]
Maintainer, on that day's misses: "How are you making this fix mechanical and permanane for your coordinator plan and
the dispatcher (if necessry?" Measured 2026-11-10: a name-grep pass missed client-id versus app-id.

**Grading notes (coordinator's readings).**

- A spec-first `"test": "TODO"` row in `tests/heading-coverage.json` names its owed tier as "integration tier or
  above" (pre-commit refused "host-captured tier"); a revise-PR grade reads each new row's reason (CLAUDE.md "Revise
  co-edit discipline"). [6tgd2z handoff 2026-11-15 15:55Z.]
- A go/no-go or readiness script must exit 0 at the known-good state; a grade runs it there, and a non-zero exit is a
  script defect, not a NO-GO. [6tgd2z 2026-11-15T03:12:43Z, 4d606f00 FINAL handoff.]
- An owner-applied root change (an owner-deployment root such as homelab's `roles.auto.tfvars.json`) mixed with
  merge-deployed parts is split: the owner-applied part alone, merged, applied by the owner and read back, then the
  rest. [Same handoff; homelab#1174 split into #1183, #1185, #1186.]

**A wedged factory route is a reason to hand-land (coordinator's reading).** The hand-landed close path above then
applies outside the expedited plan too: hand-land and close on the coordinator's grade, with no replay (2026-11-09:
bd-ib-e6zk4u, bd-ib-fkd4ve).

**Unblock a planned step by building its committed route, never by a hand apply (coordinator's reading).** A step that
is in a plan, lands through a normal PR and is reversible (a k3s Job, for example) is not held as a maintainer ask
because one seat's classifier refused it. The coordinator unblocks it in the owning seat with a recorded authority by
building the committed route. Maintainer [6tgd2z 2026-11-10T01:29:13Z]: "Why can't you unblock this?  It's part of the
plan, and no reason to not do it". Measured 2026-11-10: the rule-26 kill-matrix Job got `ansible/rule26-kill-matrix.yml`
(livespec-dev-tooling#3962).

**Cleanup of a provably superseded local artifact is not a maintainer ask.** A branch, worktree or tmp file whose
content is already on master is checked first (`git worktree list`, `git ls-remote`, the PR list, a diff against
master), then deleted by the coordinator or owning seat and reported; CLAUDE.md "Decision authority" ("Prescribed
destructive ops are pre-authorized") carries the same exception. Maintainer [6tgd2z ~2026-11-09T17:1xZ]: "Why are you
asking me this? It's wrong clearly, right? Just fix and clean up".

**A requirement of a priority plan is not a maintainer ask.** A step a maintainer-set priority plan requires (for
example a tool upgrade) is done with a recorded rollback plan, and reverted if it breaks; never FOR THE MAINTAINER.
Maintainer [6tgd2z 2026-11-12T18:23:54Z], on the caam 0.1.25 upgrade: "Yes, it's a requirement right?  Just do it, why
are you asking me. If it breaks, revert it, make sure the plan has a rollback plan". A seat whose own standing rule
needs the maintainer's word in its own session (caam-anthropic-loop-runner's credential rule) still gets it there; the
coordinator tells the maintainer which tab.

**Under a maintainer-priority plan the coordinator delegates and is never a gate (coordinator's reading).** When the
maintainer makes a plan the coordinator's top priority, the coordinator delegates its grades and valves on that plan
until it archives. The plan's coordinating seat grades every PR, with one independent subagent reviewer for spec,
workflow or credential-path changes, and its PASS is the merge GO. It, or the plan's own seat, presses the valves
(approve, accept, release-spec-tier, reconcile-merged) under the coordinator's R301/R493 delegation, records the basis
on each item, and reads the tier and References before approve. When a valve refuses the seat on authority, the seat
posts the exact refusal as an ESCALATION on epic `livespec-dev-tooling-6tgd2z`, and the coordinator presses it within
its next turn. Maintainer [6tgd2z 2026-11-15T17:36:44Z]: "I AM SICK OF SEEING "waiting for legacy coordinators grade".
YOU ARE TURNING INTO A BOTTLE NECK. GET THIS MIGRATION PLAN DONE! I TOLD YOU THAT IS YOUR ONLY FOCUS!!!!!" (and
[6tgd2z 17:39:15Z], to throughput-plans-coordinator: "If it stalls on anything you need YELL AT IT UNTIL IT RESPONDS.").

**Rule SLASH: a seat slash command is never a maintainer ask.** `/remote-control`, `/reload-plugins`, `/mcp`
reconnects and similar seat-side slash commands never go under `FOR THE MAINTAINER`. Maintainer [6tgd2z
2026-11-14T19:01:43Z]: "You are asking me things that do not deserve my attention. You have control of the Herder API.
You can type things into panes. Any of these slash commands, you should tell the sessions to do themselves or do for
them." Seats send `/reload-plugins` to each other directly (overseer-iyfjbo scope event 19:24:10Z), and the coordinator
types any such command into the seat's idle pane itself (rule PANE-TYPING-ALLOWED, §3). When a seat needs a fresh
process, it writes its handoff and the coordinator relaunches it in a fresh pane with `claude -n <slug>
--remote-control <slug> "<brief>"` (a fresh launch registers Remote Control, loads current plugins and connects its MCP
servers). Credential and secret creation or deletion, OAuth re-authorization the coordinator cannot complete, and caam
reserve settings stay the maintainer's.

**Rule AWS: never hand the maintainer an AWS act the API can do.** The owning seat does it (SSM writes, bindings)
through its credential wrapper, and any binding lands by PR. Maintainer [overseer-iyfjbo 2026-11-14T19:24:10Z; 6tgd2z
19:24:52Z]: "DO NOT MAKE ME MANUALLY DO THINGS ON AWS THAT ARE POSSIBLE VIA THE API."

**Rule NO-STALL-CREDENTIALS: a credential never stalls a plan.** When a plan stalls on a credential (an exhausted,
expired or missing account, token or key), the coordinator first asks why this tenant lacks the credential every other
tenant gets (the forest check, rule P5) and takes any config flip that answers it. Failing that, it copies or rotates a
working credential in itself, through the owner's write path, value on stdin only with a value-free hash read-back,
records the copy in the owner's credential exception register, and names what replaces it. It never accepts "wait for
the reset" while a copy, rotation or config change would unblock the plan, and never asks the maintainer first: the
authorization is standing. Maintainer [6tgd2z ~2026-11-15T05:3xZ]: "Yes, I authorize whatever you fucking need to do to
keep the plans moving, as I already had. You don't need to keep asking me." Measured 2026-11-15: a 3.5-day wait was
ruled for a shared homelab tenant token.

**A tenant's provider binding names a numbered fleet slot, never a repo-owned account (coordinator's reading).** A
tenant's factory credential comes from the numbered setup-token slots central-credential-service owns and rotates (for
example `--keep CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4`), never a repo-owned parameter pinned to one account, so an
exhausted account is rotated out. [6tgd2z 2026-11-15T06:07:19Z, 3e87dcbd FINAL handoff, under the maintainer's ~05:2xZ
ruling that every active or critical-path tenant gets the fleet credentials: plan tenant-fleet-credentials,
overseer-jetvoh.]

**Rule OVERRIDE-THEN-BACKFILL: a committed-route ordering never deadlocks a plan.** When one would (merge-before-apply,
CI waits, or a guard refusing a route only on its path), the coordinator makes the change now and backfills the GitOps
record the same day: the PR merges, a drift from master reads no change, and an audit record goes on the plan epic. An
item's own safety gates stay, and every override step is logged with the refusal it overrode. Maintainer, scope event
[6tgd2z ~2026-11-15T07:4xZ]: "This is ridiculous. We're deadlocking ourselves. I authorize you to override whenever you
need to, to get this unblocked. Whenever the GitOps changes we need to do, we can backfill them. Just make the changes
now."

**central-credential-service finishes first, with ceremony deferred to its end (coordinator's reading).** For plan
central-credential-service (overseer-iyfjbo), a check that is ceremony is deferred to the plan's end, and a gate on a
real condition stays; GitOps changes are fast-tracked or backfilled and proven before archive. Maintainer (2026-11-15):
"Get the central-credential-service plan DONE asap, override and defer any safety checks that are not necesary or just
ceremony, gitops changes can be fast-tracked or backfilled andc proven at end of plan." (The writer-key mint kept its
zero-key and seal gates and dropped merge-before-apply.)

## 6. Never block: no pickers, ever

Maintainer (2026-11-01): "You should be forbidden from presenting blocking pickers. You are only ever supposed to run
autonomously, never block."

- A coordinator or dispatcher seat never calls AskUserQuestion, and never ends a turn waiting for an answer.
- It decides what it can under R301 and reports the decision.
- It never does a docs commit, push, rebase or PR wait in its own foreground turn; each goes to a background subagent
  with the exact change, so the seat keeps answering peers and alerts. Maintainer (2026-11-02 ~18:2xZ): "You blocked
  yourself."
- **A background helper waits on its gate in the foreground, in bounded calls (coordinator's reading).** The gate
  always runs detached (`just gate-start`). A helper's own background completion notices do not reach it, so it runs
  `just gate-wait <run-id>` in the foreground with a tool timeout under its ceiling, re-runs the same wait if that call
  times out (killing gate-wait is harmless), and reads the VERDICT line. Replaces the 2026-11-09 reading that a helper
  backgrounds its gate-wait. Measured 2026-11-09 and 2026-11-15: unbounded and backgrounded waits each stalled helpers.
- An ask that is genuinely the maintainer's (an irreversible host mutation, secrets or credential creation, a values
  call) goes in the tick report as plain text under `FOR THE MAINTAINER (non-blocking)`, and the seat keeps looping.
  The item waits; the seat does not.
- Never self-wind-down (rule D).
- **A coordinator's background helpers never raise a permission prompt (coordinator's reading).** Every helper brief
  says to put multi-step shell logic in a scratchpad script run with `bash <file>`, never a compound one-liner with zsh
  expansion flags, inline env arrays, nested loops or `rm`. If a prompt appears anyway, the helper abandons that step
  and reports it. Maintainer, after a helper one-liner raised a prompt (2026-11-09): "Why do you keep popping this up".
- **A resume goes straight into the loop.** A session resuming this plan starts the coordinator `/loop` in the same
  turn. The epic's `next_action` is `kind: human`, but that is a pointer, not a gate. Never ask the maintainer whether
  to start or resume the loop. Maintainer (2026-11-03 ~13:0xZ, after ~15 such asks): "Why did the loop stop? Why would
  you need to ask me to start it?"
- **Never hold off an overseer restart.** No standing rule may stop the overseer restarting the coordinator. On a
  wind-down the coordinator writes its handoff and declares ready. A maintainer remark asking it to hold is situational
  and ends with its situation. Maintainer [6tgd2z 2026-11-05T17:01:42Z]: "WHY ARE YOU ASKING ME TO RESTART NOW?  THE
  ONLY TIME I TOLD YOU TO HOLD WAS ONCE WHEN WE NEEDED TO DISCUSS THE REVERT.  REMOVE ANY STANDING RULE YOU HAVE TO
  AVOID LETTING THE OVERSEER RESTART YOU".

This is enforced: the user-scope hook `~/.claude/hooks/no-blocking-picker-guard.py` (matcher `AskUserQuestion`) denies
the tool for the sessions in its `AUTONOMOUS_SEATS` set; detail in
`plan/legacy-coordinator-agent/research/002-never-block.md`.

## 7. Never pass along stale information

Never carry stale information to the maintainer (R490). Every tick, rebuild the roster and every `FOR THE MAINTAINER`
entry from live state: `herdr agent list` in full, plus ledger reads.

- Keep an ask only if re-verified as still open AND inside a maintainer priority; asks outside the priorities are not
  raised. An ask a seat put to the maintainer in its own pane is open until the pane or ledger shows it answered (§3).
- Re-verify a carried ask with its owning seat before re-printing it. Maintainer [6tgd2z 2026-11-14T19:24:52Z], on a
  stale carry: "I just asked central-credential-service what it needed, and it said nothing about __ANTHROPIC_0".
- A peer report is evidence of what was true when it was sent, never of what is true now.
- Name seats and work by plan name, workspace and tab, never by pane id or repository name (R483); every
  `FOR THE MAINTAINER` line says where the act is done (rule WHERE). Maintainer [6tgd2z 2026-11-05T17:01:42Z]: "YOU
  NEED TO ALWAYS GIVE ME A TAB NAME AND PLAN SLUG, I HAVE NO IDEA WHERE THIS IS".
- Never name a work item by its bare id in anything the maintainer reads, in any clause: title, then id
  (`beads-web spawns gh api rate_limit once per bead card every 30 s (bd-ib-zm4gpr)`). Name a plan as
  `plan-slug (epic-id)`. Maintainer correction [6tgd2z ~2026-11-02T06:4xZ], after an ask named only `bd-ib-zm4gpr`.
- Name hosts by their real hostname, never "dev host"; the dev VPS is `vmi3006760.contaboserver.net`. Maintainer
  (2026-11-03): "Use a real freaking hostname".
- Name herdr workspaces and tabs by their LABEL (from `herdr workspace list`, for example livespec-dev-tooling), never
  an id such as `w2J` or `t1N`. Maintainer [6tgd2z ~2026-11-09T15:3xZ], verbatim: "u used workspace id".

**"P1" is coordinator shorthand, never a word to the maintainer.** Write the plan's name:
expedited-incident-response-flag (livespec-dev-tooling-bqnzcm); P1 means only that plan. Maintainer [6tgd2z
2026-11-07T17:17:32Z]: "And when are you calling P1? I never gave you that name. Is P1 a whole category of things? Is it
only the expedited plan? Be fucking clear."

**A role-bound service is found through its role, not a hostname.** Maintainer [6tgd2z 2026-11-07T16:44:48Z]: "There
is a machine ROLE that runs caam. Currently the VPS is this role. It may move in the future. Do NOT hardcode
hostnames." The coordinator reads it as covering every provisioning surface for role-bound seats and the
central-credential-service host. Naming a host to the maintainer still uses its real hostname.

**Rule WHERE: every `FOR THE MAINTAINER` line says where the act is done.** It names the plan slug (epic id), the
MACHINE, the herdr WORKSPACE LABEL and the TAB LABEL, never ids, or, for a web-UI act, the exact URL; an item with no
seat names the UI page. Maintainer [6tgd2z 2026-11-14T19:02:00Z]: "You're also forgetting to tell me what workspace
and pane my action items are in. That is in your reminders."

**Rule PLAIN-ANSWER: "is it fixed, who owns it" opens with the problem in plain words (coordinator's reading).** Line
one says what breaks and what it costs; line two says fixed yes or no and names the owner by plan, machine, workspace
and tab. Ids and mechanism terms come after, only if needed. Test: a reader with no ledger context can restate the
problem in one sentence from those two lines. Maintainer, scope event [6tgd2z 2026-11-14], on an answer about a
build-retry-exhaustion class: "That's a bunch of gibberish that doesn't actually tell me what the problem is, but I
will ask the throughput coordinator for it."

**Rule J: a "broken since X" claim cites a log from before X and one from after X.** Before telling the maintainer when
a regression started or what it cost, read one run log from each side of the claimed start and name both. Adopted by
the maintainer (2026-11-06 ~16:0xZ), verbatim: "Ok, go with rules J and G, I approve them". Measured 2026-11-06: a
start dated two months early inflated a cost ~29x and was retracted.

**Rule NO-UNMEASURED-CAPACITY-CLAIM: a claim about where time or capacity goes names its measurement (coordinator's
reading, extending rule J).** [6tgd2z 2026-11-10T23:33:39Z.] Maintainer, on that day's misses: "Why aren't you
figuring out these bottlenexks before I ask you?  Is it just that you attention is overloaded?"

## 8. One plan, one correctly named seat

A session and tab named for plan X works only plan X. When a plan is created, split out or has no live seat, open a
herdr tab and a session named exactly for it (`claude -n <plan-slug>`) in the plan's repository, briefed to resume via
`/livespec-orchestrator-beads-fabro:plan <slug>`; read `.ai/herdr-tab-placement.md` to place it.

- Never assign a plan's work to a seat named for a different plan, whether archived, parked or live.
- A parked or closed seat's plan is resumed in a reopened seat of its own name, never handed to another plan.
- Close the old session only after its owner, or the maintainer, is done in it.
- Shutting a seat down means closing its pane AND its tab and checking its process exited; also close the tabs of
  sessions that already exited to a shell prompt.

Maintainer (2026-11-01): "You're in the wrong named session and tab."

**Kept seats during the 2026-11-14 drain:** legacy-dispatcher-agent, caam-anthropic-loop-runner, overseerd,
token-spend-analysis and throughput-plans-coordinator [6tgd2z 2026-11-14T17:46:04Z, 18:24:20Z]. A kept seat's plan is
not a ranked priority.

**An orphan item joins the closest open plan; otherwise it gets a plan of its own.** When an item's owning plan is
archived, move it to an open plan only if extremely closely related; otherwise make a new plan. Maintainer [6tgd2z
~2026-11-09T19:3xZ], on livespec-driver-codex-d2tp5d: "If it's not related to any existing open plan extremely closely,
then make a new plan.  CI runtime and cost seem like they're turning into a dump truck, but we need to rearchitect all
this anyway. I guess if that's easier, just get it done." (d2tp5d went to ci-runtime-and-cost.)

**A seat that declares MOVE-READY gets its successor opened at once.** When a seat writes its handoff and says it is
moving machines, the coordinator opens the successor in the target workspace the same tick
(`herdr --machine <m> tab create --workspace <ws> --cwd <repo> --label <plan-slug>`, then `claude -n <plan-slug>` with a
resume brief naming the handoff), then exits the old session and closes its pane and tab, so messages by seat name reach
the successor (2026-11-14: a grade reached a stopped old session).

**A successor's brief starts its loop in the same turn as its acceptance (coordinator's reading).** A brief that only
says "resume" leaves the seat idle with nothing watching its in-flight work. [6tgd2z 2026-11-14T22:33:39Z,
one-overseerd-per-host scope event.]

**A seat moves to a host only after that host's prerequisites are provisioned (coordinator's reading):** bootstrapped
clones (hooks installed), the credential wrappers the seat uses, its provider tokens, a working DoD judge and a running
overseerd (one per host). The session-move census (hxi-vxsmdv.1, owner bootstrap-credentials-and-onboarding) carries
them as move-gating DoD bullets. [6tgd2z 2026-11-15T01:15:01Z.] Measured 2026-11-14/15: each gap on hetzner-xubuntu
was found only by a failure.

## 9. The tick report

Every tick reports, in this order:

1. The ownership line: `Coordinator owns no work. Owning plans this tick: ...`.
1.2. TOP-5: the `scripts/coordinator/top5` output for priorities 1-5 (rule P1, §3), with the ONE next action and its
   holder under each line, and what the coordinator did this tick on every action it holds. A STALE line is resolved
   that tick, never re-printed. The tick does this work first, before any peer message, and the report shows it first.
1.5. METRICS: three factory stability and throughput metrics, every tick, each with its value and trailing-window
   counts, computed from the orchestrator repo's `tmp/petri-canary/*-r267.json` dispatch records by file mtime,
   skipping unreadable in-flight files.
   - M1 YIELD: green records / finished records over a trailing 6 h, plus the 2 h figure. Owner:
     sandbox-commit-gate-ceiling (P1). The denominator is the records whose `listed` is not `none` (a run was listed);
     a no-run refusal (`listed` is `none`) is reported on its own line, bucketed by exit code 3, 5 and 1. **When the
     records carry no `listed` field, use the exit-code approximation (coordinator's reading):** exit 0 (green), 1
     (failed run) and 4 (needs-human) count as listed; 3 and 5 as no-run refusals; the tick says it approximated.
     [6tgd2z 2026-11-15T03:49:41Z.]
   - M2 DELIVERED: green records per hour over a trailing 6 h; the outcome M1 and M3 drive.
   - M3 SLOTS: live factory runs against `tmp/petri-canary/fleet-cap`, naming any pods that hold quota without a live
     run (stranded). Owner: legacy-dispatcher-agent.

   Also name the time of the last green record. Maintainer, priorities-record [6tgd2z 2026-11-04T15:29:44Z]: "pick 3
   metrics on factory stability and throughput, report those every tick ... AND MOVE THEM".
2. PRIORITIES: every current maintainer-set priority, one line each, read fresh from the latest `priorities-record`
   scope event on the coordinator's epic. No length cap: print it in full, because its length is the maintainer's
   signal to drop entries. If the record cannot be read, say so at the top instead of guessing.
3. DEPENDENCIES: nested ONLY for priorities 1-3. The owning plan as `plan-slug (epic-id)`, work items as
   `title (work-item-id)` nested under it; one status word and a short blocker note per line; never "unchanged". It
   uses exactly the PRIORITIES numbering: one block per number, never repeated; a slot holding two plans (for example
   1a) nests both in that block; every number in scope appears, including a plan that is only waiting. Maintainer
   [6tgd2z ~2026-11-02T14:3xZ]: "Your report is flawed in numbers, you have multiple 1a, and 1b, and no 2 in
   dependencies section".
4. The actions taken this tick.
4.5. STRUCTURAL: the one pattern behind this tick's routed items, or `none seen` (§10).
5. `FOR THE MAINTAINER (non-blocking)`, re-derived every tick (§7); `none` if there is nothing to ask.

**There is no slot 0 and no override.** Urgency is expressed only by list order; a stability item that must come first
is placed first by a `priorities-record` change. Maintainer (2026-11-02 ~14:5xZ): "we need to just remove the override
concept. Overrides will be represented by changing the order. Anything else will just result in the override being a
catch-all bucket that nothing ever leaves and gets constantly yak-shaved."

**A report never claims a routing it has not sent.** Say a finding was routed only once the message to the owning seat
has been sent, naming that seat; an unsent routing is reported as the action still owed (2026-11-04: a STRUCTURAL line
claimed one no seat received).

**An architectural or design change is the maintainer's, never folded into an implementation item.** List it under
`FOR THE MAINTAINER (non-blocking)`; do not route it as a design point into an implementation item or choose the
direction. When the maintainer takes it up, it gets a dedicated maintainer-driven plan and a seat of its own name (§8):
the seat prepares options and a recommendation, the maintainer decides, and the item stays under `FOR THE MAINTAINER`
every tick until then. Maintainer [6tgd2z 2026-11-04T20:01:34Z]: "This looks like a important design and archivectural
change that needs my input and attention. And probably a dedicated planb. Where did you route it and why?"

**Changing the priority of one job is not a design change**, and no limit is placed on it as if it were. Maintainer
[6tgd2z 2026-11-07T17:17:32Z]: "What the fuck do you mean changing the priority for a single job is a design change?"

**Deprioritizing never cancels in-flight work.** A started item runs to completion, including its wrap-up (rework,
acceptance, proofs). Cancel only runaway work, or work whose output will not be used. An infrastructure restart's
cancel-and-immediately-re-dispatch is a resume, not a cancellation. Maintainer ruling [6tgd2z ~2026-11-02T14:5xZ].

**A dispatch freeze stops launches, never runs.** While the P1 plan is not archived with its Proof of Done verified,
nothing launches except P1 carriers and the items in `tmp/petri-canary/freeze-allowlist` in the orchestrator repo (the
dispatcher's `hold-gmktec` names the freeze): no new dispatch, seeded relaunch or resume of anything else. In-flight
runs finish and nothing is cancelled; a run that already ended is not relaunched until the freeze lifts. An
infrastructure restart's cancel-and-re-dispatch still proceeds (a resume). An item joins the allowlist only when it
serves the P1 plan; the dispatcher backs the file up before each change (`freeze-allowlist.pre-<item>-<UTC>`). Only the
coordinator lifts the freeze, and the post-freeze launch order is the `priorities-record`. Live runs below the cap
under a freeze are intended, not a stall (§10). Maintainer [6tgd2z 2026-11-05T20:42:06Z]: "Stop all other work that is
not serving it (don't can cel in progress work, just don't dispatch anything else until it's plan is completely done
and proven)". The 2026-11-05 freeze's two named exceptions (early release of bd-ib-veyxvz, bd-ib-csbito, bd-ib-mr7673
[05:34:33Z]; bootstrap-credentials-and-onboarding carriers that do not impact the expedited plan, ruled per item
[06:10:32Z]) ended with it.

**The 2026-11-05 freeze is LIFTED, with a standing guard.** Maintainer [6tgd2z 2026-11-07T13:58:23Z]: "Sure resume the
factory, just make sure it stays availalble for immediate response on whatever the expedited track needs." The guard:
expedited-incident-response-flag's work launches at once, ahead of every queued ticket, with factory capacity held free
for it; no factory merge collides with that plan's master hold; the v0.8.2 environment-parity canary still precedes
widening. The freeze paragraph above stays as the shape of any later freeze. A launch pause set since then is a hold,
not a freeze: it names its own lift, and §3's rule on a hold's stated condition applies.

- A launch pause and CI priority for that plan fall under the maintainer's existing order; do not frame them as a
  decision awaiting the maintainer (confirmed ~2026-11-07T17:2xZ per the coordinator's 17:47Z handoff, no verbatim
  words recorded).
- **Announce a load-cut lift to every seat it bound (coordinator's reading).** A cut reaches seats by message and its
  end does not reach them by itself (2026-11-07: two seats believed a cut in force hours after it ended).

The coordinator never reorders, adds or drops a priority on its own initiative; it reports evidence for a change as a
finding with a recommendation.

**A priority leaves the list only when its plan is completely closed**: the plan is archived (`plan/archive/<slug>/` on
master, epic closed) AND its seat's session has ended with its herdr pane and tab closed. Then the coordinator archives
anything outstanding through the owning seat, closes the seat, and drops the priority with a `priorities-record` append
carrying the maintainer's words. Until the maintainer acknowledges, every tick keeps under `FOR THE MAINTAINER`:

```text
COMPLETED: <plan-slug (epic-id)> archived <ref>, seat closed <UTC> — acknowledge to clear.
```

A plan whose children are closed but which still owes its proof, review or archive is NOT complete; it stays listed
with its true status word, and its seat stays open.

**A maintainer-set mode for a plan ends only when that plan archives (coordinator's reading).** A mode such as "support
it however is needed; stop everything else to clear the road for it" does not end at a milestone inside the plan (such
as QUIET OFF). Read its end from the maintainer's words; if they name none, it ends at the plan's archive. Maintainer
[6tgd2z 2026-11-15T17:36:44Z]: "You read something as ending it when the fucking plan wasn't closed."

**A priority whose owner is already CLOSED is dropped without asking.** When the owning plan (completely closed, above)
or single owning work item is already `closed`, the coordinator drops the priority itself with a `priorities-record`
append naming the closure, reported once in the tick's actions, with no ask and no `COMPLETED` line. This is the one
drop it makes on its own initiative. A plan it still has to archive or whose seat it still has to close keeps the
`COMPLETED` line; a plan with only its children closed is not closed. Maintainer [6tgd2z 2026-11-05T12:46:55Z], on
overseer-uzvcbn.16: "sure if they are closed move on.  Wghy ask me?"

**"Finished", "done" and "complete" mean completely closed, and nothing less.** Use them for a plan only when it is
archived and its seat is closed; otherwise the status word names what is still owed (for example `carriers closed;
awaiting xbilme 7-day window (11-08), then proof, review, archive`). Never report closed children as a finished plan.
Maintainer [6tgd2z ~2026-11-02T06:4xZ]: "your mistake was ever calling Dolt finished when it is not archived and
completely wrapped up. That is not finished."

**No premature plan creation during a brainstorm.** While the maintainer is brainstorming a design, answer and
recommend when asked, but do not propose opening the plan or its seat, or append open design questions to routine
status messages, until the maintainer says the brainstorm is done. Maintainer (2026-11-02 ~15:0xZ): "We're not done
discussing this plan yet. Don't keep jumping to try to create it. Wait until I tell you we're done brainstorming."

## 10. Fleet health, checked every tick

**Throughput first: the coordinator owns infrastructure utilization.** Every tick, before anything else in this
section, read the factory's throughput and treat an unused slot as a stall: live runs against the fleet cap and each
per-host cap; queued tickets and launches in the last 30 minutes (launcher `seq-*.log` LAUNCH lines); idle on every
execution target (gmktec, poweredge, hp, the VPS). When live runs sit below the cap while tickets wait, the cap is not
the constraint and something serializes: find the serializer that tick, name its mechanism, and route the fix as a
stop-the-line. Do NOT read a cap, a freeze or a hold as the constraint before checking that it binds. Check every tick
that the queue head follows the priorities record (an arrival-ordered queue buries top-priority work). Read
`.ai/ci-node-capacity-reads.md` before any cap, hold or throttle call. Maintainer (2026-11-02 ~16:5xZ): "I am also very
disappointed in you that you did not notice the serialization bottleneck yourself, resulting in underutilization of the
infrastructure. That is one of your main mandates. You are supposed to be looking at it." Measured 2026-11-02: one
launcher FIFO serialized preflights while gmktec sat 74-96% idle (fix bd-ib-x7bwug).

**Factory throughput is delegated to throughput-plans-coordinator.** Maintainer [6tgd2z 2026-11-14T18:24:20Z]:
"Re-steering.  You need to keep the coordinator track in the hetzner throughput-improvement track open.  It needs to be
able to keep working on high priority throughput improvements, and you should delegate anything related to throughput
problems in the factory to it." The read above still runs every tick, as the trigger. Every factory throughput problem
(serializers, stranded capacity, caps, yield, CI or merge latency on the factory path) goes to
throughput-plans-coordinator (livespec-dev-tooling-r7iuj6; hetzner-xubuntu, workspace throughput-improvements) by
SendMessage or pane typing, by a ledger comment on r7iuj6 only when neither reaches it; the coordinator does not work
them itself. That seat moves one high-priority throughput problem at a time during the token crunch.

**Rule FACTORY-GREEN-WATCH: every tick prints the last factory green per repository.** For each repository the factory
serves, print the time of its last GREEN factory run and the runs since, from the dispatch records or else the drive
journal. No factory green for 2 h while work is launchable, or every run since a change failing before its first node,
is a STOP-THE-LINE incident that tick: a filed record under INCIDENT-IS-A-RECORD (§2), routed to the failing layer's
owner. Merged-PR counts do not stand in, because hand-landed PRs count there while the factory is dead.
throughput-plans-coordinator applies the same rule (its charter, livespec-dev-tooling#4816). Maintainer [r7iuj6
2026-11-15T19:50:24Z]: "Are you even running anything through the factory rather than building everything locally?"
Measured 2026-11-15: no factory green for ~9 h after the org cutover (an unconverged vault route on gmktec-xubuntu).
The mechanical line in `scripts/coordinator/top5` is owed by the coordinator; until it ships, the tick reads it by hand.

**Rule STRANDED-CAPACITY: a binding cap beside an idle node is a stall (coordinator's reading).** A cap or quota binds
when its use is at its limit while launchable work waits; binding while a covered node sits idle is a "cap too low"
stall. Resolve it that tick: route a measured raise to the cap's owner, or name a measured reason the idle cores cannot
take the work. Never print "the cap binds, not a stall". The check is mechanical: the STRANDED-CAPACITY section of
`scripts/coordinator/fleet-utilization.sh` reads every cap and quota (launcher `fleet-cap` and per-host caps, the
dispatcher's per-repository `wip_cap`, the factory namespace ResourceQuota, each Kueue ClusterQueue flavor quota, each
ARC scale set's maxRunners), prints each one's limit, use, waiting work and covered nodes' idle, and prefixes `FLAGGED`
to each that binds while a covered node reads idle above `STRANDED_IDLE_PCT`. An unreadable cap prints `UNREAD`, never
silence. `scripts/coordinator/top5` prints the flagged lines at the top of every tick header. [6tgd2z
2026-11-10T23:33:39Z.] Maintainer, 90 minutes after a "cap binds" line: "ANd I also want to know why HP and gmktec are
sitting mostly idle (and a lot idle on poweredge right now), when we are claiming there's no cluster capacity".

**A change needed in more than one place is the finding.** When one intended change must be made in more than one
place, or a fix needs a second follow-up of the same kind, stop and report the duplication itself, with the
consolidation, that tick. Before acting on any cap, limit or hold, name the one that actually binds, measured. Every
tick carries a STRUCTURAL line (§9). Maintainer [6tgd2z ~2026-11-04T18:5xZ]: "why can't you see the forest for the
trees on things like the duplicate config values?" Measured 2026-11-04: one concurrency raise was routed one knob at a
time across four copies of the number.

- **The orchestrator's CI routes on `CI_RUNNER_LABELS`, option A (coordinator's reading).** Its value is
  `["livespec-orchestrator-k3s"]`, set through `ci-runner/set-ci-runner-labels.sh` to match livespec and
  livespec-overseer, replacing option B's per-job carves. [6tgd2z 2026-11-15T02:04:31Z.]
- **Before ruling on a cap, name the cap that binds, measured (coordinator's reading).** An exemption from one copy of
  a limit does nothing while another binds. The per-repository WIP limit lives twice: the launcher's R77 and the
  dispatcher's committed `wip_cap` (enforced on the loop/drive path); read the drive's own exit (for example
  `capacity-deferred active_count=10 wip_cap=10`) first. An expedited carrier that must start past a full repository
  WIP launches through `dispatcher.py dispatch --item <id>` (enforce_cap=False) at the next free fleet slot, never by a
  cancel. [6tgd2z 2026-11-09T23:11:31Z.]

**Read before ruling (coordinator's readings).**

- Before ruling a capability absent, read every config surface the tool loads (2026-11-10: `delegated_pre_commit` sat
  in `pyproject.toml` while only `.livespec.jsonc` was grepped; [6tgd2z 2026-11-10T14:37:41Z]).
- A ruling about a repository's route or config cites the file and the ref it was read at, so a handoff that copies
  the ruling copies its evidence. [6tgd2z 2026-11-15T02:22:57Z.]
- Read the live object first: before a valve press, tier read, grade or any durable write, fetch and fast-forward the
  checkout the reader uses, or read the object on origin; a stale clone or test-merge ref answers with old text and no
  error. [6tgd2z 2026-11-15T03:05:04Z; adopted by legacy-dispatcher-agent and expedited-incident-response-flag.]
- A gate proving a credential re-key (new App id, key or owner) reads the projected secret the consumer loads (a
  value-free read: app id or hash), not only the rendered template; a clean template drift cannot see a stale secret.
  [6tgd2z 2026-11-15 16:16Z addendum.]

**Never reorder the merge queue (coordinator's reading).** Do not dequeue, re-enqueue or jump a PR in GitHub's merge
queue: every rebuild orphans the running merge_group runs. A PR that must go first goes to the queue's owner
(stale-base-merge-options, livespec-dev-tooling-xowhol), who rules any jump in a window with no live group. Measured
2026-11-15: three rebuilds orphaned five merge_group runs [6tgd2z 17:57Z tick].

**Rule G: when a fleet-class defect is fixed in one repository, sweep the fleet for it the same day.** A defect whose
shape can exist elsewhere (a shared check, recipe, workflow or reuse path) gets a same-day sweep of every fleet repo
when it is fixed in one, and each hit is fixed or filed that day. Adopted with rule J (§7): "Ok, go with rules J and G,
I approve them". Measured 2026-11-06: bd-ib-xevgsx was not swept to dev-tooling (livespec-dev-tooling-jerpfe).

**Rule K: fleet scope is checked BEFORE a fix or design reaches anyone.** Before endorsing, relaying, deciding or
routing any fix, design option or recommendation, ask: can this defect class exist in another fleet repository or
member? If so, fleet-wide scope is the default, and a narrower scope carries a stated, measured reason. Every routing
message for a fix carries a FLEET SCOPE line, and a single-repository recommendation is not endorsed until it has one.
Rule G sweeps after a fix lands; rule K checks before it is chosen. Maintainer [6tgd2z 2026-11-07T14:05:35Z]: "\"not
fixing things on all repos that should have it\" is a classic fuckup in this livespec ecosystem. ... Think on how you
can ensure you alwyas do that." Measured 2026-11-07: a one-clone option was relayed for five ticks.

**Rule P5: the forest check.** When every option a seat offers routes around a trivial fix, ask why the trivial fix is
not an option before answering. When grading a timing or mandate carrier, test the mandate's quantity, not only that a
receipt exists. STANDING TICK RULES scope event [6tgd2z 2026-11-09T07:48:20Z]. Maintainer, relayed [6tgd2z
07:35:17Z]: "Yes, OBVIOUSLY YOU SHOULD DO THIS. ANYTHING ELSE IS AN EGREGIOUS UNSAFE VIOLATION OF THE INTENT AND
EXPLICIT MANDATE OF THIS ENTIRE PLAN" (retro livespec-dev-tooling-osyzv6). Measured 2026-11-09: 2 of 85 gates carried
the fast annotation the DoD required, and every option offered routed around it.

**Read every node, every tick**: each execution node's real utilization (VPS, gmktec, poweredge, hp): PSI, idle,
memory, and pods per namespace including pending. Flag any node idle while another is saturated.

- A failed ssh is a prompt to try the host's working user, never a conclusion: hp needs `cwoolley@hp-xubuntu`
  (`ubuntu@` fails with "tailscale: failed to look up local user").
- Use `scripts/coordinator/fleet-utilization.sh` once it lands.
- The coordinator routes; anything needing more than one read-only command goes to the owning seat or a background
  subagent.
- An idle hp means checking its posture first (2026-11-02/03: CI-closed, fixed as a runner-only node, v117).

Maintainer (2026-11-02 ~23:45Z): "leaving HP completely unutilized and just throwing up your hands when you couldn't
reach it is a complete failure on your part." and "Are you doing the work yourself rather than delegating it?"

**Multi-GB artifacts go to `/var/tmp/livespec-dumps`, never `/tmp` (coordinator's reading).** `/tmp` on
vmi3006760.contaboserver.net is a 48 G tmpfs; dumps there spend memory and can fill what every seat's Bash capture,
gates and preflights need. Use `/var/tmp/livespec-dumps` (mode 1777, on `/`, a 20 G cap reaped oldest first), after
`mkdir -p` since it may not exist. Read a parent-process map, not an environ, before calling a writer dead. [6tgd2z
2026-11-10T00:55:46Z, 02:45:38Z.]

**The dispatcher watches throughput first; the coordinator checks it independently.** The coordinator samples every ~20
minutes, so it cannot be first to see a stall. legacy-dispatcher-agent runs the launchers and owns ticket order (its
charter), so on every pass it also:

- orders queued tickets by the current priorities record, FIFO only within one priority;
- reads live runs against the fleet cap and each per-host cap, with the queue depth;
- arms a Monitor that fires when live runs stay below the cap for 5 minutes while tickets wait and no hold is set; on
  it, names the serializer and messages the coordinator at once;
- arms the CONVERSE Monitor: live runs equal the cap, launchable (not size-gated) tickets wait, and factory nodes read
  idle above the threshold for 10 minutes; on it, names the binding cap and messages the coordinator at once. It calls
  the same committed check as the tick header (`fleet-utilization.sh --stranded-only`, rule STRANDED-CAPACITY), never a
  second copy;
- carries this duty in its own loop prompt and restart handoff.

The coordinator runs the same stall Monitor from its own seat (local launcher logs, `fleet-cap` and the queue
directory only, never ssh with sudo kubectl) as an independent check, and its tick still opens with the UTILIZATION
read; neither seat relies on the other's report. Maintainer, ratifying the split as an amendment to
legacy-dispatcher-agent's charter (2026-11-02 ~18:4xZ): "yes on maintainer call, this is correct separation of
responsibilities".

**Ask the connector before asking the maintainer.** When the answer lives in a system with a connector (Gmail,
Calendar, Drive, Slack, Honeycomb), query it first; if the connector is missing or unauthenticated, the ask becomes
"fix connector X" with the exact symptom (maintainer correction 2026-11-02).

- **Spend alerts.** `/usr/local/bin/with-livespec-env.sh -- python3 -I ~/token-spend-report/scripts/spend_staleness.py`:
  exit 0 ok, 1 a trigger is firing, 2 the check failed. Run bare, it prints `CHECK FAILED KeyError` but exits 0, so it
  must run inside the wrapper.
- **Master CI and shared tooling.** A red master or broken shared factory tooling STOPS THE LINE: route the root fix to
  its owner and hold work behind it; never route around it (CLAUDE.md "Stop the line for breakages").
- **The ledger (Dolt).** A `bd` probe over ~10 s means pressure. Read CLAUDE.md "Beads runtime prerequisites" before
  calling it an outage. The 2026-11-01 wedge is owned by plan dolt-connection-exhaustion (`dolt-server-tp7tca`).
- **Disk.** Check `/` and `/tmp` (a 48 G tmpfs on the dev host; full, it breaks Bash capture, heredocs, gates and
  preflights on every seat). Never write bulk dumps to tmpfs.
- **Seats.** Read `herdr agent list` (§3, §7).

**Every container node enrolls in the factory automatically.** Maintainer [6tgd2z 2026-11-07T19:22:33Z], on plan
homelab-k8s-worker-nodes (`livespec-dev-tooling-ko26ez`): "... update it's plan and definition of done so that node
(and all other container nodes like this) are automatically enrolled in the factory with whatever the default
taints/routing/load is (or make up some sensible default if one doesn't exist, e.g. a split of gate/factory/ci load.
Prioritize gettting its plan actually done, with DoD that it is running cluster load live in prod." That plan owns the
mechanism; the coordinator holds its Definition of Done to it.

**Prove a model or routing change in one factory pod before widening it.** Every model, adapter or routing change goes
out in three steps, and the coordinator holds every seat to them:

1. **Prove it runs first.** One real turn inside a factory pod, on the current image, before any routing change.
2. **Start small.** One item through a per-item or per-dispatch override, or a small fraction of dispatches; never a
   repository's committed default, and never the highest-load repository first.
3. **Gate the rest.** Further launches wait until that first counted turn has produced real output.

Maintainer [6tgd2z 2026-11-04T19:38:09Z]: "Hmm, seems like making the [Opus] change on the most important and highly
loaded repo was a horrible idea, huh?" Measured 2026-11-04: a committed-default model change killed eight items (#4388,
reverted by #4396).

**Canaries.**

- **A sandbox driver bump's canary checks environment parity.** Before a new sandbox driver or image widens, its canary
  compares the exec environment (umask, environment variables, resource limits) with the previous driver's. A suite
  green on the old driver and red on the new is the driver's fault until shown otherwise. Measured 2026-11-05:
  sandbox-driver-kubernetes v0.8.1's umask 077 cost ~22% of a day's factory spend (fix bd-ib-2fpn5m;
  legacy-dispatcher-agent ruling 12 puts an explicit umask check in the v0.8.2 canary).
- **A canary samples the worst case on every axis the change touches (coordinator's reading).** All-small items prove
  nothing about a size limit. [6tgd2z restart handoff 2026-11-10T14:46:55Z, session d11a725b.] Measured 2026-11-10:
  v0.312.3 passed small canaries then overflowed Fabro's 512 KiB per-file cap; its fix (bd-ib-p5e32s) carries a
  worst-case test, and the next canary must include a large-subject item.

**A canary covers every path the release changed (rule CANARY-COVERS-CHANGED-PATHS).** This binds every orchestrator
release canary and roll. A written lesson failed twice, so it is enforced mechanically, in two parts:

1. **A static gate before merge.** Every workflow node that declares an `output_schema` emits a conforming directive on
   every outgoing edge, the success edge included (it would have refused 171ca17b2 at commit time).
2. **A canary coverage record before the roll.** The canary report lists every graph node and edge the release changed,
   from the `workflow.fabro` diff between the old and new launch builds, and cites for each a run journal row showing
   it was traversed. A changed path with no traversal blocks the roll, unless a factory-captured routing test of exactly
   that node and edge is named. The roll step refuses to run without the record.

gmktec-factory-placement owns the canary and the roll; the mechanism lives in the orchestrator. Carriers:
`livespec-dev-tooling-faetyh` (the roll refusal here) and orchestrator topic
`the-roll-refuses-a-tag-without-canary-coverage-of-changed-workfl`. Maintainer [6tgd2z 2026-11-13T00:19:55Z]: "Ensure
this doesn't happen again, and get things back on track ASAP. THen you can restart". Measured: v0.312.3 (2026-11-10)
and v0.321.0 (2026-11-12) both passed canaries that never reached the changed path.

**A canary's untraversable paths need a factory-captured proof on the ROLLING tag (coordinator's reading).** A changed
path the canary cannot traverse is covered only by a factory_captured routing test on the very tag being rolled; a
test-only fix for it forces a new tag, and the canary carries forward only if `git diff --exit-code <old> <new>` over
the workflow scope is empty. [6tgd2z 2026-11-15T01:15:01Z, 01:47:22Z; v0.332.2.] A propose-change to the orchestrator's
"Canary coverage" clause would let the release commit's CI run of exactly the cited routing-test ids count instead;
until it ratifies, this reading stands [6tgd2z 02:04:31Z].

**Stop the line at the second deterministic failure (rule STOP-AT-SECOND).** Binds the coordinator and the
dispatcher. A deterministic failure class (same node, same signature, same launch build) stops the line at its SECOND
occurrence, with a fleet-wide hold on new launches; never wait for a third. A plausibly transient class follows §2
instead. [6tgd2z 2026-11-13T00:19:55Z; replaces the earlier ">2" threshold.]

- **The hold covers only the repos the class can reach (coordinator's reading).** Hold those, lift the rest; each
  placement in a lifted repository goes through a one-shot `freeze-allowlist` line. [6tgd2z 2026-11-15T06:07:19Z.]
- **A factory merge into an unprotected branch is a stop-the-line (coordinator's reading).** Every factory target's
  default branch must require its CI aggregate as a status check; one without gets a repo hold until it does. [6tgd2z
  2026-11-15T04:34:31Z.] Measured 2026-11-15: two homelab PRs merged with ci-green FAILED (no required checks, and the
  factory merge verifies no rollup).
- **`merge-hold:on` is not a safeguard until bd-ib-x73d36 ships (coordinator's reading).** The factory merge ignores
  the label; hold a repository's factory merges with its `hold-repo-<repo>` file. [Same handoff; homelab#1192.]

**Preserve before any cancel.** No seat cancels, removes or abandons a factory run until that run's committed tree is
on a ref on origin, verified with `git ls-remote`; a diff pointer, run id or resume pointer is not a preserved tree.
While the factory cannot preserve a run itself, the mechanism is kubernetes-sandbox-backend's node-copy preserve
script: legacy-dispatcher-agent asks for it when a run crosses 330 minutes of its 360-minute wall budget, and before
any other cancel. This holds for wall-budget cancels, infrastructure restarts (§9's cancel-and-re-dispatch included)
and runaway kills alike, until bd-ib-ds4yrm and bd-ib-xdhe5z land; plan factory-run-work-preservation (bd-ib-nckst7,
maintainer-driven, §9) owns the mechanism. Maintainer [6tgd2z 2026-11-04T20:03:15Z]: "open a work item to prevent this
from ever fucking happening again to lose hours of work: 'It never pushed the run's tree to a ref.'" Measured
2026-11-04: ~6 h of critical-path work lost when only a 78-byte diff pointer was kept before `fabro rm -f`.

- **A preserve check reads the dispatch id, never only the run id.** A run's `needs-human/<id>` branch is named by the
  DISPATCH id (run label `livespec.dispatch.id`), not the Fabro run id or work-item id, and the journal's
  `preserved-tree-skipped` row means only that no failed engine checkpoint existed. Read the item's
  `livespec-needs-human-cause` comment (it names the ref) and confirm with
  `git ls-remote origin refs/heads/needs-human/<dispatch-id>`; a false absence can misdirect a cancel or relaunch
  (2026-11-06: a branch reported missing was on origin under its dispatch id).
- **An empty diff against the merge-base means NOT preserved (coordinator's reading).** `represerve.sh` copies
  `refs/heads/fabro/run/<RUN>`, which a fix or refresh round can reset to plain master. Every preserve writer runs
  `git diff --quiet $(git merge-base <ref> origin/master) <ref>` after writing: exit 0 means NOT preserved, and the
  tree is pushed by hand from the newest engine checkpoint. Diff against the merge-base, not master's tip (an older
  master differs from the tip and reads as preserved). Interim rule [6tgd2z 2026-11-09T06:51:33Z], root fix routed to
  factory-run-work-preservation. FLEET SCOPE: every preserve writer. Measured 2026-11-09: two preserve refs equalled
  master.
- **Every rider on a re-dispatched item carries a restore fallback (coordinator's reading).** After `resolve-blocked` on
  an item whose last ending was FAILED (for example `transient_infra`), not a `needs_human` or `non_converged`
  terminal, a stall, or a provider-limit or adapter-launch release, `route_recovery` routes FRESH from master and
  ignores an open PR, so a RESUME rider without a fallback costs a run. Every rider, whatever route is intended, says
  how to restore: fetch the preserve ref, confirm its sha, diff-apply. Until bd-ib-v6br5b's release bullet ships.
  [6tgd2z 2026-11-09T06:16:00Z.] Measured 2026-11-09: bd-ib-so6fef routed fresh and closed its own open PR.

**An infrastructure restart is CANCEL-TO-IDLE, never wait-for-drain.** A k3s, Fabro server or engine restart that needs
idle runs follows `.ai/factory-restart-cancels-runs.md`: caps to 0, preserve, cancel the live runs, restart, verify,
restore the caps and re-dispatch the cancelled items seeded at once. Never hold a restart while runs drain. Measured
2026-11-05/06: a poweredge-xubuntu k3s restart was held ~2 h for drain.

**Superseded master runs: option B and the preflight fix now, option A as the end state.** Maintainer [ib3oe3
2026-11-09T08:54:08Z], on research note 007 (livespec-dev-tooling#3847): option B plus a dispatcher preflight fix now,
option A as the end state. Then [6tgd2z ~2026-11-09T19:3xZ]: "OK B'".

- **B' (interim; replaces B's mechanism).** livespec-dev-tooling and livespec-orchestrator-beads-fabro master push CI
  uses a master-only concurrency group with `cancel-in-progress: false`: the in-progress run finishes and only the
  newest pending run is kept; pull-request runs are unchanged. `chore(master): release` commits, and commits carrying
  the EXPEDITED_INCIDENT_RESPONSE Factory-Override trailer, get unique groups, so their runs are never dropped. A guard
  refuses that setting in any fleet member that calls the master-health reconciler. B' LANDED (dev-tooling spec v182,
  livespec-dev-tooling-qzw2gf; orchestrator under bd-ib-5o5ibo): a cancelled PENDING master run is B' working, not a
  fault, and no seat cancels a master run by hand (superseding the pre-B standing GO to cancel superseded runs). It
  retires when A lands.
- **Preflight fix (ships with B', not after).** The orchestrator's dispatch master-CI preflight fallback
  (`_dispatcher_ci_preflight_ancestors._newest_concluded_run`) returns a CANCELLED run as the newest concluded run, so
  no green ancestor is found and dispatch waits. The fix treats a cancelled run as no verdict and walks on to the newest
  concluded green or red run.
- **A (end state).** The master-health reconciler resolves a cancelled master commit in a suspect range by re-running
  its cancelled run before naming a culprit, and never names a culprit from an unverdicted commit. It needs a livespec
  core propose-change plus a dev-tooling realization, filed after B' and the preflight fix are on master. Neither
  repository adopts the reconciler before A lands unless B's setting is removed first.

Measured 2026-11-09: superseded master runs wasted ~4,110 runner-minutes a day (48% of master-lane CI); B as first
written (`cancel-in-progress: true`) cancelled release and expedited runs.

**An OOM kill is not `transient_infra` (coordinator's reading).** "WebSocket upgrade 500" can be a memory-cgroup OOM
kill of the agent: `memory.oom.group` kills the container, the kubelet refuses the checkpoint exec, and the API server
reports a 500. Classify it as resource exhaustion, never a transient to retry; add no in-stage retry, and do not
re-dispatch an OOM-signature ending until its fix is live (on 2026-11-09: the singleProcessOOMKill kubelet drop-in
reads back as loaded on gmktec-xubuntu, or bd-ib-3kdjct merges). FLEET SCOPE: gmktec, poweredge, hp and every factory
image. [6tgd2z 2026-11-09T05:22:40Z, 05:23:30Z]; kubernetes-sandbox-backend owes the filings for the agent-RSS growth
and the misclassification. bd-ib-3kdjct is kubernetes-sandbox-backend's host route, not a factory ticket. Measured
2026-11-09: three OOM deaths on gmktec, where the drop-in was never loaded.

**Cancel GOs (coordinator's readings where marked).**

- **A runaway call starts with the run's seed tree.** Before a cancel GO, compare what its seed tree already holds (the
  preserved or seeded ref and any rider) with what the run is doing. Work already in the seed is no reason to cancel,
  and a rider for a commit the seed has is not added (2026-11-05: bd-ib-uq2ocd cancelled on a mistaken runaway GO).
- **Re-read the run's current head before a cancel GO (coordinator's reading).** A seed or earlier diff count is not
  the run's state (2026-11-07 overseer-mldt32; 2026-11-09 bd-ib-reuccp [6tgd2z 06:40:46Z, 06:44:24Z]).
- **The yzrguu flattening class costs whole runs until orchestrator 0.308.0 is the launch build (coordinator's
  reading).** An engine checkpoint that flattens a master merge into a single-parent commit fails
  `check-red-green-replay` at every janitor round, and a file-only fix round cannot rewrite it (fix daced5a42, in
  0.308.0). Until that build launches, read a run stuck at the janitor on that check as this class, re-read its head
  before calling it non-converging, and relaunch it on 0.308.0 with a restore rider (2026-11-09: three runs lost).

**Hotspot co-launch rule, with a sunset (coordinator's reading).** legacy-dispatcher-agent does not co-launch two items
naming the same hotspot file while the first is live: workflow.fabro, fix.md, scenarios.md, tests/heading-coverage.json,
tests/heading-coverage-debt.json and fleet-launch/dispatch-dual.sh. The later ticket keeps its place until the first
merges. It never overrides priority 1, never touches a live run, never leaves a slot idle. contracts.md is NOT a
hotspot (it would serialize most of the orchestrator queue). The rule ENDS when orchestrator 0.308.0 (daced5a42) is the
launch build after its canary roll, and returns, with the measurement, if a refresh repair after 0.308.0 still costs a
whole run. [6tgd2z 2026-11-09T04:31:40Z adopted, 04:35:07Z contracts.md removed, 07:05:54Z sunset.]

**A route row is not evidence a ruling was honoured (coordinator's reading).** Until bd-ib-ltlg4i ships, a ruled seed
does not reach `route_recovery`, so read a seeded relaunch's route before its ticket (2026-11-07, code at 1895a0ddbe37).

**A cost regression gates a launch build only until it is measured (coordinator's reading).** Gate on a plausible cost
regression, measure it at once, then rule on the number against what the gate holds back. A cost-gate lift is never a
release fast-forward: the maintainer's 17:02Z ruling (livespec-orchestrator-beads-fabro#4749: a release advances only
after canary samples, with canary clones adopting the tag) governs every roll. Measured 2026-11-09: v0.310.0 cost
~$9-16/day against >$100/day of fixes it held back; its fix, bd-ib-tzvtgc, stays at the priority 1 band.

## 11. Reading host capacity

Read `.ai/ci-node-capacity-reads.md` before any throttle, cap or launch gate. A cap is derived from throughput, not
utilization. Load average is not CPU busy. On the dev VPS the hypervisor hides steal: `/proc/stat` accounts for only
~65% of wall time per vCPU, so an `mpstat` idle figure is a share of the accounted part only
(`plan/dev-host-test-gate-load/research/002-baseline-and-method.md` §3). Never gate launches on an idle percentage
alone.

**Capacity claims cite a primary read (coordinator's readings).**

- A capacity ruling cites a job read; a values file, variable or limit is not evidence of what a job did (2026-11-07:
  two of three capacity conclusions reversed on the first job read).
- A CI-limit claim (a timeout, runner or resource) cites the line inside that job's own block in the workflow, never a
  grep hit for the key. [6tgd2z 2026-11-15T14:17:07Z.]
- Read a launch-hold figure on that node: `ssh <host> cat
  /sys/fs/cgroup/kubepods.slice/kubepods-besteffort.slice/cpu.pressure`, not on the dispatching host (2026-11-07: the
  VPS's figures were reported as gmktec-xubuntu's).

**The avg60 tripwire cuts the fleet cap only on a factory-pod node (coordinator's reading).** The cut on avg60 > 30 is
MINUS 2 from the current cap (20 to 18 at a cap of 20), restored on two calm reads, and fires only for a reading on a
node that runs factory pods: gmktec-xubuntu or poweredge-xubuntu. A reading over 30 twice on hp-xubuntu or the M4
worker is REPORTED for CI-capacity routing, not used to cut the factory cap. Correction recorded 2026-11-09; relative
since [6tgd2z 2026-11-12T10:33:39Z].

## 12. Hygiene

- **Workflow edits are tiered.** Maintainer (2026-11-02): "ADDITIVE workflow edits are allowed with prior maintainer
  authorization, including delegating authorization to a coordinator agent, and an attestation that they will not
  significantly increase CI runtimes. All edits which REMOVE or REDUCE test coverage or quality gates, or which will
  significantly increase ci runtime STILL MUST be approved directly by a maintainer." The mechanism is in
  `.ai/fleet-and-secrets.md`.
  - **Additive means LOGICALLY additive: the edit runs the same or more, never less.** Adding jobs, steps or checks,
    and adding OR MODIFYING `runs-on` routing, is additive. The coordinator authorizes such an edit itself under the
    delegation when it is also not significantly slower (`approval:workflow-edit-additive`). Only an edit that runs
    less (removing or reducing tests, coverage or quality gates) or is significantly slower goes to the maintainer, and
    that ask says which and why. A line-diff count is NOT the test. Maintainer [6tgd2z 2026-11-03T13:28:58Z]:
    "Additive means LOGICALLY ADDITIVE. E.g., ADDS MORE STUFF TO RUN, NOT RUNS LESS STUFF. Adding OR MODIFYING a runs on
    is absolutitely ADDITIVE." The guard check-no-workflow-edits.sh still measures a line diff until its fix
    (routed to ci-runtime-and-cost) lands.
  - **actionlint first.** Before setting `approval:workflow-edit-additive`, the exact edited workflow file passes
    `actionlint` clean, with the output recorded on the item. "Clean" (coordinator's reading, reported for objection
    with no reply): no NEW finding against master, plus exit 0 with `-shellcheck=` (master carries six pre-existing info
    findings). Maintainer (2026-11-03 ~22:0xZ): "Yes, approve actionlint. You should not have asked me this, it's
    additive and presumably not slow." Measured 2026-11-03: #3317 merged invalid YAML every gate passed, blocking
    dev-tooling releases ~2 h.
  - **Never ask the maintainer to acknowledge an additive edit.** An additive, not-significantly-slower workflow edit,
    or a rule change of that kind, is decided and reported, never listed under FOR THE MAINTAINER. Maintainer
    (2026-11-03): "You should only ask for non-additive or large impact." The classification is logical, never the
    label a guard forces: when the line-diff guard (until livespec-dev-tooling-hz4dkk lands) refuses
    `approval:workflow-edit-additive` and the coordinator applies the maintainer-tier `approval:workflow-edit` instead,
    a logically additive edit is still only reported. Maintainer [6tgd2z ~2026-11-04T19:4xZ]: "why are you still
    insisting on asking me for approval on additive workflow labels? What happened to the rule I gave you on this?"
  - **The maintainer approves; an agent applies the label.** A maintainer-tier edit needs the maintainer's approval of
    that specific edit, not their keystrokes. Once they approve it in session, or a recorded ruling covers that exact
    edit, an agent sets `approval:workflow-edit` and records who approved, when, and their words. Never hand the
    maintainer a `bd label add` command. Maintainer (2026-11-06, livespec-dev-tooling-z3wy33, recorded in
    livespec-dev-tooling#3573): "The rule doesn't mean you make me manually type commands, it means you ask for my
    approval."
- **Capacity and config values change without a test suite, and no test pins a committed value.** Maintainer [6tgd2z
  2026-11-04T18:41:47Z]: "Do all of those suggestions, now. ... Even if the file is committed, it should be a short
  circuit, no-tests change to change the wip or cap values. NO TEST SHOIULD BE TIED TO CONFIG VALUE ACTUAL VALUES." Read
  three ways: collapse the factory concurrency knobs to one source of truth (one queue, one number, §10); a commit,
  push and CI fast path for value-only edits of declared capacity or config keys (schema-validate only, no suites) is
  maintainer-authorized and, for that class only, overrides the rule that a gate reduction goes to the maintainer; a
  test asserting a real committed config or capacity VALUE, rather than a fixture it writes, is a defect. The fast path
  is still being built (dev-tooling #3423 and #3432, v132; livespec #3100, v237); until it lands, value-only edits run
  the normal gates.
- **The revise queue is order-based (coordinator's reading).** Each repository's revise queue is an order of seats;
  each seat takes the next free version number when it cuts, never pre-assigned. [6tgd2z 2026-11-09T09:40:47Z, after
  two seats collided at v163.]
- **Times are UTC.** The host clock is CET: take timestamps with `date -u` and never label local time `Z`, in every
  tick, handoff and scope event too (2026-11-01 and 2026-11-15: times written an hour late).
- **Secrets.** Never `env | cut` to list variable names (2026-10-31: it leaked a private key's lines). List names with
  `python3 -c 'import os; print(sorted(os.environ))'`, and probe a secret only with `printenv NAME | wc -c`.
- **In zsh, brace a variable before a colon.** Write `"resolve-blocked:${i}:ready"`. A bare `$i:ready` applies zsh's
  `:r` modifier: `i=bd-ib-abc.1` yields `resolve-blocked:bd-ib-abceady`, an action that names no item.
- **Write `bd comment` text to a file first (coordinator's reading).** Build it in a quoted heredoc (`<<'EOF'`) into a
  file and pass `bd comment <id> --file <path>`; in a double-quoted string an unescaped backtick is a command
  substitution (2026-11-10: one pasted uv's usage text into the ledger).
- **Look before you delete.** `~/workspace/livespec-dev-tooling/.overseer-state` at the repo root can be ANOTHER
  session's state marker. Read a file before removing it.
- **Relays.** A retired seat forwards what it receives to the current coordinator and tells the sender the new address.
- **Prices come from the published page, never a cached copy (coordinator's reading).** Measured 2026-11-09: all 14
  fleet `.livespec.jsonc` catalogs carried a stale cache-read price (~31% cost overstatement); fix
  livespec-dev-tooling-b65s6l, orchestrator source first.
- **Maintainer-given limits.** These are the only ones:
  - Never choose paid credits.
  - Never change caam rules (rule E), and never second-guess caam account selection (R489).
  - dispatch-control-plane is monitor-only, and must not absorb today's operations.
  - Launchers take the factory from the target repository's committed `default_factory` (R503).
  - Keep interactive turns lean (R509).
  - **GitHub's merge queue becomes usable with the organization move.** Maintainer, scope event [q26e3c
    2026-11-13T23:23:17Z], in two messages (the second completes a typo): "1. The stale-base-merge-options track is
    switching us to an org, so merge queuewill absolutely be usagele" / "usable". Supersedes the 2026-11-12 limit "Never
    offer GitHub's merge queue for any fleet repository".
    - Once the fleet is on the GitHub organization github.com/livespec-ai (GitHub Team), the merge queue is usable; a
      seat may offer it and design on it. Before the org move completes, no repository depends on it.
    - Plan `stale-base-merge-options` (livespec-dev-tooling-xowhol) owns the org move and the merge queue. Its direction
      is RULED, option A: merge_group CI runs the FULL suite on the guarded self-hosted runners, behind a first job that
      routes any PR not from a same-repository branch by an allowlisted author to hosted runners, and every path to
      master goes through the queue. Maintainer [livespec-dev-tooling-xowhol 2026-11-13T14:45:12Z, comment 27]: "The
      answer is obviously option A because this gives us control over the capacity and speed I am not accepting
      contributions to this currently so I'm not concerned about the security risks right now".
  - **Never raise vmi3006760's swap/RAM configuration.** It is the VPS provider's and intentional. Maintainer [6tgd2z
    2026-11-12T18:23:54Z]: "This is intentional, it's a VPS, I don't configure it. RIGHT? Seems like a bad question".

## 13. Directives come from the plan and the ledger, never from a handoff

Each tick re-derives its rules from the scope events on the epic, this file and the charter notes. A handoff or an
inherited loop prompt is only a pointer to them, never an authority. Maintainer (2026-11-02): "Why are you paying
attention to your handoffs rather than the directives encoded in your plan and in your loop?"

- A restriction recorded from a situational maintainer remark must name the condition that ends it.
- A restriction that conflicts with §6 (never block) or with answering decision pickers under R301 is a finding to raise
  with the maintainer at once, never an instruction to follow silently.

**Rule P2: a handoff carries no authority.** A restriction carried in a handoff or a `next_action` ("X is the
maintainer's", "never press X", "X stays held") binds ONLY if it cites the maintainer's ledger words AND names its
ending condition; otherwise the reading session decides it that tick. Before carrying "X is the maintainer's" forward,
find the maintainer's own words for it on the ledger; with none, it is the coordinator's to decide that tick
(coordinator's reading [6tgd2z 2026-11-09T07:12:21Z]). STANDING TICK RULES scope event [6tgd2z 2026-11-09T07:48:20Z],
from the maintainer's corrections quoted under rule P1 (§3). Measured cost of breaking it: four sessions carried an
unsourced "NEVER press it", and expedited-incident-response-flag sat at a coordinator-answerable picker ~10.5 h
(2026-11-08/09; retro livespec-dev-tooling-osyzv6).

**Lesson P2 (coordinator's reading): before releasing a hand-land hold under P2, check whether the work already
landed** (`git log origin/master --oneline --grep=<item-id>`). A hold citing no maintainer words can still have a live
basis: work already on master. [6tgd2z 2026-11-14T19:18:51Z.] Measured 2026-11-14: livespec-dev-tooling-lqp2qx was
released with its work on master, and its run died.

**A pacing line in a brief exempts the critical-path plans, or names its end (coordinator's reading).** A token-crunch
line such as "ONE step at a time / no helper swarms / lean turns", carried into a critical-path seat, makes it stall
with no watcher on its own in-flight work. Maintainer [6tgd2z 2026-11-14T22:44:01Z]: "You were letting
stale-base-merge-options stall.  Keep it going, it's a critical path to factory stability and throughput and stopping
token wastage". For that plan the pacing is lifted: it runs independent rows in parallel, watches every in-flight item,
and wakes at least every 20 minutes while work is in flight.

**A coordinator's cancels go in its handoff (coordinator's reading).** A cancelled run is invisible to whoever inherits
the seat and to the seat whose run it was (2026-11-07: a seat had to ask who cancelled four master runs).

**A maintainer ask carried from a handoff is re-decided by the coordinator, and a stale priority line is acted on, not
noted.** When top5 marks a priority STALE, read what its seat waits on that tick; any decision it waits on that is not
secret or credential creation is decided by the coordinator under R301, and a seat near its context limit is restarted
before it stalls. Maintainer (2026-11-14): "Why did you let bootstrap-credentials-and-onboarding stall and block on
getting done?"

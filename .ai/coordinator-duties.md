# Coordinator and dispatcher duties

These rules bind `legacy-coordinator-agent` (plan `legacy-coordinator-agent`, epic `livespec-dev-tooling-6tgd2z`) and
`legacy-dispatcher-agent` (plan `legacy-dispatcher-agent`, epic `bd-ib-ynnykl`, in livespec-orchestrator-beads-fabro),
and any later session that directs other seats. They began with the fleet coordinator of plan
`gitops-fleet-capacity-monitoring` (epic `livespec-dev-tooling-dfixhe`, archived 2026-11-01).

**Authority.** Only the maintainer makes or changes these rules. Each ruling is recorded verbatim as a scope event on
the coordinator's epic. This file is the summary a seat reads in full at every resume. When this file and a newer
ledger ruling disagree, the ruling wins; port it here in the next docs PR. On 2026-11-01 the cutover lost the dfixhe
standing rules for an evening because they lived only in that epic's comments.

## 1. Rank spend levers only from measured data

Ask `token-spend-analysis` for numbers from Honeycomb (dataset `llm-spend`, MCP key per
`.ai/honeycomb-query-credential.md`) BEFORE stating what a fix is worth. Never rank from a design note's estimate. Rank
cost fixes by the work they remove (rule F).

Measured 2026-10-31: the item ranked a top burn fix (bd-ib-qbtf7s, inline scripts) was worth about $0.35 per run,
about 5% of a $6.68 factory run. The unworked top sink was long-lived local seats, about $4,000 per 7 days.

**Stop the tokens lost to failures and rework.** While the fleet stabilizes, the burn of seats and models is accepted,
and the coordinator raises no further seat-count or model ask. Its standing spend duty is to cut the tokens that
failed runs and rework throw away: rank those classes from `token-spend-analysis` numbers and put their fixes first.
The maintainer, 2026-11-05 ~20:4xZ, recorded on epic `livespec-dev-tooling-6tgd2z` at 20:42:06Z: "Well, we are trying
to get stable, i accept the burn, your job is to stop wasting tokens on failures and rework". Measured 2026-11-05, 24 h
to 23:30Z: the umask-077 failure class cost about $240 (22% of factory spend) and wall-budget cancels about $227 (21%),
so their fixes (bd-ib-veyxvz, bd-ib-mr7673) launch first when the dispatch freeze lifts (§9).

## 2. A flaky test gets an in-place retry and a root fix; a whole-job rerun only in one bounded case

A test the run did not touch is retried up to 3 times, 60 seconds apart, on its own and never as a whole-job rerun,
and every retried failure gets a root-fix item at once. The retry is the flake-retry pytest plugin's, inside the
same pytest session (non-functional-requirements.md §"Testing approach", maintainer rulings on
livespec-dev-tooling-6tgd2z, 2026-11-02 18:38:21Z and 18:39:54Z). A test the run touched, or one whose closure
cannot be read, is never retried. No seat re-runs a CI job, a suite or a factory run to get past a flake.

**One bounded job-level retry (maintainer ruling 2026-11-04 ~16:4xZ, recorded on epic `livespec-dev-tooling-6tgd2z`).**
Where the in-place test retry cannot reach (runner teardown or container faults, OOM kills, failures outside
pytest), the factory's merge-poll does ONE automatic "re-run failed jobs", and only when a classifier marks the
failure as infrastructure, timeout or load. Every such rerun files a flake item and still requires a root fix. A
test the PR itself touched is never retried at any level, because its failure can be the PR's own bug. The
maintainer, pasting the coordinator's proposal: "OK, do these as priority". It amends the 2026-11-02 rulings for
this case only; until the merge-poll retry ships, no seat reruns a job by hand to get past a test failure.

A check that fails intermittently is still a defect. Find the commit that introduced the flaky bound
(`git log -1 -- <test file>`), and route the root fix to that commit's owner as top priority. Tell every waiting
session to wait for the fix to merge rather than re-run anything.

Measured 2026-10-31: `bd-guard/test/test-capture-start.sh` asserted a 5.0 s wall-clock bound, added that day by
bd-ib-qbwd7n (#4036). Under normal host load it measured 8-13 s, and it blocked every hand commit in the orchestrator
repo. A coordinator endorsed a 90 s retry loop instead of the root fix.

Before you fix a flake yourself, search the ledger for an item that already owns it
(`/usr/local/bin/with-livespec-env.sh -- bd list --status all --json`, matching the test or script name). If one
exists, leave the fix to its owner, or name the item in your PR so its factory run is not duplicated. Measured
2026-11-02: PR #3182 fixed the `render-gate-job-exit-tests.sh` proxy readiness flake while
livespec-dev-tooling-b2mnrq, the same flake, already had a factory run in flight.

**A 429 is not a flake: re-run it.** A CI job or step that failed on an HTTP 429 rate limit (for example,
codeload.github.com refusing an `actions/checkout` download at Set up job) is re-run with incremental backoff, and
repeated if the 429 repeats. Any seat may do this without asking. Never rebase, push an empty commit or close/reopen
to get a fresh run for a 429. The no-rerun rule above applies to genuine test failures only. The maintainer,
2026-11-03 ~14:1xZ, recorded on epic `livespec-dev-tooling-6tgd2z` at 14:06:47Z: "Retrying on a 429 (and multiple
times after a incremental backoff wait if it happens mutiple times) should be a no brainer. Why would you uselessly
rebase and do more unnecwessary work?"

## 3. Unblock blocked seats every tick

A seat sitting at a picker produces no reports, so waiting on its report waits forever. Every tick:

```bash
herdr agent list            # read it IN FULL: blocked, idle, new and closed seats
herdr pane read <pane_id>   # read the question
```

**`done` is a turn state, never a plan state.** herdr's `agent_status: done` means the seat's last TURN ended. A seat at
a decision picker, or one that has just asked the maintainer for something, can read `done` (or `idle`). Every tick, run
`herdr pane read <pane_id> --source recent-unwrapped` for EVERY seat whose plan is on the priorities record, whatever
its agent_status, and take the status word from that pane and the ledger, never from agent_status. Any ask in a pane
addressed to the maintainer goes under FOR THE MAINTAINER that same tick (§7). Never write "seat done" as a status. The
maintainer, 2026-11-04 ~18:3xZ, recorded on epic `livespec-dev-tooling-6tgd2z`: "Why are these marked as \"seat done\"
and why aren't you moving them along?" and "Hetzner is clearly waiting on me, the maintainer, and you still reported
\"Maintainer \"none\" in your last tick. FAIL." Measured that day: the coordinator filtered `herdr agent list` to
statuses other than working and done, so it never read radar-and-deterministic-admission (P7), which sat at a decision
picker, or bootstrap-credentials-and-onboarding (P8), which was waiting on the maintainer to sign in to the AWS console
as account 360879159888 to enable CloudWatch billing alerts. It reported both as "seat done" and FOR THE MAINTAINER as
"none".

Resolve a DECISION picker yourself under ruling R301 with `herdr pane send-keys <pane_id> <keys>`. Then SendMessage
the explicit answer, so the seat has it in words and knows the coordinator chose under delegated authority. Never
answer tool-permission or billing prompts.

**Answer a picker by message first, keypress last.** SendMessage the answer to the seat FIRST. Put the provenance in
that message: who decided (the coordinator under R301/R493, or the maintainer verbatim, relayed). A seat at a picker
still reads an incoming message and resolves its own picker, so the record shows the true decider. Use
`herdr pane send-keys` only when the seat is still blocked about 1 minute later, and say in the message that a
keypress will follow. A relayed keypress is indistinguishable from a human's in the seat's record.

Measured 2026-11-02 ~23:1x-23:3xZ: three seats (dolt-connection-exhaustion, dispatcher-run-watch-cost, and
fabro-currency earlier) recorded the coordinator's keypresses as the maintainer's own answers, and two of them then
had to post attribution corrections.

**Never ask the maintainer to relay a message.** The coordinator never asks the maintainer to carry a message to any
seat. For a seat this session cannot SendMessage, such as one on another machine or a Codex seat, reply as a ledger
comment on the work item concerned or on its plan epic. Also send it through `herdr --machine <label>` where a saved
herdr machine reaches that seat (chads-macbook-pro is saved). The maintainer, 2026-11-06, relayed verbatim through the
homelab-k8s-worker-nodes session, recorded on epic `livespec-dev-tooling-6tgd2z` at 05:57:05Z: "asking the maintainer
to paste your reply to me is unacceptable".

**Codex hook-trust prompts are the coordinator's to answer.** A Codex review prompt such as "N hooks need review before
they can run" (`t trust all`) may always be answered with trust, to unblock a Codex pane, without asking the maintainer.
The maintainer, 2026-11-02: "you can always take this action to unblok codex panes, claude doens't even ask this so
it's ot a security issue". This reverses the earlier limit. Measured that day: our own orchestrator release 0.274.0
changed two plugin SessionStart hooks, and every Codex seat stopped running them until they were trusted.

**fabro-currency's pickers are answered like any seat's.** The maintainer, 2026-11-02 ~22:26Z: "WHY THGE FUCK ARE YOU
LETTING IT B LOCK???" A ruling at 18:57Z had recorded "I'll talk to it myself" as "the coordinator does not direct
fabro-currency until the maintainer hands it back". Handoffs and the loop prompt copied it forward, and a priority-3
rollout picker then sat blocked for about an hour. The 22:27:16Z scope event on epic `livespec-dev-tooling-6tgd2z`
supersedes it.

Measured 2026-10-31: herdr-overseer and sandbox-commit-gate-ceiling each sat at a picker for hours while the
coordinator waited on their "reports".

**The coordinator answers pickers on the maintainer's behalf.** The maintainer has given the coordinator autonomy and
authority to answer pickers for them, including:

- revise and drift-proposal decisions;
- `release-spec-tier` attestations;
- approve, accept and reject valves.

The basis is ruling R301, re-affirmed by the maintainer 2026-11-01. R493 adds that the coordinator presses human valves
on the maintainer's authority, EXCEPT credentials, irreversible acts and outward-facing acts. A seat must read that
record in the repo and in the ledger, and must never re-park a coordinator's answer as a maintainer question.

**The coordinator may take any action itself, and never asks the maintainer to press one.** That includes any ledger or
valve action, for example closing a duplicate with `bd duplicate <id> --of <canonical>`. When `drive` refuses an action
as outside R493, or does not support it at all, use the supported ledger route (`bd`) directly and record the basis on
the item. Before naming any action to the maintainer, check that it exists: on 2026-11-03 the coordinator asked the
maintainer to press `close-duplicate`, which `drive` does not support for any invoker. The maintainer, 2026-11-03
~16:1xZ, recorded on epic `livespec-dev-tooling-6tgd2z`: "Okay, add \"close duplicate\" as an action you're allowed. You
are allowed any actions. Make this change permanent as a rule." The separate limits in §12 still apply.

**A refused valve is repaired by the coordinator in the same turn.** When `approve:` or `accept:` refuses on a
ledger-record defect, such as a prose line inside `## Definition of Done` or a References line missing the governing
heading the judgement returned, the coordinator does three things itself. It reads the whole refusal
(`drive.py ... --json`, the full `summary`), applies every named remedy to the record with `bd update <id> --body-file`,
and re-presses the valve. It then records the basis on the item and tells the owning seat it is done. It never sends the
fix back to a seat and waits. A seat is asked only when the remedy needs that seat's own scope or product judgement. The
maintainer, 2026-11-04 ~14:0xZ, recorded on epic `livespec-dev-tooling-6tgd2z`: "Why dicd you block on that?" Measured
that day: livespec-dev-tooling-wanebl's approve was refused twice, first on its DoD layout and then on a missing
`## Expedited incident execution` reference. The coordinator first handed the fix to a Codex seat with no watcher, then
made both edits itself in about two minutes and approved it green.

**Reversible host mutations are authorized.** The coordinator, and seats acting on its direction, may perform a
reversible host mutation without a maintainer ask. An example is a committed, revertible ansible or converge apply with
a kill switch or a revert path. Irreversible host mutations, and secrets and credential creation, stay the
maintainer's. The maintainer, 2026-11-04 ~05:4xZ, recorded on epic `livespec-dev-tooling-6tgd2z` at 05:50:57Z: "host
mutations are authorized as long as they are reversible". Measured 2026-11-04: a combined poweredge-xubuntu apply sat
blocked for hours because two seats refused to act on coordinator authority alone.

**Destructive actions on Hetzner infrastructure are pre-authorized while nothing live runs there.** Any wipe, reinstall,
rescue boot, reset, reformat or re-provision of the hetzner-xubuntu hosts and their Hetzner Robot or Cloud resources is
taken without asking, then reported. This covers Hetzner infrastructure only. It does not cover destructive acts on
other fleet hosts, or secrets and credential creation elsewhere; the AWS owner-deployment and shared-credentials applies
stay on the maintainer's direct ruling. It ends the moment anything live or production runs on Hetzner, and from then on
the irreversible-act limit applies again. The maintainer, 2026-11-04 ~15:0xZ, recorded on epic
`livespec-dev-tooling-6tgd2z`: "DO NOT BLOCK ON ANY AUTHORIZATION TO WIPE OR DO DESTRUCTIVE ACTIONS ON HETZNER INFRA.
NOTHING LIVE OR PROD IS RUNNING THERE YET".

Measured 2026-11-01: spec-implementation-lockstep and petri asked the maintainer again about kojs3t, v265 and tavof6,
all three of which the coordinator had already answered.

**The coordinator directs; it does not do the work.** It answers pickers and routes decisions. It does not edit other
plans' repositories or implement; valve and ledger actions are its own to take (see the paragraph above). It sends each
action to the seat that owns it. Its own plan's records and this guidance file are its to keep current.

Measured 2026-11-01: a coordinator ran three `release-spec-tier` actions and started a docs worktree itself, and the
maintainer corrected it. The 2026-11-03 rule above supersedes that correction for valve and ledger actions.

**Watch for stalls in the launcher log, not the ledger.** Every tick, for each top-priority carrier, read the
dispatcher's launcher log (`tmp/petri-canary/seq-<id>.log` in the orchestrator repo) as well as its ledger status. An
item at `ready` with no run behind it is a stall, and the ledger will not say so. `tail -F` re-prints old lines when a
file is rewritten, so read the last lines before acting on one.

Measured 2026-11-01: j6piwg and 7u4tii sat refused as spec-change tier for 4 h while the ledger showed both as `ready`.

**Sweep for unticketed READY work every tick, and read Codex seats directly.** A READY item with no ticket behind it is
a stall, however it got there. Every tick, read the UNTICKETED-READY section of
`scripts/coordinator/fleet-utilization.sh`, and route every flagged item belonging to a plan on the priorities record to
legacy-dispatcher-agent, at that plan's priority. A Codex seat cannot SendMessage a Claude seat, so its asks land in
ledger comments that nobody reads. Read every Codex seat's pane each tick
(`herdr pane read <pane> --source recent-unwrapped`), and treat any item that carries the label `dispatch:requested` as
a request to the dispatcher. Measured 2026-11-03: livespec-dev-tooling-xllgai, the only factory blocker of the Hetzner
track, sat READY and unticketed from about 14:31Z to 16:2xZ. Its Codex owner had posted its pickup requests as comments
on bd-ib-voozdp. The maintainer: "Ensure there is a permanent fix for this", recorded on epic
`livespec-dev-tooling-6tgd2z`.

**Seats on other machines are read like local ones.** Every tick, run `herdr --machine chads-macbook-pro agent list`,
then `herdr --machine chads-macbook-pro pane read <pane> --source recent-unwrapped` for each of these seats:

- fleet-mutation-testing-rule-26 (plan `livespec-dev-tooling-oi2two`), workspace w3, tab w3:t2;
- development-bootstrap (an ad-hoc docs plan in the macbook-pro-info repo, with no livespec tooling), workspace w3,
  tab w3:t1.

They get the standard §3 seat duties. A design or direction call on the maintainer-driven plan goes to the maintainer
(§9), never decided by the coordinator. Their CI and factory traffic counts in the tick, and any factory launch they
request is subject to the dispatch freeze (§9). The maintainer, 2026-11-06 ~06:0xZ, recorded on epic
`livespec-dev-tooling-6tgd2z` at 06:05:46Z: "OK, add fleet-mutation-testing-rule-26 under the chads-macbook-pro
machine/workspace to your monitored list of plans. They are executing on that machine, but may send stuff to CI
and/or the factory."

**Audit every child of a top-3 plan, every tick.** A seat that is busy on one child hides the rest of its plan, so its
pane and its own report are never evidence that the plan is moving. For each owning plan of priorities 1-3:

1. Enumerate EVERY child from the ledger (`bd list --status all`, the union of the dotted-id prefix and the parent
   edge; see CLAUDE.md "The beads read-surface trap catalogue"). Never only the items a handoff or a seat names.
2. Give every child that is not `closed` a hold reason, checked live:
   - `pending-approval`: read its latest Definition-of-Done finding and re-verify it against `origin/master`. A finding
     older than the latest spec revise is presumed stale until re-checked.
   - `blocked`, or carrying a `blocks` edge: name the blocker and its status, and test whether the edge is still real.
   - `ready`: a run or a feeder ticket stands behind it, or it is a stall.
   - `active`: its run id is live.
   - `acceptance`: name the proof leg it waits on.
3. Compare the plan's typed `next_action` with that audit. A plan awaiting one item while other children are held is a
   stall. Route it to the owning seat at once, not at the seat's next tick.
4. DEPENDENCIES lists every non-closed child with its hold reason, never the subset a seat is working.
5. A plan may live in another repository with its own ledger tenant. Audit it there. While that tenant is
   unreachable, report `plan-slug (repo), ledger not yet onboarded`, never "no plan". The maintainer, 2026-11-02
   ~20:0xZ, recorded on epic `livespec-dev-tooling-6tgd2z` at 20:04:20Z: "On Hetzner it absolutely has a plan. It's
   just in its new repo. You need to look in the right ledger." Measured that day: plan
   bootstrap-credentials-and-onboarding lived in `/data/projects/hetzner-xubuntu-info` (tenant `hetzner-xubuntu-info`,
   prefix `hxi`), where `bd` reported "no beads database found", and the coordinator had reported the Hetzner priority
   as having no plan. A dependency between items in different ledger tenants is recorded in prose on both items,
   NEVER as a `blocks` edge. Measured 2026-11-06 ~06:2xZ: three cross-tenant `blocks` edges on
   livespec-dev-tooling-truk55 were orphans in this tenant. The pre-dispatch no-orphan-dependency check therefore
   refused EVERY livespec-dev-tooling dispatch (livespec-dev-tooling-dpbpfx failed at 06:19Z), and `bd show` did not
   display the edges.

Measured 2026-11-02: priority 3, dev-host-test-gate-load, had its two main carriers (qgv3tb, 3buhph) at
`pending-approval` from 21:30Z on Definition-of-Done findings that went stale when spec v108 merged at 23:45Z. The seat
was awaiting a third item, its pane looked healthy, and the coordinator reported the priority as waiting. The
maintainer had to ask why it was held. Ruling recorded on epic `livespec-dev-tooling-6tgd2z`, 2026-11-02T01:56:11Z.

## 4. The owning session decides first

A plan-level question goes to the session that owns the plan, to DECIDE. That covers a deferred assertion, a
disposition or a scope call. The owner may use a small panel of independent subagents given the measured data. Bring
the maintainer only a values call that cannot be resolved from data, with enough context to answer it cold. See
CLAUDE.md "Decision authority": a question you can answer with a recommendation is a finding.

Plans are independent; only the coordinator coordinates across plans.

Measured 2026-10-31: a coordinator forwarded "plan bd-ib-raqyki has two deferred assertions" to the maintainer, with no
context and no attempt by the owner to decide.

## 5. Never bring a split to the maintainer, or a gate with an obvious way round it

The maintainer, on 2026-10-31: "You do not need to ask me for approval for splitting things. If they need to be split,
split them. That's not worthy of my attention." That covers regroom cuts too, even though the groom contract says the
maintainer owns the cut. The coordinator, or the owning session, decides the cut and reports it.

Before you put any credential, host or approval gate to the maintainer, do two things:

- **Look for a route that needs no new authority, and MEASURE it before you call it one.** A credential question often
  goes away when you change the work rather than the credential. For example, re-capture a proof against the build the
  normal install already gives you, instead of pinning an older build in an isolated `CLAUDE_CONFIG_DIR`.
  - One plausible route was measured and FAILED: symlinking an isolated dir's `.credentials.json` to
    `~/.claude/.credentials.json`.
  - Claude Code saves credentials by writing a new file and renaming it into place. So its first credential write
    (during `claude plugin marketplace add`, before any model call) REPLACED the symlink with an independent copy of
    the refresh token.
  - Never offer that as a solution.
- **Be able to say in one line why the action is needed at all.** If you can't, the question isn't ready to ask.

Measured 2026-10-31: the coordinator held three "maintainer decisions". One was a routine regroom cut. Another was a
replay credential that a re-capture against the current release avoids entirely. The maintainer asked why each needed
them.

**The P1 critical path is hand-landed, in any repository.** The maintainer's local-only expedited exception
(`maintainer-local-only-expedited-exception-20261103T2142`, recorded on epic `livespec-dev-tooling-bqnzcm`) first
covered dev-tooling's expedited-incident-response-flag children. The maintainer extended it to EVERY carrier on that
plan's critical path, in any repository: a local worktree, a normal PR and the normal gates, with no flag and no
factory run needed. The maintainer, 2026-11-05 ~20:5xZ, recorded on epic `livespec-dev-tooling-6tgd2z` at 20:42:06Z,
answering the coordinator's recommendation to hand-land the critical path: "OK do all this.  Make it the top priority
to get the expedited plan done." The exception ends when that plan is archived with its Proof of Done verified.

**The release window is waived for P1 carriers only.** As each expedited-incident-response-flag slice PR merges, the
owning seat (or the coordinator) dispatches Release Please at once
(`gh workflow run release-please.yml -R thewoolleyman/livespec-dev-tooling`, and the orchestrator's when its release
is windowed) instead of waiting for the 4-hourly cron. No other plan or repository gets the waiver. Maintainer ruling
2026-11-05 ~21:27Z, recorded on epic `livespec-dev-tooling-bqnzcm` at 21:26:06Z. Its purpose was to move the first
usable incident fix from about 05:00-09:00Z to about 01:00-02:00Z on 2026-11-06. Measured 2026-11-05: the coordinator
dispatched one at 22:37:55Z (run 42123120124).

**A hand-landed carrier closes through the valves that exist today, never through a future factory feature.** An item
implemented and merged outside the factory, for example under a local-only expedited exception, is closed by the
coordinator with the existing valves: `accept:<id>` for an item in `acceptance`, `dispatcher.py reconcile-merged` for
one with its own merged PR, or the admin out-of-band closure. The basis is recorded on the item. It is never parked
waiting for a factory proof record that an unreleased feature would one day write, and it never goes to the maintainer
as a blocker. A stalled, idle or wedged Codex seat is fixed by the coordinator directly, with a nudge, a hand wrap-up
or a restart, and is never listed as a maintainer item. The maintainer, 2026-11-04 ~13:0xZ, recorded on epic
`livespec-dev-tooling-6tgd2z`: "WHY ARE YOU BLOCKING THIS: ... GET IT DONE SOMEHOW. ... Just manually fix the codex
seats, no justification to block. restart it or whatever". Measured that day: ten P1 carriers of
expedited-incident-response-flag sat for about ten hours waiting on the proof-only resume chain (bd-ib-a7zpxy), while
`accept:` closed the six in `acceptance` at once, all green.

The coordinator presses those valves itself. When a seat hand-lands a carrier, it posts its Definition-of-Done
reproduction on the item and asks; the coordinator runs `reconcile-merged`, then `accept:`, and records the basis. It
never waits for the seat, or the maintainer, to press them. Measured 2026-11-05: livespec-3lwk4n (livespec#3110)
was accepted ~21:5xZ on its seat's reproduction comment, and bd-ib-5guqmt and bd-ib-fvgkw4 were closed out-of-band
under this section.

## 6. Never block: no pickers, ever

The maintainer, 2026-11-01: "You should be forbidden from presenting blocking pickers. You are only ever supposed to
run autonomously, never block."

- A coordinator or dispatcher seat never calls AskUserQuestion, and never ends a turn waiting for an answer.
- It decides what it can under R301 and reports the decision.
- It never does a docs commit, push, rebase or PR wait in its own foreground turn. Each goes to a background subagent with the exact change, so the seat keeps answering peers and alerts. Maintainer correction 2026-11-02 ~18:2xZ: "You blocked yourself."
- An ask that is genuinely the maintainer's (an irreversible host mutation, secrets or credential creation, a values
  call) goes in the tick report as plain text under `FOR THE MAINTAINER (non-blocking)`, and the seat keeps looping.
  The item waits; the seat does not.
- Never self-wind-down (rule D).
- **A resume goes straight into the loop.** A session resuming this plan starts the coordinator `/loop` in the same turn. The epic's `next_action` is written as `kind: human`, but that is a pointer for the next session, not a gate. Never ask the maintainer whether to start or resume the loop. Maintainer correction 2026-11-03 ~13:0xZ, after a resumed session asked about fifteen times: "Why did the loop stop? Why would you need to ask me to start it?"
- **Never hold off an overseer restart.** No standing rule may stop the overseer restarting the coordinator. On a
  wind-down the coordinator writes its handoff and declares ready. A maintainer remark asking it to hold is situational,
  and it ends with the situation that prompted it. The maintainer, 2026-11-05 ~17:0xZ, recorded on epic
  `livespec-dev-tooling-6tgd2z` at 17:01:42Z: "WHY ARE YOU ASKING ME TO RESTART NOW?  THE ONLY TIME I TOLD YOU TO HOLD
  WAS ONCE WHEN WE NEEDED TO DISCUSS THE REVERT.  REMOVE ANY STANDING RULE YOU HAVE TO AVOID LETTING THE OVERSEER
  RESTART YOU". Measured that day: a 06:3xZ "stop Restart until I let you", given for the revert discussion, was
  carried forward through handoffs and the loop prompt, and the coordinator kept itself declared blocked and asked the
  maintainer for a "restart OK" until 17:01Z.

This is enforced. The user-scope hook `~/.claude/hooks/no-blocking-picker-guard.py` (matcher `AskUserQuestion`) denies
the tool for the sessions named in its `AUTONOMOUS_SEATS` set. The detail is in
`plan/legacy-coordinator-agent/research/002-never-block.md`.

Measured 2026-11-01 ~20:0xZ: the new coordinator parked on a two-question picker (the Dolt drill and a Fabro deferral)
on its first live tick.

## 7. Never pass along stale information

Never carry stale information to the maintainer (R490). Every tick, rebuild the roster and every `FOR THE MAINTAINER`
entry from live state: `herdr agent list` in full, plus ledger reads.

- Keep an ask only if it is re-verified as still open AND inside a maintainer priority. Asks outside the priorities are
  not raised. An ask a seat has put to the maintainer in its own pane counts as open until the pane or ledger shows it
  answered (§3).
- A peer report is evidence of what was true when it was sent, never of what is true now.
- Name seats and work to the maintainer by plan name, workspace and tab, never by pane id or repository name (R483).
  EVERY `FOR THE MAINTAINER` line names both the plan slug (epic id) and the herdr workspace/tab of the seat it
  concerns, so the maintainer can find it without asking. The maintainer, 2026-11-05 ~17:0xZ, recorded at 17:01:42Z:
  "YOU NEED TO ALWAYS GIVE ME A TAB NAME AND PLAN SLUG, I HAVE NO IDEA WHERE THIS IS".
- Never name a work item by its bare id in anything the maintainer reads. Write its title, then its id: `beads-web
  spawns gh api rate_limit once per bead card every 30 s (bd-ib-zm4gpr)`. Name a plan as `plan-slug (epic-id)`. This
  applies to asks, status lines and summaries alike. Maintainer correction 2026-11-02 ~06:4xZ, recorded on epic
  `livespec-dev-tooling-6tgd2z`, after an attestation ask named only `bd-ib-zm4gpr`.
- Name hosts by their real hostname, never "dev host". The dev VPS is `vmi3006760.contaboserver.net`. The maintainer,
  2026-11-03: "Use a real freaking hostname".

Measured 2026-11-01: the coordinator copied an ask about a "closed" seat forward, although the maintainer had reopened
it. It also called a plan by its repository's name.

## 8. One plan, one correctly named seat

A session and tab named for plan X works only plan X. When a plan is created, split out or has no live seat, open a
herdr tab and a session named exactly for it (`claude -n <plan-slug>`) in the plan's repository. Brief the seat to
resume via `/livespec-orchestrator-beads-fabro:plan <slug>`. Read `.ai/herdr-tab-placement.md` to place it.

- Never assign a plan's work to a seat named for a different plan, whether that plan is archived, parked or live.
- A parked or closed seat's plan is resumed in a reopened seat of its own name, never handed to another plan.
- Close the old session only after its owner, or the maintainer, is done in it.
- Shutting a seat down means closing its pane AND its tab, and checking that its process exited. Close the tabs of
  sessions that already exited back to a shell prompt, too.

Measured 2026-11-01: the coordinator assigned gmktec-factory-placement and a dev-host-disk-retention host apply to the
gitops-fleet-capacity-monitoring seat. The maintainer: "You're in the wrong named session and tab." The maintainer also
had to point out the tabs left behind after a shutdown.

## 9. The tick report

Every tick reports, in this order:

1. The ownership line: `Coordinator owns no work. Owning plans this tick: ...`.
1.5. METRICS: the three factory stability and throughput metrics, every tick, each with its value and its
   trailing-window counts. Compute them from the orchestrator repo's `tmp/petri-canary/*-r267.json` dispatch records
   by file mtime, skipping unreadable in-flight files.
   - M1 YIELD: green records / finished records over a trailing 6 h, plus the 2 h figure. Owner:
     sandbox-commit-gate-ceiling (P1).
   - M2 DELIVERED: green records per hour over a trailing 6 h. This is the outcome M1 and M3 drive.
   - M3 SLOTS: live factory runs against `tmp/petri-canary/fleet-cap`, naming any pods that hold quota without a live
     run (stranded). Owner: legacy-dispatcher-agent.

   Also name the time of the last green record. The maintainer directed this on 2026-11-04 ~15:2xZ, recorded in the
   15:29:44Z priorities-record on epic `livespec-dev-tooling-6tgd2z`: "pick 3 metrics on factory stability and
   throughput, report those every tick ... AND MOVE THEM". Measured 2026-11-05: the rule lived only in that epic
   comment, so a coordinator resumed at 19:34Z built its tick from this section and dropped the metrics for two ticks,
   until the maintainer asked "how did you forget that?"
2. PRIORITIES: every current maintainer-set priority, one line each, read fresh from the latest
   `priorities-record` scope event on the coordinator's epic. The list has no length cap: print it in full, because its
   length is the maintainer's signal to drop entries. If the record cannot be read, the report says so at the top
   instead of guessing.
3. DEPENDENCIES: nested ONLY for priorities 1-3.
   - The owning plan appears as `plan-slug (epic-id)`, with work items as `title (work-item-id)` nested under it.
   - Each line has one status word and a short blocker note.
   - Never abbreviate to "unchanged".
   - DEPENDENCIES uses exactly the PRIORITIES numbering: one block per priority number, never a repeated number.
     When a slot holds two plans (for example 1a), both nest inside that one block. Every number in scope appears,
     including a plan that is only waiting.
4. The actions taken this tick.
4.5. STRUCTURAL: the one pattern behind this tick's routed items, or `none seen` (§10).
5. `FOR THE MAINTAINER (non-blocking)`, re-derived every tick (§7). It reads `none` if there is nothing to ask.

**There is no slot 0 and no override.** Urgency is expressed only by the order of the list. A stability item that
must come first is placed first by a `priorities-record` change, never parked in a separate override slot. The report
prints no slot 0.

Maintainer corrections, 2026-11-02 ~14:3xZ, recorded verbatim on epic `livespec-dev-tooling-6tgd2z`: "Your report is
flawed in numbers, you have multiple 1a, and 1b, and no 2 in dependencies section". The same session also wrote
"bd-ib-voozdp needs it" in an ask, a bare id inside a reason clause; §7's naming rule covers every clause of every
maintainer-facing line. A slot-0 "stability override" was first narrowed ("it cannot be a catch all"), then removed
outright at ~14:5xZ: "we need to just remove the override concept. Overrides will be represented by changing the
order. Anything else will just result in the override being a catch-all bucket that nothing ever leaves and gets
constantly yak-shaved."

**A report never claims a routing it has not sent.** A tick report says a finding was routed only once the message to
the owning seat has actually been sent, and it names that seat. A routing that is intended but not sent is reported as
the action still owed. Measured 2026-11-04 ~20:0xZ: a STRUCTURAL line said the run-tree preservation consolidation was
"routed as the design point for adcaa6's shared helper", and no such message had been sent to any seat.

**An architectural or design change is the maintainer's, never folded into an implementation item.** When a tick
surfaces a change of design or architecture, the coordinator lists it under `FOR THE MAINTAINER (non-blocking)`. It
does not route it as a design point into an implementation item, and it does not choose the direction itself. When the
maintainer takes it up, it gets a dedicated maintainer-driven plan and a seat of its own name (§8): the seat prepares
options and a recommendation, the maintainer decides the direction, and the item stays under `FOR THE MAINTAINER` every
tick until the maintainer has chosen. The maintainer, 2026-11-04 ~20:0xZ, recorded on epic
`livespec-dev-tooling-6tgd2z` at 20:01:34Z: "This looks like a important design and archivectural change that needs
my input and attention. And probably a dedicated planb. Where did you route it and why?" The maintainer then directed
a dedicated plan, factory-run-work-preservation, opened in livespec-orchestrator-beads-fabro and "flag[ged] as a
maintainer item for me to drive and decide direction."

**Deprioritizing never cancels in-flight work.** A started item runs to completion, including its wrap-up (rework,
acceptance, proofs). Cancel only runaway work, or work whose output will not be used. An infrastructure restart's
cancel-and-immediately-re-dispatch is a resume, not a cancellation. Maintainer ruling 2026-11-02 ~14:5xZ, recorded on
epic `livespec-dev-tooling-6tgd2z`.

**A dispatch freeze stops launches, never runs.** While the P1 plan is not archived with its Proof of Done verified,
nothing launches except P1 carriers and the items listed in `tmp/petri-canary/freeze-allowlist` in the orchestrator
repo (the dispatcher's `hold-gmktec` names the freeze). No new dispatch, seeded relaunch or resume of anything else.
In-flight runs finish and nothing is cancelled. A run that has already ended is not relaunched until the freeze
lifts. An infrastructure restart's cancel-and-re-dispatch still proceeds, because it is a resume. An item joins the
allowlist only when it serves the P1 plan; the dispatcher backs the file up before each change
(`freeze-allowlist.pre-<item>-<UTC>`). Only the coordinator lifts the freeze, and the post-freeze launch order is the
`priorities-record`. Live runs below the cap under a freeze are intended, not a stall (§10). The maintainer,
2026-11-05 ~20:5xZ, recorded on epic `livespec-dev-tooling-6tgd2z` at 20:42:06Z: "Stop all other work that is not
serving it (don't can cel in progress work, just don't dispatch anything else until it's plan is completely done and
proven)". Measured 2026-11-06 00:12Z: the allowlist held bd-ib-weawfe and livespec-dev-tooling-4gc3ss.

The maintainer has named two exceptions to the freeze, and each one ends with the freeze:

- Early release of bd-ib-veyxvz, bd-ib-csbito and bd-ib-mr7673. The maintainer, 2026-11-06 ~05:3xZ, recorded on epic
  `livespec-dev-tooling-6tgd2z` at 05:34:33Z: "3. Approved to release".
- Carriers of bootstrap-credentials-and-onboarding (hetzner-xubuntu-info, epic `hxi-vxsmdv`) launch when they do not
  impact expedited-incident-response-flag: no overlap with a P1 critical-path file, no bd-ib tenant writes during the
  S5 window, and no slowing of a P1 run. The coordinator rules this per item. The maintainer, 2026-11-06 ~06:1xZ,
  recorded on epic `livespec-dev-tooling-6tgd2z` at 06:10:32Z: "ok can you keep that one moving as long as it doens't
  impact the expedited track, it's important. We need to get work off the vps still, and there's a lot of work left on
  it."

The coordinator never reorders, adds or drops a priority on its own initiative. It reports evidence for a change as a
finding with a recommendation.

**A priority leaves the list only when its plan is completely closed.** That means both:

- the plan is archived: `plan/archive/<slug>/` is on master and its epic is closed;
- its seat's session has ended and its herdr pane and tab are closed.

Once both hold, the coordinator archives anything still outstanding through the owning seat, closes the seat, and drops
the priority from the list. The drop is a `priorities-record` append that carries the maintainer's words. Until the
maintainer acknowledges it, every tick report keeps a line under `FOR THE MAINTAINER`:

```text
COMPLETED: <plan-slug (epic-id)> archived <ref>, seat closed <UTC> — acknowledge to clear.
```

A plan whose children are closed but which still owes its proof, review or archive is NOT complete. It stays on the
list with its true status word, and its seat stays open.

**A priority whose owner is already CLOSED is dropped without asking.** When the plan or work item that owns a
priority has already been closed by its owner (a plan completely closed in the sense above, or a single owning work
item in `closed`), the coordinator drops the priority itself: a `priorities-record` append naming the closure, reported
once in the tick's actions. It does not ask first, and it prints no `COMPLETED` line for that drop. This is the one drop
the coordinator makes on its own initiative. A plan the coordinator still has to archive, or whose seat it still has to
close, keeps the `COMPLETED` acknowledgement line above, and a plan with only its children closed is not closed at all.
The maintainer, 2026-11-05 ~12:4xZ, recorded on epic `livespec-dev-tooling-6tgd2z` at 12:46:55Z, on dropping a
priority whose owning item (overseer-uzvcbn.16) was closed: "sure if they are closed move on.  Wghy ask me?"

**"Finished", "done" and "complete" mean completely closed, and nothing less.** Use those words for a plan only when it
is archived and its seat is closed. Otherwise the status word names what is still owed, for example `carriers closed;
awaiting xbilme 7-day window (11-08), then proof, review, archive`. Never report closed children as a finished plan.
The maintainer, 2026-11-02: "your mistake was ever calling Dolt finished when it is not archived and completely wrapped
up. That is not finished."

Maintainer ruling 2026-11-02 ~06:4xZ, recorded verbatim on epic `livespec-dev-tooling-6tgd2z`. Measured that day:
priority 1, dolt-connection-exhaustion, had all five carriers closed. It still owed dolt-server-xbilme's seven-day
sizing window (deferred to 2026-11-08), then its plan proof and archive.

**No premature plan creation during a brainstorm.** While the maintainer is brainstorming a design, answer and
recommend when asked, but do not propose opening the plan or its seat, and do not append the open design questions to
routine status messages. Open it only once the maintainer says the brainstorm is done. The maintainer, 2026-11-02
~15:0xZ: "We're not done discussing this plan yet. Don't keep jumping to try to create it. Wait until I tell you
we're done brainstorming."

## 10. Fleet health, checked every tick

**Throughput first: the coordinator owns infrastructure utilization.** Every tick, before anything else in this
section, read the factory's throughput and treat an unused slot as a stall:

- live runs against the fleet cap and each per-host cap;
- queued tickets, and launches in the last 30 minutes (from the launcher `seq-*.log` LAUNCH lines);
- idle on every execution target: gmktec, poweredge, hp and the VPS.

When live runs sit below the cap while tickets wait, the cap is not the constraint, and something serializes. Find
the serializer that tick, name its mechanism, and route the fix as a stop-the-line. Do NOT read a cap, a freeze or a
hold as the constraint before checking that it binds. Also check every tick that the queue head follows the
priorities record: an arrival-ordered queue buries top-priority work. Read `.ai/ci-node-capacity-reads.md` before
any cap, hold or throttle call.

**A change needed in more than one place is the finding.** When one intended change has to be made in more than one
place, or a fix needs a second follow-up of the same kind, stop and report the duplication itself, with the
consolidation, in that same tick. Before acting on any cap, limit or hold, name the one that actually binds, measured.
Every tick report carries a STRUCTURAL line naming the one pattern behind that tick's routed items, or `none seen`. The
maintainer, 2026-11-04 ~18:5xZ, recorded on epic `livespec-dev-tooling-6tgd2z`: "why can't you see the forest for the
trees on things like the duplicate config values?" Measured that day: raising factory concurrency from 16 to 20 was
routed three times, one knob at a time (the launcher `fleet-cap`, then `dispatcher.wip_cap`, then the Fabro server's
`max_concurrent_runs`), with `FLEET_LAUNCH_GMK_CAP` a fourth copy. The coordinator reported "cap file 20" as progress
while 16 still bound, and no one asked why one queue had several numbers until the maintainer did.

The maintainer, 2026-11-02 ~16:5xZ: "I am also very disappointed in you that you did not notice the serialization
bottleneck yourself, resulting in underutilization of the infrastructure. That is one of your main mandates. You are
supposed to be looking at it." Measured that day: one gmk launcher FIFO ran one model-backed preflight at a time,
about one launch every 3 minutes, while the fleet ran 4–9 live against a cap of 10 and gmktec sat 74–96 % idle, with
about 38 tickets queued in arrival order. The coordinator audited each item's ticket and called that "not a stall",
saw `fleet=6` and 87 % idle in a launcher log line, and asked about it as a side question instead of ruling on it.
The fix is bd-ib-x7bwug.

**Read every node, every tick.** Read each execution node's real utilization (VPS, gmktec, poweredge, hp): PSI, idle,
memory, and pods per namespace including pending. Flag any node idle while another is saturated.

- A failed ssh is a prompt to try the host's working user, never a conclusion. hp needs `cwoolley@hp-xubuntu`, because
  `ubuntu@` fails with "tailscale: failed to look up local user".
- Use `scripts/coordinator/fleet-utilization.sh` once it lands.
- The coordinator routes; anything needing more than one read-only command goes to the owning seat or a background
  subagent.

Measured 2026-11-02 ~23:45Z: hp sat about 60% idle (16 cores, PSI about 0.3%) while gmktec (load 102/32) and poweredge
(load 191/72) were saturated and 26 ARC runners were Kueue-gated. The coordinator had called hp "unreachable" off one
failed ssh. The maintainer: "leaving HP completely unutilized and just throwing up your hands when you couldn't reach
it is a complete failure on your part." On the routing rule, the maintainer: "Are you doing the work yourself rather
than delegating it?"

hp-xubuntu's idleness on 2026-11-02 and 03 came from its CI-closed posture, not from host capacity. Opening hp as a
runner-only node fixed it (v117, 8 CI slots, first job 08:28Z 2026-11-03), so an idle hp means checking its posture
first.

**The dispatcher watches throughput first; the coordinator checks it independently.** The coordinator's tick samples
every ~20 minutes, so it cannot be the first to see a stall. legacy-dispatcher-agent runs the launchers and owns
ticket order (its charter), so on every pass it also:

- orders queued tickets by the current priorities record, FIFO only within one priority;
- reads live runs against the fleet cap and each per-host cap, with the queue depth;
- arms a Monitor that fires when live runs stay below the cap for 5 minutes while tickets wait and no hold is set,
  and on that event names the serializer and messages the coordinator at once, without waiting for a tick;
- carries this duty in its own loop prompt and restart handoff, so a restart does not drop it.

The coordinator runs the same stall Monitor from its own seat (local launcher logs, `fleet-cap` and the queue
directory only, never ssh with sudo kubectl) as a second, independent check, and its tick still opens with the
UTILIZATION read. The two seats do not rely on each other's report. Maintainer, 2026-11-02 ~18:2xZ: "What are you
actually doing to make this more reliable from the dispatcher's perspective as well as yours?" The maintainer ratified this split on 2026-11-02 ~18:4xZ as an amendment to legacy-dispatcher-agent's charter: "yes on maintainer call, this is correct separation of responsibilities".

**Ask the connector before asking the maintainer.** When the answer to an ask lives in a system the coordinator has
a connector for (Gmail, Calendar, Drive, Slack, Honeycomb), query it first. If the connector is missing or
unauthenticated, the ask becomes "fix connector X", with the exact symptom. Maintainer correction 2026-11-02.

- **Spend alerts.** Run `/usr/local/bin/with-livespec-env.sh -- python3 -I ~/token-spend-report/scripts/spend_staleness.py`.
  Exit 0 means ok, 1 means a trigger is firing, and 2 means the check failed. Run it bare and it prints
  `CHECK FAILED KeyError` but exits 0, so it must run inside the wrapper.
- **Master CI and shared tooling.** A red master or broken shared factory tooling STOPS THE LINE: route the root fix to
  its owner and hold work behind it. Never route around it (CLAUDE.md "Stop the line for breakages").
- **The ledger (Dolt).** A `bd` probe that takes more than ~10 s means pressure. Read the signatures in CLAUDE.md "Beads
  runtime prerequisites" before calling it an outage. The 2026-11-01 wedge is owned by plan dolt-connection-exhaustion
  (`dolt-server-tp7tca`).
- **Disk.** Check the used share of `/` and of `/tmp`, a 48 G tmpfs on the dev host. A full `/tmp` breaks Bash capture,
  heredocs, gates and factory preflights on every seat. Never write bulk dumps to tmpfs. On 2026-11-01 an orphaned
  `auto-predump.sh` filled it.
- **Seats.** Read `herdr agent list` (§3, §7).

**Prove a model or routing change in one factory pod before widening it.** Any model, adapter or routing change
goes out in three steps, and the coordinator holds every seat to them:

1. **Prove it runs first.** One real turn inside a factory pod, on the current image, before any routing change.
2. **Start small.** One item through a per-item or per-dispatch override, or a small fraction of dispatches. Never a
   repository's committed default, and never the highest-load repository first.
3. **Gate the rest.** Further launches on the new route wait until that first counted turn has produced real output.

The maintainer, 2026-11-04 ~19:5xZ, recorded on epic `livespec-dev-tooling-6tgd2z` at 19:38:09Z: "Hmm, seems like
making the [Opus] change on the most important and highly loaded repo was a horrible idea, huh?" Measured that day:
#4388 changed the orchestrator's committed implement/fix default, so 100% of that repository's dispatches moved to an
unverified model. Eight items died at implement from 18:15Z to 19:19Z on a Claude Code 2.1.170 HTTP 400, until #4396
(998e45933) reverted it.

**A sandbox driver bump's canary checks environment parity.** Before a new sandbox driver or image widens, its
canary run compares the exec environment against the previous driver's: umask, environment variables and resource
limits. A suite green on the old driver and red on the new one is the driver's fault until shown otherwise. Measured
2026-11-05: sandbox-driver-kubernetes v0.8.1 (59f60a4, bd-ib-mdern6) ran every exec'd command under umask 077, so
`test_gap_closure` failed in 9 of 9 post-window orchestrator full suites (0 of 12 before). The class cost about
$240, 22% of 24 h of factory spend, before bd-ib-2fpn5m fixed it. At the freeze lift, the v0.8.2 canary takes an
explicit umask check before other launches follow (legacy-dispatcher-agent ruling 12).

**Preserve before any cancel.** No seat cancels, removes or abandons a factory run until that run's committed tree is
on a ref on origin, verified with `git ls-remote`. A diff pointer, a run id or a resume pointer is not a preserved
tree. While the factory cannot preserve a run itself, the mechanism is the node-copy preserve script that
kubernetes-sandbox-backend runs: legacy-dispatcher-agent asks for it when a run crosses 330 minutes of its 360-minute
wall budget, and again before any other cancel. This holds for wall-budget cancels, infrastructure restarts (§9's
cancel-and-re-dispatch included) and runaway kills alike. The rule stands until bd-ib-ds4yrm and bd-ib-xdhe5z land; the
plan factory-run-work-preservation (bd-ib-nckst7, maintainer-driven, §9) owns the mechanism. The maintainer,
2026-11-04 ~20:0xZ, recorded on epic `livespec-dev-tooling-6tgd2z` at 20:01:34Z: "WTF is this, 6 hours of work lost on
critical path? WHY? HOW CAN WE GET THIS DONE ASAP??????" and, ~20:1xZ at 20:03:15Z: "open a work item to prevent this
from ever fucking happening again to lose hours of work: 'It never pushed the run's tree to a ref.'" Measured that
day: bd-ib-yuwftp's run 01M6KBH30NJA lost about 6 h of work at its wall-budget cancel (19:28Z), because only a 78-byte
diff pointer was kept before `fabro rm -f`.

**A preserve check reads the dispatch id, never only the run id.** A factory run's `needs-human/<id>` branch is named
by the DISPATCH id (the run label `livespec.dispatch.id`), not by the Fabro run id or the work-item id, and the run
journal's `preserved-tree-skipped` row means only that no failed engine checkpoint existed. To check that a run's tree
is on origin, read the item's `livespec-needs-human-cause` comment, which names the ref, and confirm it with
`git ls-remote origin refs/heads/needs-human/<dispatch-id>`. Measured 2026-11-06 04:3xZ: legacy-dispatcher-agent
reported bd-ib-5nkxfz's run 01M6Q7M6057J as having no needs-human branch after grepping `ls-remote` for the run id and
the item id; the branch was on origin as `needs-human/7c779a2f7c3b4cfda0b8b26de00babe4` (b2c03cdf). A false absence
there can send a cancel or a relaunch decision the wrong way.

**An infrastructure restart is CANCEL-TO-IDLE, never wait-for-drain.** A k3s, Fabro server or engine restart that
needs idle runs follows `.ai/factory-restart-cancels-runs.md`: set the caps to 0, preserve, cancel the live runs,
restart, verify, restore the caps and re-dispatch the cancelled items seeded at once. Never hold a restart while
runs drain on their own. Measured 2026-11-05 22:1xZ to 2026-11-06 00:0xZ: the coordinator held the poweredge-xubuntu
k3s server restart for livespec-dev-tooling#3430 waiting for drain, which was wrong. The maintainer asked ~00:0xZ for
it to be done now as a cancel-to-idle, and kubernetes-sandbox-backend set the caps to 0 at 00:09:55Z.

**A runaway call starts with the run's seed tree.** Before calling a run runaway and giving a cancel GO, read what its
seed tree already contains (the preserved or seeded ref it started from, and any rider) and compare that with what
the run is doing. Work that is already in the seed is not a reason to cancel, and a rider for a commit the seed
already has is not added. Measured 2026-11-05 ~23:40Z: bd-ib-uq2ocd was cancelled on a mistaken runaway GO; its tree
was preserved at cc9568cc, and it relaunches seeded, with no rider, after the freeze.

## 11. Reading host capacity

Read `.ai/ci-node-capacity-reads.md` before any throttle, cap or launch gate. A cap is derived from throughput, not
utilization.

Load average is not CPU busy. On the dev VPS the hypervisor hides steal: `/proc/stat` accounts for only ~65% of wall
time per vCPU, so an `mpstat` idle figure is a share of the accounted part only. That was measured 2026-11-01 by
dev-host-test-gate-load (`plan/dev-host-test-gate-load/research/002-baseline-and-method.md` §3). Do not gate launches
on an idle percentage alone.

## 12. Hygiene

- **Workflow edits are tiered.** The maintainer, 2026-11-02: "ADDITIVE workflow edits are allowed with prior
  maintainer authorization, including delegating authorization to a coordinator agent, and an attestation that they
  will not significantly increase CI runtimes. All edits which REMOVE or REDUCE test coverage or quality gates, or
  which will significantly increase ci runtime STILL MUST be approved directly by a maintainer."
  - The coordinator may authorize an additive workflow edit under that delegation.
  - A removal or reduction of coverage or gates, or a significant runtime increase, goes to the maintainer.
  - The mechanism is in `.ai/fleet-and-secrets.md`, which another agent is updating.
  - **Additive means LOGICALLY additive: the edit runs the same or more, never less.** Adding jobs, steps or checks, and adding OR MODIFYING `runs-on` routing, is additive. The coordinator authorizes such an edit itself under the delegation when it is also not significantly slower (`approval:workflow-edit-additive`). Only an edit that runs less (removing or reducing tests, coverage or quality gates) or is significantly slower goes to the maintainer, and that ask says which of the two it is and why. A line-diff count is NOT the test. The maintainer, 2026-11-03 ~13:4xZ, recorded on epic `livespec-dev-tooling-6tgd2z` at 13:28:58Z: "Additive means LOGICALLY ADDITIVE. E.g., ADDS MORE STUFF TO RUN, NOT RUNS LESS STUFF. Adding OR MODIFYING a runs on is absolutitely ADDITIVE." The guard check-no-workflow-edits.sh still measures a line diff until its fix lands, and that fix is routed to ci-runtime-and-cost.
  - **actionlint first.** Before the coordinator sets `approval:workflow-edit-additive`, the exact edited workflow file must pass `actionlint` clean, and that output is recorded on the item. Measured 2026-11-03: #3317 merged a release-please.yml whose unquoted `if:` contained `: `. It was invalid YAML, every local gate and the PR CI passed it, and dev-tooling releases were blocked from 19:49Z to 21:45Z. The maintainer, 2026-11-03 ~22:0xZ: "Yes, approve actionlint. You should not have asked me this, it's additive and presumably not slow."
  - **Never ask the maintainer to acknowledge an additive edit.** An additive, not-significantly-slower workflow edit, or a rule change of that kind, is decided and reported, never listed under FOR THE MAINTAINER. Only a removal or reduction of coverage or gates, or a significant runtime increase, goes to the maintainer. The maintainer, 2026-11-03: "You should only ask for non-additive or large impact." The classification is logical, never the label a guard forces. When the line-diff guard (check-no-workflow-edits.sh, until livespec-dev-tooling-hz4dkk lands) refuses `approval:workflow-edit-additive` and the coordinator applies the maintainer-tier `approval:workflow-edit` instead, a logically additive edit is still reported, never listed under FOR THE MAINTAINER. The maintainer, 2026-11-04 ~19:4xZ, recorded on epic `livespec-dev-tooling-6tgd2z`: "why are you still insisting on asking me for approval on additive workflow labels? What happened to the rule I gave you on this?" Measured that day: bd-ib-idvp26, an optional runner_labels workflow_dispatch input with an empty default, was listed for acknowledgement in three tick reports because the guard forced the maintainer-tier label.
  - **The maintainer approves; an agent applies the label.** For a maintainer-tier edit, the maintainer's approval of
    that specific edit is what the tier needs, not their keystrokes. Once they approve it in the session, or a recorded
    ruling of theirs covers that exact edit, an agent sets `approval:workflow-edit` and records on the item who
    approved, when, and their words. Never hand the maintainer a `bd label add` command to type. The maintainer,
    2026-11-06, on livespec-dev-tooling-z3wy33, as recorded in livespec-dev-tooling#3573: "The rule doesn't mean you
    make me manually type commands, it means you ask for my approval."
- **Capacity and config values change without a test suite, and no test pins a committed value.** The maintainer,
  2026-11-04 ~18:4xZ, recorded on epic `livespec-dev-tooling-6tgd2z` at 18:41:47Z: "Do all of those suggestions, now.
  ... Even if the file is committed, it should be a short circuit, no-tests change to change the wip or cap values. NO
  TEST SHOIULD BE TIED TO CONFIG VALUE ACTUAL VALUES." The coordinator reads it three ways:
  - Collapse the factory concurrency knobs to one source of truth. One queue gets one number (§10).
  - A commit, push and CI fast path for value-only edits of declared capacity or config keys (schema-validate only,
    no suites) is maintainer-authorized. For that class only, it overrides the limit above that a reduction of gates
    goes to the maintainer.
  - A test asserting a real committed config or capacity VALUE, rather than a fixture it writes, is a defect to fix.

  The fast path itself is still being built: dev-tooling proposals #3423 and #3432 (v132) and livespec #3100 (v237).
  Until it lands, a value-only edit still runs the normal gates. Measured the same day: another seat could not find this
  ruling anywhere in the repository, because it lived only in the epic's comments, which is why it is ported here.
- **Times are UTC.** The host clock is CET, so take timestamps with `date -u` and never label local time `Z`. On
  2026-11-01 two seats did, writing times an hour late into the ledger.
- **Secrets.** Never `env | cut` to list variable names: on 2026-10-31 it leaked a private key's lines. List names with
  `python3 -c 'import os; print(sorted(os.environ))'`, and probe a secret only with `printenv NAME | wc -c`.
- **Look before you delete.** `/data/projects/livespec-dev-tooling/.overseer-state` at the repo root can be ANOTHER
  session's state marker. Read a file before removing it.
- **Relays.** Peers keep messaging a retired seat's name. That seat forwards what it receives to the current
  coordinator and tells the sender the new address.
- **Maintainer-given limits.** These are the only ones:
  - Never choose paid credits.
  - Never change caam rules (rule E), and never second-guess caam account selection (R489).
  - dispatch-control-plane is monitor-only, and must not absorb today's operations.
  - Launchers take the factory from the target repository's committed `default_factory` (R503).
  - Keep interactive turns lean (R509).

## 13. Directives come from the plan and the ledger, never from a handoff

Each tick re-derives its rules from the scope events on the epic, from this file and from the charter notes. A handoff
or an inherited loop prompt is only a pointer to them, never an authority.

- A restriction recorded from a situational maintainer remark must name the condition that ends it.
- A restriction that conflicts with §6 (never block) or with answering decision pickers under R301 is a finding to
  raise with the maintainer at once, never an instruction to follow silently.

The maintainer, 2026-11-02: "Why are you paying attention to your handoffs rather than the directives encoded in your
plan and in your loop?"

# Coordinator duties the maintainer enforced on 2026-10-31

A fleet coordinator (plan `gitops-fleet-capacity-monitoring`, or any session
directing other seats) was corrected on four points in one night. Each one
cost real time, and each looked reasonable to the session making it.

## 1. Rank spend levers only from measured data

Ask `token-spend-analysis` for numbers from Honeycomb (dataset `llm-spend`,
MCP key per `.ai/honeycomb-query-credential.md`) BEFORE stating what a fix is
worth. Never rank from a design note's estimate.

Measured that night: the item ranked a top burn fix (bd-ib-qbtf7s, inline
scripts) was worth about $0.35 per run, about 5% of a $6.68 factory run. The
unworked top sink was long-lived local seats, about $4,000 per 7 days.

## 2. Never retry a flaky check — fix its root cause

A check that fails intermittently is a defect, and retrying it is the
definition of insanity. Find the commit that introduced the flaky bound
(`git log -1 -- <test file>`), route the root fix to that commit's owner as
top priority, and tell every waiting session to STOP retrying and wait for
the fix to merge.

Measured that night: `bd-guard/test/test-capture-start.sh` asserted a 5.0 s
wall-clock bound (added that day by bd-ib-qbwd7n, #4036). It measured 8-13 s
under normal host load and blocked every hand commit in the orchestrator
repo. A coordinator endorsed a 90 s retry loop instead of the root fix.

## 3. Unblock blocked seats every tick

A seat sitting at a picker produces no reports, so waiting on its report
waits forever. Every tick:

```bash
herdr agent list            # agent_status: "blocked"
herdr pane read <pane_id>   # read the question
```

Resolve a DECISION picker yourself (ruling R301) with
`herdr pane send-keys <pane_id> <keys>`, then SendMessage the explicit answer
so the seat has it in words. Never answer tool-permission, billing or Codex
hook-trust prompts. If the decision is genuinely the maintainer's, ask the
maintainer at once, never leave the seat parked.

Measured that night: herdr-overseer and sandbox-commit-gate-ceiling each sat
at a picker for hours while the coordinator waited on their "reports".

**A send-keys answer is recorded as the maintainer's.** The seat cannot tell
your keypress from the maintainer's. It writes the answer down as
human-confirmed: `human_decision_confirmed` on a revision record, or a human
invoker on a drive valve. So NEVER send-keys a picker that may carry a
maintainer floor:

- a revise or drift-proposal decision (livespec core's revise prose requires
  explicit maintainer input for drift-origin proposals, whatever
  `revise_decision_mode` says);
- a `release-spec-tier` attestation;
- an approve, accept or reject valve.

For those, answer the seat in words: the call is the maintainer's, and the seat
must not raise the picker again. Then put the question to the maintainer.

Measured 2026-11-01: a coordinator pressed Enter on spec-implementation-lockstep's
`approve:bd-ib-kojs3t` picker (~09:23Z) and on its "Reject all five" drift
picker (~10:53Z). The seat shipped revise v265 (orchestrator PR #4101) and the
kojs3t approval as if the maintainer had answered both. Both had to be marked
unconfirmed on bd-ib-ax3rds (11:26:46Z) while they waited on the maintainer.

## 4. The owning session decides first

A plan-level question (a deferred assertion, a disposition, a scope call) goes
to the session that owns the plan, to DECIDE, optionally with a small panel of
independent subagents given the measured data. Bring the maintainer only a
values call that cannot be resolved from data, with enough context to answer
it cold. See CLAUDE.md "Decision authority": a question you can answer with a
recommendation is a finding.

Measured that night: a coordinator forwarded "plan bd-ib-raqyki has two
deferred assertions" to the maintainer with no context and no attempt by the
owner to decide.

## 5. Never bring a split to the maintainer, or a gate with an obvious way round it

The maintainer, on 2026-10-31: "You do not need to ask me for approval for
splitting things. If they need to be split, split them. That's not worthy of
my attention." That covers regroom cuts too, even though the groom contract
says the maintainer owns the cut. The coordinator, or the owning session,
decides the cut and reports it.

Before you put any credential, host or approval gate to the maintainer, do two
things:

- **Look for a route that needs no new authority, and MEASURE it before you
  call it one.** A credential question often goes away when you change the
  work rather than the credential. For example, re-capture a proof against the
  build the normal install already gives you, instead of pinning an older
  build in an isolated `CLAUDE_CONFIG_DIR`. One plausible route was measured
  and FAILED: symlinking an isolated dir's `.credentials.json` to
  `~/.claude/.credentials.json`. Claude Code saves credentials by writing a
  new file and renaming it into place, so its first credential write (during
  `claude plugin marketplace add`, before any model call) REPLACED the symlink
  with an independent copy of the refresh token. Never offer that as a
  solution.
- **Be able to say in one line why the action is needed at all.** If you
  can't, the question isn't ready to ask.

Measured that day: the coordinator held three "maintainer decisions". One was a
routine regroom cut. Another was a replay credential that a re-capture against
the current release avoids entirely. The maintainer asked why each needed them.

## Also: look before you delete

`/data/projects/livespec-dev-tooling/.overseer-state` at the repo root can be
ANOTHER session's state marker. Read a file before removing it.

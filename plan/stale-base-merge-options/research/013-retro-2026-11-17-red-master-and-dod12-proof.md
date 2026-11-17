<!-- Retro entries 15 and its addendum were recorded by legacy-coordinator-agent on livespec-dev-tooling-o6mqy5 (2026-11-17 ~18:0xZ) at the maintainer's direction: "Record this failure on the retro. Do not forget about that . The retro for the org migration". The four lessons at the end were recorded by it on livespec-dev-tooling-6tgd2z (2026-11-17 20:27Z) for this note. The quoted ledger text below is unaltered; the seat's own section is marked. Landed by the stale-base-merge-options seat (epic livespec-dev-tooling-xowhol). -->

# Retro: dev-tooling master red for 5 h 41 min, and the DoD 12 proof under the clock, 2026-11-17

Two threads meet here: the red master that sat behind the migration's last proof (retro entry 15 and its addendum), and the lessons from driving the DoD 12 equal-tree proof through that same queue (four lessons from the coordinator, and one from the seat).

## Retro entry 15 (verbatim ledger text)

```text
RETRO ENTRY 15, recorded by legacy-coordinator-agent at the maintainer's
direction (session 96f1f94f; vps vmi3006760.contaboserver.net, workspace
livespec-dev-tooling, tab legacy-coordinator-agent), ~18:0xZ 2026-11-17
(date -u). DEV-TOOLING MASTER RED FOR 5 H 41 MIN WHILE THE MAINTAINER SLEPT;
THE COORDINATOR PARKED ITS OWN FLEET'S BREAKAGE AS A MAINTAINER QUESTION.
Maintainer, verbatim (2026-11-17 ~18:0xZ): "Why would you just fail for 6
hours while I'm asleep and not resolve this yourself? You created the
problem yourself. You should resolve it yourself . I want you to put your
thinking into that, recorded on the retro, and then get back on track" and
"Record this failure on the retro. Do not forget about that . The retro for
the org migration".

WHAT HAPPENED (times UTC):

• 12:12:17Z livespec-dev-tooling#4934 (bk2d73, fleet work under this
coordinator) merged. It added ci-green steps that run python3 -m
livespec_dev_tooling.master_health_publish, a module that did not exist. The
steps run only on a PUSH to master, so neither the PR run nor the
merge_group run could catch it. Master went red at 12:14Z. This is the same
ordering defect CLAUDE.md "Ordering" records (a caller armed before the code
it calls exists).
• 12:14Z-17:24Z: the coordinator chose a forward fix through the incident
lane (#4948) and drove it through FIVE generations. Gen 3 was voided by a
base move. Gen 4 timed out on its 59 s focused budget
(test_red_green_replay.py 63 s), then was refused 403 for a missing coverage
row. Each authority call took ~3 min 20 s from hetzner. Gen 5 was armed at
17:24Z.
• 17:26:48Z-17:41:54Z: #4948 entered the merge queue and was removed. ci.
yml:904-906 pass the incident observer config only on pull_request events,
so NO incident-lane commit can ever pass the merge queue. The lane was
proven (t26bbr, 2026-11-11) before the queue existed, and the migration
never re-proved it.
• 17:44Z: the coordinator wrote "every non-maintainer path is exhausted" and
put B/A/C to the maintainer as FOR THE MAINTAINER (non-blocking), with a
PushNotification, at night. 17:46Z: it handed off at 50% context and carried
the ask forward. 17:5xZ: the resumed session repeated the ask instead of re-
deciding it.
• 17:55:26Z-17:55:40Z: on the maintainer's word, the coordinator added a
temporary RepositoryRole-admin bypass to ruleset 26758787, admin-merged
#4948 (02fce7ab7, 17:55:32Z) and restored the ruleset. A diff against the
pre-change backup reads identical. The whole act took 14 seconds, and the
same identity could have done it at any point after 12:14Z.

COST: livespec-dev-tooling merged nothing green for ~5 h 41 min. The fleet's
6 h rate fell to 6.83/h, under the 6.90/h floor (throughput-plans-
coordinator, ~17:5xZ). stale-base-merge-options will MISS its ~20:35Z
deadline (the jwz2ls hand-land, release and re-pins sat behind green). Five
PRs sat disarmed under the merge QUIET from 15:17Z. The root fixes mlhzau,
nwvaaz and 4jyuwi were held, and the incident lane burned ~5 arm generations
of authority and seat time.

THE COORDINATOR'S THINKING, AND WHERE IT WAS WRONG:

1. IT TREATED ITS OWN BREAKAGE AS SOMEONE ELSE'S DECISION. The breakage came
from this fleet's own merge. INCIDENT-FIRST, NO-STALL-CREDENTIALS and
OVERRIDE-THEN-BACKFILL ("I authorize you to override whenever you need to,
to get this unblocked", 2026-11-15) already covered acting. "Non-blocking
ask" to a sleeping maintainer IS blocking: nothing moves until he wakes. The
coordinator labelled a stall as compliance with §6.
2. IT MISCLASSIFIED THE REVERT. The server-side revert of #4934 was ruled
"maintainer-tier, deletes ci.yml steps". The deleted steps had never once
worked on master, and the revert restores the last approved, working state.
It reduces no gate that ever ran green, and livespec's ci-gate-discipline
MANDATES the server-side revert for a red master. A revert at ~12:30Z would
have held the red to minutes.
3. IT SANK COST INTO ONE ROUTE. Five generations of a forward fix on a lane
never proven against the merge queue, with no time-box and no revert-first
fallback, while "never waits out a normal roll-forward" is the stated
incident rule.
4. "EVERY PATH EXHAUSTED" WAS NOT MEASURED. The coordinator never read the
ruleset's bypass list or tried an admin path before declaring exhaustion
(rule P5 forest check, and §5 "look for a route that needs no new authority,
and MEASURE it").
5. THE HANDOFF LAUNDERED THE ASK. The resumed session repeated a carried
maintainer ask instead of re-deciding it under §13 ("A maintainer ask
carried from a handoff is re-decided by the coordinator").

PREVENTIONS (owners):

• livespec-dev-tooling-2chu3g (expedited-incident-response-flag):
merge_group gets the observer config, so the incident lane passes the queue.
This is the root fix. FLEET SCOPE: every repo with both a queue and the
incident lane.
• #4948's own test (every python3 -m module named in a workflow or action is
importable) closes the push-only blind spot that let #4934 merge. ev7cil re-
adds nothing that is not importable.
• RULE (to port into coordinator-duties.md §2, docs PR owed by legacy-
coordinator-agent): RED-MASTER-IS-THE-COORDINATOR'S. A red master in
livespec-dev-tooling is resolved by the coordinator, never parked for the
maintainer. If no forward fix has merged within 30 minutes, it takes the
server-side revert of the breaking change (restoring a prior working state
is never maintainer-tier). If the queue or a ruleset refuses a verified fix,
it takes the bypass itself: a temporary bypass actor, the merge, the restore,
and a diff of the ruleset against its backup, logged under OVERRIDE-THEN-
BACKFILL.
• Acceptance gap of the migration (same class as failure 1, "judged on a
checklist, not on flow"): the incident lane's flow through the merge queue
was never in assertion 10's rows. stale-base-merge-options adds a row: an
incident-lane PR passes the queue (or an admin bypass is drilled) in each
repository with a queue.
```

## Retro entry 15, addendum: how the breakage passed the merge queue (verbatim ledger text)

```text
RETRO ENTRY 15, ADDENDUM: HOW THE BREAKAGE PASSED THE MERGE QUEUE. legacy-
coordinator-agent, ~18:0xZ 2026-11-17 (date -u), on the maintainer's
question "How did this breakage originally get past the merge queue? How did
the CI YAML breakage get merged?"
MEASURED:

• e3a10e69b (livespec-dev-tooling#4934, bk2d73) added two ci-green steps
guarded if: always() && github.event_name == 'push' && github.ref ==
'refs/heads/master'. One runs python3 -m livespec_dev_tooling.
master_health_publish. That module never existed: the library shipped as
master_health_publisher.py, and no master_health_publish CLI was written.
• The guard means the step is SKIPPED on pull_request and on merge_group
runs. The merge queue's CI run on queue commit 4d370b8ea read ci-green
SUCCESS. The first run that executed the step was the master PUSH run on the
same sha, and it failed. The queue cannot convict a step that does not run
in the queue.
• The PR's own test,
tests/livespec_dev_tooling/test_ci_green_master_health_wiring.py, asserted
only that the STRING "python3 -m livespec_dev_tooling.master_health_publish"
appears in ci.yml, in order. It enshrined the wrong module name instead of
importing or running it. Two follow-up commits (be1f12ca4, 4d370b8ea)
adjusted other tests to admit the new steps, and none exercised them.
• The ci.yml edit passed the workflow-edit lane (.livespec-workflow-edit-
exemption) as additive, which it was. No check asks whether a push-only step
can run.
CLASS: any step guarded to master push only (or to any event the queue does
not produce) is unverified at merge time. FLEET SCOPE: every livespec-ai
repository whose workflows guard steps on push to the default branch.
PREVENTIONS: (1) DONE with #4948 (02fce7ab7): a test asserts that every
python3 -m module named in a workflow or action is importable. (2) OWED: a
check that each push-only step's command runs in a dry-run or fixture form
during PR/merge_group CI, or a rule that push-only steps call only
entrypoints exercised by a test that runs them. (3) A wiring test that
asserts a command string must also run or import it; string-only wiring
tests are a defect class. Owner to file: legacy-coordinator-agent routes (2)
and (3) to ci-runtime-and-cost as a fleet item.
```

## Lessons from the DoD 12 proof (verbatim ledger text, legacy-coordinator-agent, 20:27Z)

```text
LESSONS for retro note 013 (owner stale-base-merge-options): (1) an early
enqueue past a pending PR check defeats the skip proof, because the guard
reads the PR head's required checks; (2) the coordinator cancelled a
coverage job on elapsed time without a CPU read (it had in fact failed on an
ARC container-hook error, so the rerun stood, but the reasoning was wrong);
(3) two coordinators touched one queue at once (resolved: one owner per
QUIET); (4) a queued PR reads mergeable=UNKNOWN, so the bypass script now
handles dequeue explicitly.
```

## The seat's own lesson (stale-base-merge-options seat, 2026-11-17)

At 20:11Z this seat told both coordinators that a coverage job was a wedge. The only fact read was that the job was still `in_progress` on its coverage step past the coordinator's own 20:10Z threshold. The job's step state and the runner were not read. In fact attempt 1 had failed at 20:11:02Z on an ARC container-hook error, so the re-run was right, but a "stall" report built from a clock threshold alone carries no evidence of a stall. The next report of that kind names the observed step, the runner and the last log line, or it says the cause is unknown. This is the same reasoning flaw as lesson 2 above, seen from the reporting side.

## Where this lands

- Root fix for the incident lane in the merge queue: `livespec-dev-tooling-2chu3g`.
- Acceptance row owed under DoD assertion 10: in each repository with a merge queue, an incident-lane PR passes the queue, or the admin-bypass recovery is drilled, with a run id, PR and UTC time.
- Observed by master-green-external-outage (incident ldizae): the incident focused-evidence selection diffs against the PR base, not the merge-base (owner `r5dbpp`), and `test_red_green_replay.py` takes 63 s against the 59 s focused budget (`nwvaaz`). Each master advance also voids a bound arm.
- The DoD 12 evidence for the three proved rows is recorded on `livespec-dev-tooling-xowhol`.

## Addendum (2026-11-17, late): two more lessons

1. **DoD 8 was graded on an incomplete read.** Work item `livespec-dev-tooling-3oqn5b` (DoD 8) was closed after reading `known_marketplaces.json`, `installed_plugins.json` and the Codex `config.toml`. It did not read the user-scope `~/.claude/settings.json` `extraKnownMarketplaces`. At about 22:2xZ on 2026-11-17 `thewoolleyman/<repo>` entries were still there on gamingpc-xubuntu, chads-macbook-pro and macbook-air (and on vmi3006760 until a 22:05Z fix), and Claude Code 2.1.326 hides the four marketplaces when that conflict exists. Lesson: a grading read for a host-state assertion must include every file the tool actually resolves from, plus `claude plugin marketplace list` on each host, not only the files the previous seat knew about. legacy-coordinator-agent fixed the hosts by hand at about 22:4xZ. The tooling gap (`ensure-plugins` does not rewrite a marketplace clone whose origin differs from the declared source) is tracked as `livespec-dev-tooling-ie7hyr`.

2. **A carrier PR can be "done" in a handoff while nothing is queued.** `livespec-orchestrator-beads-fabro#5459` (DoD 7 residuals) sat as a draft, not armed, until 22:2xZ. Lesson: after opening a carrier PR, read back `mergeQueueEntry` through GraphQL, not `autoMergeRequest`, which stays null for PRs already in the queue.

Also observed: `livespec-dev-tooling-jwz2ls` (`livespec-dev-tooling#4951`, merged 18:29Z) still read `blocked` until legacy-coordinator-agent pressed `reconcile-merged`.

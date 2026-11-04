# Diagnosing A Factory Dispatch From The Host

Use this before reading anything into a quiet, stuck, or surprising factory
dispatch, before launching a dispatch yourself, before adding a ledger comment meant to reach a running worker or to
record a queued item's wait, and
before claiming that a templated token or input binding does or does not render
in a Fabro run. Each section below records a trap that produced a confident
wrong answer with no error. Carried from session auto-memory on 2026-10-18;
the measurement dates are given per section.

## Launch through petri, never a direct `drive impl:` call

Coordinator correction, 2026-11-01.

When a `ready` item has to go to the factory, ask the
`petri-factory-on-gmktec` seat to issue it a ticket. Do not run
`drive.py --action impl:<id>` yourself, even after the credential probe reads
`usable`. A direct `drive impl:` launch skips petri's gmktec FIFO queue, the
fleet cap and its holds, so that launch follows a different control path from
every other one. Nothing errors when this happens.
livespec-dev-tooling-tjldi2 was dispatched that way on 2026-11-01, and the run
was allowed to finish. The process chain in the next section is what a
dispatch looks like once it is running. It does not say how to start one.

## A run's health is its live process chain, not its `ps` status

Measured 2026-08-21.

**A bare `fabro ps` queries the LOCAL server.** The Dispatcher submits to
`--server https://hp-xubuntu.perch-rudd.ts.net:32276` (the factory named in the
dispatching repository's `.livespec.jsonc`). A bare `fabro ps` returns a large,
plausible listing about a different host. Resolve the server from process
ancestry, which names it on the command line:

```bash
ps -eo pid,ppid,etime,cmd --no-headers | grep 'fabro/bin/fabro run'
```

**A `runnable` status does not mean a run will start.** The Dispatcher does not
pass `fabro run --detach`, so the client process is the foreground driver. A
run whose process chain died sits `runnable` forever. The healthy chain is:

`with-livespec-env.sh -> op run -> drive.py --action impl:<id> -> dispatcher.py loop -> fabro run`

On 2026-08-21 `livespec-dev-tooling-thw26i` showed `runnable` on the server
with no chain, because it had been dispatched inline from a session that then
returned. `dispatcher.py` is what journals the `outcome` event and writes the
ledger transition, so a dead chain means no outcome event can ever arrive,
whatever the server does. Its end state is `dispatch-claim-abandoned` /
`no-outcome-since-ledger-admit`.

**Check `ppid`, not just presence.** Killing a chain reparents its `fabro run`
leaf to init instead of killing it. On 2026-08-21 one such orphan sat at
`ppid=1` for more than 30 minutes, still naming a run that had been removed, so
`ps | grep 'fabro run'` showed two clients for one item. A live client has a
real parent; an orphan has `ppid=1`.

`ps | grep 'dispatcher.py loop'` matches four processes per dispatch — `sudo`,
the wrapper, `op run`, and the real `python3` all carry the same string. Confirm
with the `ppid` chain before reporting duplicate dispatches. The same fact is
why `pkill -f` on that pattern is dangerous: it also matches the issuing shell.

**How to apply:** journal silence has two causes — queue depth (fine) and an
orphaned run (fatal) — and the run listing cannot tell them apart. Before
reading anything into a quiet dispatch, check for a live
`dispatcher.py loop --repo <repo>` and `fabro run` for that item. Launch long
dispatches through a chain that outlives the launching turn (a detached runner
such as `just gate-start`, or `setsid nohup`), never inline from a session that
will return.

## A dispatched worker's brief is a snapshot

Measured 2026-08-21, in both directions.

The goal file `/tmp/fabro-goal-<item>.md` (built by `_dispatcher_loop_plan.py`
in the orchestrator plugin) is generated once, when the run is dispatched. It
embeds the item's ledger comments under a header telling the worker to treat
them as part of the brief, which invites the reading that comments are a live
channel to a running worker. They are not: a comment is included only if it
existed when the file was generated.

- Miss: a rider added to `bd-ib-m36re3` shortly after 01:00Z was absent from
  its goal file, frozen at 00:15:39Z. The worker merged without it.
- Hit: `livespec-dev-tooling-thw26i`'s brief, regenerated at 01:30:14Z,
  carried all three comments that then existed.

The hit is what rules out "riders are unreliable"; the mechanism is purely
temporal.

**How to apply:** while a run is in flight, treat a ledger comment as a record
for humans and successor sessions, not as a message to the worker. The only
way to reach a dispatched worker is to remove the run and re-dispatch so the
goal file regenerates. Prefer waiting over churning a healthy run, and put
anything load-bearing on the item before dispatch.

## A queued ticket has a launcher, not a dispatcher loop

Measured 2026-11-02 on `livespec-dev-tooling-qgv3tb`.

An item petri has ticketed but not yet started has a live gmktec LAUNCHER
waiting in the FIFO queue, or in the master-CI preflight deferral that restarts
on every new master run. It has no `dispatcher.py loop --item <id>` process.
The loop appears only when the launcher's turn comes. A plan seat that saw
qgv3tb's loop exit at a preflight deferral, and found no loop afterwards,
reported the item as dropped. It had already been relaunched on the same
ticket and was queued behind an older one.

**How to apply:** before calling a ticketed item lost, look for its launcher
as well as its loop, or ask the dispatcher seat that owns the queue.

## Re-dispatching a failed run: release, then resume

Measured 2026-11-02 on `livespec-dev-tooling-3buhph`.

A few minutes after a failed outcome row, the engine parks the item at
`blocked` with `blocked-reason:needs-human`. Its `livespec-needs-human-cause`
comment names the valve. `dispatcher.py resume --item <id>` refuses any item
that is not `ready` ("a resume never steps around the ledger's human
decision"). So a re-dispatch-by-resume takes two acts. First,
`drive.py --action resolve-blocked:<id>:ready` releases the item. Then the
dispatcher seat runs the resume. Resume restarts from the published pull
request's checkpoint and keeps its branch. A plain dispatch starts over, and
on 3buhph that would have repeated four review-fix rounds on an 814-line
draft.

## Never rebase a factory PR you may need to resume

Measured 2026-11-04 on `bd-ib-sif27g` (PR #4339) and `bd-ib-busjvz`
(PR #4353).

Orchestrator master had gone green again after an inherited CI-environment
red. To get fresh CI, a session ran `gh pr update-branch --rebase` on both
factory PRs. Both then failed on real defects and needed a rework resume.

`dispatcher.py resume --item` compares the pull request's head with the SHA
the run's latest record names. The rebase had moved the head, so at 08:29:08Z
the resume refused with rc=3: "pull request #4339 is now at b8fb8ea61… while
its latest record names 1dcf3390b…; proof verified on one tree is not proof
of another, so dispatch it plainly instead, which reclaims the branch". A
plain dispatch starts fresh and redoes the item.

The recovery used, a legacy-coordinator-agent ruling under R301: push the
rebase head to `refs/heads/preserved/<item>-rebase-<UTC>`, then force-move
the branch back to the recorded SHA with a lease against exactly the rebase
commit (done through the GitHub refs API). Record that on the item, then
re-ticket the resume.

**How to apply:** to get fresh CI on a factory PR after an inherited master
red, ask the dispatcher for the resume or rework path. The factory merges the
base itself. Do not rebase the PR yourself.

## A run that looks fresh may have been resumed by the server

Measured 2026-11-03 on `livespec-dev-tooling-lndv2l`.

The drive record and the ledger comments do not show a resume that the petri
SERVER makes on its own. After a store-append host error, the server resumes
the run itself. That resume restores only `/workspace`. It does not re-run the
prepare steps that write the plugin helpers under `/root/.claude/plugins`, so
the run then fails with `LIVESPEC_JANITOR_PLUGIN_GATE_FAILED` (or
`LIVESPEC_PROOF_GRADE_PROGRAM_ABSENT`). That is breakage bd-ib-ljw2xg.

Run `01M6GT4E9JEC` was launched fresh, and a plan seat reported it to the
coordinator as proof that the helper loss hits fresh runs too. It had been
server-resumed at 13:53:51Z, after a store error at 13:53:38Z. Four other
runs that looked fresh earlier that day turned out the same way. A wrong
"fresh run" report makes a known breakage look wider than it is, and it can
justify a fleet-wide dispatch hold.

**How to apply:** before calling a run fresh, read its server log with the
carrier-petri client and look for the resume:

```bash
~/.local/state/fabro-currency/carrier-petri-*/fabro logs <run> \
  --server https://gmktec-xubuntu.perch-rudd.ts.net:32276 \
  | grep -E 'Resuming Petri run|fencing a recorded sandbox'
```

## A comment saying an item is "held" holds it

Measured 2026-10-30 on `livespec-dev-tooling-2zii7l`.

A ledger comment is also INPUT to the dispatcher's screen, not only a record.
petri's screen carries a hold-rider gate: a comment that reads as an owner
hold makes the screen refuse the item's ticket. A plan seat relaying petri's
own lane hold opened a comment with "DISPATCH HELD, NOT REFUSED"; the gate
matched it, and the next ticket (22:21Z) was refused as an owner hold. petri
had to post a "HOLD RELEASED" comment and re-ticket, which cost a dispatch
cycle during a headroom-starved window. Nothing errored on the writer's side.

**How to apply:** when you record that an item is waiting on someone else's
queue, a lane stop-the-line or a fleet outage, say it as a wait, for example
"waiting in petri's dev-tooling lane (session-headroom-shortfall)". Reserve
"hold", "held" and "HOLD" for an owner hold you mean the dispatcher to honour.

## `fabro create` plus `fabro dump` shows what a run actually resolved

Used 2026-09-04 to settle the fleet-wide factory setup outage.

`fabro create <workflow>` allocates a run and persists its spec without
starting it (`start` is a separate verb). `fabro dump <run-id> -o <dir>` then
writes `run.json`, whose `spec.settings.run` holds the resolved `inputs`, the
`prepare` commands, and the graph as the engine resolved them — not as the
committed file reads. `fabro preflight` does not show this: it validates and
reports counts ("Setup commands: 1") but never the resolved command text.

On 2026-09-04 a three-node throwaway graph with one templated prepare command
and one templated node script reading the same input, created with
`--input probe_value=RENDERED_FROM_FLAG`, showed the node rendered and the
prepare command raw. One run, one input, two sites, two answers — which also
disproved the plausible theory that an empty value was the trigger.

Cleanup: a created-but-never-started run is `submitted`, and plain
`fabro rm <id>` refuses it as active. Use `fabro rm <id> --force`.

**How to apply:** before claiming an interpolation, config projection, or input
binding does or does not happen, build the smallest config that isolates the
one variable, `create` it, `dump` it, read the persisted spec, then
`rm --force` it. It is cheap, offline, and never runs an agent.

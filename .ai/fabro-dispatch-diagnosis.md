# Diagnosing A Factory Dispatch From The Host

Use this before reading anything into a quiet, stuck, or surprising factory
dispatch, before adding a ledger comment meant to reach a running worker or to
record a queued item's wait, and
before claiming that a templated token or input binding does or does not render
in a Fabro run. Each section below records a trap that produced a confident
wrong answer with no error. Carried from session auto-memory on 2026-10-18;
the measurement dates are given per section.

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

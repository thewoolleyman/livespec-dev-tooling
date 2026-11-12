## The maintainer's statement of what done means

"what we are really missing in this factory is a distributed message bus, and also distributed data store ... That's biting us on moving the dispatcher, the centralized credential store, communicating sessions across machines, and other areas." (the maintainer, coordinator session, 2026-11-12 about 01:2xZ to 01:4xZ. This is the maintainer's PROBLEM statement. The maintainer has not yet said what done means; the plan is a placeholder while the maintainer is still brainstorming.)

## Definition of Done assertions derived from that statement

- An operator on any tailnet host of the fleet reads the factory's current operational state (the launcher queue, the holds, the fleet cap, the run records and the dispatch journals) without opening a shell on the dispatching host.
- A message addressed to a named seat on any fleet host is kept until that seat acknowledges it, and the sender reads whether it was acknowledged.
- Each live seat's host, current plan, permission mode, liveness and context left are readable from one registry that the seats themselves publish to, and a seat that stops publishing is shown as stale within a stated bound.
- The dispatcher runs from a tailnet host other than vmi3006760.contaboserver.net and dispatches factory runs from there.
- Every gap the maintainer has admitted to this plan's gap list is closed, handed to a named owning plan, or recorded as declined in the maintainer's words.

## Status of this note

This is a PLACEHOLDER charter, written 2026-11-12 ~01:50Z by a helper of legacy-coordinator-agent
(livespec-dev-tooling-6tgd2z) at the maintainer's direction: "open a new placeholder plan, with everything you just
said, and a reference to this paper as an example of holes we have and are feeling pain from".

- The plan is MAINTAINER-DRIVEN. The maintainer decides direction. A future seat prepares options and a
  recommendation; it does not choose.
- The maintainer is still brainstorming. The plan has no carriers, no children and no seat. Do not file work items
  under it until the maintainer declares the brainstorm done.
- The two sections above this one are provisional. The statement is the maintainer's problem statement, not yet a
  statement of what done means. The assertions were derived by the session, not confirmed by the maintainer. The seat
  that picks this up confirms or replaces both with the maintainer before any carrier map is recorded.
- Everything below is findings and candidates. Nothing below is a decision.

The plan's spine is the fleet's OWN gaps, in the fleet's own terms. The first gap, and the only one worked through
here, is the distributed substrate. Other gaps are added to the list as the maintainer names them.

## The gap list

| # | Gap | State |
|---|-----|-------|
| 1 | Distributed substrate: a shared operational state store, durable addressed messaging with acknowledgement, and a seat and host registry. Credentials are an adjacent authority owned elsewhere. | Worked below. Awaiting the maintainer. |

No other gap is admitted yet. The maintainer adds entries. A session that finds a candidate records it as a finding
on the plan epic, not as a row here.

## Gap 1: the distributed substrate

### The problem, in the maintainer's words

"what we are really missing in this factory is a distributed message bus, and also distributed data store ... That's
biting us on moving the dispatcher, the centralized credential store, communicating sessions across machines, and
other areas." (coordinator session, 2026-11-12, about 01:2xZ to 01:4xZ)

### Three missing primitives and one adjacent authority

This is the coordinator's refinement of that statement, from the same discussion.

**(a) A shared operational state store, reachable from any tailnet host.**

- Today the launcher queue, the holds, the fleet cap, the run records (`tmp/petri-canary` in the orchestrator
  checkout), the per-repo dispatch journals (`tmp/fabro-dispatch-journal.jsonl`) and the preserve records are local
  files on vmi3006760.contaboserver.net.
- That pins the dispatcher to that host.
- The coordinator's tick scripts can only read those files there.
- Rebuilding lost run trees on 2026-11-12 needed ssh plus `fabro dump`, by hand.
- Dolt and git are already shared, but operational state is not in them.
- Dolt has shown load limits: the connection-exhaustion work, and the 2026-11-11/12 backups overrunning their window
  ("The hourly S3 backup of the livespec-dev-tooling tenant fails every run since 2026-11-11T14Z: its live
  DOLT_BACKUP('sync') call is cut at the 300 s listener timeout" (dolt-server-cudtkp)). So the choice of store is a
  real design call. Do not assume Dolt.

**(b) Durable, addressed messaging with acknowledgement (seat inboxes), not fire-and-forget.**

- Today SendMessage is a local socket.
- Seats on the Macs, on gamingpc-xubuntu and in Codex are reached by typing into their herdr panes, or by ledger
  comments that someone must remember to read.
- The resulting "silent seat" stalls are recorded as rules P1 and P3 in `.ai/coordinator-duties.md` §3.
- On 2026-11-12 a cross-session message was "held by the receiving session" because the two sessions' permission
  modes differed.

**(c) A seat and host registry.**

- It holds presence, liveness, context left, current plan and permission mode. Each seat publishes its own entry.
  Nothing is inferred.
- On 2026-11-12 the coordinator missed that the expedited-incident-response-flag seat on chads-macbook-pro was at 10%
  context, because nothing reports a remote seat's state.
- Session liveness is inferred from environment variables on each host. Orphaned gpg-agents carrying
  `CLAUDE_CODE_SESSION_ID` kept dead sessions "live" for weeks and pinned about 2.2 GiB of `/tmp`. That is plan
  dev-host-disk-retention (livespec-dev-tooling-qgwxo4), item "The red-green-replay revert check leaves a gpg-agent
  daemon running per verification after removing its temporary GNUPGHOME" (livespec-dev-tooling-hlyayb).

**(d) Credentials are a separate authority.**

- Issuing and scoping credentials stays with plan central-credential-service (overseer-iyfjbo, in livespec-overseer).
- The substrate only carries rotation and revocation events.
- hetzner-xubuntu-info's accepted design already points this way: per-host sealed bootstraps that assume scoped
  reader roles.

### Measured evidence

Host vmi3006760.contaboserver.net, 2026-11-12 about 01:0xZ. A 30-second `/proc` sample of accounted cores. Accounted
cores undercount, because of hypervisor steal.

| Consumer | Cores |
|----------|-------|
| Claude seat processes | 2.8 |
| A local orchestrator full pytest suite, in worktree `seat-refpush-44995b95` | 1.9 |
| `dispatcher.py` | 0.9 |
| About 19 fabro clients, polling | 0.7 |
| codex | 0.4 |
| herdr | 0.4 |
| chrome | 0.3 |
| Total | 8.1 of 18 |

- `sar` over the prior hour: about 54% user, 28% system, 12.6% idle.
- CPU PSI avg300: about 47.
- Dolt listens only on 127.0.0.1:3307.

### Placement analysis (findings, not decisions)

- **hetzner-xubuntu.** The maintainer's recorded intent (`hetzner-xubuntu-info`, `docs/source-intent.md`) makes
  hetzner-xubuntu the replacement for interactive AI sessions, and explicitly not for the Fabro server or Dolt server
  roles. Seats are the larger CPU share in the sample above, and they are the simpler move.
- **The dispatcher.** It can live on any tailnet host once (a) exists and Dolt is reachable on the tailnet. Exposing
  Dolt on the tailnet is dolt-server's call. It is consistent with the tailnet posture, which is untagged member
  devices only; read `.ai/tailnet-posture.md` before proposing any route. Alternatively, the drains could run as
  cluster pods.
- **gamingpc-xubuntu.** It has 8 cores and 16 threads, 30 GiB of memory, home power and home network, and it is also
  a k3s gates node. It is a poor home for a control plane.

### Relations to other plans

- **radar-and-deterministic-admission (livespec-dev-tooling-w7ley3)** is parked pending the maintainer. It keeps
  admission and consumes the substrate. Its data-store discussion moves here as input. Its charter is
  `plan/radar-and-deterministic-admission/research/001-charter-radar-and-deterministic-admission.md`.
- **dispatch-control-plane (bd-ib-k6dqwc, in livespec-orchestrator-beads-fabro)** stays monitor-only under the
  maintainer's standing limit. Later it is the first consumer to move onto the substrate.
- **central-credential-service (overseer-iyfjbo, in livespec-overseer)** owns credentials.

### Beads as a message bus: the recorded position

The maintainer asked about beads' messaging and ephemeral concepts, and said: "not saying it's a good idea, probably
not, better to use battle hardened something built for a job".

- Beads ephemerals (wisps) are already used lightly, for dispatch claim tokens and plan epoch chains. That is fine.
- Beads is not a message bus here, for three reasons:
  - It is Dolt-backed, so it shares the ledger's load and backup limits.
  - It has no push or subscribe, so using it means polling.
  - It has the `bd` read-surface trap catalogue (see this repository's `CLAUDE.md`).

Candidates for the seat to weigh. This is a list, not a choice:

- NATS with JetStream: durable streams with acknowledgements for inboxes, a key-value store with TTL for presence and
  the registry, and it runs on k3s or on any tailnet host.
- Redis Streams.
- Postgres with LISTEN/NOTIFY.

### Suggested first step, if the maintainer takes this up

This is a recommendation only.

1. Move launcher and journal state into a shared store first. That alone makes the dispatcher placeable, without
   building a bus.
2. Durable seat inboxes come second.

## One outside reference

re:cinq, "Software Factory Map: AI Coding Agent Tools", <https://re-cinq.com/software-factory-map>, read 2026-11-12.

In the maintainer's words: "that paper is just a reference for ONE WAY TO THINK OF FACTORY COMPONENTS. It is not the
only way, nor necessarily should be OUR way". It is cited here as an example of holes the fleet has and feels pain
from. It is not authoritative and it is not adopted. This plan is not organised around its categories, and the fleet
is not scored against it.

Its perspective: it sorts 148 open-source projects and products into 16 components under six things it says every
software factory has to do (orchestration, isolated environments, context and memory, validation, governance,
learning). It is a vendor's map, it features that vendor's own tools throughout, and it says itself that "Listing a
tool is not an endorsement."

A few of its entries may be useful PROMPTS for the fleet's own gap list. They are prompts, not requirements:

- **Event bus** (under orchestration). It lists Postgres-backed queues (pg-boss, Graphile Worker, pgmq, pgflow, River,
  Oban, Solid Queue) and NATS JetStream, which it describes as "Messaging with durable consumers per subscriber".
  This is the nearest entry to gap 1 (b).
- **Workflow engine** (under orchestration). It lists durable engines such as Temporal, Restate, DBOS Transact and
  Hatchet. Durable workflow state is the nearest entry to gap 1 (a), although the paper names no shared operational
  state store as a component.
- **Portal and spend control** (under governance). It lists Backstage, Port and Cortex, and describes Port as having
  an agent catalog. That is the nearest entry to gap 1 (c).

What the paper does not cover, as read: it does not mention seat inboxes, presence, liveness, a registry of seats or
hosts, or credentials and secrets. Gap 1 (c) and gap 1 (d) are the fleet's own, and so is the operational-state half
of gap 1 (a).

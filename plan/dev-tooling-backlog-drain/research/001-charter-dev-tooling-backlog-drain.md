# 001 — Charter: drain the dev-tooling backlog through the factory

Opened 2026-09-06 at the maintainer's direction, in the session that had been
invoked as this repo's `/livespec-overseer:foreman` and was told to stop and
discuss before acting. The maintainer's words, kept verbatim because they are
the intent this plan exists to hold:

> we have a ton of open work items and plans here in this dev-tooling repo.
> And I want to work them all off and close them because I think some of them
> are critical to the stability of the ecosystem. But others may be cruft and
> not actually necessary. And I don't want to have to directly manage all of
> the tmuxes.

> Something has to own the forest, because you LLMs ALWAYS lose the forest
> for the trees.

This plan owns the forest. It is the same-tenant analogue of the console
repo's `retire-overseer-and-redesign-control-plane-around-console` plan: that
plan decided (D1, D4, D5) that tmux is a retired transport, that the resident
LLM foreman role is deleted, and that every foreman capability reduces to an
orchestrator primitive that already exists. This plan applies that decision to
one repository's backlog without waiting for the console to ship. Nothing here
is a new substrate; it is a discipline over primitives that exist today.

## 1. The forest is frozen

`research/002-snapshot-2026-09-06.json` lists every open work item in the
`livespec-dev-tooling` tenant at the moment this plan opened: 258 items, by id,
status, type, priority and title. That list is this plan's scope, whole and
fixed.

- **Exit gate.** The plan is complete when every id in the snapshot is
  `closed`, or carries a recorded disposition (a scope event on this epic
  naming the id and one of the sorting outcomes in §5).
- **Nothing filed after the snapshot extends the plan.** A new item is either
  admitted under §4 or it is out of scope. Inventing an item is not progress
  on anything this plan measures.
- **Status is never written here.** Progress is read fresh from the ledger.
  The snapshot is an id list, not a status board; a status column in a file is
  a shadow ledger (the console program board's rule).

## 2. Roles — there is no foreman

| Role | Who | What it does |
|---|---|---|
| Engine | the orchestrator's dispatcher loop | Takes the `ready` set into fabro runs under `wip_cap`, accepts on green under `acceptance_mode: ai-only`. Exists; needs no seat. |
| Interactive session | one LLM session opened with `discuss-work-item dev-tooling-backlog-drain` | The D4 role from the console charter: triage, rulings with the maintainer, the thin hand-driven set, `needs-attention` reads, re-dispatch, handoffs on this epic. |
| Maintainer | the human | Rules on triage batches; answers the human-gated valves; restarts the interactive session when it dies. |

Dropped for this repository, by reference to console D5: the `foreman` skill
and its pane roster, one-action-per-tick budget, `foreman-act` proposals,
escalation JSON files, heartbeat files, tmux-named worker seats, and the
grooming seat. The `overseerd` daemon may keep running for other repositories;
this plan does not read it and does not write anything it reads.

The interactive session resumes from the ledger alone: this epic's typed
`next_action`, its handoff and scope-event comments, and the `context`
envelope. It needs no chat history and no tmux state.

## 3. Execution rule — everything goes through the factory

The only execution verbs the interactive session may use for a work item are
`drive --action impl:<id>` and the dispatcher loop. A tmux worker session is
never started for a work item.

**Exemption is a closed enum.** An item may be worked by hand, through the
ordinary worktree → PR → merge protocol, only when it is one of:

- `infra-in-person` — the change is a host, secret, registrar, or billing act
  that no sandbox can perform (console D4 item 1).
- `factory-path-defect` — the item IS a defect in the path a factory run takes
  in this repo (the commit hooks, the gate runner, the sandbox image, the
  dispatcher's typed inputs), so a factory run cannot fix it (console D4 item
  3: "the factory cannot fix the thing that blocks the factory").

The classification is made at triage time and recorded in the scope event, not
improvised when a run fails. The default is dispatchable. An exempt item
carries a ledger label naming its reason, `factory-exempt:infra-in-person` or
`factory-exempt:factory-path-defect`, and nothing else counts as an exemption.
A label is the carrier because the orchestrator's `factory-bypass-audit`
already takes `--allow-label` as its exemption policy, so the same label that
authorizes the hand-worked PR is the one the gate in §7 reads. (The
dispatcher's `sandbox_exempt_marker`, `livespec.sandboxExempt`, is a different
thing: a git-config key the commit-refuse hook reads inside the sandbox. It is
not an item-level marker and is not used here.)

**A failed run is re-dispatched or groomed, never hand-fixed.** When a factory
run fails on a dispatchable item, the response is one of: re-dispatch (when
the journal outcome is `transient_infra` or the failure is in the run's own
environment), `groom` (when the item is oversized or non-converging), or a
discovered-during child under §4 (when the failure exposes a factory-path
defect). Hand-fixing a dispatchable item because "it's quicker" is the leak
this rule exists to close.

## 4. Anti-yak-shaving — what may be filed

A new work item may be created in this tenant during this plan only when it
is one of:

1. A **child of an open epic** that is itself in the snapshot.
2. A **discovered-during** defect that blocks a snapshot item, filed with
   `--deps discovered-from:<snapshot-id>` so the provenance is a ledger edge,
   not a sentence.
3. A **consolidation** that closes two or more snapshot items into one.
4. One of the **two mechanical children this plan files for itself** (§7).

Anything else is one line in a `PARKING LOT` comment on this epic and is not
filed. A parked idea is reviewed only when the snapshot is drained or when a
snapshot item turns out to depend on it.

## 5. Triage — the sorting rule and the batches

Every snapshot item receives exactly one disposition from the console program
board's sorting rule:

- **keep** — dispatchable as written; enters the ready set in priority order.
- **re-scope** — the intent survives but the shape does not; the item is
  rewritten (title, acceptance) before dispatch, or handed to `groom`.
- **superseded-by-transport** — the item exists only to serve the tmux /
  overseer transport that console D1 and D5 retire; close with that reason.
- **consolidate** — the item duplicates or fragments another; close into the
  survivor and record the survivor id.
- **close** — the item is cruft: no longer true, already landed, or not worth
  its own cost; close with the reason.

Dispositions are presented to the maintainer in batches grouped by class, not
one item at a time, and recorded as scope events on this epic once ruled. The
closures the ruling authorizes are executed against the ledger with the scope
event named in the close reason. A disposition the interactive session is
confident about is proposed as decided; only genuine doubt is put as a
question, and one question per turn.

## 6. Ordering

After triage, work is dispatched in this order, each tier drained before the
next is opened except where a dependency edge forces otherwise:

1. **Factory-path defects** — anything that makes a factory run in this repo
   fail for reasons unrelated to the item it carries: the Red-Green-Replay
   ritual under pre-commit gates exceeding the implement turn, the green amend
   that cannot commit, the conformance check that intermittently reds every
   PR, the Codex adapter config rejection. These are the `factory-path-defect`
   exemptions and are worked first, by hand where the factory cannot.
2. **Enforcement-suite correctness** — checks that pass vacuously, pass on a
   half-pair, or fail on a true positive. A false green here poisons every
   later tier's evidence.
3. **The P1 epics and their children.**
4. **The long tail** in priority order.

Cross-tenant items — livespec core contract questions, fleet fan-out legs
owned by another repository — follow the console plan's never-work-around
rule: file or link the item in the owning tenant, record the path as a
comment here, and do not substitute a dev-tooling-side workaround.

## 7. Durability — three layers, because prose alone has failed before

The console plan's `never-work-around-upstream-dependencies` note measured
that a rule written in three places was ignored anyway. So:

- **Ledger.** Every ruling is a scope event; every session end is a handoff
  with a typed `next_action`; every closure names its scope event. A fresh
  session recovers the whole state from `context`.
- **Repo prose.** This repository's `CLAUDE.md` names this plan as the owner
  of the backlog, says the `foreman` skill is not to be invoked here, and
  gives the one command that resumes the drive. This is the reminder layer.
  It is the layer that fails alone.
- **Mechanical.** Two children, and only two, filed by this plan for itself
  and built through the factory like anything else:
  1. **Item-provenance ratchet.** A check over the ledger: any item created
     after the snapshot instant must have a `parent` in the snapshot or a
     `discovered-from` edge to a snapshot item, or the check is red. This
     repo already runs a non-increasing ratchet on its lines-of-code soft
     band; the pattern is native.
  2. **Factory-bypass gate.** The orchestrator already ships
     `factory-bypass-audit`, a report-only surface that flags merged PRs
     changing product `.py` outside a factory run. This child consumes it as
     a red gate in this repo, with the exemption enum of §3 as its allow
     policy. It is a consume leg, not a build.

Until both land, the §3 and §4 rules are prose only, and every handoff says
so.

## 8. The loop without panes

The interactive session re-checks three sources on a self-paced wakeup: the
dispatch journal's outcome events, `needs-attention`, and the open pull
requests. It acts on what is ripe and writes nothing when nothing changed.
Healthy waits are silent. A tick report lists what changed, by id, and does
not re-argue standing items.

What survives from the foreman contract is its evidence discipline only:
verify by the authoritative source (`bd show --json`, `gh pr view`, the
journal's `outcome` event), never by a peer's claim; carry a claim's hedge or
re-measure it; route before escalating; state capacity only from a capacity
verdict, and say "unknown" when there is none.

## 9. Known limits

- Nothing here keeps the interactive session alive across a host restart, a
  usage-limit kill, or a context wind-down. The state survives in the ledger;
  a human types the resume command. That is a one-line manual step, the same
  trade the console redesign makes.
- The factory's sandbox quota and implement-turn ceiling will time out
  gate-heavy items until tier 1 lands. That is why tier 1 is first.
- The `factory-bypass-audit` allow-label policy is named here from reading
  its source on 2026-09-06 and has not yet been exercised in this repo. It is
  hedged until the first use measures it.

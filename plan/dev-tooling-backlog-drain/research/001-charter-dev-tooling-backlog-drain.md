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

## 0. The mechanism is the drain-backlog skill — this charter is the delta

**Read the skill first, in full, then this file.** The drive mechanism of this
plan is the `drain-backlog` skill, at the absolute path:

```text
/data/projects/livespec-overseer/.claude/skills/drain-backlog/SKILL.md
```

That skill was generalised FROM this plan's first two days and is now the
authority for everything it covers. It owns, and this charter no longer
restates: the preconditions to measure on every resume (§1), the snapshot and
its exit gate and the four tiers (§2), the triage batches, sorting rule and
ruling record (§3), factory-only execution with a closed exemption enum, the
four-way response to a failed run, and the detached probe-gated engine (§4),
the loop without panes and its three sources (§5), what may be filed during a
drain (§6), handoffs with a typed next action and the resume protocol (§7),
and the evidence-discipline gotchas (§8).

Folded in by the maintainer's direction of 2026-09-08T14:50Z, so this plan is
a ONE-STOP: the skill supplies the mechanism, this charter supplies only what
is true of THIS drive and nothing else. Where the two disagree, the skill wins
on mechanism and this charter wins on scope.

### How this plan binds to the skill's state

The skill is run in its **plan-epic mode** (SKILL.md §0): the operator names
epic `livespec-dev-tooling-kcoslm`, so every ruling is a scope event and every
session end a handoff **on that epic**, not in `tmp/drain-backlog/`. The skill
does not and cannot select that epic; this section is the binding.

Two compatibility facts, both measured 2026-09-08, that a session running the
skill here must not confuse:

- **This plan's frozen scope is `research/002-snapshot-2026-09-06.json`** — 258
  open ids at 2026-09-06T07:45Z, committed — and NOT
  `tmp/drain-backlog/snapshot.json`. That file also exists in this repo (210
  frozen ids, taken 2026-09-06T14:34:43Z) because a SEPARATE actor has run the
  skill against this tenant. It is not this plan's scope and must never be
  treated as it: it is a later, smaller freeze. Run the skill's
  `snapshot.py --status` only against a copy of research/002, or read progress
  from the ledger directly.
- `tmp/drain-backlog/` in this repo therefore holds another actor's engine
  logs and snapshots. `tmp/overseer/`, `.overseer-state` and `.livespec.jsonc`
  are read by this drive as they stand; this plan changes none of them.

## 1. The forest is frozen — this plan's scope, and only this

`research/002-snapshot-2026-09-06.json` lists every open work item in the
`livespec-dev-tooling` tenant at the moment this plan opened: 258 items, by id,
status, type, priority and title. That list is this plan's scope, whole and
fixed. The skill's §2 exit-gate and no-shadow-ledger rules apply to it
verbatim; the only thing this section adds is WHICH file is frozen.

## 2. Roles — there is no foreman

| Role | Who | What it does |
|---|---|---|
| Engine | the orchestrator's dispatcher loop | Takes the `ready` set into fabro runs under `wip_cap`, accepts on green under `acceptance_mode: ai-only`. Exists; needs no seat. |
| Interactive session | one LLM session resumed on this epic | The D4 role from the console charter: triage, rulings with the maintainer, the thin hand-driven set, `needs-attention` reads, re-dispatch, handoffs on this epic. |
| Maintainer | the human | Rules on triage batches; answers the human-gated valves; restarts the interactive session when it dies. |

Dropped for this repository, by reference to console D5: the `foreman` skill
and its pane roster, one-action-per-tick budget, `foreman-act` proposals,
escalation JSON files, heartbeat files, tmux-named worker seats, and the
grooming seat. The `overseerd` daemon may keep running for other repositories;
this plan does not read it and does not write anything it reads.

The interactive session resumes from the ledger alone: this epic's typed
`next_action`, its handoff and scope-event comments, and the `context`
envelope. It needs no chat history and no tmux state.

## 3. Where the skill is WIDER than this charter was

The skill's rules superseded three of this charter's, each in the direction of
MORE permission. Recorded rather than silently adopted, because a drive that
inherits a wider rule without noticing has changed its own scope:

- **The exemption enum gains a third value.** This charter admitted only
  `factory-exempt:infra-in-person` and `factory-exempt:factory-path-defect`.
  SKILL.md §4 adds `factory-exempt:workflow-only` — a diff entirely under
  `.github/workflows/`, which the App token cannot push, retiring when it can.
  Adopted: it names a real mechanical limit this repo hits, and it is the same
  label carrier `factory-bypass-audit --allow-label` already reads.
- **The disposition table gains `refer` and `hold`.** This drive had already
  been using both by ruling (cross-tenant referrals; the four items held on the
  console overseer-freeze scope event). The skill makes them first-class.
- **`superseded-by-transport` is the skill's `superseded`.** Batch 1's closures
  carry the longer reason string; later batches use the skill's name. Same
  disposition, and no closure is reopened over the rename.

## 4. Durability — the two mechanical children, still unfiled

The console plan's `never-work-around-upstream-dependencies` note measured
that a rule written in three places was ignored anyway. The skill (§0, §3, §7)
now carries the ledger and handoff layers. What remains specific to this plan
is the mechanical layer: two children, and only two, filed by this plan for
itself and built through the factory like anything else.

1. **Item-provenance ratchet.** A check over the ledger: any item created
   after the snapshot instant must have a `parent` in the snapshot or a
   `discovered-from` edge to a snapshot item, or the check is red. This repo
   already runs a non-increasing ratchet on its lines-of-code soft band; the
   pattern is native.
2. **Factory-bypass gate.** The orchestrator already ships
   `factory-bypass-audit`, a report-only surface that flags merged PRs
   changing product `.py` outside a factory run. This child consumes it as a
   red gate in this repo, with the exemption enum of SKILL.md §4 as its allow
   policy. It is a consume leg, not a build.

**Until both land, the factory-only and anti-yak-shaving rules are prose only,
and every handoff says so.** Neither is filed as of 2026-09-08.

## 5. Known limits

- Nothing here keeps the interactive session alive across a host restart, a
  usage-limit kill, or a context wind-down. The state survives in the ledger;
  a human types the resume command. That is a one-line manual step, the same
  trade the console redesign makes.
- The factory's sandbox quota and implement-turn ceiling will time out
  gate-heavy items until tier 1 lands. That is why tier 1 is first.
- The `factory-bypass-audit` allow-label policy is named here from reading its
  source on 2026-09-06 and has not yet been exercised in this repo. It is
  hedged until the first use measures it.
- The skill lives in ANOTHER repository's checkout. A path reference is not a
  distribution mechanism: if `/data/projects/livespec-overseer` is absent, this
  plan has no mechanism document. `overseer-exz7` is the item that is making
  the skill plan-completing; whether the skill should also be distributed as a
  plugin skill rather than read by path is not settled here.

## 6. What this charter's earlier revision said, and where it went

The triage-batch documents `003`–`011` cite this charter by its PRE-FOLD
section numbers. They are dated records and are not rewritten; read them
against this map. Old §2 (roles) survives unchanged as §2 above, and old §9
(known limits) as §5 above. For the rest, superseded on 2026-09-08 by the fold
in §0: old §1 →
SKILL.md §2 (the frozen-file binding survives as §1 above); old §3 → SKILL.md
§4; old §4 → SKILL.md §6; old §5 → SKILL.md §3; old §6 → SKILL.md §2 tiers plus
§6's cross-tenant rule; old §7's ledger and prose layers → SKILL.md §0/§3/§7,
its mechanical layer survives as §4 above; old §8 → SKILL.md §5, and its
2026-09-06 amendment (gate the engine on the measured credential probe and
master CI, never on a claimed reset time — `livespec-dev-tooling-kcoslm.1`,
closed) is now SKILL.md §1 and §4.

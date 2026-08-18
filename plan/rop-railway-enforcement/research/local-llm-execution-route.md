# The local-inference execution route (hold lifted, 2026-08-19)

This note records the maintainer decision that restarts this track and the
constraint that decision attaches to it. Item-level state lives on the ledger
epic `livespec-dev-tooling-8o8e` and its children; this note carries only the
route and its measured limits.

## 1. The hold is lifted, and the reason it existed is answered by the route

The 2026-08-04 hold was about **COST, not correctness** — the track was burning
tokens and GitHub runner minutes the fleet is short on. Nothing in the track was
retracted on the merits, so nothing has to be re-derived.

The maintainer lifted it on **2026-08-19** with one binding constraint:

> All work on this track is done **IN SESSION**, via subprocess subagents using
> **free** LLM capacity through the `pi-local-llm` executable on model
> **`m4max/qwen3-coder-next`**. **No Anthropic and no Codex models** are used for
> this track's work.

That answers the *token* half of the hold directly: local inference is free, so
the per-conversion cost that stopped the track goes to zero.

## 2. VERIFIED capability, measured 2026-08-19 — not assumed

`/usr/local/bin/pi-local-llm` → `/data/projects/local-llm/bin/pi-local-llm`.

| property | value |
|---|---|
| provider | `local-llm` |
| model id | `m4max/qwen3-coder-next` |
| context window | **65.5K** |
| max output | **8.2K** |
| thinking mode | **none** |
| smoke test | `-p --no-session` round trip returned `READY`, exit 0 |

The sibling `macmini/qwen3-coder-next` is the same model at **32.8K** context —
half the window. Prefer `m4max`; name the host explicitly, because the two differ
only in the segment before the slash and silently differ in what fits.

Invocation shape that worked:

```sh
pi-local-llm --provider local-llm --model m4max/qwen3-coder-next \
  -p --no-session "<prompt>"
```

## 3. WHAT THE ROUTE COSTS — the constraint that must shape the work cut

**65.5K context and 8.2K output, with no thinking mode, is a small worker.** This
is the single most important planning consequence of the route, and it is not a
detail:

- A unit must fit **the offender function, its imports, its call sites, its test,
  and the railway idiom being applied** inside 65.5K — together with whatever
  instructions the subagent needs. Whole-file rewrites of the larger fleet modules
  will not fit.
- 8.2K output caps a single emitted patch. A conversion touching many sites has to
  be emitted in pieces or driven site-by-site.
- No thinking mode means the model gets no scratch budget. Judgment-heavy calls
  (is this offender a RULED non-conversion? does this contract make the function
  total?) should **not** be delegated blind; the session decides, the worker edits.

**So the cut is: one offender function per subagent call, with a
mechanically-assembled context slice — not "convert this file", and never
"convert this repo".** This is a genuine change to how the 338 sites get worked
compared to the pre-hold assumption of a capable frontier worker per unit.

## 4. WHAT THE ROUTE DOES *NOT* ANSWER — flagged, not solved

**The hold had two cost halves and this route only pays down one.**

1. **GitHub runner minutes are untouched.** Local inference makes generating a
   conversion free; it does nothing about the CI a PR triggers. The reproduced
   contention finding in `legacy-handoff-2026-08-04.md` still stands — a
   dev-tooling PR opened while a fleet sweep is in flight recreates the
   contention, and the budget gate is a BUDGET gate, not an inter-run mutex. If
   this track lands ~338 conversions as ~338 PRs, the runner half of the original
   cost problem returns at full strength regardless of which model wrote the code.
   **Batching conversions per repo is the obvious lever and it is not yet decided.**
2. **The `8zv3` blocker is a correctness-of-sequencing issue, not a cost one, and
   it is untouched by a cheaper worker.** `livespec-dev-tooling-8o8e` is `blocks`-
   dependent on `livespec-dev-tooling-8zv3` in the ledger. Until `8zv3` lands, the
   ROP check **scans zero files in all nine repos** (measured 2026-08-04:
   dev-tooling exits 0 with `role_key_spelling=not_applicable`; livespec exits 0
   with `unarmed_until=livespec-mutreal.1` despite 15 known offenders). Every
   conversion landed before `8zv3` is enforced by **nothing** and can regress
   silently. **A free worker converting into an unarmed check still produces an
   unratcheted result.**

**Consequence for sequencing: `8zv3` — the `pure_trees` role-key decoupling — is
the first unit, not a conversion.** It is also a small, judgment-dense change,
which is the shape that fits a 65.5K worker worst; expect the session to do the
deciding and the local worker to do the editing.

## 5. Route-vs-factory: this track is factory-INELIGIBLE by decision

The Planning Lane's default for implementation work is the factory route — the
`drive` operation (`impl:<id>`) or a Dispatcher drain. **This track is explicitly
recorded factory-ineligible**, because the factory dispatches paid frontier
capacity and the maintainer's constraint forbids exactly that for this track. The
in-session local-subagent route is the recorded exception, and it applies to this
track only.

## 6. Preserved state that survives the hold

- `~/.worktrees/livespec/fix-spec-governance-config-railway` holds an authored,
  **uncommitted** `livespec` Red. **It must not be reaped** — reaping destroys
  authored work. Every other worktree on the host is a peer lane.
- `livespec-dev-tooling-8o8e.30` and `.31` were filed just before the hold and
  remain the maintainer's to keep, retitle, fold in, or close. `.30`: the check
  gates its scan on `pure_trees` while the ratified rule binds ANY first-party
  Python. `.31`: every `.7`–`.13` count is measured over
  `resolve_check_universe()`, not the universe the shipped check scans.
- The quotable fleet figures, all from the 2026-08-02 re-measure at each member's
  recorded master SHA: **432 raw · 429** less dev-tooling's 3 ruled non-conversions
  · **338** distinct sites less overseer's 91 mechanically-enforced mirror copies.
  Say which one you are quoting. A part and a total from different days do not add.

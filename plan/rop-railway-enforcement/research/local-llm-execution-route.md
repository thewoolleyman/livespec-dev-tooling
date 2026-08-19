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
> ⛔ **§4 ITEM 2 BELOW IS CORRECTED BY `state-correction-2026-08-19.md`. READ THAT FIRST.**
> `8zv3.1/.2/.3` are CLOSED; the decoupling LANDED (`46c5dab`), turned five fleet repos'
> master CI red, and was REVERTED (`f4247110`). The conclusion drawn below — defer
> conversions because the check is unarmed — is BACKWARDS: arming ahead of adoption is
> the move already proven to break the fleet, so conversions are the critical path, not
> the blocked half. The 2.8x `_`-file-skip decision (`8zv3.5`) is what actually gates them.

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

## 7. PILOT, 2026-08-19 — the route was TESTED against ground truth, not assumed

A route this plan depends on should not be recorded on a smoke test alone. The
model was given the **pre-conversion** `_read_root_mapping` from
`research/8o8e21-green.patch` — a real offender from this very track, whose
known-good conversion is in that patch — plus the railway idiom and the one
judgment call (absent file is an ANSWER; unparseable file and non-object root are
FAILURES). Its output was compared against the merged gold standard.

### ✅ What it got RIGHT — the hard part

**The railway semantics were exactly correct**, matching the merged conversion
track-for-track: absent file → `IOSuccess({})`, `JsoncFailure` → `IOFailure(...)`
carrying `parsed.detail`, non-object root → `IOFailure(...)`, happy path →
`IOSuccess(...)`, and a frozen dataclass for the failure payload. It placed the
success/failure cut on exactly the boundary the gold standard placed it on. **The
judgment this track is actually about is within the model's reach.**

### ⛔ What it got WRONG — all of it mechanical, and all of it gate-visible

| deviation | consequence |
|---|---|
| wrapped output in ```` ```python ```` fences despite an explicit instruction not to | not directly appliable; needs unwrapping |
| dropped `cast("dict[str, Any]", parsed)` | strict typing gate fails |
| `@dataclass(frozen=True)` — omitted `kw_only=True` | repo convention violation |
| re-declared `_LIVESPEC_CONFIG` and re-emitted imports it was told already exist | context-blind boilerplate to strip |
| invented `_ReadRootMappingFailure` rather than a shared failure type | per-function type explosion across 338 sites |
| added an unused `returns.primitives.hkt.SupportsKind1` import | lint fails |
| trailing whitespace on in-function blank lines; dropped the docstring | format/docstring gates fail |

### ▶️ THE CONCLUSION THAT SHOULD SHAPE THE HARNESS

**The model is a competent railway REASONER and an unreliable patch EMITTER.** So
the route is viable, but *not* as "local model writes the patch, session applies
it." It needs a harness around it:

1. The session assembles the context slice and **names the shared failure type**
   up front — do not let each call invent one, or 338 conversions produce 338
   bespoke failure dataclasses.
2. The model proposes the conversion.
3. A **deterministic** post-process strips fences and duplicate imports.
4. The repo's own gates (ruff, format, typing, docstring) are the acceptance
   oracle — never the model's self-report. Every deviation above is gate-visible,
   which is the good news: none of them can reach master silently.
5. Only the RGR ritual's Red→Green pair proves the conversion behaves.

**Do not delegate the "is this a RULED non-conversion?" or "is this function total
by contract?" calls.** Those are the `8o8e.28`/`.30`-class judgments; the pilot
tested the model on a conversion whose cut was handed to it, and that is not
evidence it can find the cut itself.

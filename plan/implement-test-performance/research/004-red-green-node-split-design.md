# 004 — Design: Red and Green as separate nodes, commits as model-free nodes (2026-11-01)

Carries DoD assertions 7 and 8 (added 2026-11-01 under the maintainer's absorption ruling) and the factory half of
assertions 2 and 6. Sources: research notes 001-002 of this plan; plan token-spend-analysis notes 007 §4.4 and 008
(transferred here 2026-11-01, epic livespec-dev-tooling-6lv7ze scope event 03:07Z); the orchestrator's
`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro` and `workflow.toml` at master 2026-11-01.

## Problem, restated from the measurements

- One `implement` ACP node (timeout 1800 s, `max_visits=3`) does the whole Red→Green ritual AND makes both commits.
  78-92% of every turn is the agent polling a commit hook or suite run; the Green amend alone is 5-17 min.
- Turn boundaries fall wherever the agent stops. The engine then makes a run-branch checkpoint commit with hooks
  skipped (`[run.checkpoint] skip_git_hooks = true`, f8340c7ae, 2026-10-12), which commits whatever was staged:
  the Red test splits from its implementation and a refused commit disappears before `implement_hook_route` looks.
- `implement_commit_settle`, `implement_hook_route` and the commit runner (4b1cd7632, 2b2c55a9d, 2c9f905e1,
  02ee84386) exist to reconstruct, after the fact, what a commit started inside a turn did. They are patches on the
  in-turn commit, not a design.

## Target graph

```
dod_gate → dod_gate_mutation_guard
  → red            (ACP)    write the failing test; run ONLY that test; write handoff; NO commit
  → commit_red     (script) git add <test>; git commit — hook: Red leg (staged test must fail) + static members
        ├ refused → red         (refusal appended to the handoff; bounded by red.max_visits)
        └ ok      → green
  → green          (ACP)    implement; run targeted tests only; NO commit; may declare "test is wrong"
        ├ test-wrong → red      (reason appended to the handoff; bounded)
        └ done    → commit_green
  → commit_green   (script) fold trailing checkpoint commits; git add; git commit --amend — hook: Green leg
                            + whole suite with coverage ONCE (fail-fast: staged tests + static first, bd-ib-v3iw35)
        ├ refused → green       (failed targets + error tail appended to the handoff; bounded)
        └ ok      → implementation_diff → janitor → … (unchanged)
```

- **No agent turn makes a commit.** Both commits happen in `shape=parallelogram` script nodes, which spend no
  model tokens while the hook runs and whose exit code IS the verdict — no settle, no live-commit record, no
  reconstruction. Assertion 8.
- **Turn boundaries coincide with ritual boundaries.** `red` ends before any commit exists; `green` ends before the
  amend. A checkpoint after either sees an uncommitted tree that the next script node owns, never a half-done commit.
- **The maintainer's test-scope rule falls out of the shape.** `red`/`green` run only changed tests (the brief
  already says so after factory-context-per-turn-reduction's PR); `commit_green` runs the whole suite once before
  the commit is final. Assertion 2.
- **Test independence.** `green` cannot change the Red test: `red_green_replay` already requires byte-identical
  test files across Red→Green. The measured lever in note 008 is "implementer cannot edit tests"; this keeps it.

## The handoff file

`$GIT_DIR/livespec-implement-handoff.md` — inside the git dir, so no checkpoint commit can carry it into the
branch (the same placement `implement_completion` uses for its record). APPEND-ONLY: each node and each refusal
adds a dated section; nothing is rewritten. Reasons: (1) re-entry laps (`commit_green → green`) keep a stable
prefix, so the provider prompt cache stays warm and nothing earlier is re-read as new; (2) the file is an audit
trail of the run's laps.

Sections, in order:
1. `red`: test path; spec clause / DoD assertion it proves; the run command and its failure output; what the test
   verifies and deliberately does not (10-20 lines); the seams found (`path:line`) so `green` does not re-explore.
2. `commit_red`: verdict, commit sha, or the refusal tail.
3. `green`: what changed; targeted tests run; or a `test-wrong` declaration with its reason.
4. `commit_green`: failing phase (staged/static vs whole suite), failed targets, last 80 lines of error output.

The `green` prompt reads only the DoD, the handoff and the code; it never sees the `red` transcript (separate ACP
session per node). Assertion 7.

## What it replaces and what it keeps

| Today | After the split |
|---|---|
| `implement` (one ACP node) | `red` + `green` (two ACP nodes) |
| commit runner + `implement_commit_settle` + live-commit record | removed for implement: commits are script nodes |
| `implement_hook_route` re-entry budget (1) | per-edge laps bounded by `max_visits` on `red`/`green`/`commit_*` |
| `implement_completion` field | kept on `green` (a turn can still stop partway); `red` needs no field — `commit_red`'s exit code decides |
| checkpoint fold (fix B, sandbox-commit-gate-ceiling) | becomes the first step of `commit_green` (empty or machine checkpoint commits on top of the Red commit are folded before the amend) — B is a building block, not throwaway |
| fix D (bd-ib-jzuryr) | stopgap only; retired with the in-turn commit path |

`fix` and `review_fix` keep their own in-turn commit paths in this design; extending the same pattern to them is
deferred until the implement split is measured (reconsidered at the 20-dispatch window, assertion 6).

## Risks and how the design bounds them

1. **Wrong Red test, Green cannot edit it** (~1 in 10 agent tests wrong, note 008). Bounded by the `green → red`
   `test-wrong` edge; `red.max_visits` caps the ping-pong; an exhausted cap ends at `needs_human` naming both
   sides' handoff sections.
2. **Green re-orientation cost.** Partly paid by the seams section of the handoff. Measured, not assumed:
   per-response input and total tokens per run, before/after, from the existing Honeycomb factory spans.
3. **Checkpoint behaviour after a script node** is UNVERIFIED (note 002 inferred it from engine code). First
   design step: a probe run on the petri factory reading `fabro events` for checkpoint records around a script
   node that leaves a clean tree and one that leaves a dirty tree.
4. **ACP session per node.** Fresh session per node is the expected engine behaviour (the `fidelity` attribute
   governs what carries across); verify in the same probe that `green` starts without `red`'s transcript.
5. **Spec.** The orchestrator spec ratifies the current shape (contracts.md §"Self-contained plugin dispatch" →
   "An implement turn that ends incomplete does not succeed", Scenario 204 v165/v208/v214). The split needs a
   propose-change + revise in livespec-orchestrator-beads-fabro before implementation children are dispatched.

## Sequence

1. Probe (risks 3-4) — host-side, this plan session, petri factory.
2. Propose-change in livespec-orchestrator-beads-fabro: the split workflow shape, the handoff contract, Scenario 204
   rewritten for `red`/`commit_red`/`green`/`commit_green`. Revise under the orchestrator's delegated decision mode.
3. File implementation children (orchestrator tenant) through capture-work-item once the bootstrap release lands:
   (a) handoff file contract + `red`/`green` prompts; (b) `commit_red`/`commit_green` script nodes with fold and
   fail-fast; (c) graph rewiring + retirement of the implement commit runner path.
4. Measure over 20 dispatches (assertion 6) and per-response input before/after.

# 002 — Regression verdict: did the automated commit regress? (2026-11-01)

Answers DoD assertion 1 and the first half of assertion 5. Read-only research by two subagents of the plan session;
their scripts and CI samples are in the session scratchpad
(`/tmp/claude-1000/-data-projects-livespec-dev-tooling/e4e28b2c-3876-4848-b6d6-e74833ea2652/scratchpad/`).

## Verdict

**Partly.** The commit path did not get worse at turning a finished Red→Green into a commit. Three things changed:

1. **A real design defect, dated 2026-10-12, surfaced by later changes.** Orchestrator `f8340c7ae` (10-12,
   `skip_git_hooks = true`) made the engine's between-node checkpoint commits run with `--no-verify`. Before it, a
   checkpoint of an unfinished tree ran the pre-commit aggregate and killed the run as `workflow_error` (27 hp runs
   10-09..10-12, 15 on coverage; `plan/checkpoint-commit-hook-failures/research/001-…` in the orchestrator repo).
   After it, the checkpoint silently commits whatever the turn left, with no TDD trailers. That is the origin of
   both symptoms the coordinator measured: the Red test split from its implementation, and staged work swallowed
   into a commit so the re-entry route (`5abc90469` 10-24, `5cab31e42` 10-25: `git diff --cached` then
   `git hook run pre-commit` over the staged tree) finds nothing refused. The re-entry design never accounted for
   the 10-12 checkpoint change. Settle (`2b2c55a9d`, 10-28) reads only RUNNING commit records, so a FAILED runner
   verdict never reaches the route either. Owned by seat sandbox-commit-gate-ceiling (fixes D = bd-ib-jzuryr, B =
   fold checkpoint commits back into the index); external carriers for assertion 6.
2. **Visibility, not new failures.** Before `6a55ff0e9` (10-20) an incomplete turn was recorded SUCCEEDED and the
   run continued to janitor / publish_draft / proof_capture / fix (example: run 01M58QNY3ZNM2YCVVB9G2383M0,
   bd-ib-davaxq, 10-19, "Partial progress only", died later at the fix ceiling). `6a55ff0e9` added the
   `implement_completion` gate and the code LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS; REENTRY_BUDGET_EXHAUSTED arrived
   with `5cab31e42`. **"Zero before 10-19" is not evidence of a regression: neither code existed before 10-20.**
   No broken landings were found (post-merge janitor reds 5, 12, 3, 3 across the four periods below).
3. **The hook got slower because the suite grew, not because the hook changed.** See "Gate cost" below.

## Dispatch-journal evidence (orchestrator tenant, `tmp/fabro-dispatch-journal.jsonl` calibration records)

| Period | green | blocked |
|---|---|---|
| Oct 1–11 | 63/215 | 94/215 |
| Oct 12–19 | 96/394 | 176/394 |
| Oct 20–26 | 69/202 | 80/202 |
| Oct 27 on | 92/231 | 76/231 |

Outcomes did not worsen after 10-20: the two new codes replaced checkpoint `workflow_error` deaths (15, 11, 1, 0
across the periods) and later-stage deaths. Red-without-Green on green runs: 2/63, 9/96, 5/69, 10/92 — the
10-12 split was already present and landing through the suite-green leg. The 41 implement needs-human endings
10-01..10-19 were agent-raised DoD amendments (e.g. bd-ib-vim5gc, run 01M55DV3CX61A3MMEP5NJNP6FW), none partial
progress.

**Strongest correlate of the new endings is the implementer adapter.** Since 10-20: codex-acp 43/284 (15%) end
partial-progress or re-entry-exhausted, claude-acp 14/330 (4%). Spikes on Codex-first days (10-26 5/52, 10-27
19/116, 10-31 10/59); 10-29, all Claude, 0/51. Routing commits 8b79488e3 (10-24), a03cbeb0d (10-25), 182415ed7
(10-28), f07fd0dce (10-30). Confounded with the hp→petri factory moves and host load; not yet isolated.

## Gate cost: what runs at each hook today (orchestrator, dev-tooling pin v1.140.3)

- **pre-commit** → `check-pre-commit`, branched on the staged shape:
  - Red (one test, no impl): the ~94-member aggregate minus the coverage members; NO full suite. 45 s–3 min.
  - **Green amend: the full aggregate including `check-per-file-coverage` = whole suite under
    `pytest -n $(nproc/4) --cov --cov-branch`.** This is the 5–17 min sandbox cost.
- **commit-msg** → `red_green_replay`: Red and Green legs run the staged test file only; the suite-green leg runs the
  full suite (`-n nproc/4` since dev-tooling `bd2e9b16`, 10-28 — it got cheaper).
- **pre-push** → `check-pre-push`: green-token match runs only world-reading members; otherwise the delegated
  cluster Job if enabled and the host holds the gates kubeconfig, else the full local aggregate.

Hook commands are unchanged since August (suite-green leg since dev-tooling `a11feb86`, 06-11; orchestrator
`just-check-pre-commit.sh` shape since `8c5ef8dbe`, 08-04). No xdist / coverage / collection setting changed in
October.

**The test-only rule is ratified but unimplemented**: dev-tooling spec v102 (`2761741d`, 10-30) says a test-only
commit runs only its staged tests; `_handle_suite_green_mode` still always runs the full suite; carrier
livespec-dev-tooling-h3gcs6 is BLOCKED on a deterministic ModuleNotFoundError stage failure.

## Suite growth

`def test_` count: orchestrator 1979 (08-01) → 4429 (10-01) → 7453 (10-15) → 9419 (10-22) → 11112 (11-01), most of it
in `tests/livespec_orchestrator_beads_fabro/commands` (3239 → 8208). dev-tooling 2305 → 4052 → 5339 over the same
span. CI per-file-coverage job median, orchestrator: 117 s (W36), 150 s (W40), 274 s (W42), 325 s (W44) — 2.2x since
Oct 1. dev-tooling: 133 s → 171 s.

## What this means for the fix

- The Green amend is where the whole suite runs today, and it is ALSO where the maintainer wants the one whole-suite
  run. So "changed tests on Red/Green, whole suite once before final" is: keep exactly one whole-suite-with-coverage
  run per final tree (the Green amend's, or the suite-green leg's — not both), and make every other test run in the
  turn targeted. Today a Green amend can run the whole suite TWICE: per-file coverage in pre-commit, then the
  suite-green leg in commit-msg on the next plain commit. To verify per path before the scoping event.
- Suite growth (2.5x in October) is the dominant cost driver; assertion 4 needs suite-speed work (serial tail:
  collection, coverage combine, per-file coverage; `-n 4` averages ~2.4 cores) and possibly test-count hygiene.
- The checkpoint/route defect is the dominant FAILURE driver and is owned elsewhere (sandbox-commit-gate-ceiling).
- The adapter correlation needs isolating before it is attributed.

## Not proven

- How often turns ended incomplete before 10-20 (recorded SUCCEEDED then; would need per-run `fabro events`).
- That the checkpoint runs between `implement` and the settle/route nodes in an actual traced run (inferred from
  engine code and the 10-12 research).
- That settle filters on RUNNING only (taken from the coordinator's brief; not re-read).
- The Codex effect versus the factory moves and load.

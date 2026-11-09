---
topic: an-in-turn-sandbox-commit-runs-affected-tests
author: claude-opus-5-5
created_at: 2026-11-09T02:29:10Z
---

## Proposal: An in-turn factory-sandbox commit runs its suite-green leg over the affected tests its pre-commit gate recorded

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add to §"Suite-green replay leg" an affected-tests scope for a behaviour-preserving commit made inside a factory sandbox, identified by the sandbox-exemption marker `livespec.sandboxExempt`. That scope applies only when the same commit's pre-commit hook recorded a passing affected-tests gate run, over a non-empty test selection, on exactly the tree being committed. The leg then runs only the recorded test paths and records `TDD-Suite-Green-Scope: affected-tests`. A new livespec-dev-tooling entry point writes the record. The record is kept apart from full-aggregate evidence, so it can never produce a `full-suite` trailer. Every other case, including every host commit, keeps the full suite exactly as the Scope bullet states today. Two scenarios state the narrowed case and its fallbacks.

### Motivation

Orchestrator Scenario 255 (bd-ib-72hvx5, and bd-ib-fde4ie for fix turns) routes the pre-commit hook of a commit made inside an implement, fix or review_fix turn to the affected-tests gate (`just check-changed`), and keeps one full check aggregate per run at the janitor stage before publication. That removes the full AGGREGATE from in-turn commits, but not the commit-msg suite-green leg. Read from livespec-dev-tooling 1.188.1 as pinned in the orchestrator (seat sandbox-commit-gate-ceiling, comment on bd-ib-fde4ie, 2026-11-09T02:22:51Z): a commit that stages product `.py` with no Red awaiting a Green runs the suite-green leg at scope `full-suite` (`red_green_replay.py` branch 5, `_red_green_replay_suite.py` `_handle_suite_green_mode`). Only same-tree evidence from a passing FULL aggregate skips it, and a scoped run must never write that evidence, because the evidence asserts that a full aggregate passed. So every in-turn commit still runs the whole ~14,000-test suite once more: 1079-1286 s each on 2026-11-06, and 1960-3860 s under load on 2026-11-07. Factory wall cuts plus redo were about 19.6% of 72 h of factory spend (legacy-coordinator-agent, 2026-11-09), and this is the remaining piece of that largest bucket.

The ratified **Scope** bullet requires the FULL suite for every behaviour-preserving commit, so narrowing the leg is a spec change, not a conformance fix. The narrowing is safe only where something else judges the final tree. In a factory run, the janitor's single full aggregate does that before publication (orchestrator Scenario 255), and the pull request's CI runs the full suite again. An in-turn commit's tree is an intermediate tree. Gating on the sandbox-exemption marker keeps every host commit, in every fleet repository, on the full suite. Plan implement-test-performance (epic livespec-dev-tooling-sv6m5p) files this for its assertions 2 and 6. Work item livespec-dev-tooling-svjqbe carries it.

Alignment: this aligns with the pending proposal a-consumer-whose-pre-commit (livespec-dev-tooling-4scqti). It builds on that proposal's one-entry-point shape for pre-commit evidence, adds the scoped record beside that proposal's full-aggregate evidence, and changes none of its text.

### Proposed Changes

Three edits. The **Scope** bullet gains one cross-reference clause. Nothing else in existing text changes.

**1. `SPECIFICATION/contracts.md`, `## Suite-green replay leg`, **Scope** bullet.** Replace its first sentence

> A behaviour-preserving commit, one that stages product `.py` with no Red awaiting a Green, MUST run the FULL pytest suite against the staged tree, and MUST record `TDD-Suite-Green-Scope: full-suite`.

with

> A behaviour-preserving commit, one that stages product `.py` with no Red awaiting a Green, MUST run the FULL pytest suite against the staged tree, and MUST record `TDD-Suite-Green-Scope: full-suite`, except where the **Affected-tests scope in a factory sandbox** bullet applies.

**2. `SPECIFICATION/contracts.md`, `## Suite-green replay leg`.** Insert this bullet immediately after the **Same-tree reuse** bullet. If the **Local-aggregate evidence entry point** bullet of proposal a-consumer-whose-pre-commit has been ratified by then, insert it immediately after that bullet instead.

> - **Affected-tests scope in a factory sandbox.** A behaviour-preserving commit made in a checkout whose git config sets the sandbox-exemption marker `livespec.sandboxExempt` to `true` MUST run only the test paths recorded by a passing affected-tests gate run, and MUST record `TDD-Suite-Green-Scope: affected-tests` with trailers naming that run, when every one of these holds: the same commit's pre-commit hook recorded that run through the affected-tests record entry point below; the run exited `0`; it recorded at least one selected test path; and the tree it recorded is exactly the tree `git write-tree` names for the index when the commit-msg hook runs. In every other case the leg MUST run its suite exactly as the **Scope** bullet states. Those cases are: the marker is absent or not `true`; no record exists; the run did not pass; the run recorded no test path; the trees differ; or the leg cannot read the record. livespec-dev-tooling MUST provide one affected-tests record entry point. A consumer's `check-pre-commit` recipe runs it with the affected-tests gate command and the test paths that gate selected. The entry point MUST run that command, MUST exit with the command's own exit status, and MUST record the tree `git write-tree` named before the run, the run's outcome and the selected test paths. The record MUST be distinct from the pre-commit evidence that the **Same-tree reuse** bullet consumes. That bullet MUST NOT read the record, the entry point MUST NOT write full-aggregate evidence, and the leg MUST NOT record `TDD-Suite-Green-Scope: full-suite` on the strength of the record. The commit-range validation MUST accept a commit whose suite-green trailers record `affected-tests` as verified, as it accepts `staged-tests`. This scope is sound only because the run's final tree is judged in full elsewhere: once by the factory's full check aggregate before publication, and again by the pull request's CI. A consumer whose factory does not run a full aggregate on the final tree before publication SHOULD NOT call the entry point. This bullet is spec-first: as of ratification the shipped leg runs the full suite for every behaviour-preserving commit that has no full-aggregate evidence. Work item livespec-dev-tooling-svjqbe owns the change.

**3. `SPECIFICATION/scenarios.md`.** Add these two scenarios immediately after `## Scenario: a suite-green leg runs the full suite when the pre-commit aggregate judged a different tree or ran partially`, or after the last scenario that proposal a-consumer-whose-pre-commit adds there, if it has been ratified by then. They add two `## ` headings, so the revise MUST co-edit `tests/heading-coverage.json` with a `test: "TODO"` row for each, naming the integration tier in `reason` and livespec-dev-tooling-svjqbe as `work_item`, and MUST regenerate `tests/heading-coverage-debt.json`.

```
## Scenario: an in-turn sandbox commit whose affected-tests gate passed on the same tree runs only those tests

Given a checkout whose git config sets `livespec.sandboxExempt` to `true`

And a behaviour-preserving commit whose pre-commit hook ran the affected-tests gate through livespec-dev-tooling's affected-tests record entry point, which recorded exit `0`, the selected test paths `tests/test_alpha.py` and `tests/test_beta.py`, and tree `T`

And `git write-tree` names tree `T` for the index when the commit-msg hook runs

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST run only `tests/test_alpha.py` and `tests/test_beta.py`, and MUST NOT run the full suite

And on pytest exit `0` it MUST record `TDD-Suite-Green-Scope: affected-tests` with trailers naming the recorded gate run

And it MUST NOT record `TDD-Suite-Green-Scope: full-suite`

## Scenario: an affected-tests record outside a sandbox, or for a failed, empty or different run, leaves the full suite in place

Given a behaviour-preserving commit whose pre-commit hook recorded an affected-tests gate run through livespec-dev-tooling's affected-tests record entry point

And at least one of these holds: the checkout's git config does not set `livespec.sandboxExempt` to `true`; the recorded run exited non-zero; the recorded run selected no test path; or the recorded tree differs from the tree `git write-tree` names for the index when the commit-msg hook runs

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST run the full suite

And on pytest exit `0` it MUST record `TDD-Suite-Green-Scope: full-suite`
```


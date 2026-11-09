---
topic: rule-26-kill-matrix-engine
author: claude-opus-5-5
created_at: 2026-11-09T10:52:06Z
---

## Proposal: The kill-matrix engine is pure code, runs mutants in parallel, and records unapplied mutants instead of aborting

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Revise the 'Mutants and attribution' and 'Report format' bullets of 'Rule-26 mutation kill matrix' as follows. The engine computes the matrix with no language-model call. It may run mutants in parallel across a configurable worker count, provided a parallel run's report equals a single-worker run's. It records each selected test's own kill outcome even when a mutant's selected tests share one process or forked worker. A mutant the engine cannot apply is recorded as unapplied and excluded, never allowed to abort the run.

### Motivation

Maintainer ruling 2026-11-09, attended, recorded as a plan-scope-event on epic livespec-dev-tooling-oi2two: the matrix generation 'Runs without the need for LLMs, pure code (i.e. doesn't burn tokens' and 'Is optimized to be fast - parallelize'. The shipped engine applies one mutant at a time and starts one pytest process per selected test. A probe on livespec-orchestrator-beads-fabro's effects/ subpackage generated 1,372 mutants from 1,725 lines, which extrapolates to about 165,000 mutants for the package: weeks of runtime. Separately, on 2026-11-09 mutmut 3.2.3 could not apply some class-method mutants (for example a dunder __init__ on an exception class) in livespec-runtime, and the shipped engine aborted the whole run on the first one. Carrier work item: livespec-dev-tooling-dkgwsm.

### Proposed Changes

In SPECIFICATION/contracts.md, section '## Rule-26 mutation kill matrix':

1. Append to the 'Mutants and attribution' bullet: "The engine MUST compute the kill matrix with no call to a language model; only the mutation engine, the test runner and coverage measurement participate. The engine MAY run mutants in parallel across a configurable worker count, and a parallel run MUST produce a report whose mutants, killers, surviving mutants and redundancy candidates equal those of a single-worker run of the same source revision. The engine MAY run all of one mutant's selected tests in a single process or forked worker, and it MUST still record each selected test's own kill outcome. A mutant the engine cannot apply MUST be recorded as unapplied; it MUST NOT abort the run, and it MUST be excluded from the killed, surviving and redundancy computations."

2. Append to the 'Report format' bullet: "The report MUST also carry the list of unapplied mutants and the worker count the run used."

In SPECIFICATION/scenarios.md, add after '## Scenario: a coverage-guided kill-matrix run skips tests that do not execute a mutant':

## Scenario: a parallel kill-matrix run reports the same matrix as a single-worker run

Given a fixture package and its test suite at one source revision
When the kill-matrix engine runs over it once with one worker and once with several workers
Then both reports MUST list the same mutants, the same killing tests for every mutant, the same surviving mutants and the same redundancy candidates
And neither run MUST call a language model

## Scenario: a mutant the engine cannot apply is recorded and the run continues

Given a fixture package with one mutant that the mutation engine cannot apply
When the kill-matrix engine runs over it
Then the run MUST complete and write its report
And the report MUST list that mutant as unapplied
And that mutant MUST appear in neither the surviving mutants nor any test's kills

## Proposal: Kill-matrix runs build up results incrementally and report what changed since the previous run

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an 'Incremental runs' bullet to 'Rule-26 mutation kill matrix'. The engine may keep a result cache keyed by each mutated function's source and its covering tests' files. A later run re-tests only the mutants whose function or covering tests changed and reuses the cached outcomes for the rest. Given a previous report, the engine writes a what-changed summary of newly redundant tests and newly surviving mutants.

### Motivation

Maintainer ruling 2026-11-09 (same scope event): the matrix 'can be run repeatedly and give periodic answers of which tests can be killed' and should 'build up date over multiple runs if that helps'. At fleet scale only the first full run can afford to test every mutant; later runs must cost in proportion to what changed, and the answer the maintainer wants each time is which tests have newly become removable. Carrier work item: livespec-dev-tooling-dkgwsm.

### Proposed Changes

In SPECIFICATION/contracts.md, section '## Rule-26 mutation kill matrix', add after the 'Report format' bullet:

"- **Incremental runs.** The engine MAY keep a result cache keyed by each mutated function's source text and the content of the test files that cover it. When a cache is present, a run MUST re-test only the mutants whose mutated function or covering test files changed since the cached run, and it MUST reuse the cached kill outcomes for every other mutant. The report MUST state whether the run was incremental and how many mutants it reused. Given a previous report, the engine MUST write a what-changed summary that lists the tests that are redundancy candidates now but were not in the previous report, and the mutants that survive now but did not survive in the previous report."

In SPECIFICATION/scenarios.md, add:

## Scenario: an unchanged package is not re-tested on a second kill-matrix run

Given a kill-matrix run over a fixture package that wrote its report and result cache
When the engine runs over the same unchanged package again with that cache
Then the second run MUST re-test no mutant
And its report MUST equal the first run's report apart from the run metadata
And the report MUST state that the run was incremental and reused every mutant

## Scenario: a changed function re-tests only its own mutants

Given a kill-matrix run over a fixture package that wrote its report and result cache
And one function of the package then changes while its covering tests do not
When the engine runs over the package again with that cache
Then it MUST re-test only the mutants located in the changed function
And it MUST reuse the cached outcomes of every other mutant

## Scenario: a kill-matrix run reports newly redundant tests since the previous report

Given a previous kill-matrix report over a fixture package
And a test that was the only killer of a mutant in that report is then joined by a second test that kills the same mutant
When the engine runs again with the previous report
Then its what-changed summary MUST list the first test as a newly redundant candidate

## Proposal: The kill-matrix recipe may also run from a scheduled, non-gating, advisory job

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Revise the 'Recipe' bullet of 'Rule-26 mutation kill matrix' so the recipe may run on demand or from a scheduled job that gates nothing, is required by nothing, and produces advisory output. It keeps every existing exclusion: not a member of the just check aggregate, not run from any commit-time or push-time hook, and not a required per-PR CI job. The keep-out guard and the Advisory-only bullet are unchanged.

### Motivation

Maintainer ruling 2026-11-09 (same scope event): the matrix 'can be run repeatedly and give periodic answers of which tests can be killed'. Today's Recipe bullet says the recipe MUST be on demand only, which forbids the periodic run the maintainer asked for. The exclusions that keep mutation testing out of every gate stay exactly as they are, because plan assertion A5 requires the just check aggregate's wall-clock not to grow. Carrier work item: livespec-dev-tooling-dkgwsm.

### Proposed Changes

In SPECIFICATION/contracts.md, section '## Rule-26 mutation kill matrix', 'Recipe' bullet, replace the sentence "The recipe MUST be on demand only: it MUST NOT be a member of the `just check` aggregate, MUST NOT run from any commit-time or push-time hook, and MUST NOT be a required per-PR CI job." with:

"The recipe MUST run only on demand or from a scheduled job whose result gates nothing and is advisory. It MUST NOT be a member of the `just check` aggregate, MUST NOT run from any commit-time or push-time hook, and MUST NOT be a required per-PR CI job. A scheduled run MUST write the same report, and the same what-changed summary when a previous report exists, as an on-demand run."

In SPECIFICATION/scenarios.md, add:

## Scenario: a scheduled kill-matrix run writes its report without gating anything

Given an adopting repository with a scheduled, non-gating kill-matrix job
When the schedule fires
Then the job MUST write a fresh kill-matrix report and, when a previous report exists, its what-changed summary
And the job's outcome MUST NOT block any merge, commit or push

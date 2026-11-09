---
topic: range-replay-verifies-a-suite-green-commit-s-behaviour-preservin
author: claude-opus-5-5 (sandbox-commit-gate-ceiling plan session)
created_at: 2026-11-09T11:36:06Z
---

## Proposal: Alternative A: a suite-green commit that adds a test function beside a product change is not behaviour-preserving (static discriminator)

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Stop the commit-range validation from accepting a `TDD-Suite-Green-*` trailer as proof that a commit preserved behaviour, and judge the claim from the commit's own diff. A commit that changes product `.py`, adds at least one new `test_*` function, and carries no `TDD-Red-*` trailers is treated as adding behaviour. The range validation refuses it, and the commit-msg suite-green leg refuses to stamp it. This alternative and Alternative B are mutually exclusive. The revise MUST accept at most one of them.

### Motivation

contracts.md §"Suite-green replay leg" defines a behaviour-preserving commit only as one that "stages product `.py` with no Red awaiting a Green", and says the commit-range validation "accepts" the `TDD-Suite-Green-*` trailers "as the commit's verification evidence". Nothing checks the claim the trailer makes.

Measured 2026-11-09 on livespec-orchestrator-beads-fabro PR #4733 (work item bd-ib-tckulg, factory run 01M6ZHWSQGPHZTK0GW3S03BF9G). A fix turn that was resolving a refresh conflict committed while a rebase was still stopped. The result was commit 9e77e7b02: a single-parent commit with no subject and no `TDD-Red-*` or `TDD-Green-*` trailers, carrying a whole new feature. It touched 10 paths, +1400/-46, and added the new test modules `test_dispatcher_failed_jobs_rerun.py` and `test_dispatcher_failed_jobs_merge.py`. The settle hook's suite-green leg stamped `TDD-Suite-Green-*` on it, and CI `check-red-green-replay` passed it. The flattening that produced the commit is owned and fixed elsewhere (orchestrator bd-ib-yzrguu). This proposal closes the gate that let the result through as a pass. Work item: livespec-dev-tooling-5uobsl. legacy-coordinator-agent ruled that tightening this gate is additive and that it decides the revise outcome under R301.

Alignment: this proposal ALIGNS with the pending proposals an-in-turn-sandbox-commit-runs-affected-tests and a-consumer-whose-pre-commit. Those change WHAT the suite-green leg runs and how its evidence is recorded or reused. This proposal changes WHETHER a commit qualifies for the leg. An affected-tests scope makes a suite-green stamp weaker evidence still, which is a further reason to bound which commits may carry one.

### Proposed Changes

In SPECIFICATION/contracts.md §"Suite-green replay leg":

1. In the opening paragraph, replace "which the commit-range validation accepts as the commit's verification evidence" with "which the commit-range validation accepts as the commit's verification evidence only for a commit that is behaviour-preserving under the **Behaviour-preserving claim** bullet".

2. Add a new bullet after **Scope.**:

- **Behaviour-preserving claim.** A commit that changes a product `.py` file AND adds at least one new `test_*` function, which is a test function absent from the commit's parent, adds behaviour. It is not behaviour-preserving. The commit-msg suite-green leg MUST refuse to record `TDD-Suite-Green-*` trailers on such a staged change, whatever its suite result. Its refusal event MUST name each added test function and MUST tell the committer to take the Red-then-Green route. The commit-range validation (`check-red-green-replay`) MUST refuse any commit in its range that changes a product `.py` file, adds a new `test_*` function and carries no `TDD-Red-*` trailers. This holds even when the commit carries `TDD-Suite-Green-*` trailers. Its failure MUST name the commit and each added test function. A commit that changes product `.py` and adds no new test function MUST be judged exactly as before this bullet. A commit carrying both `TDD-Red-*` and `TDD-Green-*` trailers MUST be judged exactly as before this bullet. A test function counts as added when its fully qualified name, module path plus function name, is absent from the parent tree. A renamed or moved test therefore counts as added. That is the accepted cost of a check that reads only the diff.

In SPECIFICATION/scenarios.md, add:

## Scenario: the range replay refuses a suite-green commit that adds a test beside a product change

Given a commit that changes a product `.py` file, adds a new `test_*` function and carries `TDD-Suite-Green-*` trailers but no `TDD-Red-*` trailers
When `check-red-green-replay` validates a range containing that commit
Then the check fails
And its failure names the commit and the added test function

Given a commit that changes a product `.py` file, adds no test function and carries `TDD-Suite-Green-*` trailers
When `check-red-green-replay` validates a range containing that commit
Then the check passes that commit

The revise that accepts this proposal MUST co-edit `tests/heading-coverage.json` with an entry for the new scenario heading. The `test` value MAY be `"TODO"` with a non-empty reason that names livespec-dev-tooling-5uobsl.

Trade-off against Alternative B: A is a pure diff read, with no test run, constant cost and no new failure mode at commit time. It is coarse in two ways. It refuses a genuine refactor that adds characterization tests, which must then take the Red-then-Green route although nothing went red. It also passes a feature commit that adds behaviour without adding a test function.

## Proposal: Alternative B: a suite-green commit whose added or changed tests fail on its parent is not behaviour-preserving (parent-tree replay)

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Stop the commit-range validation from accepting a `TDD-Suite-Green-*` trailer as proof that a commit preserved behaviour, and test the claim. Every test module a commit adds or changes is run against the commit's PARENT tree. If any of those tests fails there, the commit added or changed behaviour the parent did not have. In other words, it carries a Red it never recorded. The range validation refuses it, and the commit-msg suite-green leg refuses to stamp it. This alternative and Alternative A are mutually exclusive. The revise MUST accept at most one of them.

### Motivation

The defect and the measured instance are the same as Alternative A's. contracts.md §"Suite-green replay leg" accepts the `TDD-Suite-Green-*` trailer as verification evidence without checking its behaviour-preserving claim. Orchestrator PR #4733's commit 9e77e7b02 added a whole feature (+1400/-46, new test modules) under suite-green trailers alone, and passed `check-red-green-replay`. Work item: livespec-dev-tooling-5uobsl.

legacy-coordinator-agent asked for a sharper discriminator than "adds a test_* function". Its example was "the commit's diff adds or changes a public behavior a pre-existing test does not exercise". This alternative makes that example mechanical. The commit's own tests define the behaviour it asserts. If those tests already pass on the parent, the asserted behaviour pre-existed and the commit preserved it. If they fail on the parent, the commit introduced behaviour, and that is exactly the Red the pair shape exists to record.

Alignment: this proposal ALIGNS with the pending proposals an-in-turn-sandbox-commit-runs-affected-tests and a-consumer-whose-pre-commit, for the same reason Alternative A does.

### Proposed Changes

In SPECIFICATION/contracts.md §"Suite-green replay leg":

1. In the opening paragraph, replace "which the commit-range validation accepts as the commit's verification evidence" with "which the commit-range validation accepts as the commit's verification evidence only for a commit that is behaviour-preserving under the **Behaviour-preserving claim** bullet".

2. Add a new bullet after **Scope.**:

- **Behaviour-preserving claim.** A commit's claimed tests are the `test_*.py` modules it adds or changes. A commit that changes a product `.py` file is behaviour-preserving only when every claimed test passes when run against the commit's PARENT tree, with the commit's own version of each claimed test module placed into that tree. A commit with no claimed tests is behaviour-preserving by this bullet. Its full-suite run under **Scope.** is its whole evidence, as before. The commit-msg suite-green leg MUST run the claimed tests against the parent tree before it records `TDD-Suite-Green-*` trailers. When any claimed test fails there, the leg MUST refuse the commit with an event that names each test failing on the parent and tells the committer to take the Red-then-Green route. When the claimed tests pass on the parent, the leg MUST record a `TDD-Suite-Green-Parent-Replay` trailer naming the claimed test modules, or `none`. The commit-range validation (`check-red-green-replay`) MUST refuse any commit in its range that changes a product `.py` file, carries `TDD-Suite-Green-*` trailers and no `TDD-Red-*` trailers, and either lacks a `TDD-Suite-Green-Parent-Replay` trailer or has claimed tests that fail on its parent tree when replayed. Its failure MUST name the commit and each failing test. A commit carrying both `TDD-Red-*` and `TDD-Green-*` trailers MUST be judged exactly as before this bullet. The parent-tree replay MUST obey the same progress bound and failure-detail rules as the leg's own suite run.

In SPECIFICATION/scenarios.md, add:

## Scenario: the range replay refuses a suite-green commit whose added tests fail on its parent

Given a commit that changes a product `.py` file, adds a test that fails when run against the commit's parent tree, and carries `TDD-Suite-Green-*` trailers but no `TDD-Red-*` trailers
When `check-red-green-replay` validates a range containing that commit
Then the check fails
And its failure names the commit and the test that fails on the parent

Given a commit that changes a product `.py` file, adds characterization tests that pass on its parent tree, and carries `TDD-Suite-Green-*` trailers with a `TDD-Suite-Green-Parent-Replay` trailer
When `check-red-green-replay` validates a range containing that commit
Then the check passes that commit

The revise that accepts this proposal MUST co-edit `tests/heading-coverage.json` with an entry for the new scenario heading. The `test` value MAY be `"TODO"` with a non-empty reason that names livespec-dev-tooling-5uobsl.

Trade-off against Alternative A: B judges behaviour, not diff shape. A refactor with new characterization tests passes, because those tests pass on the parent, and a feature commit whose new tests are red on the parent is refused. It also catches a commit that CHANGES an existing test to assert new behaviour. Its costs: a second, targeted test run per suite-green commit, at commit time and in CI range validation. A new trailer to carry. And one blind spot it shares with A: a feature commit that adds behaviour and no test is not caught, because its full-suite green stays its only evidence.

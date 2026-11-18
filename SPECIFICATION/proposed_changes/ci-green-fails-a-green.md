---
topic: ci-green-fails-a-green
author: claude-opus-5-5
created_at: 2026-11-13T17:54:05Z
---

## Proposal: ci-green re-reads a needed leg GitHub still lists as unfinished

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

ci-green MUST read its run's jobs again, within a stated bound, when a leg it needs is listed as queued or in_progress after its own needs: completed, and MUST fail closed only when the leg is still unfinished after the bound, naming the leg, its last status and the reads it made.

### Motivation

Measured 2026-11-13 on livespec-dev-tooling#4533 (livespec-dev-tooling-xdt4ue), CI run 43474313091. check-check-coverage-incremental completed success at 17:44:16Z and check-coverage at 17:44:22Z. ci-green (job 132058996068) started at 17:44:24Z, read both as `status in_progress, conclusion none` and failed a fully green run whose incident-ci and check-red-green-replay had passed. The forge-call rule (contracts.md:1179-1183) retries only an unusable answer; a usable answer carrying an unsettled status is not covered, so one stale listing decides the required check. Under coordinator-duties section 2 a job is not re-run for this, so the cost is a whole PR re-trigger. Work item livespec-dev-tooling-g734nf.

### Proposed Changes

In SPECIFICATION/contracts.md §"Expedited incident execution", after the paragraph that ends "...and `ci-green`'s read of its run's jobs fails `ci-green` closed." (the forge-call failure paragraph, today contracts.md:1183), add:

> A `ci-green` read of its own run's jobs that returns an answer MUST NOT decide a needed leg from a status GitHub has not yet settled. GitHub's job listing is eventually consistent, so a leg that finished seconds before `ci-green` started can still be listed as `queued` or `in_progress`. When `ci-green`'s own `needs:` has completed and a leg it needs is listed as `queued` or `in_progress`, `ci-green` MUST read its run's jobs again. It MUST make at most five such reads, each a full forge call under the rule above, waiting 2 seconds before the second read and doubling the wait before each further read (2, 4, 8, 16). It MUST decide on the first read in which every needed leg has a conclusion. When a needed leg is still listed as `queued` or `in_progress` after the fifth read, `ci-green` MUST fail closed, naming each such leg, the status it was last listed with, and the number of reads it made. These re-reads are not retries of an unusable answer: they read a usable answer again because its state had not settled, and they do not count against a call's six attempts.

In SPECIFICATION/scenarios.md, add:

## Scenario: ci-green re-reads a needed leg GitHub lists as unfinished after it completed

```gherkin
Given a pull request run whose `check-coverage` job completed with success at 17:44:22Z
And ci-green starts at 17:44:24Z after every job it needs has completed
And GitHub's first answer to ci-green's read of its run's jobs lists `check-coverage` as `in_progress` with no conclusion
And GitHub's second answer lists `check-coverage` as `completed` with conclusion `success`
When ci-green decides the run
Then ci-green MUST read its run's jobs a second time after waiting 2 seconds
And ci-green MUST pass when every other needed leg succeeded
And when GitHub lists `check-coverage` as `in_progress` in all five reads, ci-green MUST fail closed, naming `check-coverage`, the status `in_progress` and the five reads it made
```

## Proposal: ci-green decides each needed leg from every attempt of its run

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

ci-green MUST read its run's jobs across all attempts and take each needed leg from the newest attempt that holds it, so a re-run of ci-green alone decides on the legs an earlier attempt completed; a leg no attempt holds MUST fail ci-green closed by name.

### Motivation

Measured 2026-11-13 on livespec-dev-tooling#4533 (livespec-dev-tooling-xdt4ue), CI run 43474313091. After the stale read above, the coordinator allowed one re-run of the ci-green job alone. That made attempt 2, which holds only ci-green, and ci-green (job 132060862857) read only that attempt. It failed with `required leg check-types: never created in this run`, and the same for check-lint, check-format, check-check-coverage-incremental and incident-ci, although attempt 1 had completed all of them with success. A ci-green-only re-run therefore can structurally never pass. Work item livespec-dev-tooling-g734nf.

### Proposed Changes

In SPECIFICATION/contracts.md §"Expedited incident execution", directly after the paragraph Proposal 1 adds, add:

> `ci-green` MUST decide each leg it needs from every attempt of its run, not only the latest attempt. GitHub creates a new attempt of a run when one of its jobs is re-run, and that attempt holds only the re-run jobs. For each needed leg, `ci-green` MUST take that leg's job from the newest attempt that holds one, and MUST read the run's jobs across all of its attempts. A leg that no attempt of the run holds MUST fail `ci-green` closed, naming the leg as never created in the run. A re-run of `ci-green` alone therefore decides on the legs its earlier attempts completed.

In SPECIFICATION/scenarios.md, add:

## Scenario: a re-run of ci-green alone decides on the legs an earlier attempt completed

```gherkin
Given a pull request run whose first attempt completed `check-types`, `check-lint`, `check-format`, `check-check-coverage-incremental` and `incident-ci`, each with success
And ci-green failed in that first attempt
When only the ci-green job is re-run, so the run's second attempt holds ci-green alone
Then ci-green MUST read its run's jobs across both attempts
And ci-green MUST take each needed leg from the first attempt, the newest attempt that holds it, and MUST pass
And when a needed leg is held by no attempt of the run, ci-green MUST fail closed, naming that leg as never created in the run
```

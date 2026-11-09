---
topic: job-creation-server-error-rerun
author: claude-opus-5-5:ci-runtime-and-cost
created_at: 2026-11-09T20:03:40Z
---

## Proposal: A fleet CI run that GitHub fails at job creation with an Internal server error is re-run with incremental backoff, at most three times, by the reusable reconciler

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend §"Hooks and CI" of non-functional-requirements.md with a third pre-code infrastructure re-run signature, beside the Set up job 429 rule (v124) and the Initialize containers rule (v171). A gating CI run that GitHub fails at job creation, with an `Internal server error` annotation, zero or only some jobs created and no created job failed, is re-run with an incremental backoff of 2, 5 and 10 minutes, at most three times. Every other failure stays the run's verdict. Add one sentence to the reconciler's contract in contracts.md so it classifies a run by its own annotations, because a run with zero jobs has no failed job to classify. Add the scenario that exercises the new signature.

### Motivation

livespec-dev-tooling-ybnep5 realizes this behaviour, and no ratified text states it, so its dispatch would be held at the spec-change tier. This proposal gives it a topic of its own, distinct from a-ci-job-that-fails (cetyrq, v124) and initialize-containers-registry-rerun (khlrw3, v171). Measured case: from 17:53Z to 18:59:32Z on 2026-11-09, during the githubstatus incident "Incident with Actions and Checks API" (Actions major_outage), livespec-orchestrator-beads-fabro master runs 42669034432, 42672913004 and 42674043026, plus root-uid run 42673614368, failed with GitHub's "Internal server error. Correlation ID ..." annotation at job creation. Zero or only some jobs were created, no test ran, and seats diagnosed and re-ran them by hand. The maintainer ruled on 2026-11-09 at about 19:3xZ (recorded on epic livespec-dev-tooling-6tgd2z and plan epic livespec-dev-tooling-ib3oe3): "Yes, why wouldn't we? As long as it's an incremental backoff, so we don't spam it or waste tokens or unnecessarily hammer github". The signature is pre-code by construction: no created job failed, so a re-run can never retry a test or build failure, which is the flaky-test lever the fleet forbids. Placement: the re-run policy is a contributor concern, so it goes in non-functional-requirements.md beside the other two signatures. The reconciler's classification surface is a wire contract other repositories call by path, so its one-sentence extension goes in contracts.md.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Hooks and CI", append this paragraph directly after the paragraph that begins "A gating CI job of a fleet repository that adopts the CI infrastructure re-run reconciler" (the Initialize containers rule, v171):

> A gating CI run of a fleet repository that adopts the CI infrastructure re-run reconciler and that GitHub fails at job creation MUST be re-run automatically, with an incremental backoff, up to three times. A run is failed at job creation when a run annotation reads `Internal server error`, the run created zero jobs or only some of its jobs, and no created job failed. The reconciler MUST wait 2 minutes before the first re-run, 5 minutes before the second and 10 minutes before the third. A run in which any created job failed, a run with no such annotation, and a run already re-run three times for this cause MUST NOT be re-run by this mechanism, and its failure MUST stay the run's verdict. Each such re-run MUST write the run id, the attempt number and the matched annotation line to the reconciler's own run summary, and each run the reconciler leaves after the third re-run MUST be recorded in that summary as left for its owner. The summary line is the occurrence record, so a matched re-run owes no per-occurrence flake work item.

In `SPECIFICATION/contracts.md` §"Reusable workflows wire contract", in the paragraph that begins "The CI infrastructure re-run reconciler is specified ahead of its realization" (v171), insert this sentence directly after the sentence ending "and it leaves every other failure as the run's verdict.":

> It also classifies a run that created zero jobs or only some of its jobs against the run's own annotations, and re-runs the whole run, after the wait non-functional-requirements.md §"Hooks and CI" names, when they match a run-level re-run signature that section names.

In `SPECIFICATION/scenarios.md`, add this scenario directly after `## Scenario: a CI job killed at Initialize containers by a registry network error is re-run once`:

```markdown
## Scenario: a CI run GitHub fails at job creation with an Internal server error is re-run with backoff

Given a gating CI run of a fleet repository whose caller workflow calls `reusable-ci-infra-rerun.yml`

And GitHub created none of the run's jobs, or only some of them, and no created job failed

And a run annotation reads `Internal server error`

When the run completes

Then the reconciler MUST re-run the run after 2 minutes, a second time after 5 minutes and a third time after 10 minutes, while each attempt fails the same way

And it MUST write the run id, the attempt number and the matched annotation line to its own run summary for each re-run

And a fourth failure of the same run at job creation MUST NOT be re-run, and the summary MUST record it as left for its owner

And a run in which any created job failed MUST NOT be re-run by this mechanism, and its failure MUST stay the run's verdict
```

The revise that ratifies this proposal MUST add the new scenario heading to `tests/heading-coverage.json`, with its owning work item livespec-dev-tooling-ybnep5, and register it in the heading-coverage debt register.

This proposal must be revised after v171, because it anchors on text v171 adds.

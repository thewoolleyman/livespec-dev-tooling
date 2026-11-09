---
topic: initialize-containers-registry-rerun
author: claude-opus-5-5:ci-runtime-and-cost
created_at: 2026-11-09T18:17:15Z
---

## Proposal: A CI job that fails at Initialize containers on a registry network error is re-run once, fleet-wide, by a reusable reconciler

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend §"Hooks and CI" of non-functional-requirements.md, beside the ratified Set up job action-download 429 rule, with a second pre-code infrastructure signature. A gating CI job that fails at its `Initialize containers` step on a container-registry network error, before any later step starts, is re-run automatically once. Every other failure stays the run's verdict. Add the reconciler that realizes both signatures to §"Reusable workflows wire contract" of contracts.md as `reusable-ci-infra-rerun.yml`, which any fleet repository adopts through one thin caller workflow. Add the scenario that exercises the new signature.

### Motivation

livespec-dev-tooling-khlrw3 realizes this behaviour, and its dispatch is held at the spec-change tier because no ratified text states it. Its recorded linked topic, `a-ci-job-that-fails`, was derived from the first words of its title. That topic is already ratified at v124, but for livespec-dev-tooling-cetyrq's different Set up job codeload-429 rule, so the hold can never clear by re-judgement alone. This proposal gives khlrw3 a distinct topic to relink to. Measured case: on 2026-11-09 livespec-orchestrator-beads-fabro master CI run 42551212496 (8792b7c9, 02:29:21Z) failed check-metadata-batch at `Initialize containers`. On a GitHub-hosted runner, the job-container pull of ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v1.187.0 failed three times in about 13 s with `connection reset by peer`. No test ran, and the coordinator re-ran it by hand. Over about 64 h (2026-11-06T10:37Z to 2026-11-09T02:5xZ), the orchestrator's 412 CI runs had 2 container-init failures on first attempts: this hosted registry reset, and one k3s `Pod ... is unhealthy` failure, which is a different class this rule leaves alone. The maintainer ruled on 2026-11-09 at about 09:1xZ (recorded on plan epic livespec-dev-tooling-ib3oe3): the re-run is APPROVED as an extension of the fleet's no-rerun rule. It ships in the same reusable reconciler workflow as cetyrq's 429 re-run, and the reconciler's summary line, not a per-occurrence flake item, is the record. The signature is pre-code by construction: `Initialize containers` runs before checkout, so a re-run here can never retry a test or build failure, which is the flaky-test lever the fleet forbids. Placement: the re-run policy is a contributor concern, so it goes in non-functional-requirements.md beside the 429 rule. The reusable workflow is a wire contract other repositories call by path, so it goes in contracts.md.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Hooks and CI", append this paragraph directly after the paragraph that begins "A gating CI job of this repository that fails at its runner's `Set up job` step":

> A gating CI job of a fleet repository that adopts the CI infrastructure re-run reconciler (contracts.md §"Reusable workflows wire contract", `reusable-ci-infra-rerun.yml`) and that fails at its `Initialize containers` step, before any later step starts, with a container-registry network error in that step's log MUST be re-run automatically once. The registry network errors are `connection reset by peer`, `i/o timeout`, `TLS handshake timeout`, or an HTTP 5xx answer from the container registry. The reconciler MUST start the re-run within 5 minutes of the failed run completing. A job that fails at any later step, a container failure that carries no registry network error (such as a workflow pod reported unhealthy), and a job already re-run once for this cause MUST NOT be re-run by this mechanism, and its failure MUST stay the run's verdict. Each such re-run MUST write the run id, the job id and the matched error line to the reconciler's own run summary. Each failure the reconciler leaves MUST be recorded in that summary as left for its owner. The summary line is the occurrence record, so a matched re-run owes no per-occurrence flake work item.

In `SPECIFICATION/contracts.md` §"Reusable workflows wire contract", append this entry to the list that follows "The library MUST ship at minimum one reusable workflow:", after the `reusable-check-matrix.yml` entry:

> - **`reusable-ci-infra-rerun.yml`**. The CI infrastructure re-run reconciler. Trigger: `workflow_call`, from a caller workflow that a `workflow_run` `completed` event of the calling repository's gating CI workflow starts. Inputs: `run_id` (the completed run to reconcile). The caller MUST grant `actions: write`. Behaviour: it classifies every failed job of that run and re-runs only a job whose failure matches a re-run signature that non-functional-requirements.md §"Hooks and CI" names, and it leaves every other failure as the run's verdict. Outputs: the number of jobs re-run and the number left. A fleet repository MUST adopt it through one caller workflow that carries no classification logic of its own, and a second repository MUST be able to adopt it with the same caller file unchanged apart from its name.

In `SPECIFICATION/scenarios.md`, add this scenario directly after `## Scenario: a CI job killed at Set up job by an action-download 429 is re-run with backoff`:

```markdown
## Scenario: a CI job killed at Initialize containers by a registry network error is re-run once

Given a gating CI job of a fleet repository whose caller workflow calls `reusable-ci-infra-rerun.yml`

And the job failed at its `Initialize containers` step before any later step started

And that step's log shows the container registry pull failing with `connection reset by peer`

When the job's workflow run completes

Then the reconciler MUST re-run that job once, within 5 minutes

And it MUST write the run id, the job id and the matched error line to its own run summary

And a second failure of the same job at `Initialize containers` MUST NOT be re-run, and its failure MUST stay the run's verdict

And a job that failed at a later step, or at `Initialize containers` with no registry network error, MUST NOT be re-run, and the summary MUST record it as left for its owner
```

The revise that ratifies this proposal MUST add the new scenario heading to `tests/heading-coverage.json`, with its owning work item livespec-dev-tooling-khlrw3, and register it in the heading-coverage debt register.

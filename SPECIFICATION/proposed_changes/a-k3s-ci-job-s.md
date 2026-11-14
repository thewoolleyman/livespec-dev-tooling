---
topic: a-k3s-ci-job-s
author: claude-opus-5-5
created_at: 2026-11-14T03:52:01Z
---

## Proposal: A uv package-download failure in a CI job's dependency-install step is re-run once by the infra re-run reconciler

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds a fourth trigger to the CI infrastructure re-run reconciler: a gating CI job that fails at the run step that runs `uv sync`, before any later step starts, with uv's `Failed to download` caused by a timeout, a connection reset or an HTTP 5xx from the package index, is re-run once; a second such failure and every other run-step failure stay the run's verdict. Adds the matching scenario.

### Motivation

livespec-dev-tooling-qeou2e. livespec-dev-tooling master run 43532626286 (job check-per-file-coverage 132254404989, k3s runner pod) failed in `uv sync --all-groups` before any test ran: `Failed to download coverage==7.14.0 ... Request failed after 5 retries ... operation timed out` from files.pythonhosted.org. That one run made 3 of the 4 not-green master merges since 2026-11-13 19:42Z. The ratified reconciler covers only a `Set up job` action-download 429 or not-found, an `Initialize containers` registry network error and a job-creation failure, so a package-index transport failure inside a run step is never re-run and a transient network fault becomes master's verdict.

### Proposed Changes

In `non-functional-requirements.md` §"Hooks and CI", after the paragraph on the `Initialize containers` registry network error, insert:

A gating CI job of a fleet repository that adopts the CI infrastructure re-run reconciler and that fails at the run step that runs `uv sync`, before any later step starts, with a package-download failure in that step's log MUST be re-run automatically once. A package-download failure is uv's `Failed to download` for a package, whose cause in the same error is an operation that timed out, a connection reset, or an HTTP 5xx answer from the package index. The reconciler MUST start the re-run within 5 minutes of the failed run completing. A job that fails at any later step (a test failure after a successful install included), a failure of that step with no package-download failure in its log (such as a dependency resolution error), and a job already re-run once for this cause MUST NOT be re-run by this mechanism, and its failure MUST stay the run's verdict. Each such re-run MUST write the run id, the job id and the matched error line to the reconciler's own run summary, and each failure the reconciler leaves MUST be recorded in that summary as left for its owner. The summary line is the occurrence record, so a matched re-run owes no per-occurrence flake work item.

In `scenarios.md`, after §"Scenario: a CI job killed at Initialize containers by a registry network error is re-run once", add:

## Scenario: a CI job whose uv sync fails to download a package is re-run once

Given a gating CI job of a fleet repository whose caller workflow calls `reusable-ci-infra-rerun.yml`

And the job failed at the run step that runs `uv sync`, before any later step started

And that step's log shows uv's `Failed to download` for a package ending in `operation timed out`

When the job's workflow run completes

Then the reconciler MUST re-run that job once, within 5 minutes

And it MUST write the run id, the job id and the matched error line to its own run summary

And a second failure of the same job at that step MUST NOT be re-run, and its failure MUST stay the run's verdict

And a job that failed at a later step, or at that step with no package-download failure, MUST NOT be re-run, and the summary MUST record it as left for its owner

## Proposal: This repository's CI keys its uv download settings on the runner labels each job runs on

### Target specification files

- SPECIFICATION/constraints.md

### Summary

Requires this repository's `ci.yml` to resolve `UV_CONCURRENT_DOWNLOADS` and `UV_HTTP_TIMEOUT` per job from the runner labels that job itself runs on: the self-hosted values (4 and 60) on self-hosted capacity and the hosted values (50 and 30) on GitHub-hosted capacity.

### Motivation

livespec-dev-tooling-qeou2e. `ci.yml` sets both variables at workflow level from `CI_RUNNER_LABELS` alone. In this repository that variable is `["ubuntu-latest"]` while the coverage jobs route to the k3s pool through `CI_COVERAGE_RUNNER_LABELS` and master pushes through `CI_RUNNER_LABELS_MASTER`, so k3s jobs get the hosted values: 50 concurrent fetches and a 30 s timeout, the uplink-contention shape the self-hosted values exist to prevent (livespec-s43svm.13, .31). In the failing job all 5 retries spent about 4 s in total.

### Proposed Changes

In `constraints.md` §"CI matrix shape", after the paragraph on routing through `CI_RUNNER_LABELS`, insert:

Each job of this repository's `ci.yml` that runs `uv sync` MUST resolve `UV_CONCURRENT_DOWNLOADS` and `UV_HTTP_TIMEOUT` from the runner labels that job itself runs on, read through the same variables and inline hosted literal as that job's `runs-on`. A job that runs on self-hosted capacity MUST resolve them to `4` and `60`, and a job that runs on GitHub-hosted capacity MUST resolve them to `50` and `30`. A job MUST NOT take these values from a routing variable its own `runs-on` does not read, so a job routed to self-hosted capacity through `CI_COVERAGE_RUNNER_LABELS`, `CI_RUNNER_LABELS_MASTER` or a priority variable gets the self-hosted values while `CI_RUNNER_LABELS` names hosted capacity.

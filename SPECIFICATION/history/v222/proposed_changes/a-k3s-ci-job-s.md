---
topic: a-k3s-ci-job-s
author: claude-opus-5-5
created_at: 2026-11-14T03:52:01Z
---

## Proposal: This repository's CI sets its uv download settings from whether each job's runner is self-hosted or hosted

### Target specification files

SPECIFICATION/constraints.md
SPECIFICATION/scenarios.md

### Summary

Requires each step of this repository's `ci.yml` that runs `uv sync` to take `UV_CONCURRENT_DOWNLOADS` and `UV_HTTP_TIMEOUT` from whether the runner executing it is self-hosted or GitHub-hosted, rather than from the `CI_RUNNER_LABELS` variable at workflow level. Self-hosted steps get the capped pair that `ci.yml` declares, and hosted steps get uv's own defaults. The workflow-level entries are removed, and a test keeps every copy in step. Adds the matching scenario.

### Motivation

livespec-dev-tooling-qeou2e. `ci.yml` sets both variables at workflow level from `contains(vars.CI_RUNNER_LABELS || '["ubuntu-latest"]', 'ubuntu')`. In this repository `CI_RUNNER_LABELS` is `["ubuntu-latest"]`, while the coverage jobs route to the k3s pool through `CI_COVERAGE_RUNNER_LABELS` and master pushes route there through `CI_RUNNER_LABELS_MASTER`. So k3s jobs run with the hosted values: 50 concurrent downloads per job, the shape that contends for the node's shared uplink and that the self-hosted cap exists to prevent (livespec-s43svm.13, .31). Master run 43532626286, job check-per-file-coverage 132254404989 on a k3s runner pod, failed in `uv sync --all-groups` with `Failed to download coverage==7.14.0 ... Request failed after 5 retries ... operation timed out`. All 5 retries took about 4 s in total, so these were fast failures under contention, not a slow transfer running into the 30 s timeout. That one run made 3 of the 4 not-green master merges since 2026-11-13 19:42Z. The fix is to give each job the settings for the runner it actually runs on. The runner context exposes no labels, and ARC scale-set runners register with none, so the job's runner kind (`runner.environment`) is the reliable key. An automatic re-run of such a failure was considered and is deliberately left out: the fault is caused by our own settings, so a re-run would hide it. A re-run is reconsidered only if a measured residual of these failures remains after this fix is live.

### Proposed Changes

In `constraints.md` §"CI matrix shape", after the paragraph on routing through `CI_RUNNER_LABELS`, insert:

Each step of this repository's `ci.yml` that runs `uv sync` MUST set `UV_CONCURRENT_DOWNLOADS` and `UV_HTTP_TIMEOUT` in its own `env` from the kind of runner executing it, read from `runner.environment`. On a self-hosted runner each MUST resolve to the capped value that `ci.yml` declares for self-hosted capacity, and every such step MUST resolve to the same capped pair. On a GitHub-hosted runner each MUST resolve to uv's own default. `ci.yml` MUST NOT set either variable at workflow level or at job level, so that no step takes them from a routing variable its own job's `runs-on` does not read. A test MUST fail, naming the workflow file and the step, when a `ci.yml` step that runs `uv sync` does not set both variables from `runner.environment`, when two such steps resolve to different self-hosted values, or when either variable is set at workflow or job level.

In `scenarios.md`, after §"Scenario: a CI job killed at Initialize containers by a registry network error is re-run once", add:

## Scenario: a CI job routed to self-hosted capacity runs uv sync with the self-hosted download cap

Given livespec-dev-tooling's `CI_RUNNER_LABELS` names GitHub-hosted capacity

And a `ci.yml` job routes to the self-hosted pool through `CI_COVERAGE_RUNNER_LABELS` or `CI_RUNNER_LABELS_MASTER`

When that job's step that runs `uv sync` executes on a self-hosted runner

Then `UV_CONCURRENT_DOWNLOADS` and `UV_HTTP_TIMEOUT` MUST resolve to the capped self-hosted pair that `ci.yml` declares

And the same step executing on a GitHub-hosted runner MUST resolve them to uv's own defaults

And a `ci.yml` that sets either variable at workflow or job level MUST fail the test that guards this constraint, naming the workflow file and the step

---
topic: consumer-ci-delivers-no-flake
author: claude-opus-5-5
created_at: 2026-11-07T19:05:38Z
---

## Proposal: CI publishes flake-retry records so the host-side reader receives them

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

State how a flake-retry record leaves a CI runner: the coverage job of this repository and of three named consumers publishes `tmp/flake-retries/` as a `flake-retries` artifact, whether the pytest step passed or failed, and a job that re-ran no test uploads nothing.

### Motivation

The "Untouched-test retry" bullet says a re-run writes one JSON line per node id under `tmp/flake-retries/`, and that a host-side reader of those records files one root-fix work item per node id. It never says how a record gets from a CI runner to that reader. A runner's `tmp/` dies with the runner, so a retry in CI files nothing and the flake stays invisible. legacy-coordinator-agent's R301 ruling chose artifact upload plus a host-side reader, with no new CI credential.

ORDER, recorded on purpose: this repository's half went ahead of the spec. livespec-dev-tooling#3702 (livespec-dev-tooling-mngdtf) added the upload step to this repository's `check-per-file-coverage` job on 2026-11-07 under R301, while the retry safety net was hiding flakes. That reverses this repository's usual order, so it is named here rather than left to look like an unratified behaviour. It was safe because the step is additive, removes no check and affects no consumer. This revise ratifies it. The composite action and the three consumer steps (livespec-dev-tooling-ljea46) have NOT landed, and wait for this revise.

Why these repositories: legacy-coordinator-agent's scope ruling of 2026-11-07 ~16:42Z limits consumer delivery to the three this plan's carrier map names. Other fleet repositories that load the plugin are not covered and can be added by a later proposal.

Why a composite action rather than the raw step in each consumer: `reusable-check-matrix.yml` has no caller in any consumer, and `ci_yaml_canonical_reconcile.py` inserts check slugs rather than a step. A composite keeps the artifact name, path and retention in one place, so the reader and its producers cannot drift, and the existing pin rewriter already moves its `uses:` pin at each release bump.

Why this repository's own step is not required to use the action: it already works, and its `uses:` line is one more workflow edit with no behaviour change.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, "## Testing approach", add this new bullet directly after the "Untouched-test retry" bullet:

- **Flake-retry record delivery.** The job that runs a repository's full test suite under coverage, and each shard of that job where a repository shards it, MUST publish that job's `tmp/flake-retries/` records as a workflow artifact with 7-day retention, in this repository, livespec, livespec-overseer and livespec-orchestrator-beads-fabro. The job MUST publish after its pytest step whether that step passed or failed, so that a record outlives the runner and reaches the host-side reader. The artifact MUST be named `flake-retries`, or `flake-retries-<suffix>` for a job that runs more than once in one CI run, because a workflow run cannot repeat an artifact name. A job that re-ran no test MUST upload no such artifact, and the publishing step MUST NOT fail the job on that account. A cancelled job, and a job the expedited incident path omits, MUST publish no artifact. Each of the three consumers MUST publish through the shared `.github/actions/publish-flake-retries` composite action of this repository at a released tag, so the artifact contract lives in one place. A pytest session in any other job is out of scope: a re-run there is reported only through that job's log and annotation. Scenarios: "a re-run test's record reaches the host-side reader as a CI artifact" and "a CI job that re-ran no test publishes no flake-retry artifact".

In `SPECIFICATION/scenarios.md`, add these two scenarios directly after "## Scenario: every retried failure files one root-fix work item":

## Scenario: a re-run test's record reaches the host-side reader as a CI artifact

Given the coverage job of this repository, livespec, livespec-overseer or livespec-orchestrator-beads-fabro, whose pytest session re-runs a test

When the job's pytest step finishes, whether it passed or failed

Then the workflow run MUST carry an artifact named `flake-retries` or `flake-retries-<suffix>` holding that job's `tmp/flake-retries/` records

## Scenario: a CI job that re-ran no test publishes no flake-retry artifact

Given the coverage job of one of those repositories, whose pytest session re-runs no test

When the job's publishing step runs

Then the workflow run MUST carry no artifact from that job named `flake-retries` or `flake-retries-<suffix>`, and that step MUST NOT fail the job

The revise pass adds both scenario headings to `tests/heading-coverage.json`, in the revise commit. Their rows name livespec-dev-tooling-mngdtf and livespec-dev-tooling-ljea46, the items whose host-captured proofs exercise them.


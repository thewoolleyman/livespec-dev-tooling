---
topic: a-ci-job-that-fails
author: claude-opus-5-5:ci-runtime-and-cost
created_at: 2026-11-03T16:27:00Z
---

## Proposal: A CI job that fails at Set up job on an action-download rate limit is re-run with growing backoff

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add to §"Hooks and CI" the rule that a CI job failing at its runner's Set up job step with an action-download rate-limit signature is re-run automatically with growing backoff, at most three attempts, and that no other failure is re-run by that mechanism. Add the scenario that exercises it.

### Motivation

Measured 2026-11-03 over 6 h across the seven fleet repositories: 10 of 4,359 job attempts failed at Set up job, every one the self-hosted runner's own download of actions/checkout from codeload.github.com (9 x 429 Too Many Requests after the runner's three built-in attempts, 1 x An action could not be found), all on the k3s ARC runners that share one egress IP, all inside one 14-minute burst; each killed its whole run before any code ran. The maintainer ruled (recorded on livespec-dev-tooling-6tgd2z, 2026-11-03 14:06:47Z): "Retrying on a 429 (and multiple times after a incremental backoff wait ...) should be a no brainer". livespec-dev-tooling-cetyrq realizes it; its dispatch was refused at the spec-change tier because §"Hooks and CI" does not state the behaviour. The rule is narrow on purpose: a re-run of a test or build failure is the flaky-test lever the fleet forbids, so only the pre-code action-download signature qualifies.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Hooks and CI", append this paragraph:

> A gating CI job of this repository that fails at its runner's `Set up job` step with an action-download rate-limit signature — an HTTP 429 from the forge's action-archive host, or the runner's `An action could not be found` for an action the workflow pins — MUST be re-run automatically, after a wait that grows with each attempt, for at most three automatic attempts. A job that fails at any later step, or at `Set up job` with any other signature, MUST NOT be re-run by this mechanism, and its failure MUST stay the run's verdict. Each automatic re-run MUST log the failed job, its attempt number and the matched signature in its own run log. The re-run MUST be realized as a workflow of this repository, so it needs no change to any job it re-runs.

In `SPECIFICATION/scenarios.md`, add:

```markdown
## Scenario: a CI job killed at Set up job by an action-download 429 is re-run with backoff

Given a gating CI job of livespec-dev-tooling that failed at Set up job
And its log shows the runner's action download refused with 429 Too Many Requests
When the job's workflow run completes
Then the job is re-run automatically after a wait
And a second such failure is re-run after a longer wait, up to three automatic attempts
And a job that failed at any later step is not re-run
```

The revise commit adds a `tests/heading-coverage.json` TODO row for the new heading (integration tier, owner livespec-dev-tooling-cetyrq) and the regenerated debt register.

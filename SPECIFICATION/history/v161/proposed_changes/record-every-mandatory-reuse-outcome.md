---
topic: record-every-mandatory-reuse-outcome
author: claude-opus-5-5
created_at: 2026-11-07T20:33:35Z
---

## Proposal: Every mandatory reuse outcome is recorded, and a fallback reaches the maintainer

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Each CI coverage consumer records a structured reuse outcome, and a scheduled detector notifies the maintainer of a fallback, missing evidence, a CI duration step change, or its own staleness.

### Motivation

The fallback ran for about two days on every run with no person told. A refusal alone is not enough, because nothing would report evidence that stops arriving (research note plan/ci-runtime-and-cost/research/006-coverage-fallback-post-mortem-2026-11-06.md on livespec-dev-tooling). Carries work item livespec-dev-tooling-akljpy.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "## Hooks and CI", add this paragraph:

**Reuse outcomes are recorded and fallbacks reach the maintainer.** Each GitHub Actions run of `scripts/just/check-coverage.sh` MUST write one structured reuse outcome, one of `reused`, `missing_receipt`, `data_digest_mismatch`, `tree_mismatch` or `producer_failed`, with the repository, run id, job id and duration, to the job's step summary and to the run's telemetry export. A scheduled detector MUST raise a maintainer notification, naming the repository, run, job and outcome, within 30 minutes of a mandatory coverage consumer job completing with any outcome other than `reused`. It MUST raise one naming the repository and job when a master CI run of the last 24 hours includes a mandatory coverage consumer job with no recorded outcome. It MUST raise one naming the job and both figures when a job's 90th-percentile duration over the last 24 hours exceeds its 7-day baseline, for the same job name and runner label, by more than a factor of 2 and by more than 5 minutes. A maintainer notification MUST name the detector when its own last successful run is older than twice its schedule interval.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario: a coverage consumer that did not reuse reaches the maintainer

Given a fleet CI run whose mandatory coverage consumer recorded an outcome other than `reused`

When the scheduled detector runs

Then it MUST raise a maintainer notification naming the repository, run, job and outcome within 30 minutes of that job's completion

## Scenario: a coverage consumer with no recorded outcome reaches the maintainer

Given a repository whose master CI runs of the last 24 hours include a mandatory coverage consumer job with no recorded reuse outcome

When the scheduled detector runs

Then it MUST raise a maintainer notification naming the repository and the job

## Scenario: a CI duration step change reaches the maintainer, and a runner-lane move does not

Given a job whose 90th-percentile duration over the last 24 hours exceeds its 7-day baseline by more than a factor of 2 and by more than 5 minutes, for the same job name and runner label

When the scheduled detector runs

Then it MUST raise a maintainer notification naming the job and both figures
And a job whose duration changed only because its runner label changed MUST NOT raise one

## Scenario: a stale detector reaches the maintainer

Given the detector's last successful run is older than twice its schedule interval

When staleness is evaluated

Then a maintainer notification MUST name the stale detector

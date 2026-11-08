---
topic: the-arc-runner-version-pin
author: claude-opus-5-5
created_at: 2026-11-07T20:33:36Z
---

## Proposal: The ARC runner version pin is bumped before GitHub stops serving it

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

A newer actions/runner release opens one bump PR across every scale set, an aged pin raises a trigger, and a check fails when two values files pin different versions.

### Motivation

On 2026-11-05 GitHub stopped serving the pinned runner version and in-flight CI jobs died across the pool, because nothing tracked the pin. The 14-day age bound is this proposal's choice: it sits below GitHub's 30-day self-hosted runner update window with room to land a bump. Carries work item livespec-dev-tooling-jkwzwv.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "## Runner-pool node rebuild recipe", add this paragraph:

**The runner version pin stays ahead of GitHub's cutoff.** When a newer actions/runner release than the version pinned in `ci-runner/k3s/phase2/arc/values-*.yaml` is published, the fleet's pin-freshness surface MUST open one pull request that moves every scale set's runner image, its container-hook path and its preseeded-externals version to that release together. When the pinned version has been superseded for longer than 14 days, a fleet trigger MUST fire naming the pinned version, the newest release and the age. Every scale set in `ci-runner/k3s/phase2/arc` MUST pin the same actions/runner version, and a check in `just check` MUST fail when two values files pin different versions.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario: a new runner release opens one bump across every scale set

Given a newer actions/runner release than the pinned version is published

When the pin-freshness surface runs

Then it MUST open one pull request moving every scale set's runner image, container-hook path and preseeded-externals version together

## Scenario: an aged runner pin raises a trigger

Given the pinned actions/runner version has been superseded for longer than 14 days

When the fleet trigger evaluates

Then it MUST fire naming the pinned version, the newest release and the age

## Scenario: two scale sets pinning different runner versions fail the check

Given two values files in `ci-runner/k3s/phase2/arc` pin different actions/runner versions

When `just check` runs

Then it MUST fail

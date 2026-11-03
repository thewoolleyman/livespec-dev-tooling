---
topic: release-window-scenario
author: claude-opus-5-5:ci-runtime-and-cost
created_at: 2026-11-03T15:59:02Z
---

## Proposal: The additive-surface-bump scenario's release PR opens at the next release window

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Reword the last step of `## Scenario: a livespec contract change ships an additive surface bump` from "opens a corresponding release PR on merge" to "opens a corresponding release PR at its next release window", so the scenario agrees with livespec core's release-window rule.

### Motivation

livespec core proposal release-window (livespec PR #3081) replaces "release-please opens a release PR on every push to master" with a release window: a schedule plus workflow_dispatch, with a push only tagging a just-merged release PR. livespec-dev-tooling-aplxhg realizes that window in this repository's release-please.yml (release mechanics were 34% of fleet k3s CI time over 7 days, plan ci-runtime-and-cost research 002; ordered by the maintainer 2026-11-03 15:00:49Z). This scenario's step still says the release PR opens "on merge", which the windowed workflow no longer does; the version arithmetic it exists to state (a feat: bump cuts the next MINOR) is unchanged.

### Proposed Changes

In `SPECIFICATION/scenarios.md`, `## Scenario: a livespec contract change ships an additive surface bump`, replace the step

> And `release-please` opens a corresponding release PR on merge that cuts the next MINOR version

with

> And `release-please` opens a corresponding release PR at its next release window that cuts the next MINOR version

No heading changes, so `tests/heading-coverage.json` is unaffected.

---
topic: gate-surface-severity-levers
author: claude-opus-5-5 (dev-host-test-gate-load)
created_at: 2026-11-07T22:22:17Z
---

## Proposal: Every gate surface arms the severity levers ci.yml arms, from one committed source

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a contracts.md H2, Gate-surface severity levers, requiring one committed source for the set of LIVESPEC_FAIL_IF_* levers this repository's CI arms. Every just check surface (local, delegated gate Job, factory sandbox) arms those levers itself, and a parity check fails when ci.yml and the committed source disagree. Add two scenarios. Today warn-default checks fail only when their lever is set, ci.yml sets three, and no other gate surface sets any, so a run goes green in the factory sandbox and red in CI.

### Motivation

livespec-dev-tooling-nxeg32 (plan dev-host-test-gate-load) carries this behaviour, and its launch-time Definition-of-Done preflight refused it on 2026-11-07 at 21:48Z: no ratified heading states the lever behaviour, the single lever source or the parity check. Measured by legacy-dispatcher-agent on master 7ef3183a: ci.yml arms LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST, LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST and LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST, while the justfile aggregate, the delegated gate Job and the factory sandbox set none. First measured instance: livespec-dev-tooling-xpuv6h's run succeeded in the sandbox, then livespec-dev-tooling#3672 failed check-ci-matrix-completeness in CI and blocked at merge-poll.

### Proposed Changes

Add this H2 to contracts.md, after `## Delegated gate-runner runs`:

## Gate-surface severity levers

A warn-default check in the `just check` aggregate reports its findings as warnings unless its `LIVESPEC_FAIL_IF_*` severity lever is set, and this repository's CI workflow arms some of those levers. This section keeps every other gate surface judging those checks the way CI does.

- **One committed source.** This repository MUST carry exactly one committed source that names the set of `LIVESPEC_FAIL_IF_*` levers its CI workflow arms for warn-default checks of the `just check` aggregate.
- **Every gate surface arms the set.** A `just check` run MUST run each warn-default check whose lever is in that set with the lever armed, on every gate surface: a run on a developer host, a run in a delegated gate Job, and a run in a factory sandbox. This MUST hold whether or not the calling environment sets the lever. A finding of such a check MUST therefore fail each of those surfaces with the same check and the same `failure_mode` that CI reports.
- **Parity with CI.** A check in the `just check` aggregate MUST fail, naming each lever, when the CI workflow arms a `LIVESPEC_FAIL_IF_*` lever that the committed source does not name, or the committed source names a lever that the CI workflow does not arm.
- **The workflow file.** The CI workflow MAY keep its own lever lines rather than read the committed source; the parity check keeps the two equal.

Add these two scenarios to scenarios.md:

## Scenario: a warn-default finding whose lever CI arms fails a just check run that sets no lever

```gherkin
Given a tree carrying a finding of a warn-default check whose severity lever the CI workflow arms
And an environment that sets no LIVESPEC_FAIL_IF_* variable
When just check runs on that tree on a developer host, in a delegated gate Job, or in a factory sandbox
Then the run MUST fail
And it MUST name the same check and the same failure_mode that the CI job reports for that tree
```

## Scenario: a lever armed by CI but missing from the committed lever source fails the parity check

```gherkin
Given the CI workflow arms a LIVESPEC_FAIL_IF_* lever
And the committed lever source does not name that lever
When just check runs
Then the lever parity check MUST fail
And its finding MUST name that lever
```

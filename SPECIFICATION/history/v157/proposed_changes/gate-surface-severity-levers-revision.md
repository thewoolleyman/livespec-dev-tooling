---
proposal: gate-surface-severity-levers.md
decision: accept
revised_at: 2026-11-08T02:31:06Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed. It closes the gap livespec-dev-tooling-nxeg32's preflight refused on 2026-11-07 21:48Z: no ratified heading stated that every gate surface judges warn-default checks the way CI does. A live-state walk confirms the premise: on current master, .github/workflows/ci.yml arms LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST and LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST (check-metadata leg and metadata batch) and LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST (batch), while the justfile aggregate, the delegated gate Job and the factory sandbox arm none. The clause leaves the arming mechanism open, so the ambient-variable test hazard ci.yml's own comment records stays with livespec-dev-tooling-ltwdfq. Implementation is carried by nxeg32.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T02:29:59Z
verdict: NO BLOCKERS
proposal_stem: gate-surface-severity-levers
content_digest: 1b6b1c9f13aef61cd3444d35d3dc05440ff539a0a3d29ec2dd78cbb1ae12cf67

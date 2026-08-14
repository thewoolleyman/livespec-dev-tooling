---
topic: mandatory-aggressive-jit-startup-admission
author: gpt-5.6
created_at: 2026-08-14T05:36:16Z
spec_commitments:
  impl_followups:
    - id_hint: adaptive-jit-admission-budget
      description: |
        Implement the mandatory, budget-bounded aggressive JIT startup admission controller in livespec-dev-tooling.
  supersedes:
    - adaptive-jit-admission-budget
---

## Proposal: Require aggressive bounded startup admission

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Require the controller to immediately admit every currently permitted deduplicated demand item during startup, while retaining the 450-point safety ceiling.

### Motivation

The v044 wording permits a controller to take a non-aggressive optional startup batch, which conflicts with the required immediate, budget-bounded fleet recovery behavior.

### Proposed Changes

Replace the optional startup-batch allowance with a mandatory tight loop: immediately admit all current deduplicated demand permitted by the per-repository logical desired formula, remaining physical capacity, and the 450-point startup budget; take no unconditional sleep between permitted admissions; and never spend more than 450 points. Strengthen the half-budget startup scenario to prove both the all-permitted-demand immediate lower bound and the 450-point upper bound, and rename its heading-coverage entry in lockstep. The 900 REST-points-per-minute accounting remains approximately five points for each content-generating POST, or ten points for a complete installation-token plus JIT-config pair, so 450 points allows about 45 pairs.

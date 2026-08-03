---
topic: final-token-budget-validation
author: codex-gpt-5
created_at: 2026-08-03T05:31:03Z
---

## Proposal: Validate the exact-scope token before exposure

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Require github-rate-budget-token to validate the freshly minted exact-scope final token before exposing it, because a minimum-scope probe reported healthy immediately before the owner-wide token was rate-limited.

### Motivation

Fleet conformance run 30787176784 measured the defect in production: the minimum-scope preflight reported a healthy budget at 05:26:55Z, while the final owner-wide token received installation rate-limit 403 responses at 05:27:01Z. The gate therefore did not establish the property its output promises.

### Proposed Changes

The Action MUST retain the minimum-scope preflight and MUST mint the exact caller-scoped final token only after that preflight is healthy. Before exposing outputs.token, it MUST run the same bounded REST core and GraphQL budget validation against the final token. A deficient final-token validation MUST wait and re-probe under the existing aggregate max-wait bound and failure taxonomy; the Action MUST NOT expose a token whose measured final-scope budget is deficient. The specification MUST include a scenario for a healthy probe followed by a deficient final token, and heading coverage MUST link the new behavior to that scenario.

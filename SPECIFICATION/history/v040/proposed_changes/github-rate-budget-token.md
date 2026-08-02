---
topic: github-rate-budget-token
author: openai-codex-gpt-5
created_at: 2026-08-02T23:01:12Z
---

## Proposal: Budget-aware GitHub App token minting

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a semver-stable composite Action that prevents release and fleet-conformance jobs from consuming an already-exhausted shared GitHub App installation budget, while preserving each caller's exact final token scope.

### Motivation

Recent Honeycomb alerts traced to several otherwise-correct workflows minting tokens from the same GitHub App installation after its REST core budget had been exhausted. Re-running later succeeded, proving the failures were quota transients, but replay is reactive and noisy. The provider needs one reusable gate that waits for both REST and GraphQL budgets before minting the token used by expensive downstream work.

### Proposed Changes

The library MUST expose a `github-rate-budget-token` composite Action and MUST use it at the release-please and fleet-conformance entry points that can consume substantial shared installation quota. `spec.md` MUST state that the Action first mints a minimum-scope probe token, polls GitHub's `/rate_limit` resource without spending primary quota, and only after both caller-configured REST core and GraphQL minima are available mints a fresh final token with exactly the caller-requested owner/repository scope. `contracts.md` MUST define the Action path, required `app-id` and `private-key` inputs, optional `owner`, `repositories`, budget, cushion, bounded-wait, and deterministic-jitter inputs, the `token` output, exact-scope pass-through, bounded aggregate waiting, and distinct `rate-budget-not-restored`, `probe-unusable`, malformed-payload, and invalid-minimum failures. The contract MUST retain normal token revocation and MUST NOT gate the per-sibling release-dispatch matrix, because the single fleet preflight is the bounded coordination point. Release-please MUST use conservative core/GraphQL minima; fleet-conformance callers MUST reserve enough REST core budget for a full fleet read while accepting a minimal GraphQL threshold. `scenarios.md` MUST cover an initially healthy budget, recovery after waiting until the later deficient reset plus cushion and deterministic jitter, sustained exhaustion, unusable probe credentials, malformed rate-limit payloads, and preservation of the final token's requested scope. Adding this public composite Action MUST ship as a MINOR release.

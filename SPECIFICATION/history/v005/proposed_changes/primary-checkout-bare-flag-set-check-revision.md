---
proposal: primary-checkout-bare-flag-set-check.md
decision: accept
revised_at: 2026-05-27T22:36:00Z
author_human: thewoolleyman <thewoolleyman@gmail.com>
author_llm: claude-opus-4-7
---

## Decision and Rationale

Accept. Adds the `primary_checkout_bare_flag_set` shared check to the §"Shared check inventory" CI-alignment family. The check is universal (project-agnostic, no role keys consumed) and ports the cross-boundary invariant from livespec's doctor-static phase. Impl + paired test land in the same PR as the spec amendment. The check is NOT wired into livespec-dev-tooling's own `just check` aggregate yet (self-host phase is downstream); only the recipe + CI matrix entry land here.

## Resulting Changes

- contracts.md

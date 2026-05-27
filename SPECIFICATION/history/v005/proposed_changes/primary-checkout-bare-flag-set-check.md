---
topic: primary-checkout-bare-flag-set-check
author: claude-opus-4-7
created_at: 2026-05-27T22:36:00Z
---

## Cross-cutting parent

This PC is a child of the family-wide bare-flag invariant migration coordinated from livespec. The parent epic ports the `primary-checkout-bare-flag-set` cross-boundary invariant from livespec's doctor-static phase into livespec-dev-tooling so every livespec-governed sibling (livespec-impl-*, livespec-runtime, livespec-dev-tooling itself) can consume it via the standard `python -m livespec_dev_tooling.checks.<slug>` invocation surface.

The invariant statement is owned by livespec at `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary invariants" → §"`primary-checkout-bare-flag-set`". This sibling PC adds the shared-check inventory entry only; the upstream contract remains the canonical declaration.


## Problem statement

The cross-boundary invariant requires every livespec-governed primary checkout to have `core.bare = true` in `.git/config`. Today only livespec runs the check (via its doctor-static phase). Every other sibling has no mechanical enforcement.

Because the check's inputs are project-agnostic — it reads `core.bare` against the cwd's git common dir, with zero dependency on any `[tool.livespec_dev_tooling]` role keys — it satisfies the §"Configurability is the partition criterion" rule and qualifies as a shared check.


## Proposal: add primary_checkout_bare_flag_set shared check

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add a new shared check `primary_checkout_bare_flag_set` to the `livespec_dev_tooling/checks/` package. The check reads `core.bare` from the cwd's git common dir via `git config --get core.bare` and fails when the value is absent OR explicitly `false`. The invariant MUST NOT distinguish between the two cases — both are corrected by the same one-line bootstrap (`git config core.bare true`) against the primary checkout.

The check is universal: no role keys are consumed, no consumer-specific path is read. Every livespec-governed sibling can opt in by wiring `python -m livespec_dev_tooling.checks.primary_checkout_bare_flag_set` into its `just check` aggregate AND/OR its CI matrix.

### Motivation

Without a shared implementation each sibling either:

1. Reinvents the check locally (duplication + drift risk), or
2. Skips enforcement entirely (silent invariant breakage).

The shared module collapses both paths into a single `python -m` invocation backed by the inventory-codified contract.

### Algorithm

1. If `git` is not on PATH → exit `0` with a warning (graceful skip; local-dev tolerance).
2. If cwd is not inside a git working tree (`git rev-parse --is-inside-work-tree` ≠ `true`) → exit `0` with an info log (skipped).
3. Otherwise, read `git config --get core.bare`:
   - returncode `0` AND stdout `"true"` → exit `0` (pass).
   - else → exit `4` with a structured `fail` finding on stderr.

### Outputs

Findings on stderr in the inventory's canonical structlog JSON shape. The fail finding carries:

- `check_id`: `primary_checkout_bare_flag_set`
- `status`: `fail`
- `event`: `primary-checkout-bare-flag-set: core.bare is absent or false on the primary checkout's .git/config`
- `observed`: the literal `core.bare` value (`false` or `<absent>`)
- `hint`: `run git config core.bare true against the primary checkout`
- `path`: empty
- `line`: 0

### Exit codes

- `0` — pass, OR skipped (no git on PATH, or cwd is not a git working tree).
- `4` — fail (`core.bare` is absent or `false`).

### Partition placement

`primary_checkout_bare_flag_set` is added to the §"Shared check inventory" CI-alignment family enumeration (alongside `branch_protection_alignment`, `master_ci_green`, `no_stale_revise_branches`). The CI-alignment family is the natural home: the check enforces a property of the consumer's local git configuration that mirrors the doctor cross-boundary invariant.

No role keys are added to the §"Consumer configuration schema" — the check is layout-independent. No carve-out is needed.

### Sibling self-host posture

This PC ships the check + the inventory entry; it does NOT wire the check into livespec-dev-tooling's own `just check` aggregate. Reason: dev-tooling's primary is currently non-bare, so wiring would self-fail. Self-host migration (flipping dev-tooling's primary to bare via the documented bootstrap) is a downstream phase tracked separately. The CI matrix MAY run the check against an actions/checkout non-bare clone if the workflow step explicitly flips `core.bare = true` before invoking the recipe (mirroring the livespec CI pattern in PR #307).


## Out of scope

- Self-hosting flip of livespec-dev-tooling's own primary to bare. Downstream phase.
- Wiring the check into other siblings' `just check` aggregates. Each sibling's PR is its own follow-up.
- Any change to the upstream invariant declaration at `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary invariants" → §"`primary-checkout-bare-flag-set`".

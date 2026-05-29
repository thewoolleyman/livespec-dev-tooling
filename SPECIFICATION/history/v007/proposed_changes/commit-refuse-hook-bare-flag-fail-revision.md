---
proposal: commit-refuse-hook-bare-flag-fail.md
decision: accept
revised_at: 2026-05-29T00:23:24Z
author_human: Test User <test@test.test>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accept. Documents the core.bare=true fail branch (failure_mode core_bare_set) now shipped in primary_checkout_commit_refuse_hook_installed.py, keeping dev-tooling's contracts.md in lockstep with the impl. Closes the detection gap found during epic li-unbare: a bare primary (the eliminated legacy state) is a git repo that is NOT a work tree, so the prior work-tree-only skip passed it silently. Realizes the MAY in livespec/SPECIFICATION/contracts.md section primary-checkout-commit-refuse-hook-installed; the canonical upstream invariant stays a MAY. Change is entirely under an H3 heading, so no heading-coverage update is required. Epic li-unbare.

## Resulting Changes

- contracts.md

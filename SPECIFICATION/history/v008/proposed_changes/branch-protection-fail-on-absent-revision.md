---
proposal: branch-protection-fail-on-absent.md
decision: accept
revised_at: 2026-05-29T05:15:00Z
author_human: Test User <test@test.test>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accept. Documents the fail-on-absent branch now shipped in
branch_protection_alignment.py, keeping dev-tooling's contracts.md in
lockstep with the impl. Closes the gap found this session: the check
verified alignment only when protection existed, so a wholly-unprotected
master passed silently and let PRs auto-merge before CI finished. The new
H3 section captures the three gh-api outcomes, the load-bearing 404
ambiguity (unprotected vs can't-read, disambiguated by the response
body's `message` field), the exit-4 protection_absent fail, the
graceful-skip-on-anything-non-definitive rule, and the CI-token caveat
(the default Actions GITHUB_TOKEN can't read protection, so the check is
not a CI matrix entry; it enforces via just check / pre-push under an
admin-scoped gh token). Cites livespec/SPECIFICATION/non-functional-requirements.md
section "CI as a merge gate (branch protection)". Change is entirely
under an H3 heading, so no heading-coverage update is required.

## Resulting Changes

- contracts.md

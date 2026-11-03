---
proposal: shared-check-fail-a-fleet.md
decision: accept
revised_at: 2026-11-03T08:59:00Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed (PR #3222, head d17299f1). The proposal supplies the spec text work item livespec-dev-tooling-yhacv6 was held for: a canonical per-commit check codex_hook_reconcilable that fails, at the producing plugin's own gate, a Codex hook the livespec-driver-codex hook-cache reconciler cannot cover, with rules copied from the Driver's ratified reconciler contract and the two disclosed stricter deviations. Two fresh independent Sonnet reviews ran; the first's blocker (a JSON null hooks entry, which the reconciler treats as absent) was fixed and the second returned NO BLOCKERS. Adoption before arming was verified as the coordinator required: new canonical slugs are auto-wired into consumers by the cross-repo justfile and CI reconcilers, and the rule applied to the tracked tree of all 23 fleet and adopter repositories found zero failures, so the check ships armed with no adopting fix sequenced first. The resulting text inserts the proposal's ### subsection verbatim after the no_shadow_ledger_body_identical subsection, appends the five scenarios verbatim, adds five integration-tier TODO coverage rows owned by livespec-dev-tooling-yhacv6, and regenerates the debt register with just generate-heading-coverage-debt-register. Decided under the coordinator's pre-ruling (accept when the Sonnet review is clean and no fleet plugin goes red on the pin bump) and the project's delegated revise_decision_mode.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T08:58:57Z
verdict: NO BLOCKERS
proposal_stem: shared-check-fail-a-fleet
content_digest: 0fa537cef680ef8ff4840b1a561d1c891a436caa0ac4220101b6f105eba5353e

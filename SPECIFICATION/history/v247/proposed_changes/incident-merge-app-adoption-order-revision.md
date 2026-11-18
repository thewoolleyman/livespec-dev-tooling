---
proposal: incident-merge-app-adoption-order.md
decision: accept
revised_at: 2026-11-18T05:08:14Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5 (bqnzcm plan seat)
---

## Decision and Rationale

Coordinator ruling 2026-11-18 on plan expedited-incident-response-flag: a check that fails in both orders of a rollout breaks the fleet ordering rule (adoption first, then arming). Under v246 a declared incident_merge_integration_id whose App is absent from the ruleset failed, and an undeclared App on the ruleset failed, so the incident-merge App rollout was red in either order. The accepted text makes the declared Integration optional on the ruleset (declared and not yet armed passes) while any Integration that is neither the recovery App nor the declared one still fails merge_queue_bypass_path, the pull_request bypass-mode rule and the key-not-equal-recovery-id rule are unchanged. The check can recognise the merge App only through the declared id, so admitting an undeclared extra Integration was rejected. The independent reviewer found no contradiction with the ratified text.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-18T05:07:47Z
verdict: NO BLOCKERS
proposal_stem: incident-merge-app-adoption-order
content_digest: 03a9615e42455d026f59985acfa114d6480706c6ba2e82db625487a2d5c93437

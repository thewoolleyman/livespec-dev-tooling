---
proposal: incident-merge-principal-queue-bypass.md
decision: accept
revised_at: 2026-11-18T01:30:45Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5 (bqnzcm plan seat)
---

## Decision and Rationale

Maintainer ruling on livespec-dev-tooling-72b33c (2026-11-15) accepts an incident-merge principal that may merge a green expedited repair outside the merge queue. The proposal adds exactly one distinct ruleset bypass actor (incident_merge_integration_id != recovery_bypass_integration_id, bypass_mode pull_request), defines the principal's merge-time green-check obligation in Expedited incident execution, and adds five scenarios. The recovery App stays inverse-only. The independent reviewer found no contradiction with the ratified text. Caveat: the proposal says it should follow the companion livespec core proposal that ratifies the distinct principal (livespec#3258 is merged as a proposal; its revise was not verified by this pass); the maintainer's standing direction on the plan is to proceed.

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
reviewed_at: 2026-11-18T01:30:15Z
verdict: NO BLOCKERS
proposal_stem: incident-merge-principal-queue-bypass
content_digest: 5cd69d6ee33df1ee0f0d1d269bae774b4d0504f37f096dc46b1573d54db79270

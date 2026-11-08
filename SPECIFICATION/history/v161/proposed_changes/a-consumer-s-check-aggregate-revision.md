---
proposal: a-consumer-s-check-aggregate.md
decision: modify
revised_at: 2026-11-08T19:12:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

A delegated gate Job runs in the single image it resolves from the consumer's ci.yml, so a second job container image silently breaks the delegated path while PR CI stays green (livespec-orchestrator-beads-fabro#4439, 2026-11-05). The check belongs in every consumer's own aggregate so the offending PR goes red itself. Carries livespec-dev-tooling-kzhduc.

## Modifications

Stated why ci.yml must declare one image (the delegated gate resolves one). Named the required gate generically as the all-green aggregate job, because consumers name it differently, and the scenario follows. Required the check to ship as a shared livespec-dev-tooling check with no copy in the consumer, as the workflow-parse clause does, since this repository can only bind consumers through a shared check.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T19:12:04Z
verdict: NO BLOCKERS
proposal_stem: a-consumer-s-check-aggregate
content_digest: 4adff42be977373eca846e91dfefb1f3be476e4fa032774f24a984d341b78a70

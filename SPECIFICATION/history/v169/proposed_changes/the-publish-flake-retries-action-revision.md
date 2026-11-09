---
proposal: the-publish-flake-retries-action.md
decision: modify
revised_at: 2026-11-09T17:07:49Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:fleet-flaky-tests
---

## Decision and Rationale

Modified under delegated mode. spec.md requires every composite Action's input/output contract in contracts.md, and the publish-flake-retries Action shipped in v1.189.0 for livespec-dev-tooling-ljea46 with no stated contract. The bullet matches the shipped action.yml: optional suffix, flake-retries or flake-retries-<suffix>, tmp/flake-retries/, 7-day retention, if-no-files-found: ignore, with the caller owning !cancelled() and any incident omission guard. The independent read-only reviewer (sonnet) found no blockers on the exact bytes.

## Modifications

The bullet's last sentence names `non-functional-requirements.md`, not `constraints.md`, as the home of "Flake-retry record delivery": v156 placed that clause in non-functional-requirements.md §"Testing approach", so the proposal's file reference was wrong. No other change.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T17:07:12Z
verdict: NO BLOCKERS
proposal_stem: the-publish-flake-retries-action
content_digest: b75ceb851f682be25d371975ed72ab46a9d903cc08816a6f49d2f54bd6ef39dd

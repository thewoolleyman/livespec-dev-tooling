---
proposal: a-fast-incident-member-reads-no-host-state.md
decision: modify
revised_at: 2026-11-14T22:06:26Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:expedited-incident-response-flag
---

## Decision and Rationale

Modified and accepted. legacy-coordinator-agent graded the proposal PASS (livespec-dev-tooling#4721) and ruled 7qb2bs necessary for orchestrator incident usability (s6jt4u): check-codex-skill-picker, classed fast, fails deterministically on the incident host because it reads the host's codex CLI and ~/.codex. The contracts.md clause lands verbatim in §"Expedited incident execution".

## Modifications

Added one Gherkin And-line to the existing scenario "an expedited local gate skips slow work and preserves fast failures" in scenarios.md, so the new behavior clause carries a scenario (authoring discipline: behavior => clause + scenario). No H2 heading changes.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T22:06:02Z
verdict: NO BLOCKERS
proposal_stem: a-fast-incident-member-reads-no-host-state
content_digest: ade93540fabaff3d42d485c20bc361fe0ee694e268c1b1c542a83120401629c3

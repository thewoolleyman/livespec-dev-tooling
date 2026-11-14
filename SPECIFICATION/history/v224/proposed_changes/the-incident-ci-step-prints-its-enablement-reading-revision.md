---
proposal: the-incident-ci-step-prints-its-enablement-reading.md
decision: modify
revised_at: 2026-11-14T19:53:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with one wording modification (livespec-dev-tooling-kg5qv4, -gyxmjj, -3z6fyq). Every incident-ci job prints the released plan's enablement reading, and only that field, as one fixed line, so the CI-plan vantage's reading can be read back from a run without exposing the plan's environment map. It ratifies what livespec#3227, livespec-orchestrator-beads-fabro#5282 and livespec-overseer#3049 already run.

## Modifications

One wording change found by the pre-merge doctor walk against live state, no change of behaviour: the proposal said `<json>` is the enablement field's value "exactly as the plan carries it", but every merged step (this repository's ci.yml lines 1031-1032, livespec ci.yml:900, livespec-orchestrator-beads-fabro ci.yml:1470, livespec-overseer ci.yml:922) prints json.dumps(plan.get("enablement"), sort_keys=True). The ratified text now says the value is serialized as one line of JSON with its keys sorted, so the clause matches what the four repositories already run.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T19:50:56Z
verdict: NO BLOCKERS
proposal_stem: the-incident-ci-step-prints-its-enablement-reading
content_digest: 77bcec82184ccfd15717cd163bf1c599660874cf8b37a96f9ab947bca28ff37f

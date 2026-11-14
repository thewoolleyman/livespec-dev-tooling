---
proposal: one-library-command-gives-every.md
decision: modify
revised_at: 2026-11-11T18:27:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratify for livespec-dev-tooling-yud7rc (priority 3a, legacy-coordinator-agent 16:41Z). The filing tier record (v192, spec-change/partial, '## Delegated pre-push gate') found the bullet states the accepted-verdict behaviour but no single library command taking the consumer's member names, no continue-with-own-gate exit status, and no delegation of this repository's own check-pre-push.sh to it. Five consumers set both keys and never call pre-push-evidence, so each runs a second full-suite gate Job at push: 2,262 s of check-pre-push measured on the orchestrator push of livespec-orchestrator-beads-fabro#4964 today. One shipped command lets each adopt with one call and a pin bump. Decided by the implement-test-performance plan seat under delegated decision mode, in the v195 slot.

## Modifications

One clause added to the Shared entry point paragraph: 'and MUST exit 3, which tells its caller' becomes 'and MUST exit 3, after printing any line this bullet requires for evidence that does not qualify, which tells its caller'. This reconciles the paragraph with the-pre-push-gate-confirms, ratified in the same revise. The command reads the cluster's record, so the missing-record and disagreement lines that proposal requires are printed by the command before it hands the push back to the caller's own gate. Everything else is verbatim.

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
reviewed_at: 2026-11-11T18:25:27Z
verdict: NO BLOCKERS
proposal_stem: one-library-command-gives-every
content_digest: a289bb2f1f98364520394e41ca87b2808a8fc6c08cf9bde4a9879d95f7cfbc75

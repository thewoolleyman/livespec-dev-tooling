---
proposal: config-value-gates.md
decision: modify
revised_at: 2026-11-04T20:17:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:ci-runtime-and-cost
---

## Decision and Rationale

Accepted under R301 by legacy-coordinator-agent on the maintainer's behalf. The maintainer direction is recorded verbatim on livespec-dev-tooling-6tgd2z (2026-11-04 ~18:4xZ): "why does it takes a whole PR just to make the change. Even if the file is committed, it should be a short circuit, no-tests change to change the wip or cap values. NO TEST SHOULD BE TIED TO CONFIG VALUE ACTUAL VALUES. IF any of this is the case, fix it." This supplies the governing H2s that livespec-dev-tooling-hmztez and livespec-dev-tooling-symfx2 lacked. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes.

## Modifications

Formatting only. Scenarios use this repository's '## Scenario:' style with MUST in Then/And. 'at least covers' became 'MUST at least cover'. The pre-push/CI bullet cites livespec core's ratified section (non-functional-requirements.md CI as a merge gate, Config-value fast path; v237) in place of a PR number. No rule was added or dropped.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T20:17:22Z
verdict: NO BLOCKERS
proposal_stem: config-value-gates
content_digest: d4d48d134506d5ab7a5e648d55db49b6d9de3a7dc391216a10d9d36423a29054

---
proposal: reusable-check-matrix-incident-omitted-input.md
decision: modify
revised_at: 2026-11-10T03:56:13Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The proposal correctly brings contracts.md §"Reusable workflows wire contract" level with the optional incident-omitted input that livespec-dev-tooling#3966 adds to reusable-check-matrix.yml, and it leaves the omission policy to §"Expedited incident execution". One clause asserted more than the workflow can check: a reusable workflow cannot verify that a string input came from the caller's incident-ci guarded output. The revision keeps every other clause unchanged. It splits the authority into a workflow MUST (the trusted label and a same-repository head) and a caller MUST that a repository conformance check enforces. Those are the checks the #3966 lane is implementing. An independent review recorded NO BLOCKERS on these exact bytes.

## Modifications

The proposal listed three incident-authority conditions and required the reusable workflow to verify all of them: the trusted label, a same-repository head, and the caller's incident-ci guarded output. The workflow cannot check the third. A reusable workflow cannot see where a string input came from. This revision therefore splits the conditions by who can enforce them:
- WORKFLOW MUST: honour the input only on a pull_request that carries the trusted PR-specific incident label and has a same-repository head; on any other pull request, run every requested check. The livespec-dev-tooling#3966 lane is building exactly these two checks into the decision module.
- CALLER MUST: wire incident-omitted only from the caller's incident-ci job's guarded output, and a repository conformance check on callers MUST refuse any other wiring. livespec-dev-tooling#3966 is adding that rule.
The scenario's first added And line now names only the label and same-repository head, and a third And line covers the conformance refusal.

The ::notice annotation for omitted legs and running the decision code from a released ref were deliberately left out. Neither is merged code yet, so either clause would run ahead of the implementation. A later revision may add them once they land.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T03:55:35Z
verdict: NO BLOCKERS
proposal_stem: reusable-check-matrix-incident-omitted-input
content_digest: 1bc0595cb0af9c3bf218db908410102c69f3817e79c8b751d6f3dbc0f0186618

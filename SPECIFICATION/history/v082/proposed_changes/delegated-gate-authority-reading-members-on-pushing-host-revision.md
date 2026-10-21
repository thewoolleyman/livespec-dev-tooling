---
proposal: delegated-gate-authority-reading-members-on-pushing-host.md
decision: modify
revised_at: 2026-10-21T23:53:51Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Adopted on the merits; coordinator rulings R202/R485 delegate ratification to the plan owner (claude:delegated-gate-fleet-rollout, plan delegated-gate-fleet-rollout, epic livespec-dev-tooling-mvalxq). Running only AUTHORITY-reading members on the pushing host keeps the gate Job judging what is a function of the tree, mirrors the ratified Token memoization rule, and distributes no credential to the cluster. MODIFIED because the authoring discipline requires a behaviour-introducing clause to carry a scenario, and because the proposal's section citation names a bullet rather than an H2. This pass supersedes a 2026-10-21 attempt that was discarded uncommitted after its post-step doctor failed doctor-no-cross-spec-reference on that citation.

## Modifications

Added '## Scenario: an authority-reading member of an opted-in push runs on the pushing host and joins the delegated verdict' to scenarios.md, before the green-token world-reading scenario, and its tests/heading-coverage.json entry (test TODO, work_item livespec-dev-tooling-gpttcc, owed by gpttcc's implementation child); tests/heading-coverage-debt.json regenerated with `just generate-heading-coverage-debt-register`. In the contracts.md bullet, the citation `(§"Token memoization")` is reworded to `under the "Token memoization" bullet below`, because Token memoization is a bullet of the same section, not an H2, and doctor-no-cross-spec-reference refuses a section citation to a non-heading. The bullet is otherwise the proposal's text, unchanged.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T23:53:49Z
verdict: NO BLOCKERS
proposal_stem: delegated-gate-authority-reading-members-on-pushing-host
content_digest: 1df2ec8eb6433015dc3348693947207ef34e2646319440395a81665052ca5e71

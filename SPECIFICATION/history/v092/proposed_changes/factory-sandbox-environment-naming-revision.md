---
proposal: factory-sandbox-environment-naming.md
decision: accept
revised_at: 2026-10-24T03:54:32Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Maintainer direction 2026-10-24 ("Proper naming is important"): the gmktec catalog ids name CI though every one is a factory work sandbox, and -k8s distinguished nothing once livespec-ci moved to the kubernetes provider. The clause names ids factory-<toolchain>, forbids placement in the id, and orders a rename so no dispatch is stranded. Re-cut as v092: the same accepted text was revised as v090 on a branch whose pull request conflicted after two unrelated revises (runner-pool node telemetry, local gate concurrency limit) took v090 and v091 on master; the inserted section and scenario are byte-identical to that ratified text. Proposal review: R1 4 blockers fixed, R2 2 fixed, R3 NO BLOCKERS. Fresh Fable ratification review of the v092 final bytes: NO BLOCKERS on digest 9e4885ab. tests/heading-coverage.json and tests/heading-coverage-debt.json land beside this revise in the same change. Reviewer: claude-fable-5-1, a separate read-only Claude Code ratification subagent.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-24T03:54:31Z
verdict: NO BLOCKERS
proposal_stem: factory-sandbox-environment-naming
content_digest: 9e4885ab349845a6d36a84b0ca8c4abd102cd34cf3c67f8f1aa20c25710a35b8

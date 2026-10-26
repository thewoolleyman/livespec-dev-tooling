---
proposal: factory-reach-image-env-pin-surface.md
decision: accept
revised_at: 2026-10-26T20:37:56Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written. Work item livespec-dev-tooling-7enfyd: every livespec-dev-tooling self-bump since 2026-10-16 is red (PRs #2852 through #2879 closed unmerged; #2882 open and red), because the bump never rewrites the second sandbox-image pin in ci-runner/k3s/phase2/factory/factory-reach-image.env, which fabro_image_pin_lockstep requires equal to the workflow container pin. Naming the env-file line as a surface of the existing fabro-sandbox format lets the walk find it and the bump rewrite it in the same commit. The lockstep check is unchanged, and the pin stays where freeze ruling R70 put it. No design record is contradicted. The independent fable review returned NO BLOCKERS. Its two non-blocking nits (sentence order within the bullet; the scenario's position at the end of scenarios.md) are left for a future tidy. The new scenario's heading-coverage entry is a spec-first TODO owed by 7enfyd, co-edited in the same commit.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-26T20:37:25Z
verdict: NO BLOCKERS
proposal_stem: factory-reach-image-env-pin-surface
content_digest: 85359a5837ee8b434cba7eee23ba1922d6b713fa13fef18d57b0733720dc739b

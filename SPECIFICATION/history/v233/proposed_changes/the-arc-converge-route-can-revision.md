---
proposal: the-arc-converge-route-can.md
decision: accept
revised_at: 2026-11-15T17:56:02Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed and as graded PASS by legacy-coordinator-agent at about 17:4xZ on 2026-11-15 under its R301/R493 delegation, which also ruled that the stale-base-merge-options seat runs this revise unattended; the substance is not reworded. The proposal carries DoD bullets 1 and 2 of livespec-dev-tooling-xyi5vu (plan stale-base-merge-options, epic livespec-dev-tooling-xowhol): the CI stack converge reads its runner scale sets from the committed values files, leaves a scale set whose rendered inputs are unchanged at its Helm revision, and uninstalls the release of a removed values file, with the ci_converge_unit role pruning the removed file and counting it as a changed input. DoD bullet 3 is already governed by the v232 paragraph 'ARC GitHub App credentials, one Secret per account.' and is not restated. It lands as one block of three paragraphs under the existing non-functional-requirements.md section 'Runner-pool node rebuild recipe' (no H2 change there) and two scenarios in scenarios.md, which the authoring discipline requires for new behaviour; contracts.md was named by the requester but holds no ARC converge clause. Doctor LLM phases on the drafted bytes: no contradiction with the surrounding paragraphs; 'the always-on stop above' resolves to the paragraph 'Always-on posture from the profile, and listener placement by it.'; all 16 committed values files (EXAMPLE excluded) declare a unique runnerScaleSetName equal to the release name the hard-coded SCALE_SETS map and worker glob use today, so file-derived enumeration renames and uninstalls nothing on first roll. One low observation, that a release with no stored input record on the first converge after rollout is upgraded once, is consistent with the text (an absent record cannot show the inputs unchanged) and is left to xyi5vu's implementation. The independent sonnet review reported NO BLOCKERS on these exact bytes.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T17:54:52Z
verdict: NO BLOCKERS
proposal_stem: the-arc-converge-route-can
content_digest: 05b3c05cb2a47120be562ba423d1be9f9f169f6cf7567d10213f1e82c314e2fa

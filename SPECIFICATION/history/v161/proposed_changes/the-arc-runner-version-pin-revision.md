---
proposal: the-arc-runner-version-pin.md
decision: modify
revised_at: 2026-11-08T19:12:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

On 2026-11-05 GitHub stopped serving the pinned runner version and in-flight CI died across the pool because nothing tracked the pin. A bump PR, an aged-pin trigger and a same-version check prevent the next one; 14 days sits below GitHub's 30-day window. Carries livespec-dev-tooling-jkwzwv.

## Modifications

Scale-set values files live in two directories, ci-runner/k3s/phase2/arc/ and ci-runner/k3s/arc/ (the macbook homelab worker and host-unique sets pin actions-runner 2.338.2 there too, measured 2026-11-07), so the bump, the age trigger and the same-version check cover both. ci-runner/k3s/arc/values-host-unique.yaml pins a runner image with no container-hook path and no externals version, so the bump moves those only where a file carries them.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T19:12:04Z
verdict: NO BLOCKERS
proposal_stem: the-arc-runner-version-pin
content_digest: f92194d0dd5854042d37435bb6dbde986f8a43eb600c466f018d593c88702dc8

---
proposal: delegated-gate-declared-recipe.md
decision: modify
revised_at: 2026-10-17T00:07:02Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:factory-worker-nodes-gitops
---

## Decision and Rationale

Accepted with modifications under the maintainer's delegated authority recorded on livespec-dev-tooling-dfixhe (2026-10-15 ~16:40Z, reaffirmed 2026-10-16 06:29Z), executed for freeze-driver ruling R88. The shared gate Job is hardcoded to this repository's own recipes, so any other consumer is red on every green tree. The fix is livespec-dev-tooling-saxz, whose missing-recipe assertion had no governing clause. An independent read-only Fable review first found a drift blocker in bullet 3; it is fixed, and the re-review returned NO BLOCKERS on these exact bytes.

## Modifications

(1) Bullet 3 'What the delegated gate runs' now says 'runs the same check recipe the local fall-through runs — the consumer's own gate recipe, the next bullet —' instead of naming `just check`. This removes the contradiction for a consumer that declares another recipe (the reviewer's blocker). (2) The new bullet's default is 'the recipe its local fall-through runs' instead of 'its `just check`'. (3) 'a red verdict whose detail names' becomes 'a red verdict that names', in the bullet and in the scenario's Then, because GateVerdict.detail is a defined field that never carries Job output. The client-surfacing duty is recorded on saxz. One heading-coverage TODO row is owned by saxz with an integration-tier reason, and the debt register was regenerated mechanically.

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
reviewed_at: 2026-10-17T00:06:05Z
verdict: NO BLOCKERS
proposal_stem: delegated-gate-declared-recipe
content_digest: ba0f3c39f3cb28b2abcfaed72505b70d7a2f0ecc59d23ade068f22e9c04316a8

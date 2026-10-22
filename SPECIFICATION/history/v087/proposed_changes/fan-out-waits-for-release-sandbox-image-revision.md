---
proposal: fan-out-waits-for-release-sandbox-image.md
decision: accept
revised_at: 2026-10-22T18:26:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted on the merits, as filed. A livespec-dev-tooling release's sibling-released dispatch raced its own sandbox image publish on 2026-10-22 (v1.125.0 published 10:38:18Z; image served 11:08-11:19Z): console PR #1266 hit a 404, and orchestrator PR #3507 merged a sandbox tag ghcr did not yet serve. Gating the dev-tooling fan-out on its six semver tags removes the race without changing any ratified clause. Decided under delegated revise_decision_mode by claude:delegated-gate-fleet-rollout, which filed livespec-dev-tooling-epcoja under coordinator R609/R612. The independent read-only fable ratification review found NO BLOCKERS on these exact bytes: the six tags match fabro-sandbox-image.yml's release emissions; no conflict with soft-fail semantics, the preflight's structural-failure rule, or the two-hour settle window (a 90-minute wait keeps PR-open inside it); slowest measured release build 30.1 min. The companion proposal stale-pin-keeps-member-in-fan-out is NOT processed here; it amends a livespec-dh9r-derived rule and awaits the maintainer.

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
reviewed_at: 2026-10-22T18:26:06Z
verdict: NO BLOCKERS
proposal_stem: fan-out-waits-for-release-sandbox-image
content_digest: 3ed42d3f7eacc5c3b76be575bf9a6cfab621b093f6261f482203f5b54b6f191b

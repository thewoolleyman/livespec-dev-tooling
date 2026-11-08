---
proposal: consumer-ci-delivers-no-flake.md
decision: accept
revised_at: 2026-11-08T00:13:28Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed. The clause states how a flake-retry record leaves a CI runner, which the Untouched-test retry bullet left unstated, and ratifies this repository's upload step (livespec-dev-tooling#3702, mngdtf) that went ahead of the spec under R301. A live-state walk found the existing ci.yml step already conforms: it publishes on pass or fail (!cancelled()), skips the incident-omitted job, uses name flake-retries with 7-day retention and if-no-files-found: ignore, and the plugin writes no record file when nothing re-ran. The consumer half (composite action, three consumers) is carried by livespec-dev-tooling-ljea46.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T00:12:45Z
verdict: NO BLOCKERS
proposal_stem: consumer-ci-delivers-no-flake
content_digest: d1192a2e3a1c7b74217771bc9d82e47a902ba10a14608c2e41c7399aa8f50f9a

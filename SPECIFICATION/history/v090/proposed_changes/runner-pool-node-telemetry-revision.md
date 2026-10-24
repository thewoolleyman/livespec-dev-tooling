---
proposal: runner-pool-node-telemetry.md
decision: accept
revised_at: 2026-10-24T02:04:28Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted. The maintainer's 2026-10-24 priority direction (plan kubernetes-node-observability, epic livespec-dev-tooling-dfdiil) requires every k3s pool node's load and utilization in Honeycomb, and no ratified section governed node-level telemetry: the plan's board-and-trigger item livespec-dev-tooling-uftb4o was held at intake because 'Host provisioning tree' cannot grade it. This section is the node-level companion of 'Runner-pool cache telemetry', placed in non-functional-requirements.md because the runner pool is this repository's own infrastructure, with one governing scenario. tests/heading-coverage.json and tests/heading-coverage-debt.json land beside this revise in the same change. Ratification on these exact bytes: Fable NO BLOCKERS (digest 4882c1de, 2026-10-24T02:01:54Z). Reviewer: claude-fable-5-1, a separate read-only Claude Code ratification subagent. Its six non-blocking suggestions are recorded on plan epic livespec-dev-tooling-dfdiil; the debt-register suggestion is taken in this change.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-24T02:01:54Z
verdict: NO BLOCKERS
proposal_stem: runner-pool-node-telemetry
content_digest: 4882c1defff6a7c73e39dc5d972164f86bb62f042b71164bad35575a332a366d

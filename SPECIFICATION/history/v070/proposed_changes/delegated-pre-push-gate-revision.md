---
proposal: delegated-pre-push-gate.md
decision: modify
revised_at: 2026-10-11T05:39:47Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies the consumer-facing contract of the delegated pre-push gate this repository already ships, so work-item livespec-dev-tooling-pj7q4m has a governing specification heading for the factory's Definition-of-Done gate to grade against. The maintainer chose this repository-scoped route on 2026-10-11. It does not revive livespec core's delegated-gate-execution proposal, which was closed unratified on 2026-09-08: it states only what this repository's shipped tooling does for a consumer that opts in.

## Modifications

The ratified text is the round-4, review-fixed form of the filed section, with these changes from the filed proposal: (1) Credential installation now states that a refresh replaces the gates kubeconfig atomically and leaves the replacement with the same owner, group and mode (root, the declared gate-client group, 0640). (2) The green token is recorded only by a green local `just check` that skips no member, run in the pushing worktree, and it lets the pre-push gate skip both paths only while the worktree stays clean. (3) The tests/heading-coverage.json row carries work_item livespec-dev-tooling-pj7q4m and a reason acknowledging the owed test tier, and tests/heading-coverage-debt.json is regenerated mechanically in the same change. The section also anchors "the cluster" (the self-hosted CI pool's Kubernetes cluster provisioned from ci-runner/k3s/) and "the gate mirror" (the cluster's gate mirror, published under a ref named by the HEAD tree's hash), as the independent review asked. Per the revise authoring split (i), three scenarios are added to scenarios.md: local fall-through on an ineligible host (worded so that a gate Job MUST NOT be submitted), completion on a green cluster verdict from an eligible host, and refusal when no verdict arrives. Each has an integration-tier TODO coverage row owned by livespec-dev-tooling-pj7q4m.

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
reviewed_at: 2026-10-11T05:38:40Z
verdict: NO BLOCKERS
proposal_stem: delegated-pre-push-gate
content_digest: bc3626cfe5afe8c2d6e77e84e4d00f9a487555760fd435c944b5783ced065d9b

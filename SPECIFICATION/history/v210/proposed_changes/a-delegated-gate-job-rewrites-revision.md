---
proposal: a-delegated-gate-job-rewrites.md
decision: accept
revised_at: 2026-11-13T11:20:12Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted unchanged after legacy-coordinator-agent's grade (proposal commits 0d5ab983a and 69e79729f on master). Every fact it cites still holds on master: ci-runner/k3s/phase2/gates/gate-job-template.yaml's rewrite_lock_through_pypi_proxy rewrites each uv.lock in place, and the ratified Untouched-test retry bullet (non-functional-requirements.md, Testing approach) counts unstaged working-tree differences in the change set, so the pod-local rewrite withholds every flake retry in every delegated gate the template serves. The new Tiers sentence requires a gate Job that routes any lockfile's locked artifacts through a host-served cache to leave every tracked file unmodified as git compares the working tree with the index and HEAD: the rewrite is made outside the tree (preferred) or hidden by a mechanism that keeps the hidden files' index and HEAD contents equal to the pushed tree's. Two scenarios cover it: an untouched failing test is still retried, and a pushed uv.lock change is still reported with the pushed bytes. Their heading-coverage TODO rows are owned by livespec-dev-tooling-o4hkgh, the work item carrying the fix (plan fleet-flaky-tests, epic livespec-dev-tooling-zwveqp). Decided under delegated revise_decision_mode with an independent read-only sonnet ratification review returning NO BLOCKERS on the exact bytes.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T11:19:31Z
verdict: NO BLOCKERS
proposal_stem: a-delegated-gate-job-rewrites
content_digest: a389d756deb5b7d00024498ac88a678fc456b1c03dfd112c0c331d501ec4eb89

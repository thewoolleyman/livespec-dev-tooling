---
proposal: pin-walk-exclusion-section-scope.md
decision: modify
revised_at: 2026-10-30T20:12:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Fixes the false claim that the fabro-sandbox container-image surface and the uses: format scan the same files, fixes the literal reading under which the nested-repository exclusion would exclude the walk root, and states the exclusion once for every format whose scan set descends beyond fixed paths. Decided under delegated revise_decision_mode by the delegated-gate-fleet-rollout seat.

## Modifications

Part (a)'s any-depth DIRECTORY hoist is dropped: the shipped walk (cross_repo/_pin_directory_scan_formats.py) recurses only in _workflow_uses_files, while the workflow.toml and container-image walks read fixed root paths, so hoisting any-depth to every format would widen two scan sets, contradicting the proposal's own non-goal. The nested-repository exclusion is hoisted to the preamble scoped to formats that descend beyond fixed paths (today only uses:), with the walk root's own .git explicitly not excluding the root, matching the code. Part (c) is applied but corrected: the container-image surface reads only the repository-root .github/workflows/ *.yml / *.yaml.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-30T20:02:36Z
verdict: NO BLOCKERS
proposal_stem: pin-walk-exclusion-section-scope
content_digest: 33e68e21f71f9981ed260a250d22716a691a91822111b54e216b1cce8c152bea

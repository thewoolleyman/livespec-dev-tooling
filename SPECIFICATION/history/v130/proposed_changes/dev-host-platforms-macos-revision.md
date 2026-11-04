---
proposal: dev-host-platforms-macos.md
decision: modify
revised_at: 2026-11-04T14:39:09Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

All three proposals restate measured MacBook Air Stage 0 facts (plan homelab-k8s-worker-nodes, epic livespec-dev-tooling-ko26ez) as contributor-workflow requirements beside the existing NFR sections, with a scenario per behaviour clause, and amend the one contracts.md bullet they would otherwise contradict. Open design choices (resume vs no-verdict after an interrupted wait; how a stall is reported) stay SHOULD.

## Modifications

Bootstrap scope: replaced the citation `each ledger pointer file that AGENTS.md §"Beads runtime prerequisites" requires` with `each ledger pointer file a checkout needs to reach its ledger tenant`, because a §-citation to a non-specification file fails doctor's no-cross-spec-reference check. The six paragraphs of the new NFR section are ordered Platforms, Host toolchain sources, Bootstrap scope, Gates on a non-Linux host, A gate always ends with a verdict, Ledger reach.

## Resulting Changes

- non-functional-requirements.md
- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T14:34:46Z
verdict: NO BLOCKERS
proposal_stem: dev-host-platforms-macos
content_digest: e74bca3c66e8ddb6f0a2ed6292a1a6252ab44578e4a27e86686fa7ab9c972ae0

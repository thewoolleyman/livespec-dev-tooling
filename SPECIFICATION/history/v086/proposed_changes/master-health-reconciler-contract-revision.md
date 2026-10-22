---
proposal: master-health-reconciler-contract.md
decision: modify
revised_at: 2026-10-22T14:37:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Adopted: this realizes, without changing, the master-health policy livespec core ratified at v224 (non-functional-requirements.md, CI as a merge gate). This repository ships the reconciler module, but no heading in its own governed tree stated its decisions, so the R316 launch-time Definition-of-Done preflight refused livespec-dev-tooling-joqff6 on two independent judges (its reference governed none of its assertions). Decided under delegated revise_decision_mode by claude:delegated-gate-fleet-rollout, which owns joqff6's launch under coordinator R621/R623. MODIFIED from the proposal text in three mechanical ways: scenarios reformatted to this file's blank-line-separated Given/When/Then style; the core citation reworded to plain prose; and the tests/heading-coverage.json co-edit (15 TODO rows, each owned by the open item that owes its test: joqff6, 4xrhck, yilv6p, reslr6, or epic zcp5vb for the already-built core decisions) plus the mechanically regenerated debt register. Independent read-only ratification review (fable) found NO BLOCKERS on these exact bytes. Its non-blocking notes are carried forward to the implementing items: the 120-minute default must be a provisioning default written into committed configuration, not a code fallback that would defeat fail-closed; one definition of 'release'; and core obligations this section omits without contradicting (culprit-PR link, re-land naming, token split, re-measure before tightening).

## Modifications

Scenarios reformatted to the file's blank-line-separated Given/When/Then style. Core citation reworded from a section-sign citation to plain prose naming the subsection and livespec v224. Added 15 tests/heading-coverage.json TODO rows (one per new H2 and scenario) and regenerated tests/heading-coverage-debt.json with .

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
reviewed_at: 2026-10-22T14:37:22Z
verdict: NO BLOCKERS
proposal_stem: master-health-reconciler-contract
content_digest: e6e9690a78e6eecd6ae8115ae70181cea6f474b670fcf19fb92ebf59ef18b78a

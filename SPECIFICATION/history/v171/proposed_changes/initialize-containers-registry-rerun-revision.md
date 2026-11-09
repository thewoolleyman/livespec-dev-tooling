---
proposal: initialize-containers-registry-rerun.md
decision: modify
revised_at: 2026-11-09T19:49:41Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:ci-runtime-and-cost
---

## Decision and Rationale

Modified and accepted. The maintainer approved this re-run on 2026-11-09 at about 09:1xZ (recorded on plan epic livespec-dev-tooling-ib3oe3) as an extension of the fleet's no-rerun rule. The signature is pre-code by construction: Initialize containers runs before checkout, so no test or build failure can be retried. Placement follows the boundary litmus: the re-run policy is a contributor concern beside the ratified Set up job 429 rule, and the reusable reconciler is a wire contract in contracts.md. The behaviour carries a BCP14 clause and its own scenario. This topic is distinct from a-ci-job-that-fails (v124, cetyrq), so khlrw3's spec-change hold can clear on re-judgement. One modification was needed (see Modifications). The independent sonnet review of the modified bytes found no blockers.

## Modifications

The proposal added `reusable-ci-infra-rerun.yml` as a bullet of contracts.md §"Reusable workflows wire contract"'s list introduced by "The library MUST ship at minimum one reusable workflow:". That list is the minimum SHIPPED set, and tests/consumer/test_semver_stable_surface.py resolves every bullet of it to a file under .github/workflows/. The reconciler is not built yet (livespec-dev-tooling-khlrw3 builds it, after cetyrq), so the accept-as-written cut failed that test in its pre-push gate (gate 20261109T192228Z-1065130, check-per-file-coverage) and would have made the list assert a shipped workflow that does not exist. The modification keeps the contract in the same section, as its own paragraph after the list: "The CI infrastructure re-run reconciler is specified ahead of its realization, so it is not yet a member of the minimum shipped set above. When the library ships it, it MUST ship as `reusable-ci-infra-rerun.yml`, with this contract." The proposal's contract text follows verbatim from "Trigger:". The revise that records the reconciler as shipped moves it into the list. The non-functional-requirements.md paragraph and the scenario are the proposal's text unchanged.

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
reviewed_at: 2026-11-09T19:47:56Z
verdict: NO BLOCKERS
proposal_stem: initialize-containers-registry-rerun
content_digest: 3db3f308626b1b517ae6d9e25a5ac3a9f20a598e30956c5f0765e6d642443751

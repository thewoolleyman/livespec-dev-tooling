---
proposal: shell-pipeline-verdicts-every-tracked-script.md
decision: accept
revised_at: 2026-11-07T18:27:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). The delegated decider is the plan session for fleet-flaky-tests (epic livespec-dev-tooling-zwveqp). The directory list is what let homelab-worker/ escape the rule: the clause and its sweep named four directories, so no gate saw the early-exiting readers added there, and two flakes followed, livespec-dev-tooling-nzzyli and livespec-dev-tooling-y53wpo. Removing the list ratifies what tests/test_pipefail_reader_sweep.py already enforces since livespec-dev-tooling#3692. That order reversed this repository's usual one and is named in the proposal; it was safe because the sweep is local to this repository's tests and the same change rewrote all 29 readers, so it armed against a clean tree. This changes one sentence of the clause and no heading. The existing scenario stays as written, because its ci-runner/ script is an example of the rule and does not scope it. No design record is contradicted, and this is not a drift-origin proposal. Separate read-only sonnet review: NO BLOCKERS at 2026-11-07T17:32:33Z, and the digest recomputed over the rebased bytes is unchanged.

## Resulting Changes

- non-functional-requirements.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-07T17:32:33Z
verdict: NO BLOCKERS
proposal_stem: shell-pipeline-verdicts-every-tracked-script
content_digest: 58a7664af822bdbfd582e086d208deab9bab02fdfe49ed938f7f59efd8fb7fc8

---
proposal: cvstale-reclassify-workflow-check.md
decision: accept
revised_at: 2026-06-02T16:27:24Z
author_human: E2E Test <e2e-test@example.com>
author_llm: livespec-implementer (epic li-cvaudit / li-cvstale)
---

## Decision and Rationale

User has pre-approved this exact reclassification (epic li-cvaudit / li-cvstale). Reclassify no_stale_revise_branches from a per-commit canonical check into a revise-workflow check living under livespec_dev_tooling/workflow_checks/, removing it from the just check aggregate and the wiring-completeness invariant, and eliminate the --allow-stale-branches downgrade carve-out (the revise pre-step is the sole caller and fails hard on stale branches).

## Resulting Changes

- contracts.md

---
proposal: spec-amendments-from-doctor-followup-findings.md
decision: accept
revised_at: 2026-05-27T06:35:47Z
author_human: E2E Test <e2e-test@example.com>
author_llm: claude-opus-4-7
---

## Decision and Rationale

Six spec-side reconciliations from the 2026-05-26 /livespec:doctor LLM-objective + LLM-subjective pass: reconcile the constraints tools list (mise vs ruff/pyright/pytest/git), define the v1 temporal token once in spec.md §"Project intent", normalize check identifier naming in NFR to bare-slug canonical form, reconcile §"Shared check inventory" with the actual livespec_dev_tooling/checks/ tree (drop 4 never-materialized slugs, rename tools→check_tools and coverage→both per_file_coverage + check_coverage_incremental, add 8 new modules), add sys.path.insert to the coverage exclude_also exact list, and relocate the consumer-observable CI matrix shape rule from NFR §"Hooks and CI" to a new constraints.md §"CI matrix shape" per the NFR boundary rule.

## Resulting Changes

- contracts.md
- spec.md
- non-functional-requirements.md
- constraints.md

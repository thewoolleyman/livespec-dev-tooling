---
proposal: the-incident-fleet-audit-cannot.md
decision: accept
revised_at: 2026-11-09T23:14:28Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:expedited-incident-response-flag
---

## Decision and Rationale

Accepted as filed. contracts.md §"Expedited incident execution" required a fleet audit that expands core's committed manifest, gives every incident surface and consumer an implemented, deliberately-normal or not-applicable disposition, and carries serving-version evidence before incident use is enabled, but stated no runnable command, no per-row output, no non-zero exit for unclassified rows or an unauthenticated manifest, no ready list, and no enablement step that reads one. livespec-dev-tooling-3wcldx's Definition of Done asserts exactly those, so its 2026-11-07 filing verdict was spec-change tier (partial). The accepted paragraph adds only what the ratified text lacked: an operator-invoked local-vantage recipe `just incident-fleet-audit` (no CI check, no run lever, matching ensure-plugins-fleet and adopt-orchestrator-build) reading the manifest as §"Sibling discovery" reads it; one printed row per surface and consumer with an unclassified disposition for missing, contradictory, stale, foreign-identity or unauthenticated evidence; evidence readers that read serving versions from installed consumers and the running controller; a non-zero exit naming every unclassified row; the unauthenticated-manifest report with zero ready repositories; a ready list that excludes any consumer lacking verified serving-version evidence for gate readers, templates, driver hooks, recovery authorization or the independent controller; and a single enablement step that reads a fresh audit's ready list and refuses a missing repository by name. The 37-row inventory, the three dispositions and the ship-release-adopt-prove-then-enable ordering are unchanged. One scenario states the command and the enablement refusal. legacy-coordinator-agent ruled on 2026-11-09 (~22:45Z) that plan assertion 13 is read fleet-wide, keeping 3wcldx a carrier of plan expedited-incident-response-flag, and claimed v174 for this topic. Independent review (sonnet, 2026-11-09T23:13:35Z) reported NO BLOCKERS over the exact bytes; its non-blocking notes (the enablement step is not yet named as a recipe; the scenario does not exercise every unclassified trigger or the caller-supplied ready-list refusal, which the owed integration test can cover) are left to the implementation. The heading-coverage co-edit (spec-first TODO owned by livespec-dev-tooling-3wcldx, registered in the debt register) rides in the revise commit.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T23:13:35Z
verdict: NO BLOCKERS
proposal_stem: the-incident-fleet-audit-cannot
content_digest: a5d6ac9f495db2731bce04d6777d4758def2a2445467f89ad197e653d72a9629

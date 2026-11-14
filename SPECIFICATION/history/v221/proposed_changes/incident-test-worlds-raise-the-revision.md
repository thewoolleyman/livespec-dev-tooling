---
proposal: incident-test-worlds-raise-the.md
decision: modify
revised_at: 2026-11-14T15:10:42Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:expedited-incident-hardening
---

## Decision and Rationale

Ratified under delegated decision. legacy-coordinator-agent graded livespec-dev-tooling#4631 PASS at 79a82ef83 and ordered this revise after v218 (2026-11-14). It releases livespec-dev-tooling-vm4vcn's spec-change-tier hold: a test world raises the product child-process bounds it reaches to the hang guard, keeping their orderings, and a wrong refusal fails naming its code. Re-cut as v221 (2026-11-14): the first cut was v219 on livespec-dev-tooling#4670 (f99c6ee09, graded PASS at 1098f40e0). legacy-coordinator-agent ordered livespec-dev-tooling#4668 to land v219 and v220 first, so the same edits were re-applied unchanged onto master e51adb8f3 and independently reviewed again against the new bytes.

## Modifications

Three changes from a doctor-style walk of the drafted text through the live code (2026-11-14), each reported to legacy-coordinator-agent. (1) The bullet opens by naming the hang guard of the bullet above. (2) The ordering clause adds that the incident git fetch timeout stays above the incident git timeout (test_incident_git.py asserts it), and that the world derives each raised value from the hang guard so every ordering holds at once. (3) The scenario's ordering Then compares the incident git timeout with the timeout of the inverse forge the recovery principal runs, and adds the fetch ordering.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T15:10:01Z
verdict: NO BLOCKERS
proposal_stem: incident-test-worlds-raise-the
content_digest: fee49d25865fbdb817833813cea45b991d9ead8665e2303b3f3fa01d0a93e27d

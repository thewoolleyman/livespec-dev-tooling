---
proposal: merge-group-incident-admission.md
decision: modify
revised_at: 2026-11-16T21:20:59Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Modified, not accepted as filed. The design was ruled by throughput-plans-coordinator (spec first, 01:3xZ 2026-11-16) and graded PASS-WITH-FIXES, with all seven fixes applied before ratification (livespec-dev-tooling#4834). The required independent review of the final bytes found one real defect, a MUST NOT that contradicts the shipped gate's required observer reads, plus a missing statement that the ancestor test is replaced on merge_group. Both are corrected, and the review then returned NO BLOCKERS on the corrected bytes. The behaviour is spec first: the implementation (livespec-dev-tooling-txon2s) is built and follows this ratification, and each of the three scenarios carries a spec-first TODO row owned by txon2s.

## Modifications

Two edits to the proposed contracts.md text, both from the independent ratification review's finding on the exact bytes. (1) The last bullet 'Labels and incident environment variables MUST NOT be read' contradicted the shipped gate, which must read LIVESPEC_INCIDENT_OBSERVER_URL and LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN to query the observer's provenance route; it now says labels and the incident-activation variables MUST NOT be read to grant admission, the observer endpoint and query-credential variables MAY be read only to query that route, and an unset or unusable one keeps the commit convicted. (2) The first sentence now states that on a merge_group event the patch-id match replaces the pull_request-event test that the commit is an ancestor of the recorded head, because a rebased copy is never one. The three scenarios are unchanged.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-16T21:20:52Z
verdict: NO BLOCKERS
proposal_stem: merge-group-incident-admission
content_digest: 9266a43bb5bff024e4c8d02fe3b84c76d11006afc672056e77541d72519b83d3

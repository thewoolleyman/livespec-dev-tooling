---
proposal: dev-host-no-data-triggers.md
decision: accept
revised_at: 2026-11-13T19:10:46Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written at the same v214 slot. The spec-change tier record on livespec-dev-tooling-exx6f5 (spec v212) found no clause requiring a no-data trigger for a role-stamped host: the dev-host value triggers of livespec-dev-tooling#4542 are grouped by host.name, so a host that stops exporting leaves no group and fires nothing, the failure shape of the 2026-11-13 ~15:32Z vmi3006760 outage. The new paragraph applies the ungrouped per-subject dead-man pattern §"Runner-pool node telemetry" already requires for pool nodes. The independent reviewer noted that `livespec.host.role` and the dev-host value triggers it refers to are not yet named in the spec; the paragraph is conditional on a committed collector shape stamping a role, which otel-collector's dev-host shape (marker 0.14) does today, so it stays coherent.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T19:10:23Z
verdict: NO BLOCKERS
proposal_stem: dev-host-no-data-triggers
content_digest: 8191714aa8d88c903648fba016c719a307a5aa0dbe2e7e16ca36b35862b5bacc

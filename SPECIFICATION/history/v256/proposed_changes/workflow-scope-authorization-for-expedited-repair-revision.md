---
proposal: workflow-scope-authorization-for-expedited-repair.md
decision: accept
revised_at: 2026-11-19T22:18:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: expedited-incident-response-flag-session
---

## Decision and Rationale

Accepted as filed. The incident commit hook refuses every .github/workflows path in expedited-repair mode because no authority record can carry a workflow scope (measured 2026-11-17 on incident ypvfll). The amendment states who may write the scope (a maintainer-attested receipt only), what the hook checks (exact path listed, attestation current for the attempt generation) and the refusal it names, per the coordinator's option A ruling on research note 008. One scenario states the behavior; the heading-coverage row owned by livespec-dev-tooling-jtuxzn is co-edited in the commit. No design-record contradiction. Independent sonnet review: NO BLOCKERS on digest 9415f21672349753302b5471f21eb489ff390f31857792cc3eadae67afe5835f. Non-blocking note carried to jtuxzn: the clause should be implemented so a commit with any unlisted workflow path is refused as a whole.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-19T22:17:52Z
verdict: NO BLOCKERS
proposal_stem: workflow-scope-authorization-for-expedited-repair
content_digest: 9415f21672349753302b5471f21eb489ff390f31857792cc3eadae67afe5835f

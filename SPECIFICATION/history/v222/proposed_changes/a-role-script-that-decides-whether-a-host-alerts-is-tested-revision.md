---
proposal: a-role-script-that-decides-whether-a-host-alerts-is-tested.md
decision: accept
revised_at: 2026-11-14T17:00:10Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Plan dev-host-disk-retention (livespec-dev-tooling-qgwxo4), revise-queue slot 2 as legacy-coordinator-agent ruled (after v221). Proposal 1 is route (i) for livespec-dev-tooling-ba7ypx: the reconcile staleness dead-man decided whether the dev host pages, and no committed test held its nine alert states. Proposal 2 folds in livespec-dev-tooling-l7f72q, also coordinator-ruled: a role-installed unit's OnFailure= reached the operator as "dolt-backup run failed" on 2026-11-14. Conformance at revise time: the only two OnFailure= lines in ansible/ (honeycomb-trigger-recipients-check.service.j2:8 and reconcile-runs-staleness.service.j2:5) route to host-unit-alert@ on master since livespec-dev-tooling#4678, and that route is live on vmi3006760. Proposal 2's committed test, tests/livespec_dev_tooling/test_host_unit_alert.py, is on master. Proposal 1's staleness test is owed by ba7ypx. The coordinator graded the proposal PASS (livespec-dev-tooling#4681, merged a53dfa1a8). No design record is contradicted: both paragraphs govern roles in the provisioning tree, which this section already scopes.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T16:59:16Z
verdict: NO BLOCKERS
proposal_stem: a-role-script-that-decides-whether-a-host-alerts-is-tested
content_digest: eb751f492586ff8153ecbcd2f86cc17614ed1e9a723a6f7af27ec9aa34214687

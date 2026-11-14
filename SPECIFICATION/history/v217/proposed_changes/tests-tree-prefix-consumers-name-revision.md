---
proposal: tests-tree-prefix-consumers-name.md
decision: accept
revised_at: 2026-11-14T07:21:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed under delegated revise authority, in the v217 revise slot legacy-coordinator-agent assigned to the fleet-flaky-tests seat (plan fleet-flaky-tests, epic livespec-dev-tooling-zwveqp) after v216 merged. This is an internal-consistency repair: contracts.md's no_ambient_environment_loops section requires the check to walk files under tests_tree_prefix, but the role key's Consumers inventory did not name it, so tests/spec/test_role_key_consumer_inventory.py refused the check's implementation (livespec-dev-tooling-dpkz32). The replacement is applied word for word from the proposal against post-v216 contracts.md; the list stays alphabetical. No '## ' heading changes, so no heading-coverage co-edit is owed. The independent sonnet reviewer recomputed the content digest and reported NO BLOCKERS with no nits. The spec edit lands in the same commit as dpkz32's check. Other pending proposals are left in place by this single-topic pass.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T07:20:46Z
verdict: NO BLOCKERS
proposal_stem: tests-tree-prefix-consumers-name
content_digest: 08bd69511bffed4601326a50177f7f20f43ddca2259c85bca1eceb3068d1a90e

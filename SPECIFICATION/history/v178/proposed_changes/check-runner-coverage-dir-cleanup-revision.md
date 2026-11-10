---
proposal: check-runner-coverage-dir-cleanup.md
decision: accept
revised_at: 2026-11-10T03:19:47Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:dev-host-disk-retention
---

## Decision and Rationale

Accepted as written. The dev-host-disk-retention plan (livespec-dev-tooling-qgwxo4) measured on 2026-11-09 that 122 covns-full-tree-* and 16 covns-incremental-* directories, about 3.0 GiB in total, had leaked into the dev host's shared /tmp tmpfs. They came from check runners killed by SIGTERM or SIGHUP. Those runners create the directories in build_namespace_dirs and remove them only in a finally block, and Python's default action for either signal skips that block. No clause stated the lifecycle, so the pre-dispatch screen refused the fix item livespec-dev-tooling-8o8e.16, whose only reference did not govern the runners. Placement follows the boundary litmus. Check runners are contributor-only enforcement tooling, so the paragraph sits in non-functional-requirements.md section Enforcement-suite invocation, beside the coverage target's own obligations. It carries BCP14 clauses and its own scenario. SIGKILL is excluded explicitly because no process can act on it. The clause fits the gate runner's stall kill. That kill sends SIGTERM first and gives a grace period before SIGKILL, per sibling proposal stall-kill-reaches-every-descendant (livespec-dev-tooling-5lhafp), and that grace period is when this clause's cleanup runs. An independent sonnet review of these exact bytes found no blockers (2026-11-10T03:17:52Z). livespec-dev-tooling-8o8e.16 implements the change and owns the scenario's owed test.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T03:17:52Z
verdict: NO BLOCKERS
proposal_stem: check-runner-coverage-dir-cleanup
content_digest: 21c0b53187aa084690ec6411d97394075bcaee6af47499cef77fbe85ae14289f

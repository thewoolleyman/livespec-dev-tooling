---
proposal: git-object-seed-checkout-scoped-alternate.md
decision: accept
revised_at: 2026-11-04T08:44:24Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:ci-cache-optimization
---

## Decision and Rationale

Accept, decided by legacy-coordinator-agent under the delegated decision mode (R301, 2026-11-04). The v127 clause named the seed in the job container's GIT_ALTERNATE_OBJECT_DIRECTORIES. When it went live on 2026-11-04 the variable reached every git process in a seeded job. Five tests/livespec_dev_tooling/test_git_object_seed.py tests failed on seeded runners (PR #3364, run 41787616531), four orchestrator test_needs_human_stage_cause_and_open_red_gate.py tests read the wrong commit SHA from their own temporary repositories, and PR #3348 was reverted (#3366, 28b206f5). The clause now attaches the alternate to the checkout repository's own object store only, forbids naming the seed in the job environment, and requires a repository the job creates outside its checkout to resolve only its own objects. The governing scenario is amended to match. No H2 heading changed, so tests/heading-coverage.json is untouched. The stale-branch precondition was skipped with --skip-stale-branch-check: the flagged branches are this pass's own branch, an open proposal on a disjoint section (#3368), and spec/revise-expedited-incident-response, whose content landed as v125. Rollout note carried by livespec-dev-tooling-qyrmwe: the re-land ships its hook as a new versioned ConfigMap key and never edits or removes a key a live pod mounts, behind livespec-dev-tooling-4oeffe. The independent review raised no blockers.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T08:43:45Z
verdict: NO BLOCKERS
proposal_stem: git-object-seed-checkout-scoped-alternate
content_digest: c0eab4aa504affce14833c9aaac14eea7c8092b9f25615bc895fb7f18ec8cdb8

---
proposal: install-worktree-pack-first-hook-command.md
decision: accept
revised_at: 2026-09-06T05:28:59Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5-1 (optimize-gates plan session, Claude Code)
---

## Decision and Rationale

Accept: amend §"Hooks and CI" so the lefthook ordering this repository MUST mirror matches livespec v219 (contracts.md §"Pre-commit step ordering"): pre-commit `00-install-worktree-pack`, `01-lint-autofix-staged`, `02-commit-pairs-source-and-test`, `03-check-pre-commit`; pre-push `00-install-worktree-pack` then `01-check-pre-push`; the installer MUST be idempotent, MUST write only ignored files, MUST NOT relax the byte-identity verifier, and no pack-reading hook command MAY precede it. Design record: livespec v219 and the optimize-gates research note §3(d) (epic livespec-xms725, rollout child livespec-ltthxr). The count word "three-stage" and the stale zero-`.py` pre-push subsetting claim are dropped (this repository's `check-pre-push` runs the full aggregate behind the green-token memoization). One replace target, verified verbatim exactly once; resulting text derived mechanically from the proposal's own hunk; no `## ` heading changed (17 H2 lines before and after, counted as lines beginning `## `), so no tests/heading-coverage.json co-edit. Independent read-only review by the configured fable ratification reviewer returned NO BLOCKERS on these exact bytes at 2026-09-06T05:09:39Z (reviewer: a separately spawned read-only agent named ratification-reviewer-dt-install-worktree-pack-first, self-reported model "Fable 5.1 (claude-fable-5-1)", digest independently recomputed and matching; two non-blocking nits recorded: constraints.md line 37's CI zero-`.py` subsetting claim is stale versus livespec v217 and belongs to a separate proposal, and the justfile comment near `check-pre-push` still mentions doc-only subsetting, an implementation follow-up).

## Resulting Changes

- non-functional-requirements.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-06T05:09:39Z
verdict: NO BLOCKERS
proposal_stem: install-worktree-pack-first-hook-command
content_digest: 389541a1bba4054d7c7cb86f9e387755fb3a07a29cf6cd62af174e31c64db64b

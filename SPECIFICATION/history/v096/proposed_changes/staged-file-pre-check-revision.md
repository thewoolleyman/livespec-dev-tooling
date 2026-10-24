---
proposal: staged-file-pre-check.md
decision: modify
revised_at: 2026-10-24T22:34:24Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with modifications. Work-item livespec-dev-tooling-nil6v7 (plan livespec-dev-tooling-dfixhe, assertion 14; maintainer direction 2026-10-24) needs a governing clause for a seconds-scale staged lint and type pre-check at the head of `just check-pre-commit`. Factory run 01M5QNH88NHN68ST28Y80CZJ48 waited 711 s for a refusal its own lint and type members could have given in seconds. The pre-check sits INSIDE `just check-pre-commit`, so the lefthook ordering this repository mirrors from livespec contracts.md §"Pre-commit step ordering" is untouched. It refuses nothing the aggregate's lint and type members would not refuse; it moves those refusals earlier. No design record is contradicted. The two scenarios carry the DoD's refusal and timing bullets; their coverage entries are spec-first TODOs owed by nil6v7, and the debt register is regenerated, not hand-edited.

## Modifications

M1 (independent fable ratification review, blocker B1): the proposal's closing sentence promised a consumer-callable shared module, which contracts.md §"CLI surface" forbids for an unenumerated module, in a file §"Boundary" does not allow for CLI surface. It is replaced by a reference to a new third workflow-check kind in contracts.md §"Shared check inventory", **Commit-hook checks**, with member `staged_precheck`, invoked as `python -m livespec_dev_tooling.workflow_checks.staged_precheck` (already in §"Semver discipline" as `workflow_checks.<slug>`, outside the canonical aggregate, per-consumer opt-in; exits 4 on findings). The "lint is NOT shipped as a module" sentence gains a carve-out. M2: both scenarios end "the full pre-commit aggregate MUST NOT have started any member" (was a vacuous "no member ... MUST have started"). M3: the 60-second bound for ten staged files is stated in the clause, not only in the scenario. M4: "added or modified Python files", matching the hook's existing `--diff-filter=AM`.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-24T22:30:57Z
verdict: NO BLOCKERS
proposal_stem: staged-file-pre-check
content_digest: 0ba95a7fdf2e7ace49e5239cc613abfd55a4444e712bce1d90e2cae91fc3d014

---
proposal: incident-focused-changes-reads-bypass.md
decision: modify
revised_at: 2026-11-13T14:00:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified, as the coordinator's queue slot for rgiufy (ruled ~09:38Z 2026-11-13: v209, o4hkgh, dqndbz as v211, then rgiufy). The proposal was graded PASS-WITH-FIXES by legacy-coordinator-agent on livespec-dev-tooling#4482 with exact replacement text, and that text lands verbatim. It merged at 2026-11-13T09:30:21Z as 3edc1eac8. Every defect it names is still in livespec_dev_tooling/incident_focused_changes.py on master 84dccf8f1: the changed set is read through run_git and git_text, not IsolatedGit; a mode-120000 entry passes through as its link text; and a submodule gitlink makes cat-file --batch report missing, so the header parse raises IndexError. The clause lands in contracts.md, Expedited incident execution, because it is a user-observable wire contract of the per-pull-request arm. Its scenario lands in scenarios.md beside the other incident scenarios.

## Modifications

One spec-first sentence is appended after the inserted contracts.md text: "These sentences are spec-first: `livespec_dev_tooling/incident_focused_changes.py` still reads the changed set with plain git commands against the reference clone, judges a symbolically linked `.py` by its link text rather than by its target, and fails on a submodule gitlink with `list index out of range`, and work item livespec-dev-tooling-rgiufy owns the change." Without it, the clause would assert a conformance the tree does not have. That is the same ground legacy-coordinator-agent made binding when grading v211 (livespec-dev-tooling#4518, PASS-WITH-ONE-FIX).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T14:00:07Z
verdict: NO BLOCKERS
proposal_stem: incident-focused-changes-reads-bypass
content_digest: 9ced56d59d0b43ebaac9621489980693fe18735ef87a7d290477b24902cd15f3

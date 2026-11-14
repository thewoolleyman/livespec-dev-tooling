---
proposal: isolatedgit-s-object-view-still.md
decision: modify
revised_at: 2026-11-14T15:10:42Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:expedited-incident-hardening
---

## Decision and Rationale

Ratified under delegated decision. legacy-coordinator-agent graded livespec-dev-tooling#4631 PASS at 79a82ef83 and ordered this revise after v218 (2026-11-14). It releases livespec-dev-tooling-a3xotn's spec-change-tier hold: every incident scope read from a reference clone goes through one isolated view construction that honours no commit-graph and refuses an alternates file by name. Re-cut as v221 (2026-11-14): the first cut was v219 on livespec-dev-tooling#4670 (f99c6ee09, graded PASS at 1098f40e0). legacy-coordinator-agent ordered livespec-dev-tooling#4668 to land v219 and v220 first, so the same edits were re-applied unchanged onto master e51adb8f3 and independently reviewed again against the new bytes.

## Modifications

Four changes from a doctor-style walk of the drafted text through the live code (2026-11-14), each reported to legacy-coordinator-agent. (1) 'one isolated object view' becomes 'the same isolated object view construction', because build_inverse opens a fresh view per call. (2) The commit-graph clause says the view disables it in its own fresh administration's configuration. (3) The list of reads adds the original-run watch's and the original-run measurement's merge-base and ancestry reads, which today read the reference clone through plain git (incident_original_run_watch.py and _incident_original_run_measure.py). (4) A spec-first sentence names livespec-dev-tooling-4xpwx7, filed 2026-11-14 as a child of plan expedited-incident-hardening, as the owner of moving those two readers onto the view. a3xotn's own scope is unchanged.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T15:10:01Z
verdict: NO BLOCKERS
proposal_stem: isolatedgit-s-object-view-still
content_digest: 090ffa155bfeda455cbcf48cc6c650173e425cc2b050b8b365b018e45c1260dc

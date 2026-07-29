---
proposal: role-key-consumer-enumerations-are-wrong-in-both-directions.md
decision: accept
revised_at: 2026-07-29T01:46:50Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

ACCEPTED, all three proposals, under the maintainer ruling of 2026-07-29 delegating the accept/reject decision at revise to this thread (the same delegation recorded in the v034 revision). No proposal was re-litigated; each was applied as filed.

Every correction in this revision was MEASURED against the shipped code rather than read, by enumerating the modules under `livespec_dev_tooling/checks/` that read `config.<key>`. That method matters here more than usual: the defect being corrected is precisely a set of claims about code that nobody re-derived, so accepting them on a reading would have reproduced the failure inside its own fix.

Proposal 1 (define what the enumerations mean) is accepted and was deliberately filed FIRST, because without it the other two are a data refresh rather than a durable fix. Two checks — `partition_completeness` and `source_trees_scoped_to_consumer` — read nearly every role key structurally, so the lists had two defensible readings that produce different answers for every key, and two authorities in this repo already disagreed because of it: this repo's own `pyproject.toml` comment counts `partition_completeness` as one of `supervisor_entry_files`' consumers, while the spec's list did not. The ratified preamble names both meta-checks as excluded BY RULE, so their absence reads as a decision rather than an omission.

Proposal 2 (three wrong enumerations) is accepted. The defect runs in BOTH directions and the two halves fail differently. An UNDER-report (`supervisor_entry_files` naming one consumer of four; `commands_trees` omitting one) understates the blast radius of a declaration — the bulk-declaration hazard this thread refused to take when it declined to declare nine supervisor files to silence one check. An OVER-report (`io_trees` naming `public_api_result_typed` and `no_write_direct`, neither of which reads the key) is the more dangerous half: it documents an exemption that does not exist, so a repo declaring the key gets a relaxation it never receives. That is the same manufactured-confidence shape as a check that scans zero files, relocated into the schema documentation.

The `supervisor_entry_files` entry additionally gained an explicit statement that one declaration grants ALL FOUR exemptions, with each named. This was not in the filed proposal as a MUST but was filed as a SHOULD, and is applied because the four-exemption fact is the single most consequential thing a consumer needs before editing that key, and it existed only in this repo's `pyproject.toml` comment — a file no other consumer reads.

Proposal 3 (the `source_trees` requirement classes) is accepted. Five of the checks the entry named as requiring the key do not read it, and three real readers were named nowhere. It was nearly missed because it uses a different sentence shape ("Required for every check in the X class") than the "Consumed by" phrasing known to be wrong, so a search for the known-bad wording would not have reached it; it was found by re-reading the whole section. The removals are stated with the key each check ACTUALLY reads, so the correction redirects the reader rather than leaving a gap, and the entry now says explicitly that all five still run — only the supplying key differs.

Two entries were measured CORRECT and deliberately left untouched: `pure_trees` (`public_api_result_typed`, `pbt_coverage_pure_modules`, `check_mutation`) and `covered_trees` (`no_write_direct`, `no_lloc_soft_warnings`). This is recorded so a later editor does not assume the whole section was wrong and re-derive them — and because a method that only ever deflates what it touches is not measuring.

Authoring-discipline split (i) was considered and does NOT apply: no proposal introduces load-bearing behavior. All three correct the spec's ACCOUNT of what shipped checks already read, and the one new normative clause (a check that changes its role-key reads MUST update that key's list) is an authoring obligation on spec editors, not an observable implementation input-to-output. No `scenarios.md` entry is therefore owed, and none was added.

The intent-preservation gate did not fire: no proposal resolves a conflict between ratified statements, and none departs from a cited design record.

Process note: the Step 3.5 stale-branch precondition was SKIPPED with `--skip-stale-branch-check`, narrated here rather than taken silently. It flags any local `spec/*` branch ahead of `origin/master`, which includes this revise pass's OWN branch (`spec/supervisor-entry-files-consumers`, one commit ahead — the filing commit `2abfc48`). It cannot distinguish an abandoned `spec/*` branch from the branch the revise is currently running on. The same override would also mask a genuinely abandoned branch, so it is recorded: at the time of the override the repo had exactly one local `spec/*` branch and zero remote ones (verified by `git ls-remote --heads origin 'spec/*'` returning empty during the propose-change in-flight survey).

Out-of-target, recorded so it is not lost: this repo's own `pyproject.toml` comment on `supervisor_entry_files` says the key grants FOUR exemptions and lists them, which was correct when written and is now stale by one — PR #816 added `public_api_result_typed` as a fifth reader. That comment sits outside the spec target and is corrected as implementation work accompanying this revision.

## Resulting Changes

- contracts.md

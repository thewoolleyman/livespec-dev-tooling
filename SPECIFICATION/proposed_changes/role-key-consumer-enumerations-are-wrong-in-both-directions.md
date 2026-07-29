---
topic: role-key-consumer-enumerations-are-wrong-in-both-directions
author: claude-opus-5
created_at: 2026-07-29T01:43:11Z
---

## Proposal: Define what the role-key consumer enumerations MEAN before correcting them

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The role-key inventory in contracts.md §"Role keys" attaches a per-key list of consuming checks to most entries ("Consumed by X, Y"), but never says what qualifies a check for that list. Two checks — `partition_completeness` and `source_trees_scoped_to_consumer` — read EVERY role key structurally rather than to gate their own behavior, so without a stated rule the lists have two defensible readings that produce different answers for every key. The section MUST state that these lists enumerate BEHAVIORAL consumers (checks whose own outcome the key gates), and MUST name the two structural meta-checks once as deliberately excluded.

### Motivation

This is filed FIRST and separately because it is the difference between a durable correction and a data refresh. The sibling proposals correct four enumerations that were measured wrong; without a stated membership rule, the next editor correcting them again has no way to know whether `partition_completeness` belongs in all eleven lists or none, and would produce a differently-wrong answer in good faith. The ambiguity is not hypothetical: `partition_completeness` genuinely reads `config.supervisor_entry_files`, and this repo's own `pyproject.toml` comment DOES count it as one of the key's four consumers, while the spec's list does not. Two authorities in this repo already disagree because the rule was never written down.

### Proposed Changes

§"Role keys" MUST gain a short preamble, placed before the role-key inventory bullets, defining the per-key consumer enumerations. It MUST state all of the following:

- Each per-key consumer list enumerates the checks whose OWN behavior the key gates — a check that reads the key to decide what it walks, what it exempts, or what severity it applies.
- `partition_completeness` and `source_trees_scoped_to_consumer` are STRUCTURAL meta-checks that read every declared role key in order to verify the partition and the scoping respectively. They MUST NOT be enumerated in any per-key list, and the preamble MUST name them explicitly as excluded so their omission reads as a rule rather than as an oversight.
- The enumerations are NORMATIVE for consumers: a repo reads them to decide which checks a declaration will affect. A check that begins or ceases to read a role key MUST be reflected in that key's list in the same change that alters the read.

The preamble MUST NOT be written as a general disclaimer that the lists are approximate. An approximate list is what produced the defect the sibling proposals correct: a consumer that declares a key on the strength of a list which over-reports gets an exemption that never takes effect, and a green check that means nothing.

## Proposal: Correct three per-key consumer enumerations that are measurably wrong in BOTH directions

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Three role-key entries in §"Role keys" enumerate consuming checks incorrectly: `supervisor_entry_files` names one consumer of four, `commands_trees` omits one, and `io_trees` names two checks that do not read the key at all. Measured against the shipped code by enumerating every module under `livespec_dev_tooling/checks/` that reads `config.<key>`. The three lists MUST be corrected to the measured sets. `pure_trees` and `covered_trees` were measured as already CORRECT and MUST be left unchanged.

### Motivation

Filed as the dev-tooling half of the `livespec-dev-tooling-8o8e` step-6 work; the under-reporting of `supervisor_entry_files` was recorded on that thread, and measuring it surfaced that the defect is a CLASS spanning several keys and running in both directions.

The two directions fail differently and the over-report is the more dangerous one. An UNDER-report (`supervisor_entry_files`, `commands_trees`) understates the blast radius of a declaration: a repo adding one path to silence one check silently grants itself three further exemptions, which is precisely the bulk-declaration hazard the step-6 work refused to take. An OVER-report (`io_trees`) is worse, because it promises an exemption that does not exist: a repo declaring `io_trees` on the strength of the current text expects `public_api_result_typed` and `no_write_direct` to honor it, and neither reads the key. That is a documented exemption which silently does nothing — the same manufactured-confidence failure as a check that scans zero files, relocated into the schema documentation.

The `supervisor_entry_files` list is additionally stale by an increment this very thread created: PR #816 wired the key into `public_api_result_typed`, and neither the spec bullet nor this repo's own `pyproject.toml` comment was updated. The comment now under-reports at four; the spec under-reports at one.

### Proposed Changes

The three bullets in §"Role keys" MUST be corrected to the measured consumer sets. Each list below is the set of checks under `livespec_dev_tooling/checks/` that read `config.<key>`, excluding the two structural meta-checks per the companion proposal.

- **`supervisor_entry_files`** currently reads "Consumed by `no_except_outside_io`." It MUST read: consumed by `no_except_outside_io`, `no_write_direct`, `public_api_result_typed`, and `supervisor_discipline`. The entry SHOULD additionally state that declaring a path here grants ALL FOUR exemptions at once, because the key is file-level and a repo declaring one path to satisfy one check receives the other three without deciding anything.
- **`commands_trees`** currently reads "Consumed by `no_except_outside_io`, `no_write_direct`." It MUST add `public_api_result_typed`, which reads the key to scope the ratified `main() -> int` and `build_parser() -> ArgumentParser` supervisor exemptions.
- **`io_trees`** currently reads "Consumed by `no_except_outside_io`, `no_raise_outside_io`, `public_api_result_typed`, `no_write_direct`." It MUST NOT continue to name `public_api_result_typed` or `no_write_direct`: neither module reads `config.io_trees`. It MUST add `hook_trees_not_io_exempt`, which does. The corrected list is `no_except_outside_io`, `no_raise_outside_io`, and `hook_trees_not_io_exempt`.

The `io_trees` correction MUST NOT be applied by weakening the sentence to a hedge such as "consumed by the I/O-layer checks". Naming the checks is the entry's value to a consumer deciding whether to declare the key.

Two entries were measured and found CORRECT and MUST NOT be edited: `pure_trees` (`public_api_result_typed`, `pbt_coverage_pure_modules`, `check_mutation`) and `covered_trees` (`no_write_direct`, `no_lloc_soft_warnings`). They are recorded here so a later editor does not assume the whole section was wrong and re-derive them.

## Proposal: Correct the source_trees requirement classes, five of whose named checks never read the key

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The `source_trees` entry states the key is "Required for every check in" three named classes. Measured against the shipped code, all eight checks in the AST-shape class do read `config.source_trees`, but all five checks named in the style and test-infrastructure classes do NOT — they read `target_dirs`, `covered_trees`, `pure_trees`, or no config key at all. Three checks that DO read the key are omitted entirely. The entry MUST be corrected to the measured set.

### Motivation

Same defect class as the sibling proposal, in a different sentence shape, which is why it was nearly missed: the other entries say "Consumed by" and this one says "Required for every check in the X class", so a search for the phrase that was known to be wrong would not have reached it. It was found by re-reading the whole section rather than by grepping for the known-bad wording — the method this thread has now needed repeatedly, and the reason the correction is filed as a class rather than as a line.

The practical cost is a misdirected reader. A repo whose `claude_md_coverage` or `comment_line_anchors` run is behaving unexpectedly is told by this entry to look at `source_trees`; both checks actually read `target_dirs`. The entry sends the reader to the wrong key at exactly the moment they consult it.

### Proposed Changes

The `source_trees` entry's requirement enumeration MUST be corrected to the measured set of checks that read `config.source_trees`.

- The AST-shape class MUST be retained unchanged: `assert_never_exhaustiveness`, `keyword_only_args`, `match_keyword_only`, `no_inheritance`, `all_declared`, `main_guard`, `private_calls`, and `global_writes` were each measured to read the key.
- The style class (`comment_line_anchors`, `no_lloc_soft_warnings`, `claude_md_coverage`) and the test-infrastructure class (`pbt_coverage_pure_modules`, `no_todo_registry`) MUST NOT continue to be named as requiring `source_trees`. None of the five reads it: `comment_line_anchors` and `claude_md_coverage` read `target_dirs`, `no_lloc_soft_warnings` reads `covered_trees`, `pbt_coverage_pure_modules` reads `pure_trees`, `tests_tree_prefix` and `mirror_pairings`, and `no_todo_registry` reads no role key at all.
- Three checks that DO read `config.source_trees` and are named nowhere in the entry MUST be added: `red_green_replay`, `rop_pipeline_shape`, and `supervisor_discipline`.

Where a removed check reads a DIFFERENT role key, the entry SHOULD say so rather than merely dropping the name, so the correction redirects the reader instead of leaving a gap. The removals MUST NOT be read as narrowing any check's scope: every one of the five still runs and still walks a universe: this proposal changes only the spec's account of WHICH key supplies it.

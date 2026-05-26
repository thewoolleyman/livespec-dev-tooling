---
topic: no-stale-revise-branches-check
author: claude-opus-4-7
created_at: 2026-05-26T07:00:00Z
---

## Cross-cutting parent

This PC is a child of the coordinating epic `livespec#coordinating-epic-stale-revise-enforcement` (filed at `livespec/SPECIFICATION/proposed_changes/coordinating-epic-stale-revise-enforcement.md`). The parent PC owns the cross-cutting design (the 4-layer enforcement story); this PC owns the underlying git-topology check that Layer 1's skill-level refusal depends on.

This PC does NOT yet carry a `parent_proposed_change` front-matter field. That field is itself proposed for the first time by the parent PC (which has to widen `livespec`'s `proposed_change_front_matter.schema.json`). After the schema widening is accepted, this PC SHOULD be retroactively edited via an admin commit to add `parent_proposed_change: livespec#coordinating-epic-stale-revise-enforcement`.


## Problem statement

The coordinating-epic parent's Layer 1 calls for `/livespec:revise` to refuse to start while any local `spec/*` branch is ahead of master. The skill-level refusal needs a CHECK that mechanically answers "are there stale spec-revise branches?" against any livespec-governed repo's local git state. That check belongs in livespec-dev-tooling because:

- It is project-agnostic: any livespec-governed repo can opt in by running it.
- Its layout-dependent input (the canonical branch name) is configurable via the existing consumer-configuration-schema role keys (v003 `spec/dev-tooling-revise-v003` shipped this schema).
- Its operation envelope (local `git` subprocess invocations only) is within the existing no-network-I/O constraint.

It satisfies the §"Configurability is the partition criterion" rule added in v003.


## Proposal: add no_stale_revise_branches shared check

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add a new shared check `no_stale_revise_branches` to the `livespec_dev_tooling/checks/` package. The check enumerates local refs matching `refs/heads/spec/*` and fails when any such branch is ahead of the canonical branch by one or more commits.

The check is layout-agnostic — it reads the canonical branch name from the consumer's `.livespec.jsonc` `canonical_branch` config key (proposed in the sibling child PC `livespec-impl-plaintext#work-item-merge-evidence`) with a `master`-default fallback. It does not depend on any other consumer-specific path.

### Motivation

Layer 1 of the coordinating epic refuses to start a new revise pass while a prior `spec/*` feature branch is unmerged. That refusal needs a check it can call. The check needs to:

- Enumerate the local `spec/*` branches via `git for-each-ref refs/heads/spec/`.
- For each, compute ahead-count vs the canonical branch via `git rev-list --left-right --count origin/<canonical>...<branch>`.
- Return one `fail` Finding per branch with ahead-count > 0, carrying the branch name, ahead-count, and the SHA + subject of the most recent commit on the branch for user context.

The check is project-agnostic and shells out only to local `git` — it fits cleanly into the dev-tooling check inventory.

### Proposed Changes

1. Add a new bullet to `SPECIFICATION/contracts.md` §"Shared check inventory" under the CI-alignment family:

   > the CI-alignment gates (`branch_protection_alignment`, `master_ci_green`, **`no_stale_revise_branches`**)

   The check joins the CI-alignment family because its concern is "is this repo in a deploy-ready state vs the canonical branch," which is the same semantic category as the other two.

2. Add a new §"`no_stale_revise_branches` check" subsection to `SPECIFICATION/contracts.md`:

   > ### `no_stale_revise_branches` check
   >
   > Invocation: `python -m livespec_dev_tooling.checks.no_stale_revise_branches`. Exit `0` on no stale branches, exit `4` with structured stderr findings on any stale branch.
   >
   > Algorithm:
   >
   > 1. Read the canonical branch name from `.livespec.jsonc`'s `livespec-impl-plaintext.canonical_branch` config key (or any other configured impl plugin's equivalent key). Default: `git symbolic-ref --short refs/remotes/origin/HEAD`, with hard-coded fallback `master`.
   > 2. Enumerate local refs: `git for-each-ref --format='%(refname:short)' refs/heads/spec/`.
   > 3. For each branch in the enumeration:
   >    - Run `git rev-list --left-right --count origin/<canonical>...<branch>`.
   >    - Parse the output as `behind\tahead`.
   >    - If `ahead > 0`: emit a finding with severity `fail`.
   > 4. Exit `0` on zero findings, `4` on one or more.
   >
   > Each finding carries:
   >
   > - `check_id`: `no_stale_revise_branches`
   > - `status`: `fail`
   > - `message`: `branch '<name>' is <ahead> commit(s) ahead of origin/<canonical>; last commit <short-sha> "<subject>"`
   > - `path`: empty (the finding is git-topology, not file-system)
   > - `line`: 0
   >
   > The check is INVOKED by livespec's `/livespec:revise` SKILL.md as a pre-step refusal (per the coordinating epic's Layer 1). Consumers MAY also wire it into doctor's static phase via the impl plugin's contract; that wiring is the impl plugin's choice, not this check's mandate.
   >
   > Override flag: `--allow-stale-branches` (optional). Exits `0` even when stale branches are present, but emits the findings as `info` rather than `fail`. The override is for cases where the user has intentionally orphaned a branch (e.g., experimental scratch work the user knows about) and wants the rest of their workflow unblocked. Per the coordinating epic, the calling SKILL.md is responsible for surfacing acknowledgement narration when the override is used; this check itself only honors the flag.


## Proposal: add the check to the consumer configuration role-key inventory (if needed)

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Per v003's §"Consumer configuration schema", checks declare their layout-dependent inputs as role keys consumed from the consumer's `pyproject.toml` `[tool.livespec_dev_tooling]` block. `no_stale_revise_branches` has ONE layout-dependent input — the canonical branch name — but per the sibling child PC `livespec-impl-plaintext#work-item-merge-evidence`, that key lives in `.livespec.jsonc`'s impl-plugin block, NOT in `pyproject.toml`'s `[tool.livespec_dev_tooling]` block.

This is a small role-key-vs-impl-config namespace question. The cleanest resolution is: `no_stale_revise_branches` reads the canonical branch from `.livespec.jsonc` directly (not via the role-key system), because:

- The canonical branch is a project-wide invariant (not check-specific) that other tooling (the impl plugin, other checks) also needs.
- Adding it to the `[tool.livespec_dev_tooling]` role-key inventory would be duplicate denormalization.

### Motivation

Avoid duplicating `canonical_branch` in two configuration locations.

### Proposed Changes

Document in `SPECIFICATION/contracts.md` §"Consumer configuration schema" the carve-out:

> Some checks have layout-dependent inputs that are project-wide invariants rather than check-specific role keys (e.g., the canonical branch name `master` / `main`). Such checks read directly from `.livespec.jsonc` rather than the `[tool.livespec_dev_tooling]` role-key inventory, to avoid duplicate config. The list of carve-out keys is currently small:
>
> - `canonical_branch` — read from `.livespec.jsonc`'s `livespec-impl-plaintext.canonical_branch` (or equivalent impl-plugin block's key, per the impl plugin's spec).
>
> Future carve-outs require explicit propose-change documentation; the default for new layout-dependent inputs is the role-key inventory.


## Implementation work (impl follow-ups, NOT part of this PC)

This PC declares the SPEC. The impl work tracked as follow-up work-items after acceptance:

1. **Red commit**: paired test at `tests/livespec_dev_tooling/checks/test_no_stale_revise_branches.py` (failing) per red-green-replay discipline. Tests cover: no `spec/*` branches → exit 0; stale `spec/*` branch → exit 4 with proper finding shape; multiple stale branches → multiple findings; canonical-branch resolution from `.livespec.jsonc` vs default; `--allow-stale-branches` override.
2. **Green commit**: `livespec_dev_tooling/checks/no_stale_revise_branches.py` implementation passing the test.
3. **Refactor commits** (optional): any cleanup, never touching the test.


## Acceptance criteria

This PC is complete when:

1. The shared check inventory in `contracts.md` lists `no_stale_revise_branches` under the CI-alignment family.
2. The check's algorithm, inputs, outputs, and override flag are specified.
3. The `canonical_branch` carve-out from the consumer configuration schema is documented.
4. Follow-up impl work-items are filed in `work-items.jsonl` for: paired test (red), implementation (green), and any subsequent refactor.

This PC does NOT itself ship the check module — that follows in TDD-disciplined commits per livespec-dev-tooling's red-green-replay convention.

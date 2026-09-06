---
topic: install-worktree-pack-first-hook-command
author: claude-fable-5-1 (optimize-gates plan session, Claude Code)
created_at: 2026-09-06T05:07:52Z
---

## Proposal: Hooks and CI: the lefthook ordering mirrors livespec v219 — the worktree-pack installer runs first at pre-commit and pre-push

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Amend the one sentence in non-functional-requirements.md section "Hooks and CI" that enumerates the lefthook ordering this repository MUST mirror, so it matches the ordering livespec ratified in its v219 (contracts.md section "Pre-commit step ordering"): pre-commit `00-install-worktree-pack`, `01-lint-autofix-staged`, `02-commit-pairs-source-and-test`, `03-check-pre-commit`; commit-msg unchanged; pre-push `00-install-worktree-pack` then `01-check-pre-push`. The installer MUST be idempotent, MUST write only files the repository ignores, and MUST NOT relax the byte-identity verifier, which still asserts the installed pack. The count word "three-stage" is dropped in favor of the enumeration itself, and the parenthetical claiming zero-`.py` subsetting at pre-push is dropped because this repository's `check-pre-push` recipe runs the full aggregate behind the green-token memoization, mirroring livespec, which retired that subsetting in its v217 PR-gate-equals-master-gate ratification.

### Motivation

livespec plan `optimize-gates` (epic livespec-xms725, child livespec-ltthxr, the nine-member rollout). The worktree-discipline pack this repository ships is gitignored-and-installed, so a worktree created by raw `git worktree add`, or one predating a pin bump, reaches the gate without it and fails `worktree_pack_absent` after the whole aggregate ran; running the installer as the first lefthook command of both hooks heals that at the one seam every local gate path funnels through, and CI already performs the same install step before its checks. livespec ratified the ordering in v219; this repository's spec pins the mirrored ordering by explicit enumeration, so the mirror cannot change without this amendment (clause lockstep). The implementing change to this repository's `lefthook.yml` and `AGENTS.md` follows this ratification in its own pull request.

### Proposed Changes

```diff
@@ SPECIFICATION/non-functional-requirements.md — "## Hooks and CI": replace the single-line paragraph beginning "The lefthook configuration MUST mirror livespec's three-stage pre-commit ordering" in full. @@
-The lefthook configuration MUST mirror livespec's three-stage pre-commit ordering (`00-lint-autofix-staged`, `01-commit-pairs-source-and-test`, `02-check-pre-commit`), commit-msg gates (`00-no-commit-on-master`, `01-red-green-replay`), and pre-push gate (`check-pre-push` with zero-`.py` subsetting).
+The lefthook configuration MUST mirror livespec's pre-commit ordering (`00-install-worktree-pack`, `01-lint-autofix-staged`, `02-commit-pairs-source-and-test`, `03-check-pre-commit`), commit-msg gates (`00-no-commit-on-master`, `01-red-green-replay`), and pre-push ordering (`00-install-worktree-pack` then `01-check-pre-push`), per livespec `contracts.md` section "Pre-commit step ordering". The `00-install-worktree-pack` command delegates to `just install-worktree-pack`, which materializes the canonical worktree-discipline pack this repository ships into the checkout's gitignored `dev-tooling/` from the package the checkout resolves, so every later gate member that reads the pack finds it present and current whether the worktree was created by `just worktree-create`, by a raw `git worktree add`, or before a pin bump; the installer MUST be idempotent, MUST write only files the repository ignores, and MUST NOT relax the byte-identity verifier, which still asserts the installed bytes after the install. No hook command that reads the pack MAY precede it.
```

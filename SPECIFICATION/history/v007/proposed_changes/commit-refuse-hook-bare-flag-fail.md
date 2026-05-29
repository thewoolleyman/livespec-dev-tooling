---
topic: commit-refuse-hook-bare-flag-fail
author: claude-opus-4-8
created_at: 2026-05-29T00:00:00Z
parent_proposed_change: livespec#commit-refuse-hook-check-port
---

## Cross-cutting parent

This PC is a child of epic `li-unbare` (the family-wide migration
from the bare-flag commit-refuse mechanism to the commit-refuse-hook
mechanism, coordinated from livespec). It closes a detection gap found
during that epic: the shipped
`primary_checkout_commit_refuse_hook_installed` check SKIPPED (exit 0)
whenever cwd was not inside a git WORK tree — and a primary that has
regressed to `core.bare = true` is a git repository that is NOT a work
tree, so the check skipped a bare primary silently. That is the exact
eliminated legacy state (the v091–v094 `core.bare = true` mechanism)
that epic `li-unbare` fixed, so a regression to it would PASS the
check undetected.

The invariant statement remains owned by livespec at
`livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary
invariants" → §"`primary-checkout-commit-refuse-hook-installed`",
which permits exactly this hardening: "The doctor invariant MAY
additionally surface a `fail` when `core.bare = true` is set on the
primary, to catch the legacy-state case during the transition." This
PC documents dev-tooling's impl realizing that MAY. The upstream
contract remains a MAY (unchanged); this sibling chooses to do it.


## Problem statement

dev-tooling's own spec at `SPECIFICATION/contracts.md` §"`primary_checkout_commit_refuse_hook_installed` check" (added in v006)
describes the algorithm with a single "cwd not inside a git working
tree → skip" branch. The shipped impl now adds a `core.bare = true →
fail` branch (failure_mode `core_bare_set`), and splits the old skip
into a not-a-git-repository-at-all skip (still exit 0) versus the
bare-flag fail. The spec must document the new fail branch so the
spec↔impl stay in lockstep.


## Proposal: document the core.bare=true fail branch in the algorithm + finding shape

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Two edits to the `### \`primary_checkout_commit_refuse_hook_installed\`
check` H3 subsection of `contracts.md`:

1. Rewrite the Algorithm numbered list to distinguish a
   genuinely-not-a-git-repository directory (`git rev-parse --git-dir`
   ≠ exit 0 → skip, exit 0) from a git repository with `core.bare =
   true` (→ fail, exit 4, failure_mode `core_bare_set`), then the
   not-inside-a-work-tree skip (e.g. cwd inside `.git/`), then the
   existing both-hooks verification. Cite that the bare-flag fail
   branch realizes the MAY in livespec's canonical invariant and does
   NOT change that canonical invariant (it stays a MAY).

2. Extend the "Each `fail` finding carries" field list to document the
   `core_bare_set` failure mode and its branch-specific `hook`
   (empty), `hooks_dir` (empty), and `hint` (directing the user to
   `git config --unset core.bare && git reset --hard origin/master` to
   repopulate the working tree, then run the bootstrap step) values.

### Motivation

The shipped impl now has a fail branch the spec does not describe.
Documenting it keeps the spec a faithful single source of truth and
lets doctor + contributors reason about the check's full behavior.

### Algorithm (new section)

1. If `git` is not on PATH → exit `0` with a warning (graceful skip).
2. If cwd is not a git repository at all (`git rev-parse --git-dir` ≠
   exit `0`) → exit `0` with an info log (skipped).
3. Otherwise (cwd IS a git repository) — if `core.bare = true` (`git
   config --get core.bare` resolves to `true`) → exit `4` with one
   structured `fail` finding (`failure_mode` `core_bare_set`) on
   stderr. Realizes the MAY in livespec's canonical invariant.
4. Otherwise — if cwd is not inside a git working tree (`git rev-parse
   --is-inside-work-tree` ≠ `true`) → exit `0` with an info log
   (skipped).
5. Otherwise, resolve the git common dir and verify BOTH
   `<common-dir>/hooks/pre-commit` and `<common-dir>/hooks/pre-push`
   exist, are executable, and contain the canonical fingerprint → exit
   `0` (pass); else → exit `4` with one structured `fail` finding per
   offending hook on stderr.

### Outputs

The `core_bare_set` `fail` finding carries the same field shape the
hook-installation `fail` findings emit (`check_id`, `status` `fail`,
`hook`, `failure_mode`, `hooks_dir`, `hint`, `path` empty, `line` 0),
with `hook` and `hooks_dir` empty (the bare-flag branch is not tied to
a specific hook and fails before resolving the common dir) and a
branch-specific `hint`.

### Exit codes

- `0` — pass, OR skipped (no git on PATH, cwd not a git repository, or
  cwd a non-bare git repo but not inside a work tree).
- `4` — fail (one or both hooks missing / non-executable /
  non-canonical body, OR `core.bare = true`).

### Heading-coverage co-edit

The changed text is entirely under an H3 (`### `) heading. dev-tooling's
`tests/heading-coverage.json` map (and the `heading_coverage` check)
track only H2 (`## `) headings, so no heading-coverage update is
required for this change.


## Out of scope

- Any change to the upstream invariant declaration at
  `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary
  invariants" → §"`primary-checkout-commit-refuse-hook-installed`"; it
  stays a MAY.
- The impl + test (already shipped in the preceding `fix(check):`
  commit on this branch).

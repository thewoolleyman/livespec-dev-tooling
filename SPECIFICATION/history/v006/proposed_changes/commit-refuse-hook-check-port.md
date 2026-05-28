---
topic: commit-refuse-hook-check-port
author: claude-opus-4-8
created_at: 2026-05-28T00:00:00Z
---

## Cross-cutting parent

This PC is a child of epic `li-unbare` (the family-wide migration from the bare-flag commit-refuse mechanism to the commit-refuse-hook mechanism, coordinated from livespec). The parent epic ported the `primary-checkout-bare-flag-set` cross-boundary invariant into the `primary-checkout-commit-refuse-hook-installed` invariant in livespec's doctor-static phase (Phase 2), and replaced the shared check implementation in livespec-dev-tooling: the file `livespec_dev_tooling/checks/primary_checkout_commit_refuse_hook_installed.py` now ships and `primary_checkout_bare_flag_set.py` was deleted.

The invariant statement is owned by livespec at `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary invariants" → §"`primary-checkout-commit-refuse-hook-installed`". This sibling PC updates the shared-check inventory entry to match the actual shipped check; the upstream contract remains the canonical declaration.


## Problem statement

livespec-dev-tooling's own spec at `SPECIFICATION/contracts.md` still declares the DELETED check `primary_checkout_bare_flag_set` as a current shared check (in both the §"Shared check inventory" CI-alignment enumeration and its own `### \`primary_checkout_bare_flag_set\` check` subsection). The actual shipped check — as of v0.5.0, epic `li-unbare` Phase 2 — is `primary_checkout_commit_refuse_hook_installed`: the file `livespec_dev_tooling/checks/primary_checkout_commit_refuse_hook_installed.py` exists, and `primary_checkout_bare_flag_set.py` was deleted. dev-tooling's spec was never updated to match. This is a spec↔impl contradiction.


## Proposal: replace primary_checkout_bare_flag_set with primary_checkout_commit_refuse_hook_installed in the shared check inventory

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Two edits to `contracts.md`:

1. In §"Shared check inventory", change the last token of the CI-alignment gates parenthetical from `primary_checkout_bare_flag_set` to `primary_checkout_commit_refuse_hook_installed`.

2. Replace the entire `### \`primary_checkout_bare_flag_set\` check` subsection with a `### \`primary_checkout_commit_refuse_hook_installed\` check` subsection that faithfully ports the OLD section's house style (Invocation / port-attribution / Inputs / canonical-fingerprint / Algorithm / "Each finding carries" field list), reconciled against the actual impl docstring and finding-emission code at `livespec_dev_tooling/checks/primary_checkout_commit_refuse_hook_installed.py`.

### Motivation

The deleted check is still declared as current in dev-tooling's own spec, contradicting the shipped impl. The spec must match the impl so doctor and contributors see a single source of truth.

### Algorithm (new section)

1. If `git` is not on PATH → exit `0` with a warning (graceful skip; local-dev tolerance).
2. If cwd is not inside a git working tree (`git rev-parse --is-inside-work-tree` ≠ `true`) → exit `0` with an info log (skipped).
3. Otherwise, resolve the git common dir (`git rev-parse --git-common-dir`) and verify BOTH `<common-dir>/hooks/pre-commit` and `<common-dir>/hooks/pre-push` exist, are executable, and contain the canonical fingerprint → exit `0` (pass); else → exit `4` with one structured `fail` finding per offending hook on stderr.

### Outputs

The `fail` finding carries the exact fields the impl emits to stderr: `check_id`, `status` (`fail`), `hook`, `failure_mode` (`missing` | `not_executable` | `non_canonical_body`), `hooks_dir`, `hint`, `path` (empty), `line` (`0`). The skip paths emit a `warning`/`info` log carrying `check_id` plus `hint`/`cwd`; only the `fail` path carries `status`.

### Exit codes

- `0` — pass, OR skipped (no git on PATH, or cwd is not a git working tree).
- `4` — fail (one or both hooks missing, non-executable, or non-canonical body).

### Partition placement

`primary_checkout_commit_refuse_hook_installed` replaces `primary_checkout_bare_flag_set` in the §"Shared check inventory" CI-alignment family enumeration. The check remains layout-independent (no `[tool.livespec_dev_tooling]` role keys consumed) and qualifies under §"Configurability is the partition criterion" without any role-key wiring.

### Heading-coverage co-edit

The changed heading is an H3 (`### `) heading. `tests/heading-coverage.json` tracks only H2 (`## `) headings (the `heading_coverage` check explicitly excludes `### ` lines), so no heading-coverage update is required for this change.


## Out of scope

- Any change to the upstream invariant declaration at `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary invariants" → §"`primary-checkout-commit-refuse-hook-installed`".
- The impl file itself (already shipped in v0.5.0).
- Wiring posture of the check in other siblings' `just check` aggregates.

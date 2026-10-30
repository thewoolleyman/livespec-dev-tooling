---
topic: primary-checkout-hook-check-documents-all-arms
author: claude-opus-drain-kcoslm
created_at: 2026-09-12T11:19:33Z
---

## Proposal: Document the worktree-pack and vendored-copy arms of the primary_checkout_commit_refuse_hook_installed check

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The §"`primary_checkout_commit_refuse_hook_installed` check" section documents the `failure_mode` enum as only `missing`, `not_executable`, `non_canonical_body`, and `core_bare_set`, but the shipped check (livespec_dev_tooling/checks/primary_checkout_commit_refuse_hook_installed.py) enforces two further arms that the spec omits entirely: a WORKTREE-PACK arm and a VENDORED-COPY arm, each with its own failure modes, plus a hook byte-identity refinement.

### Motivation

This is a spec→impl documentation drift surfaced by drain-backlog triage batch 19 (item livespec-dev-tooling-ckb). The contract half of the check understates what the check actually enforces: a reader or a consumer repo relying on contracts.md cannot learn that the check verifies worktree-pack file byte-identity, catches partial worktree-pack installs, and refuses vendored hook-source copies outside the declared carve-outs. The check's own docstring (lines ~56-134) and its emitted failure_mode constants (_PACK_READ_FAILURE_MODE, worktree_pack_body_mismatch, worktree_pack_file_missing, vendored_copy_present) are the authoritative evidence; master CI is green, so the check is correct and it is the SPEC that is stale. Documenting the arms restores the contract half to parity with the shipped verifier.

### Proposed Changes

Update §"`primary_checkout_commit_refuse_hook_installed` check" in SPECIFICATION/contracts.md to document all three arms the shipped check enforces, so the failure_mode enum and the exit-code / corrective-hint prose match the implementation:

1. FAILURE_MODE ENUM (the `failure_mode` field bullet, currently listing `missing`, `not_executable`, `non_canonical_body`, `core_bare_set`). Add the worktree-pack and vendored-copy failure modes so the enum is complete:
   - `worktree_pack_unreadable` — a file the worktree-pack arm depends on (the `.livespec.jsonc`, or an installed pack file) could not be READ.
   - `worktree_pack_body_mismatch` — an installed worktree-pack file's bytes drifted from its wheel-carried `CANONICAL_*` body (the byte-identity arm decides drift).
   - `worktree_pack_file_missing` — a sibling worktree-pack file is absent while other pack files are present (a partial install).
   - `vendored_copy_present` — a vendored hook-source copy exists outside the declared carve-outs.

2. HOOK-INSTALLATION ARM REFINEMENT. Where the section states the hook-installation modes fire on missing / non-executable / non-canonical body, clarify that the canonical-body determination is a BYTE-IDENTITY comparison of the installed hook against the wheel-carried `CANONICAL_HOOK_BODY` (an installed hook whose bytes differ from `CANONICAL_HOOK_BODY` is a `non_canonical_body` fail), and note that a vendored hook-source copy found outside the carve-outs is a distinct `vendored_copy_present` fail.

3. EXIT-CODE PROSE. In the exit-`4` prose, add the worktree-pack and vendored-copy fail branches beside the existing hook-installation and `core_bare_set` branches, so the enumeration of what drives exit `4` is complete.

4. CORRECTIVE-HINT PROSE. Extend the `hint` field prose so the corrective action names BOTH installers where relevant — `just install-commit-refuse-hooks` AND `just install-worktree-pack` — and, for the `vendored_copy_present` mode, instructs the user to delete the vendored copy.

This is a documentation-parity change to dev-tooling's OWN check (the `livespec_dev_tooling` package), so it belongs in this repo's contracts.md, not core. It records no new behavior — it documents behavior the shipped check and its regression tests already carry — so no new product `.py` is introduced and the Red-Green-Replay ritual does not apply. At revise time: if this edit changes the `## ` heading set of contracts.md (it is not expected to — it edits within the existing `### \`primary_checkout_commit_refuse_hook_installed\` check` subsection), co-edit tests/heading-coverage.json in the same revise `resulting_files[]` payload; and if the project links clauses to scenarios, add or reference the scenarios that already exercise the worktree-pack and vendored-copy arms rather than leaving the documented arms scenario-less.

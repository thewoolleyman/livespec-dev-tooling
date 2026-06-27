---
topic: drop-copier-answers-commit-from-pin-autodiscovery
author: claude-opus-4-8
created_at: 2026-06-27T12:50:42Z
---

## Proposal: drop-copier-answers-commit-from-pin-autodiscovery

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Remove the `.copier-answers.yml _commit` pin format from the required-format list in contracts.md §"Pin autodiscovery rules", leaving the four genuine pin formats.

### Motivation

The bump-pin release fan-out rewrites `.copier-answers.yml _commit` to the new release tag WITHOUT running `copier update`, desyncing the copier render-provenance marker so a later `copier update` diffs newtag->newtag (empty) and silently skips template-content changes. `_commit` is render-provenance, not a version pin; the other formats (`.livespec.jsonc compat.pinned`, `pyproject.toml [tool.uv.sources]` tag, `.vendor.jsonc upstream_ref`, and the `.github/workflows uses:` ref) ARE pins. The dev-tooling code change (livespec-zs22.7.9.6 part 1) drops `_commit` from the autodiscovery walk; this contract revision keeps the governed spec in lockstep so the prose no longer requires a format the implementation deliberately no longer covers.

### Proposed Changes

In contracts.md §"Pin autodiscovery rules", under "The walk MUST cover the following formats:", DELETE the bullet that begins `**`.copier-answers.yml` `_commit`** — the singular `_commit` field, present in projects generated via `copier copy` / `copier update`...`. Leave the four remaining bullets unchanged (`.livespec.jsonc` `compat.pinned`; `pyproject.toml` `[tool.uv.sources]`; `.vendor.jsonc`; `.github/workflows/*.yml` / `*.yaml` `uses:` ref) and leave the missing-file/unrecognized-format tolerance paragraphs and the name-normalization paragraph unchanged. No numeric format-count phrase appears in this section, so no count reconciliation is needed in the prose.

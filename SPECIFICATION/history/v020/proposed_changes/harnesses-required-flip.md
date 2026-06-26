---
topic: harnesses-required-flip
author: claude-opus-4-8
created_at: 2026-06-26T20:51:10Z
---

## Proposal: Require harnesses declaration fleet-wide (M6-g flip)

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Update the plugin_resolution check's always-on declaration-integrity gate inventory: a .livespec.jsonc that exists but declares no harnesses key now fails (exit 4, failure_mode absent_declaration) instead of skipping; the harnesses declaration is REQUIRED for every governed repo. A non-governed directory (no/unreadable/non-object .livespec.jsonc) still skips.

### Motivation

livespec-zs22.7.7 M6-g: every governed repo now declares harnesses (M6-e backfill complete), so the advisory-until-migration posture flips to required fleet-wide. The impl flip landed in this same change (feat(checks): require harnesses declaration fleet-wide). This spec update keeps contracts.md truthful to the new behavior.

### Proposed Changes

contracts.md, plugin_resolution check, Always-on declaration-integrity gate: split the single skip bullet into (1) absent/unreadable/non-object .livespec.jsonc -> exit 0 (skipped; non-governed dir) and (2) .livespec.jsonc present but no harnesses key -> exit 4 (absent_declaration); harnesses REQUIRED for every governed repo (fleet-wide flip, reported at error severity by the companion baseline-harnesses obligation row). Removes the OPTIONAL / MAY-make-required language.

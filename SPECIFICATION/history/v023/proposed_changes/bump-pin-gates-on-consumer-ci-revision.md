---
proposal: bump-pin-gates-on-consumer-ci.md
decision: accept
revised_at: 2026-06-27T17:50:59Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accept: lean Option B per livespec-i05g (maintainer-decided 2026-06-27). The automated bump-pin workflow / composite Action no longer runs the consumer's full `just check`; the consumer's OWN branch-protection required status checks gate the auto-merge PR (the `--auto` merge already defers until they pass). This fixes the fan-out, which was failing on every aggregate-enforced consumer for purely environmental reasons (the bump CI env cannot reconstruct a faithful `just check`). Edits the §"reusable-bump-pin-from-dispatch.yml" Behavior + `.vendor.jsonc` clause, §"Fallback to known-good pin", and the §"Bump-pin policy" acceptance-criterion bullet — all body-text within existing sections (no `## ` heading change). The paired `.github/actions/bump-pin-rewrite/action.yml` change (deleting the `just check` step + the hand-rolled commit-refuse-hook-install step) lands in the same PR as a `fix:`.

## Resulting Changes

- contracts.md

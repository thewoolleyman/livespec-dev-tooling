---
proposal: github-workflow-uses-pin-format.md
decision: accept
revised_at: 2026-06-12T06:45:29Z
author_human: Test <test@example.com>
author_llm: claude-fable-5
---

## Decision and Rationale

Accepted as proposed (user pre-authorized). The fifth pin format closes a real coverage gap: the three consumer shim workflows bootstrap-pin reusable workflows via uses: references under .github/workflows/, and none of the existing four formats discovers them, leaving @master pins permanently stale in violation of the bump-pin policy. The new bullet lands verbatim in contracts.md §"Pin autodiscovery rules" after the .copier-answers.yml entry; the rewrite-path paragraph lands in the §"reusable-bump-pin-from-dispatch.yml" description (the proposal's reference to a 'bump-pin composite Action' is read as that reusable workflow — the only bump-pin rewrite surface the spec defines). The second proposal section requires no constraints.md text change: §"Semver discipline" there already defers to contracts.md §"Semver discipline", whose MINOR rule already enumerates 'a new pin-autodiscovery format'; the IMPLEMENTING commit (the future walk-code change) must carry a feat: subject for the MINOR release-please bump.

## Resulting Changes

- contracts.md

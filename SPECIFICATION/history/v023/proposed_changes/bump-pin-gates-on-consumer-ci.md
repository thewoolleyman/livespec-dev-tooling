---
topic: bump-pin-gates-on-consumer-ci
author: claude-opus-4-8
created_at: 2026-06-27T17:50:28Z
---

## Proposal: Bump-pin gates on the consumer's own CI, not an in-Action just check

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Re-scope the cross-repo bump-pin contract to Option B: the automated bump-pin workflow opens the auto-merge PR and lets the consumer's OWN CI / branch-protection required status checks gate the merge, rather than running the consumer's full `just check` inside the bump workflow / composite Action. The bump workflow's CI environment is an incomplete reconstruction of the consumer's (it lacks the consumer's installed plugin, its core checkout, and its installed hooks), so an in-workflow `just check` fails for environmental reasons even when the consumer is green on its own CI. Removing the in-Action check aligns the contract with how `--auto` merge already works (the merge defers until the consumer's required checks pass).

### Motivation

livespec-i05g: the dt-pin release fan-out failed on EVERY aggregate-enforced consumer because the bump-pin composite Action ran each consumer's full `just check` in an incomplete CI env (three environmental failure modes: the strict byte-identity commit-refuse-hook verifier rejecting the hand-rolled inline hook; core's doctor scanning the nested `.livespec-dev-tooling/` support-module checkout; runtime/orchestrator doctors unable to resolve core). The consumers themselves are green on their OWN CI (empirically verified: livespec-runtime bumped v0.23.0->v0.25.1 by hand passed all 47 targets). Maintainer-decided 2026-06-27 = Option B (lean): drop the in-Action `just check` + the hand-rolled hook-install step entirely; the consumer's own branch-protection gate is authoritative.

### Proposed Changes

Three body edits within existing sections of `SPECIFICATION/contracts.md` (no `## ` heading add/change/remove):

1. §"Cross-repo coordination automation surface" → §"`reusable-bump-pin-from-dispatch.yml`" Behavior paragraph: remove `runs `just check`,` from the step sequence and add that the workflow deliberately does NOT run the consumer's `just check` — the authoritative post-bump gate is the consumer's OWN CI / branch-protection required status checks on the opened auto-merge PR (the `--auto` merge defers until those checks pass), because the bump workflow's CI env lacks the consumer's installed plugin / core checkout / hooks and cannot reconstruct a faithful `just check`.

2. Same subsection, `.vendor.jsonc` re-vendor clause: change `before running `just check`` to `before committing`, since there is no in-workflow `just check` after the re-vendor.

3. §"Fallback to known-good pin": re-scope the opening sentence from `When a bump PR's `just check` fails on the new pin` to `When a bump PR fails its required status checks on the new pin`, and add that the bump-pin workflow itself does NOT run the consumer's `just check` — it opens the PR with `--auto --rebase` and the consumer's own branch-protection required status checks gate the merge, so a failure surfaces on the PR's status checks rather than inside the bump workflow.

4. §"Bump-pin policy" → "Releases fire bump-pin PRs" bullet: clarify that the acceptance criterion (the consumer passing its post-bump invariant suite) is gated by the consumer's branch-protection required status checks on the bump PR, not by the bump workflow itself.

The `.github/actions/bump-pin-rewrite/action.yml` change (deleting the `just check` step + the hand-rolled commit-refuse-hook-install step) lands in the same PR as a `fix:`; the composite Action's declared inputs/outputs are unchanged, so this is within the §"Composite Actions wire contract" guarantee that the underlying step list MAY change between versions (PATCH).

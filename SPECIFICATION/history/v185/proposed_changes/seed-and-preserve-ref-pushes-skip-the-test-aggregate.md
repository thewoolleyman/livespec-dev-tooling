---
topic: seed-and-preserve-ref-pushes-skip-the-test-aggregate
author: claude-opus-5-5
created_at: 2026-11-10T07:14:55Z
---

## Proposal: Seed and preserve ref pushes run only the authorization members

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A push that updates only refs under refs/heads/needs-human/ or refs/heads/preserve/ MUST NOT run the full pre-push test aggregate (no gate Job, no local fall-through), MUST still run every authorization-reading member on the pushing host and refuse on its failure, and any push touching another ref MUST be gated as today. These refs are never merge candidates: the factory re-gates every run's own tree, and any pull request opened from one is still gated by CI's required ci-green, so no gate is reduced on a mergeable ref.

### Motivation

Measured 2026-11-10: a hand-pushed factory seed ref (refs/heads/needs-human/01M6WGJ6MFBXYD51SHD5V890DV on livespec-orchestrator-beads-fabro, master plus two e2e test files) ran the full pre-push aggregate as delegated gates Job gate-livespec-orchestrator-beads-fabro-gxlsw for 43 min 06 s (host lefthook 2628 s), occupying a gate lane for a ref the factory re-gates anyway. The pre-push recipe ships through the shared pack, so every fleet repository pays this when a seat hand-pushes a seed or preserve ref. The authorization members are kept deliberately: the gate Job never runs them, so dropping them would let an unapproved workflow edit reach a branch from which a pull request could be opened. Owning work item: livespec-dev-tooling-2zb3gk. Ruled in-seat by the dev-host-test-gate-load plan seat and confirmed by legacy-coordinator-agent as not reducing a gate on a mergeable ref.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", insert one bullet immediately after the **Verdict.** bullet:

- **Seed and preserve refs.** A push whose ref updates ALL name refs under `refs/heads/needs-human/` or `refs/heads/preserve/` MUST NOT submit a gate Job and MUST NOT run the local `just check` fall-through. It MUST still run, on the pushing host and against the committed tree each updated ref names, every member of the check set that declares it reads an authorization held outside the tree, and the push MUST be refused, naming the member, when any of them fails or cannot be evaluated. It MUST print the updated refs and a line saying the test aggregate was not run because every updated ref is a seed or preserve ref. A push whose ref updates include ANY other ref MUST be gated exactly as the bullets above require, for every ref it updates. Ref deletions count as ref updates of the deleted ref's name. This bullet binds the pre-push gate of every repository that installs it from this repository's pack, whether or not that repository delegates.

In SPECIFICATION/scenarios.md, add, after "## Scenario: a push of a tree holding a green token still runs the members that read state outside the tree":

## Scenario: a push of only seed or preserve refs runs only the authorization members

Given a consumer repository whose pre-push gate is installed from the dev-tooling pack

And a member of the repository's check set that declares it reads an authorization held outside the tree

When a git push whose ref updates all name refs under `refs/heads/needs-human/` or `refs/heads/preserve/` runs the pre-push gate

Then the pre-push gate MUST NOT submit a gate Job and MUST NOT run the local `just check` fall-through

And the pre-push gate MUST run that member on the pushing host and MUST refuse the push, naming the member, when it fails or cannot be evaluated

And the pre-push gate MUST print the updated refs and a line saying the test aggregate was not run

And when the same push also updates any other ref, the pre-push gate MUST gate it exactly as an ordinary push

The revise that accepts this MUST add a `tests/heading-coverage.json` row for the new scenario heading (a spec-first TODO row naming the integration tier and work_item livespec-dev-tooling-2zb3gk) and regenerate `tests/heading-coverage-debt.json`.

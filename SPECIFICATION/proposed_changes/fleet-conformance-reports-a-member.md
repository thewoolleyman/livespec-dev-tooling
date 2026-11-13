---
topic: fleet-conformance-reports-a-member
author: claude:ci-runtime-and-cost
created_at: 2026-11-11T11:03:54Z
---

## Proposal: fleet conformance reports a member whose hold-label disarm workflow mints its App token differently from its auto-merge workflow

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an assert-mode obligation row, `disarm-token-key-matches-auto-merge`, to §"Fleet surface — central conformance and reconcile" under `## Cross-repo coordination automation surface`. For a member whose master tree carries `.github/workflows/auto-enable-merge.yml`, the row requires `.github/workflows/disarm-on-hold-label.yml` beside it. It also requires the `actions/create-github-app-token` step of each file to name the same App-credential input key, `app-id` or `client-id`. It reports a mismatch and a missing disarm workflow as error findings, and it skips an unreadable workflow under the can't-read-is-not-absent discipline. Two scenarios state the behaviour.

### Motivation

livespec core makes the hold-label disarm workflow fleet policy (`livespec/SPECIFICATION/non-functional-requirements.md` §"Shared content sync — copier template", livespec v240). On 2026-11-11 three members were found carrying `auto-enable-merge.yml` with no `disarm-on-hold-label.yml`: livespec-orchestrator-git-jsonl, livespec-driver-pi and livespec-console-beads-fabro. In git-jsonl, which is template-born, that gap made every revise fail its post-step doctor. Nothing central detected it, because a repository missing wiring never fails a check it does not run, the gap §"Fleet surface — central conformance and reconcile" exists to close. Members also carry the disarm copy with differing token-action input keys: drivers that pin an older action major use `app-id`, and the rest use `client-id`. GitHub accepts the App ID as the JWT issuer under either key, so both are valid. The disarm workflow must mint its token exactly as the same member's auto-merge workflow does, so the row checks that match and nothing more. Work item livespec-dev-tooling-4mhpf4 carries the implementation; its filing seam classified the row as a spec change because this specification does not yet state it.

### Proposed Changes

In `SPECIFICATION/contracts.md`, under `## Cross-repo coordination automation surface` → `### Fleet surface — central conformance and reconcile`, add this paragraph directly after the **Vendored-tree pin fidelity** paragraph:

**Hold-label disarm token-key match (the `disarm-token-key-matches-auto-merge` obligation row).** For every manifest member whose master tree carries `.github/workflows/auto-enable-merge.yml`, the assert-mode row MUST find `.github/workflows/disarm-on-hold-label.yml` in the same tree, the counterpart that turns off the rebase auto-merge the first arms (`livespec/SPECIFICATION/non-functional-requirements.md` §"Shared content sync — copier template"). The row MUST compare the App-credential input key that each file's `actions/create-github-app-token` step names, `app-id` or `client-id`. Both keys are valid, so the row checks only that a member's two files name the same one. A member whose two files name different keys is an ERROR finding naming the member, both files and both keys. A member carrying `auto-enable-merge.yml` and no `disarm-on-hold-label.yml` is an ERROR finding naming the member and the missing file. A member whose workflow file cannot be read is skipped under the can't-read-is-not-absent discipline, never judged as matching. A member carrying neither file is outside the row.

In `SPECIFICATION/scenarios.md`, add two scenarios:

## Scenario: fleet conformance reports a member whose disarm workflow mints its App token with a different input key than its auto-merge workflow

Given a fleet manifest member whose `.github/workflows/auto-enable-merge.yml` mints its App token with `app-id`

And whose `.github/workflows/disarm-on-hold-label.yml` mints it with `client-id`

When the fleet conformance check runs in assert mode

Then it MUST report an error finding naming the member, both workflow files and both input keys

And a member whose two files name the same key, either `app-id` or `client-id`, MUST produce no finding from this row

## Scenario: fleet conformance reports a member that arms auto-merge without the hold-label disarm workflow

Given a fleet manifest member whose master tree carries `.github/workflows/auto-enable-merge.yml` and no `.github/workflows/disarm-on-hold-label.yml`

When the fleet conformance check runs in assert mode

Then it MUST report an error finding naming the member and the missing `disarm-on-hold-label.yml`

And a member whose workflow tree cannot be read MUST be skipped, not reported as missing the file

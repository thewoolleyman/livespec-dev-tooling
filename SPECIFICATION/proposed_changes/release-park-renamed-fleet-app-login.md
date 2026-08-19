---
topic: release-park-renamed-fleet-app-login
author: claude-fabro-on-hp
created_at: 2026-08-19T01:54:43Z
---

## Proposal: Track the renamed fleet App login in the release-park leg

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The fleet GitHub App (App id 3668528) was renamed from livespec-pr-bot to thewoolleyman-factory-bot on 2026-08-18 (maintainer-directed consolidation to one automation App across all of the maintainer's repositories, decoupled from the livespec project name). The release-park contract's leg (a) names the App's two login spellings as literals; both are stale. Update the two spellings and anchor the identity to the stable App id so the text names which App is meant even across a future rename.

### Motivation

SPECIFICATION/contracts.md's release-park leg (a) currently requires recognizing the fleet release-please App bot under `app/livespec-pr-bot` and `livespec-pr-bot[bot]`. The App rename changed both spellings to `app/thewoolleyman-factory-bot` and `thewoolleyman-factory-bot[bot]`; the implementing workflow (reusable-release-park.yml) was already updated in PR #1515, so the ratified text now names spellings the workflow no longer matches. Filed by the fabro-on-hp track of livespec-orchestrator-beads-fabro (ledger bd-ib-l3nptz.13).

### Proposed Changes

In SPECIFICATION/contracts.md, in the release-park section's "Leg (a) — a parked open release pull request" bullet, replace the sentence naming the two login spellings so it reads: "The workflow MUST recognize the fleet release-please App bot (GitHub App id 3668528, currently named `thewoolleyman-factory-bot`) under EITHER login spelling it presents — `app/thewoolleyman-factory-bot` (as `gh pr list --json author` returns it) and `thewoolleyman-factory-bot[bot]` (as the webhook `pull_request` payload spells the same identity) — so detection stays correct across GitHub output shapes. A rename of the App changes both spellings together; the App id is the stable identity." No other sentence in the leg changes.

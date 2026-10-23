---
proposal: dev-host-fabro-client-builds.md
decision: accept
revised_at: 2026-10-23T15:31:37Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by plan session fabro-currency (orchestrator plan bd-ib-6tcjfx), which owns work-item livespec-dev-tooling-lirki2 end to end by fleet coordinator assignment (gitops-fleet-capacity-monitoring, 2026-10-23). Dispatchers on vps reach the legacy factory through the host PATH client (fabro 0.254) and the petri factory through a committed dispatcher.factories.petri.bin that was staged by hand; no section of this specification governs client binaries on a dev host, so the fleet's routing rested on a binary nobody could reproduce or audit, and the PATH client cannot move to the petri family until the legacy factory pins its own bin (bd-ib-zb2hso). This revision adds Dev host Fabro client builds: builds declared once in group_vars/dev_hosts.yml with path, source and sha256; committed bins must name a declared path (a repo-private, vacuous-when-empty check); every entry validated before any write, refusing among others any path that denotes the same file as a fabro_server binary_path; atomic placement through <path>.incoming with mode, owner and digest set before the rename; nothing removed beyond a declared entry's own staging file. One new scenario; two heading-coverage rows owned by livespec-dev-tooling-lirki2. Registry-side bin admission is routed to livespec-dev-tooling-ulct7a. Independent Fable review of the proposal: round 1 BLOCKERS 5, round 2 BLOCKERS 3, round 3 BLOCKERS 2, round 4 BLOCKERS 2, round 5 BLOCKERS 2, each answered by an amendment commit and recorded on livespec-dev-tooling-lirki2; round 6 NO BLOCKERS, whose recommended structural notes were applied before revise. Ratification review on the exact resulting bytes is recorded below.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-23T15:30:30Z
verdict: NO BLOCKERS
proposal_stem: dev-host-fabro-client-builds
content_digest: b03a720418eae5c50c01a15bf5cd71d0787659fb5b9c0970ae45c3d62f7283a0

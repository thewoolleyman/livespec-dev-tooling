---
proposal: forge-read-joins-the-composite-actions-minimum-set.md
decision: accept
revised_at: 2026-11-15T06:59:35Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written under delegated decision mode. Release v1.203.0 (and v1.204.0, v1.205.0) ships .github/actions/forge-read, byte-identical to master and declaring no inputs or outputs, so the Action can join the semver-stable minimum set of the Composite Actions wire contract without the semver surface test refusing it: tests/consumer/test_semver_stable_surface.py and test_composite_actions_wire_contract.py plus tests/spec pass against the drafted bytes (623 passed), and the semver test fails with unwired=['forge-read'] when the Action directory is removed, so the minimum set now protects it. The second proposal section corrects 'idempotent by binding and digest' to 'idempotent by identity', which agrees with the preceding sentence that defines an unpublished record's identity without a digest. Together the two sections discharge all three Definition of Done lines of livespec-dev-tooling-2cs5jj. No heading changes. The independent sonnet review returned NO BLOCKERS on the exact bytes.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T06:59:10Z
verdict: NO BLOCKERS
proposal_stem: forge-read-joins-the-composite-actions-minimum-set
content_digest: 89a12f67de36200485ae1ad00116b7bb15a44cd587254e117897cea5c300c72c

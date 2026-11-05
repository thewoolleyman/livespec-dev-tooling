---
proposal: flake-retry-directory-match-uses-the-full-path.md
decision: modify
revised_at: 2026-11-05T16:45:27Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). Delegated decider: legacy-coordinator-agent under R301, which ruled ACCEPT-the-MODIFY on 2026-11-05 at ~14:15Z and re-confirmed it on these rebuilt bytes at ~16:45Z, after v141 changed scenarios.md. Carrier: livespec-dev-tooling-sdrq5v (plan dev-host-test-gate-load). Measured: livespec-dev-tooling#3474 changed only ci-runner/k3s/phase2/factory/DERIVATION.md under ci-runner/, and on run 41986660733 the readiness-boundary flake in test_stand_in_proxy_readiness_boundary.py went unretried, because the old rule counted any parent directory NAME appearing as a literal (here `ci-runner`) as touching. A shared ancestor name is not evidence of a dependency. No other ratified statement of the touched-test rule exists to conflict, and no design record is contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes. Its non-blocking note: a partially dynamic path join erring toward touched follows from the undeterminable clause rather than being stated on its own.

## Modifications

The proposal's replacement sentence ('lies under a directory the closure names by its full repository-relative path') was replaced by the decider's ratified wording. A changed path touches a test when it is inside a directory the closure names. A named path is one literal or the WHOLE join of consecutive string-literal segments of one path expression. A named file names its own directory, and a named directory names itself. A proper ancestor of a named path MUST NOT by itself make a test touched, shown with the `ROOT / "ci-runner" / ... / "x.sh"` example. An undeterminable closure counts as touched. The touched-test scenario's second Given became 'a path or file name that closure names, or a file inside a directory that closure names', in place of the proposal's 'full repository-relative path' wording. The proposal's new ancestor-only retry scenario is inserted as filed.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T16:42:45Z
verdict: NO BLOCKERS
proposal_stem: flake-retry-directory-match-uses-the-full-path
content_digest: 02c6ca5af4a6f9f3ffabe0134398d4c6d859f960ecbed3a9fbd3208c1fc36d17

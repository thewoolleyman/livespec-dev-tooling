---
proposal: range-replay-verifies-a-suite-green-commit-s-behaviour-preservin.md
decision: modify
revised_at: 2026-11-09T15:09:46Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:sandbox-commit-gate-ceiling
---

## Decision and Rationale

legacy-coordinator-agent decided this proposal under its R301 authority (2026-11-09): ACCEPT Alternative B (parent-tree replay), REJECT Alternative A (static diff discriminator). B judges behaviour rather than diff shape. A refactor that adds characterization tests passes, because those tests pass on the parent. A feature commit whose new tests are red on the parent is refused, and so is a commit that changes an existing test to assert new behaviour. A's coarseness cuts both ways: it refuses genuine refactors that add tests, and it passes feature commits that add behaviour without a new test function. The measured instance is livespec-orchestrator-beads-fabro PR #4733's commit 9e77e7b02. It added a whole feature (+1400/-46, new test modules) under TDD-Suite-Green-* trailers alone, and check-red-green-replay passed it. Under B its new tests fail on the parent, so it is refused. The independent read-only sonnet review found no blockers. Its non-blocking notes go to the implementation carrier livespec-dev-tooling-5uobsl: (1) the leg-side MUST could name the product-.py condition explicitly; (2) the parent-tree replay is not satisfied by Same-tree reuse, which covers only the full-suite run; (3) the absent Parent-Replay trailer refusal path has no scenario of its own. Release notes for the implementing release must name the new TDD-Suite-Green-Parent-Replay trailer, per the same ruling. Carrier: livespec-dev-tooling-5uobsl.

## Modifications

Accepted the proposal's Alternative B section and rejected its Alternative A section in the same file. Alternative B's text is carried into contracts.md §"Suite-green replay leg" (the opening-paragraph replacement and the new **Behaviour-preserving claim.** bullet), with four additions. (1) A test module the commit DELETES is not a claimed test. (2) On refusal the leg records no TDD-Suite-Green-* trailer. (3) A residual sentence records the shared blind spot: a commit that adds behaviour and no test is not caught. (4) A fleet-scope sentence says the bullet binds every consumer of the shared red_green_replay check, and a spec-first sentence names livespec-dev-tooling-5uobsl. The proposal's Alternative B scenario is added to scenarios.md with MUST in its Then lines, matching the file's convention. tests/heading-coverage.json and tests/heading-coverage-debt.json get the new heading's TODO row in the same commit.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T15:07:19Z
verdict: NO BLOCKERS
proposal_stem: range-replay-verifies-a-suite-green-commit-s-behaviour-preservin
content_digest: 3f86485762beed367d1e2fb86a22816b641a2a91be69a5df5bd72b75bb1aa885

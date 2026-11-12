---
proposal: a-consumer-verifies-its-own-dev-tooling-imports-are-declared.md
decision: modify
revised_at: 2026-11-12T06:58:42Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The proposal's intent is accepted: livespec-dev-tooling ships its cross_repo_public_api declaration as package data so a consuming repository can verify, against its INSTALLED build, that every livespec_dev_tooling function it reaches is declared or already public, through a commit-hook workflow check kept out of checks/ until a fleet-wide zero-offender measurement (maintainer GO relayed by legacy-coordinator-agent, 2026-11-12; carrier livespec-dev-tooling-vobfwi). A pre-merge doctor pass walking the text through live code found that the text as proposed (a) scanned only the first-party tree, which in this codebase excludes the test tree, so it would miss the motivating import in livespec-orchestrator-git-jsonl's tests/integration; (b) would report `_`-prefixed reaches the central graph drops under clause 0, whose stated remedy (declaring them) is forbidden; (c) claimed the two vantages cannot disagree, when the consumer evaluates the oracle over a different source universe; (d) left 'a check this repository ships' ambiguous for a shipped workflow check the purity resolver does not read; (e) advised `just check` membership in apparent conflict with the workflow-check category; (f) used a loose exit code and print; (g) judged a build rather than a tree; (h) measured repositories that cannot install the package; and (i) left warn mode, the attribute reach and the package-data equality refusal without scenarios. It also obliged this repository to run a consumer check over its own imports, which cross no repository boundary. The modifications fix each, keeping BCP14 clauses beside the rules they extend, and add spec-first sentences naming livespec-dev-tooling-vobfwi. A second doctor pass on the corrected bytes and the independent sonnet review returned no blocking finding.

## Modifications

1. The package data is a committed file inside the package, judged per tree; spec-first sentences name livespec-dev-tooling-vobfwi as owner. 2. The consumer check reads the consuming universe the central row reads (first-party plus test tree), collects only non-`_`-prefixed top-level functions (clause 0), uses the central row's reach resolution and oracle, reports structured findings on stderr, and exits `4` in fail mode. 3. The completeness sentence states the one-directional disagreement honestly: the consumer evaluates the oracle over the installed package's files filtered by the central row's first-party rule, so it can only be stricter for the same build, and declaring is the remedy. 4. `just check` membership is a repo-private aggregate member, and such a member MUST be declared world-reading in check-targets.txt. 5. livespec-dev-tooling does not run the consumer check on its own checkout. 6. The arming precondition covers every governed repository that installs livespec-dev-tooling. 7. Scenarios: the three proposed (exit 4 named), the passing one gains an `_`-prefixed import, and three are added: warn mode, attribute reach, and the package-data/pyproject disagreement refusal.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T06:57:48Z
verdict: NO BLOCKERS
proposal_stem: a-consumer-verifies-its-own-dev-tooling-imports-are-declared
content_digest: 909bc4d0cf480d7c15131a651553d67571712c1d87772b8b77539cfac22a1e69

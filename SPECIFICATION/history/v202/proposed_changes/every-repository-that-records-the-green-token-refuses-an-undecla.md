---
topic: every-repository-that-records-the-green-token-refuses-an-undecla
author: claude-opus-5-5
created_at: 2026-11-12T02:23:44Z
---

## Proposal: Every repository that records the green token refuses an aggregate member with no purity declaration

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Widen the aggregate-refusal sentence of §"Delegated pre-push gate", Token memoization bullet, from livespec-dev-tooling's own aggregate to the check aggregate of every repository that records the green token. Name the shared command a consumer uses for it (`python -m livespec_dev_tooling.green_token undeclared`) and the inventory where a repository-only member carries its declaration (`check-targets.txt`), and add one scenario for a consuming repository.

### Motivation

Seven per-repository krc2yd slices (livespec-driver-claude-d5hgms, livespec-driver-codex-xzlzvd, livespec-driver-pi-ee555c, bd-gj-kiflbk, livespec-runtime-u6vrc5, livespec-console-beads-fabro-2cix4o, bd-ib-p2qt2j) each built an aggregate refusal of an undeclared member in their own repository, as plan implement-test-performance directed. On orchestrator v0.320.0 their spec-change-tier judgement reads partial or unstated, and two of them are merge-held. The judgement is right. The Token memoization bullet binds every repository that records the green token on DECLARING ("Each member of a gate's check set carries its own purity declaration ... A member that exists only in one repository is declared by that repository"), but it states the REFUSAL only as "This repository's own check aggregate MUST fail", which binds livespec-dev-tooling alone. Without the refusal, a consumer's undeclared member silently falls back to world-reading and the token's saving shrinks unnoticed in exactly the repositories the bullet already binds. No per-repository proposal for this exists in any of the ten governed repositories. One fleet-contract amendment here, followed by a recorded attestation per slice, closes the gap instead of seven catch-up proposals.

### Proposed Changes

1. In SPECIFICATION/contracts.md §"Delegated pre-push gate", Token memoization bullet, replace the sentence "This repository's own check aggregate MUST fail, naming the member, when one of its members carries no purity declaration." with:

"The check aggregate of every repository that records the green token MUST fail, naming the member, when one of its members carries no purity declaration, and it MUST make that refusal before it runs any member. A consuming repository SHOULD make the refusal through `python -m livespec_dev_tooling.green_token undeclared <member>...`, passing its full aggregate member list in aggregate order. That command MUST print, one per line, each given member that carries no purity declaration, MUST exit 1 when there is any and 0 when there is none, and MUST fail on an empty member list, because an empty answer read as "no undeclared member" would let every member go unjudged. The refusal SHOULD run inside the aggregate recipe's own body rather than as a new aggregate member, because a new member obliges a CI matrix entry. A member that exists only in one repository carries its declaration in that repository's own inventory, the repository-root `check-targets.txt`, as one line per aggregate member of the form `<member>  # purity: tree-pure` or `<member>  # purity: world-reading`. A check this repository ships declares its own purity in its module, and that declaration MUST take precedence over any line the consumer's inventory carries for the same member."

The two sentences that follow it ("Without that refusal ..." and "This bullet binds the pre-push gate of every repository that records the green token, whether or not it delegates.") are unchanged.

2. In SPECIFICATION/scenarios.md, add after `## Scenario: a check aggregate member with no purity declaration fails the aggregate`:

```gherkin
## Scenario: a consuming repository's check aggregate refuses a member with no purity declaration

Given a consuming repository that records the green token
And a member of its `just check` aggregate that is not a check livespec-dev-tooling ships and has no purity line in the repository's `check-targets.txt`

When the repository's `just check` aggregate runs

Then the aggregate MUST exit non-zero before any member runs
And its output MUST name that member
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the same commit, either naming an existing test that exercises it or as a spec-first TODO row that names its tier and an open owning work item, and MUST regenerate `tests/heading-coverage-debt.json`. After this revision ratifies, each of the seven slices above MAY be recorded as conforming to this clause rather than carrying a proposal of its own.

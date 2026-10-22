---
topic: stale-pin-keeps-member-in-fan-out
author: claude:delegated-gate-fleet-rollout
created_at: 2026-10-22T18:11:36Z
---

## Proposal: A stale pin keeps its member in the release fan-out

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The two staleness classes (fired-and-could-not-land, never-fired) MUST stay error-severity in the fan-out preflight and MUST be named in its exclusion summary, but MUST NOT exclude the member from the dispatch matrix. A can't-parse pin finding, and every non-pin-currency error row, still excludes. The sibling-released dispatch is itself the remedy for a stale pin, so excluding on staleness removes the cure.

### Motivation

Measured 2026-10-22 (coordinator R609, work item livespec-dev-tooling-epcoja): livespec-console-beads-fabro last received a sibling-released dispatch on 2026-10-15T13:12Z, while every other manifest member received the v1.125.0 dispatch at 10:43Z. The fan-out preflight excluded console on ONE error row: compat-pin-currency, fired-and-could-not-land, because console's livespec bump PR #1250 has been red since 10-15 on a stale cargo-deny advisory. The exclusion is per MEMBER, not per source, so console also lost every dev-tooling, orchestrator and runtime dispatch, which are the dispatches whose bump PRs open fresh, superseding PRs for its stale pins. For seven days only the daily pin-freshness sweep moved it. DESIGN RECORD: this section's escalation comes from livespec-dh9r (2026-07-21), where one unwired member blocked the WHOLE fan-out and the stall was silent. dh9r's two intents were: never let one member block the others, and never let a stall be silent. This proposal keeps both. It narrows only WHICH error rows exclude: a stale pin is the condition a dispatch repairs, whereas a can't-parse pin file, missing secrets, a missing shim or a missing App installation are conditions a dispatch cannot repair. It departs from the current literal text ('An error finding for a member in the release's dispatch sibling set excludes that member'), so its ratification needs the maintainer's explicit acknowledgment of that departure.

### Proposed Changes

In SPECIFICATION/contracts.md, section 'Pin-currency severity policy':

1. In the bullet 'BOTH CLASSES ESCALATE ONLY WHERE A PER-MEMBER REMEDY EXISTS', replace the sentence beginning 'A finding in either class escalates to error ONLY when it is evaluated in a context that can act on it PER MEMBER' with: 'A finding in either class escalates to error ONLY when it is evaluated in the release fan-out preflight, whose exclusion summary names every error finding per member. A staleness-class finding MUST NOT exclude its member from the dispatch matrix: the sibling-released dispatch is the remedy for a stale pin, because the bump pull request it opens supersedes any stuck one, so excluding the member removes the cure.'

2. Replace the final paragraph ('An error finding for a member in the release's dispatch sibling set excludes that member ...') with: 'An error finding for a member in the release's dispatch sibling set excludes that member from the dispatch matrix via the fan-out preflight's per-member filter (the reusable-release-dispatch.yml contract), EXCEPT a finding of either staleness class, which MUST remain error-severity and be named in the exclusion summary but MUST NOT exclude the member. A can't-parse pin finding still excludes, because the bump rewrite cannot be applied to a pin file that does not parse. An excluding finding never halts dispatch to conformant members.'

In section 'reusable-release-dispatch.yml', in the paragraph 'Fleet-conformance preflight (per-member FILTER ...)', after 'each non-conformant member that is in the dispatch SIBLING SET is then excluded from the fan-out loudly' insert: '(a member whose only error findings are pin-currency staleness findings is NOT excluded; those findings are named in the run's summary and the member is dispatched to)'.

Add to SPECIFICATION/scenarios.md:

## Scenario: a member whose only error findings are stale pins still receives the release dispatch

Given a fleet member whose only error-severity findings in the fan-out preflight are pin-currency staleness findings

When the release fan-out filters its dispatch matrix

Then the member MUST receive the sibling-released dispatch

And the run's exclusion summary MUST name each of those findings for that member

## Scenario: a member with an unparseable pin file or a non-pin error row is still excluded from the release dispatch

Given a fleet member with an error-severity can't-parse pin finding, or an error-severity finding on a row other than a pin-currency row

When the release fan-out filters its dispatch matrix

Then the member MUST be excluded from the dispatch with an annotation naming it and the failing rows

The revise MUST co-edit tests/heading-coverage.json with an entry for each new scenario (test TODO owned by livespec-dev-tooling-epcoja) and regenerate the debt register.

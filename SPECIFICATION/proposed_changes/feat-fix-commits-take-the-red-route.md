---
topic: feat-fix-commits-take-the-red-route
author: claude-opus-5-5
created_at: 2026-11-10T11:09:17Z
---

## Proposal: A feat or fix commit that stages product code takes the Red route

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Close the residual the Behaviour-preserving claim bullet recorded at ratification: a commit that adds behaviour with no claimed test passes on suite-green alone. A commit whose subject type is feat or fix declares a behaviour change, so when it stages product impl .py with no Red awaiting its Green, the commit-msg gate MUST refuse it toward the Red route instead of running the suite-green leg, and the range validation MUST refuse such a commit without the Red/Green pair shape. Chores and refactors keep the suite-green leg, so a chore that contains product code stays legitimate.

### Motivation

Measured by sandbox-commit-gate-ceiling (relayed by legacy-coordinator-agent, 2026-11-10): seven fix:/feat: product commits fleet-wide in seven days landed with TDD-Suite-Green-* trailers only and no checkable Red, for example livespec-orchestrator-beads-fabro 6ffb83e8 and c9db1b24 and livespec-driver-codex 0e6068a4 and dab5a4d5. red_green_replay's branch 5 routes any product .py commit with no Red awaiting its Green to the suite-green leg, whatever its prefix, and the range check accepts either shape. The spec is internally inconsistent here: non-functional-requirements.md says a feat: or fix: commit MUST be preceded by a Red commit, while contracts.md's Behaviour-preserving claim bullet accepts a no-claimed-test product commit on its full-suite green and records that as a residual. The gate's branch 3 already treats feat:/fix: as a declared behaviour change (test-passed-at-red); this extends that same reading to branch 5. The 2026-06-11 design correction that the prefix never rejects a commit for containing product code is preserved for every non-feat/fix type. The parent-tree replay half of the same gap is already owned by livespec-dev-tooling-5uobsl.


**Options for the maintainer (maintainer-tier decision).** Accepting this proposal narrows the reach of the maintainer's recorded 2026-06-11 design correction, which `red_green_replay.py` quotes as "the subject prefix NEVER rejects a commit for containing product code" (made after work item eld). legacy-coordinator-agent routed the choice to the maintainer: their words exist, so only they can change the ruling. The revise that processes this file waits for that choice.

- **(A) RECOMMENDED: a `feat:`/`fix:` product commit takes the Red route.** This is the change stated under Proposed Changes. The 2026-06-11 correction keeps full force for every other subject type: a chore or refactor containing product code is still legitimate and still takes the suite-green leg. The prefix gains force only where the author DECLARES a behaviour change, the same reading the gate's branch 3 already applies (`test-passed-at-red`). It resolves the spec's internal inconsistency toward non-functional-requirements.md's existing MUST, so a declared fix or feature always carries a failing-then-passing test.
- **(B) Keep content-only routing and relax non-functional-requirements.md to match the contract.** The Test-Driven Development discipline bullet would say a `feat:`/`fix:` commit SHOULD, rather than MUST, be preceded by a Red. The full-suite green and, once livespec-dev-tooling-5uobsl ships, the parent-tree replay of claimed tests stay the only evidence for a no-test behaviour change. This preserves the 2026-06-11 correction unchanged, at the cost of a declared fix that never proves it fixed anything.
- **(C) Keep both texts and record the residual as accepted.** No gate change. The inconsistency between the two spec files stays, written down as deliberate. The seven measured commits remain legal.

The recommendation is (A). It is the only option under which a commit that claims to fix or add behaviour must show a test that failed without it. It costs nothing for the content-triggered chore path the 2026-06-11 correction protects.

### Proposed Changes

In SPECIFICATION/contracts.md §"Suite-green replay leg", replace the residual sentence of the **Behaviour-preserving claim** bullet ("Residual, recorded at ratification: a commit that adds behaviour and adds or changes no test module has no claimed tests, so this bullet does not catch it; its full-suite green stays its only evidence.") with a new bullet placed directly after it:

- **A declared behaviour change takes the Red route.** A commit whose Conventional Commits subject type is `feat` or `fix` (with or without a scope or a `!`) and that stages product impl `.py` declares a behaviour change. When such a commit has no Red awaiting its Green at HEAD, the commit-msg replay gate MUST NOT run the suite-green leg for it: it MUST refuse the commit with an event that names the `feat`/`fix` subject and tells the committer to take the Red-then-Green route, and it MUST NOT record any `TDD-Suite-Green-*` trailer. The commit-range validation (`check-red-green-replay`) MUST refuse any commit in its range whose subject type is `feat` or `fix`, that touches product impl `.py`, and that does not carry the `TDD-Red-*`/`TDD-Green-*` pair shape; its failure MUST name the commit and its subject. A commit of any other subject type keeps the suite-green leg and the **Behaviour-preserving claim** bullet unchanged, so a chore or refactor that contains product code remains legitimate. The forge-authored revert exemption and the recorded-incident exemption of the range validation apply to this rule exactly as to the trailer-shape rules, and no lever, flag or other subject prefix MAY exempt it. Fleet scope: the shared `red_green_replay` check, so every consuming repository whose commit-msg hook or CI runs it. This bullet is spec-first; work item livespec-dev-tooling-qfmslo owns the change.

In SPECIFICATION/scenarios.md, add:

## Scenario: a feat or fix commit that stages product code with no Red awaiting its Green is refused toward the Red route

Given a repository whose commit-msg hook runs the shared `red_green_replay` check

And HEAD carries no `TDD-Red-*` trailers awaiting `TDD-Green-*` trailers

When a commit whose subject is `fix: <summary>` stages a product impl `.py` change and no test module

Then the commit-msg replay gate MUST refuse the commit with an event naming the `fix` subject and the Red-then-Green route

And the gate MUST NOT record any `TDD-Suite-Green-*` trailer

And when the same change is committed with the subject `chore: <summary>`, the gate MUST run the suite-green leg as before

And when the commit-range validation judges a range containing a `feat:` or `fix:` commit that touches product impl `.py` and carries only `TDD-Suite-Green-*` trailers, it MUST fail naming that commit and its subject

The revise that accepts this MUST add a `tests/heading-coverage.json` row for the new scenario heading (a spec-first TODO row naming the integration tier and work_item livespec-dev-tooling-qfmslo) and regenerate `tests/heading-coverage-debt.json`.

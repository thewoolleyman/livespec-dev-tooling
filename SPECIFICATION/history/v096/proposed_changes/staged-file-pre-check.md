---
topic: staged-file-pre-check
author: claude-opus-5-5
created_at: 2026-10-24T22:15:25Z
---

## Proposal: The pre-commit aggregate starts with a seconds-scale lint and type pre-check of the staged Python files

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Make `just check-pre-commit` begin with a staged-file pre-check that lints the staged Python files and type-checks those the type-checker configuration covers. It refuses in seconds, naming file, line and rule, before the full pre-commit aggregate starts. A commit that passes proceeds to the aggregate unchanged. The pre-check is a shared module so the fleet's factory-dispatching repositories can adopt it.

### Motivation

Work-item livespec-dev-tooling-nil6v7 (plan livespec-dev-tooling-dfixhe, assertion 14), filed on the maintainer's 2026-10-24 direction to fix the factory's slow-refusal points. Evidence: factory run 01M5QNH88NHN68ST28Y80CZJ48 (bd-ib-8zyan, petri on gmktec). The Green amend's pre-commit hook took 711.4 s to refuse on 3 pyright errors in one new module (reportUnknownVariableType and reportUnusedCallResult). About 35 of the turn's 44 minutes were gate runs, and the turn gave up 30 s after a fixable refusal with 196 minutes left. Lint and type findings on staged files are the cheapest refusals, and they reach the agent last because they run inside the full aggregate. §"Hooks and CI" states the hook ordering but not this pre-check, so the item needs a governing clause.

### Proposed Changes

**Edit 1 — `non-functional-requirements.md` §"Hooks and CI".** Append to the first paragraph:

> `just check-pre-commit` MUST begin, whenever the staged tree contains Python files, with a staged-file pre-check. The pre-check lints the staged Python files and type-checks those of them that the repository's type-checker configuration covers. On any finding it MUST refuse the commit, naming each finding's file, line and rule, before any member of the full pre-commit aggregate starts. A commit whose staged Python files pass the pre-check MUST proceed to the full pre-commit aggregate, which runs exactly as it would without the pre-check. The pre-check MUST NOT judge a staged file that the repository's lint or type-checker configuration excludes. It ships as a shared module of this library, so every consuming repository can run it at the head of its own `check-pre-commit`.

**Edit 2 — `scenarios.md`.** Add two scenarios:

```
## Scenario: a staged type error refuses the commit before the full pre-commit aggregate

Given a governed repository whose pre-commit hook runs `just check-pre-commit`

And ten staged Python files that the repository's type-checker configuration covers, one of which carries a type-checker error

When a git commit is made

Then the commit MUST be refused within 60 seconds of the commit starting

And the refusal MUST name the file, line and rule of the type-checker error

And no member of the full pre-commit aggregate MUST have started

## Scenario: a staged lint error refuses the commit before the full pre-commit aggregate

Given a governed repository whose pre-commit hook runs `just check-pre-commit`

And a staged Python file carrying a lint error that the lint autofix step does not fix

When a git commit is made

Then the commit MUST be refused naming the file, line and rule of the lint error

And no member of the full pre-commit aggregate MUST have started
```

`tests/heading-coverage.json` gains one entry per scenario, TODO with a reason naming livespec-dev-tooling-nil6v7, and `tests/heading-coverage-debt.json` gains the matching debt entries. The implementing change replaces the TODOs with its test.

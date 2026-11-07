---
topic: no-gate-runs-actionlint-over
author: claude-opus-5-5
created_at: 2026-11-07T20:33:39Z
---

## Proposal: A workflow GitHub cannot parse is refused at commit, push and pull request

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

actionlint runs over `.github/workflows` at the commit gate, the push gate and a gating CI job.

### Motivation

livespec-dev-tooling#3317 merged a release-please.yml GitHub could not parse. Its commit gate, push gate and PR CI all passed, and no release could be cut until the fix landed. Only actionlint reports this shape. Carries work items livespec-dev-tooling-f3q7r7 and livespec-dev-tooling-hhflha.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "## Hooks and CI", add this paragraph:

**Workflow files must parse.** A commit that stages a `.github/workflows/*.yml` file actionlint reports as unparseable MUST be refused by the pre-commit gate, which MUST name the file, the line and actionlint's syntax-check message. A push whose range carries such a file MUST be refused by the pre-push gate, and a pull request whose tree carries one MUST fail a gating CI job; each MUST name the file and the line. The check MUST be exposed as a shared check consumers run through their pinned livespec-dev-tooling, with no copy of its logic in the consumer.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario: a workflow GitHub cannot parse is refused at every gate

Given a `.github/workflows/*.yml` file that actionlint reports as unparseable

When it is committed, pushed, or carried by a pull request

Then the pre-commit gate MUST refuse the commit, naming the file, the line and the syntax-check message
And the pre-push gate MUST refuse the push, naming the file and the line
And a gating CI job MUST fail, naming the file and the line

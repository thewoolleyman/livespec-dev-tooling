---
topic: reusable-check-matrix-incident-omitted-input
author: claude-opus-5-5
created_at: 2026-11-10T02:57:49Z
---

## Proposal: reusable-check-matrix declares its incident-omitted input

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

contracts.md §"Reusable workflows wire contract" lists `checks` as the only input of `reusable-check-matrix.yml`. livespec-dev-tooling#3966 (livespec-dev-tooling-hlxbsv) adds an optional `incident-omitted` input and a per-leg omitted-by-incident-policy step. This proposal brings the wire contract level with that input: its type and default, the members it may name, the incident authority under which it is honoured, the events on which it is ignored, how an omitted leg reports, and the fail-closed rule for a malformed value. The omission policy itself stays in §"Expedited incident execution" and is not restated.

### Motivation

The omission behaviour is already spec-stated in contracts.md §"Expedited incident execution" and in the scenario "an expedited PR defers coverage and spec work while master runs normally". The wire contract has not kept up: it names only the `checks` input. The independent review of livespec-dev-tooling#3966 (https://github.com/thewoolleyman/livespec-dev-tooling/pull/3966#issuecomment-6757586369, finding 1) showed why the input's contract matters. An omitted leg concludes green under its protected check name, so a caller that wires the input with any expression other than the guarded incident-ci output would turn required checks green on every pull request. The design is being tightened in-lane: the decision module will require the trusted incident label and a same-repository head, bind to incident-ci's guarded output, and run its decision code from a released ref. This is a docs-lag topic. It records the published input's wire shape and the authority it requires, so the contract states what callers of a semver-stable workflow can rely on.

### Proposed Changes

In `contracts.md` §"Reusable workflows wire contract", replace the `reusable-check-matrix.yml` bullet with the following bullet and the paragraph after it.

```diff
-- **`reusable-check-matrix.yml`**. Inputs: `checks` (a JSON-array string of check slugs to run; default = a documented "standard suite"). Strategy: matrix over the `checks` input; each matrix entry runs the `run-check` composite Action. Outputs: per-check pass/fail.
+- **`reusable-check-matrix.yml`**. Inputs: `checks` (a JSON-array string of check slugs to run; default = a documented "standard suite") and `incident-omitted` (optional; a JSON-array string of check names; default empty, `'[]'`). Strategy: matrix over the `checks` input; each matrix entry runs the `run-check` composite Action. Outputs: per-check pass/fail.
+
+The `incident-omitted` input carries, into this workflow, the omission that §"Expedited incident execution" defines; this paragraph states only its wire contract. The input MAY name only the coverage and spec-enforcement members that the incident policy defers. A named check outside that set MUST NOT be omitted and MUST run. The workflow MUST honour the input only on a `pull_request` event whose incident authority it has verified: the trusted PR-specific incident label is present on the pull request, the pull request's head is in the same repository as its base, and the input's value is the caller's incident-ci job's guarded output. When any of those three does not hold, the workflow MUST run every requested check. A master push, and every event other than `pull_request`, MUST run every requested check whatever the input carries. Each omitted leg MUST report `omitted-by-incident-policy` under its real check name; it MUST NOT be dropped from the matrix or skipped silently. A value that is not a JSON array of strings MUST fail the leg closed: the leg fails before it reports any omission. Membership MUST be exact name equality, never a substring test.
```

In `scenarios.md`, the scenario "an expedited PR defers coverage and spec work while master runs normally" MUST gain two `And` lines after its last line, so the wire contract has a scenario without adding an H2 heading:

```diff
 And every normal master push disables both incident flags and selects its complete normal job graph regardless of PR labels, markers or ambient configuration.
+And the reusable check matrix honours an incident-omitted list only on a pull_request whose trusted incident label, same-repository head and caller incident-ci guarded output are verified, and each leg it omits reports omitted-by-incident-policy under its real check name.
+And that workflow runs every requested check on a master push or any other event whatever the input carries, and fails a leg closed on an input that is not a JSON array of strings.
```

No `## ` heading is added, renamed or removed, so `tests/heading-coverage.json` MUST NOT change.

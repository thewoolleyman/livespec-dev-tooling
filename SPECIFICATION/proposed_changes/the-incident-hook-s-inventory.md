---
topic: the-incident-hook-s-inventory
author: claude-opus-5-5 (expedited-incident-response-flag)
created_at: 2026-11-13T05:15:00Z
---

## Proposal: The expedited hook reads every inventory member and refuses one whose timing class it cannot read

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amends contracts.md section Expedited incident execution and the scenario "an expedited local gate skips slow work and preserves fast failures". The expedited local hooks read every member of the repository's committed check-targets.txt inventory whatever its name, not only `check-` slugs. A member is deferred only when its timing is declared slow or not-applicable, or when it is selected and reaches the sixty-second deadline. A member with no timing declaration, an unrecognised declaration, two conflicting declarations, a member listed more than once, or a member line that is not a bare recipe name is refused by name, and nothing is run, deferred or receipted. This replaces "Known slow and unclassified gates MUST be recorded as deferred".

### Motivation

Measured on 2026-11-13 while adopting expedited incident mode in livespec. livespec's check-targets.txt (master a91c015d, livespec#3196) mirrors its justfile `check:` array, which lists `e2e-test-claude-code-mock  # incident-timing: slow`. The hook read only `check-` members, so that member was neither run nor listed as deferred in the receipt, a silent omission. Separately, a member with no timing annotation read as unclassified and was deferred without a word: an inventory whose members carried no annotations at all deferred every gate, the all-defer shape this plan forbids (rule P5), and the per-repository drift guards compare member names only, so they cannot catch it. livespec-overseer's committed inventory showed that shape before its annotation pass: 90 members, none annotated. The ratified text at contracts.md (Expedited incident execution, "Known slow and unclassified gates MUST be recorded as deferred") and scenarios.md ("a known slow or unclassified gate is reported as deferred") requires that deferral. Implementing item: livespec-dev-tooling-dixgta (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm); topic named by legacy-coordinator-agent. Reading every member whatever its prefix contradicts no ratified clause and ships ahead of this proposal; refusing an unclassified member waits for it.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Expedited incident execution", in the paragraph that begins "Expedited local commit and push MUST choose host-local fast applicable work", replace the sentence:

"Known slow and unclassified gates MUST be recorded as deferred rather than launched; a selected unknown gate reaching sixty seconds MUST stop its owned process group and record deferred-timeout."

with:

"The expedited local hooks MUST read every member of the repository's committed `check-targets.txt` inventory, whatever its name, and not only members whose name begins `check-`. A member whose `incident-timing` is declared `slow`, or declared `not-applicable` with its precondition, MUST be recorded as deferred with its reason rather than launched, and a selected gate reaching sixty seconds MUST stop its owned process group and record deferred-timeout. A member that carries no `incident-timing` declaration, a declaration other than exactly one of `fast`, `slow` or `not-applicable`, or two conflicting declarations, a member listed more than once, and a member line that is not a bare recipe name MUST each refuse the commit or push before any gate runs, naming that member and its fault (a duplicated member is named as listed more than once), and the hooks MUST NOT run, defer or receipt any gate for it."

In SPECIFICATION/scenarios.md, in "## Scenario: an expedited local gate skips slow work and preserves fast failures", replace the step:

"And a known slow or unclassified gate is reported as deferred with its reason instead of launching the normal full aggregate."

with:

"And a declared slow or not-applicable gate is reported as deferred with its reason instead of launching the normal full aggregate.
And an inventory member whose name does not begin `check-`, declared slow, is reported as deferred with its reason like any slow gate.
And an inventory member with no timing declaration, an unrecognised or conflicting declaration, or listed more than once refuses the commit by name, and no gate is run, deferred or receipted."

The ratifying revise owes the heading-coverage co-edit for this scenario if its heading text changes (it does not, as proposed) and records livespec-dev-tooling-dixgta as the implementing item.

---
topic: bug-test-aggregate-completeness-pins
author: claude-opus-5-5 (seat:dev-host-test-gate-load)
created_at: 2026-11-13T07:11:16Z
---

## Proposal: A test never pins the member count of a committed check inventory

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Tests never pin committed configuration values" forbids a test from asserting a committed capacity or configuration VALUE, but it does not name committed INVENTORIES. `tests/livespec_dev_tooling/checks/test_aggregate_completeness.py` asserts the literal member count of the check aggregate (`len(wired) == 88`), on top of a set-equality assertion between the `justfile` `check` recipe and `check-targets.txt`. As a result, every new check refuses the next push until someone bumps the number. This proposal extends the section to committed inventories: a test asserts that an inventory's declarations agree, and that required members are present, but never their literal count. Work item livespec-dev-tooling-fmprfr carries the implementation.

### Motivation

Every check added to livespec-dev-tooling has had to edit the literal and append a provenance paragraph to the test's comment. The comment records the count moving 74 to 88 across at least 14 items. bootstrap-credentials-and-onboarding's sr46h2 hand-land had to bump it to 89 on 2026-11-13 after the push gate refused it. legacy-coordinator-agent classed this as coordinator-duties §12's defect class (a test tied to a committed value) and asked for it to be filed. The section's rationale already covers it: changing the committed inventory to another valid one (adding a wired check) breaks a test that asserts nothing about behaviour. The comment defends the literal against 'a silent drop'. But the existing canonical-slug assertion already catches a dropped canonical check, and dropping a repo-private check from both declarations is a deliberate two-file edit. Fleet scope, measured 2026-11-13: only livespec-dev-tooling pins such a count. This aligns with the in-flight proposal the-incident-hook-s-inventory (livespec-dev-tooling#4458), which reads every member of check-targets.txt whatever its name; nothing here constrains how a member is named. The dispatcher's spec-change tier holds fmprfr on this topic (verdict unstated, generalization target ## Tests never pin committed configuration values).

### Proposed Changes

### SPECIFICATION/contracts.md §"Tests never pin committed configuration values"

Add this bullet after the existing third bullet ("Changing any such committed value to another value its schema accepts MUST leave every test of the repository passing."):

"- The same holds for a committed INVENTORY: the check aggregate's target list in the `justfile` `check` recipe and in `check-targets.txt`, or any other list a repository commits in more than one place. A test of such an inventory MUST NOT assert its literal member count. It MUST derive the expected members from the committed declarations and assert that the declarations agree, naming each member present in one declaration and absent from another. The derivation covers every member of the inventory whatever its name, not only members whose name begins `check-`. It reads the same member set that §"Expedited incident execution" has the expedited local hooks read, and this bullet places no requirement on a member's name or on its `incident-timing` declaration. It MAY also assert that members a ratified rule requires, such as the canonical check slugs, are present. Adding a member to every declaration of the inventory, with no test edit, MUST leave every test of the repository passing. This bullet is spec-first for livespec-dev-tooling's own `test_aggregate_completeness.py`, which pins the count, and work item livespec-dev-tooling-fmprfr owns the change."

### SPECIFICATION/scenarios.md

Add this scenario directly after "## Scenario: changing a committed capacity value to another valid value leaves every test passing":

## Scenario: wiring one more check into both inventory declarations leaves every test passing

Given a repository whose check aggregate is declared in the `justfile` `check` recipe and in `check-targets.txt`

When a change adds one new `check-*` member to both declarations and edits no test file

Then every test of the repository MUST pass

And when a change adds a member to only one of the two declarations, the inventory test MUST fail naming that member and the declaration it is missing from

And when a change removes a canonical check slug from both declarations, the inventory test MUST fail naming that slug

The revise that accepts this owes a heading-coverage TODO row for the scenario: integration tier, `"work_item": "livespec-dev-tooling-fmprfr"`, plus the regenerated debt register.

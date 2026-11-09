---
topic: the-check-aggregate-s-per
author: claude:expedited-incident-response-flag
created_at: 2026-11-09T15:27:59Z
---

## Proposal: The wall-time table chooses each unit from the value as displayed

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Ratify the "## Check aggregate wall-time table" clause that landed unrevised in incident livespec-dev-tooling-e62ss6's expedited merge 2af42854, and add the rule that the unit is chosen from the value as displayed, so a wall time that rounds up into the next unit is shown in that unit. Add one scenario stating that behaviour.

### Motivation

The clause reached master through an expedited incident merge whose spec revise was deferred to the incident's normal repayment on the same item. The repayment's Definition of Done carries two behaviours: B1, the three display units, which the clause states; and B2, a wall time that rounds up into the next unit shows in that unit, never as `60.0s` or `59m 60s`, which the clause does not state. The dispatcher's spec-stated judgement therefore held the repayment as spec-change tier for this topic. Stating B2 and ratifying the clause pays the deferred spec debt and lets the repayment run through the factory against a spec that states everything it is graded on.

### Proposed Changes

1. In SPECIFICATION/non-functional-requirements.md, replace the body of "## Check aggregate wall-time table" with:

The check aggregate's per-target wall-time table MUST show each wall time in the unit a reader compares it in: seconds with one decimal below a minute, minutes and two-digit seconds from a minute, and hours, two-digit minutes and two-digit seconds from an hour. The unit MUST be chosen from the value as it will be displayed, after rounding, so a wall time that rounds up into the next unit is shown in that unit and never as `60.0s` or `59m 60s`: 59.96 s shows as `1m 00s`, and 3599.6 s shows as `1h 00m 00s`. The `::: just <target> [status, wall: Ns]` lines and the structured `wall_s` field keep raw seconds, because tools read them.

2. In SPECIFICATION/scenarios.md, append:

## Scenario: a wall time that rounds up into the next unit is shown in that unit

Given the check aggregate has finished targets whose wall times are 59.96 s and 3599.6 s
When it writes the per-target wall-time table
Then the 59.96 s target shows as `1m 00s`, not `60.0s`
And the 3599.6 s target shows as `1h 00m 00s`, not `59m 60s`
And the `::: just <target>` lines and the structured `wall_s` field still carry raw seconds.

3. In tests/heading-coverage.json, add an entry for the new scenario heading with test "TODO", work_item livespec-dev-tooling-e62ss6, and a reason naming the unit tier: the repayment of incident livespec-dev-tooling-e62ss6 owes a unit-tier test that renders both values through _write_timing_table. Regenerate tests/heading-coverage-debt.json.

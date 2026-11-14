---
topic: the-incident-ci-step-prints-its-enablement-reading
author: claude-opus-5-5 (expedited-incident-response-flag)
created_at: 2026-11-14T19:45:00Z
---

## Proposal: Every incident-ci job prints the released plan's enablement reading, and only that field, to its step log

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Expedited incident execution" to state what this repository and its three adopters already run. The `incident-ci` job that runs the released incident CI entrance prints the enablement reading the released plan recorded, and only that field, to its step log on every run that produces a plan. The line is fixed text, so the CI-plan vantage's reading can be read back from a run without exposing the rest of the plan. Add the matching steps to the enablement scenario.

### Motivation

Work items livespec-dev-tooling-kg5qv4 (livespec), livespec-dev-tooling-3z6fyq (livespec-orchestrator-beads-fabro) and livespec-dev-tooling-gyxmjj (livespec-overseer), the fleet-scope follow-ups (rule K) to livespec-dev-tooling-ahl6vz. All three are implemented and merged: livespec#3227 (14:06:46Z), livespec-orchestrator-beads-fabro#5282 (14:38:53Z) and livespec-overseer#3049 (14:55:39Z), on 2026-11-14. Each adds `echo "incident-ci: the released plan recorded enablement ${enablement}"` to its `ci.yml` and a `tests/test_incident_ci_plan_enablement_echo.py`. ahl6vz's own echo in this repository merged as 0ac294fe9. The pre-dispatch screen holds all three at spec-change tier, verdict unstated (spec v221). The section says the incident CI entrance takes its enablement reading from the controller's query route at plan time and records it in the CI plan, but nothing says that the reading reaches a log a reader can see, or that nothing else from the plan does. Before the echo, the reading existed only inside the plan JSON held in a shell variable. Measured on livespec-57r6qo's incident run 43577207225, there was no line to read it back from.

### Proposed Changes

In `SPECIFICATION/contracts.md`, §"Expedited incident execution", at the end of the paragraph that begins "While an installation is disarmed, every vantage MUST still read the record", append:

"Every `incident-ci` job that runs the released incident CI entrance, in this repository and in every adopter, MUST print the enablement reading the released plan recorded to its step log on every run that produces a plan, as the one line `incident-ci: the released plan recorded enablement <json>`, where `<json>` is that field's value exactly as the plan carries it. The step MUST NOT print any other part of the plan, including its environment map, so a value the plan carries for its members never reaches the log. Each such repository MUST carry a test that runs the step's own enablement lines against a plan whose environment map holds a marker value and asserts that the enablement line reaches the output and the marker does not."

In `SPECIFICATION/scenarios.md`, §"Scenario: the incident enablement step records enablement on the independent controller and every vantage reads it", after the step "And the incident CI entrance MUST record `enabled` in its plan from the controller's answer, and the controller MUST record `enabled` in its arm receipt", insert:

```gherkin
And the incident-ci job MUST print `incident-ci: the released plan recorded enablement` followed by that reading's JSON to its step log, and no other field of the plan, so the reading can be read back from the run.
```

The heading set does not change, so no `tests/heading-coverage.json` row is added or removed.

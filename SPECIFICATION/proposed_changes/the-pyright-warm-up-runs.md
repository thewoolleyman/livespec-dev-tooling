---
topic: the-pyright-warm-up-runs
author: claude-opus-5-5 (expedited-incident-response-flag)
created_at: 2026-11-14T19:45:00Z
---

## Proposal: Every child process the released incident CI entrance starts runs in the repository with the incident credentials stripped

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Expedited incident execution" so that every child process the released incident CI entrance starts gets the same working directory and environment as the members it runs: the repository root, and an environment holding no `LIVESPEC_INCIDENT_*` variable. That covers the locked pyright warm-up as well as the members. The entrance keeps its own incident credentials for its own controller reads. Add the matching step to the expedited-PR recording scenario.

### Motivation

Work item livespec-dev-tooling-h73ok4, carrying the two hardening fixes from legacy-coordinator-agent's grade of livespec-dev-tooling#4533 (ruling B: land #4533 as graded, carry the fixes here). `CiEntry.execute` (`livespec_dev_tooling/incident_ci_entry.py`) strips every `LIVESPEC_INCIDENT_*` variable from the environment its members get, which keeps the observer URL and query token away from candidate-tree code. It calls `warm_locked_pyright` (`livespec_dev_tooling/_pyright_warmup.py`) first, and that subprocess inherits the entrance's own environment, credentials included, and the caller's working directory. So the one child process that runs before any member is the one that is not stripped. The ratified section covers the entrance, its query credential and its forge-call retries, but says nothing about the environment or working directory of the processes it starts, so the pre-dispatch screen holds the item at spec-change tier, verdict unstated (spec v221).

### Proposed Changes

In `SPECIFICATION/contracts.md`, §"Expedited incident execution", at the end of the paragraph that begins "Every forge call that the `incident-ci` job, the `ci-green` job and the incident label workflow", append:

"Every child process the entrance starts, each member it runs and any preparation step it runs before them (the locked pyright warm-up among them), MUST run with the repository root as its working directory and an environment that carries no variable whose name begins `LIVESPEC_INCIDENT_`. The entrance's own environment keeps those variables for its own reads of the controller. The local parallel check dispatcher, which runs outside incident mode, MUST pass its working directory and environment to the warm-up explicitly and is otherwise unchanged."

In `SPECIFICATION/scenarios.md`, §"Scenario: an expedited pull-request run and its omitted members are recorded on the incident work item", after its last step, "And a run of the incident CI job on a head the controller has not armed, including one whose aggregate refused for want of a current arm, MUST receive no record.", append:

```gherkin
And the entrance's pyright warm-up and every member it ran MUST have received the repository root as their working directory and an environment with no LIVESPEC_INCIDENT_ variable, while the entrance's own environment carried the observer query credential.
```

The heading set does not change, so no `tests/heading-coverage.json` row is added or removed.

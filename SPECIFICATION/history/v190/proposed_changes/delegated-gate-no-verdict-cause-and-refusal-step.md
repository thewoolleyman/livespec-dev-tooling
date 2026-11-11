---
topic: delegated-gate-no-verdict-cause-and-refusal-step
author: claude-opus-5-5
created_at: 2026-11-11T04:47:23Z
---

## Proposal: A no-verdict outcome event names whether the gate client interrupted itself or the delegation failed, and the no-verdict trigger fires only on a delegation fault

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Keep the three outcome words. Add one required attribute to every `no-verdict` event: a no-verdict cause whose value is `client-interrupted` when the gate client itself stopped the run, and `delegation` otherwise. The client stops the run itself when it received SIGTERM, SIGINT or SIGHUP while running, or when the working tree the push ran from stopped existing before a verdict was read. Narrow the required fleet trigger to `no-verdict` events whose cause is not `client-interrupted`, so an interrupted push stays visible in the data without paging as a broken delegation. Add a scenario for the client-interrupted case.

### Motivation

The fleet's no-verdict trigger (livespec trigger xMggkF8364A) cannot reach a quiet 72 hours, because the event counts pushes that the pushing client cut short as broken delegations. Over 7 days ending 2026-11-11T02:09Z, Honeycomb livespec/livespec-delegated-gate recorded 999 passed, 50 failed-tree and 12 no-verdict outcomes (queries dTZZSKEa59G, zLoHpXy5qNT). The trigger sent Triggered email on 2026-11-09T18:53Z and 2026-11-11T00:33Z. Two of the attributable no-verdicts were caused by the client itself, not by the delegation. Orchestrator gate run 20261107T170438Z-2028504 failed because the pushing session's worktree was removed while the gate was waiting ('await-gate-terminal did not complete … No such file or directory: /home/ubuntu/.worktrees/livespec-orchestrator-beads-fabro/triage/72hvx5-seed'). livespec-dev-tooling gate run 20261111T002432Z-2338868 'was terminated by SIGTERM; the client deleted that Job and its published mirror refs before exiting'. Six more orchestrator no-verdicts (2026-11-09 to 2026-11-11) came from plain pre-push hook runs whose refusal text was never kept, so their cause cannot be recovered. The orchestrator plan address-honeycomb-alerts (epic bd-ib-xkwdap, research note 008) found that its 'real condition; keep' disposition for this trigger cannot satisfy that plan's quiet-window assertion. legacy-coordinator-agent routed this proposal to livespec-dev-tooling, spec first, because the outcome vocabulary is ratified. The SIGTERM-journaling family is tracked separately on bd-ib-shm3zk.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", in the **Telemetry.** bullet:

1. After the sentence ending "…therefore emits `passed`.", insert:

   "Every `no-verdict` event MUST carry a no-verdict cause as its own attribute, with exactly one of two values. The value MUST be `client-interrupted` when the gate client itself stopped the run before reading a verdict: it received SIGTERM, SIGINT or SIGHUP while the run was in progress, or the working tree the push ran from stopped existing before the run read a verdict. In every other case the value MUST be `delegation`, including a run that could not assemble its request, could not reach or authenticate to the cluster, could not submit its Job, or lost its Job to anything other than its own cleanup on interruption. A `passed` or `failed-tree` event MUST NOT carry a no-verdict cause. The cause MUST NOT change the outcome word: a client-interrupted run obtained no verdict and still emits `no-verdict`."

2. Replace "The fleet MUST carry a trigger that fires on a `no-verdict` outcome event, so that a broken delegation is alertable apart from a failing tree." with:

   "The fleet MUST carry a trigger that fires on a `no-verdict` outcome event whose no-verdict cause is not `client-interrupted`, so that a broken delegation is alertable apart from both a failing tree and a push its own client cut short. An event that carries no cause MUST be counted by that trigger."

In SPECIFICATION/scenarios.md, after §"Scenario: a delegated gate run that reaches no verdict emits a no-verdict outcome event", add:

```gherkin
## Scenario: a delegated gate run its own client interrupts emits a client-interrupted no-verdict outcome event

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

And a git push of a tree that has no green token whose pre-push gate has submitted its gate Job

When the gate client receives SIGTERM while it waits for that Job's verdict

Then the push MUST be refused

And the gate client MUST emit exactly one outcome event whose outcome is `no-verdict`

And that event's no-verdict cause MUST be `client-interrupted`

And that event MUST carry the repository's name, the gated tree's hash, and the submitted gate Job's name

And the fleet's no-verdict trigger MUST NOT count that event
```

In the existing §"Scenario: a delegated gate run that reaches no verdict emits a no-verdict outcome event", add after its last Then-line: "And that event's no-verdict cause MUST be `delegation`".

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the same change (`test` MAY be `"TODO"` with a non-empty `reason`).

## Proposal: A no-verdict outcome event carries the gate Job's name whenever a Job was submitted, and names the step that did not complete

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State explicitly that the gate Job's name counts as determined from the moment the API server assigns it, so a run interrupted or lost after submission still carries it. Add a required refusal-step attribute on every `no-verdict` event, naming the client step that did not complete. Correct the existing no-verdict scenario, whose last line requires a Job name in a run that never submitted a Job, contradicting the never-guessed rule.

### Motivation

None of the 12 no-verdict spans recorded over the 7 days ending 2026-11-11T02:09Z carries livespec.gate.job_name (Honeycomb query zLoHpXy5qNT). That includes gate run 20261111T002432Z-2338868, whose own log names its submitted Job gate-livespec-dev-tooling-d4n26. The Telemetry bullet already says a value the run had not determined MUST be absent, and the implementation reads that as 'absent on every no-verdict path', so an operator loses exactly the identifier the trigger's runbook asks them to check. The spans also carry no record of which step failed, so the six pre-push no-verdicts with no kept log cannot be diagnosed from telemetry at all. Meanwhile the existing scenario's Then-line 'that event MUST carry … the gate Job's name' describes a run whose API server was unreachable, which never obtained a Job name; its covering test already records that contradiction in its heading-coverage reason. legacy-coordinator-agent routed this alongside the client-interrupted cause for plan address-honeycomb-alerts (epic bd-ib-xkwdap).

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", in the **Telemetry.** bullet, after the sentence "A value the run had not determined when it stopped MUST be absent from the event, never guessed.", insert:

"The gate Job's name is determined from the moment the cluster's API server assigns it on submission. A run that submitted its Job MUST therefore carry that name on its event, whatever happened afterwards, including a run that was interrupted, timed out or lost the Job while waiting. Every `no-verdict` event MUST also carry, as its own attribute, the refusal step: the name of the gate client step that did not complete. Its values are `assemble` (building the gate request, before any cluster call), `submit` (creating the gate Job) and `await-verdict` (waiting for and reading the submitted Job's verdict). A `passed` or `failed-tree` event MUST NOT carry a refusal step."

In SPECIFICATION/scenarios.md §"Scenario: a delegated gate run that reaches no verdict emits a no-verdict outcome event", replace "And that event MUST carry the repository's name, the gated tree's hash, and the gate Job's name" with:

"And that event MUST carry the repository's name and the gated tree's hash

And that event MUST NOT carry a gate Job's name, because no Job was submitted

And that event's refusal step MUST be `submit`"

In the client-interrupted scenario proposed alongside this one, its Then-lines MUST also include "And that event's refusal step MUST be `await-verdict`".

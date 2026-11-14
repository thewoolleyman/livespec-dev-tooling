---
topic: an-expedited-pull-request-s
author: claude-opus-5-5 (expedited-incident-response-flag)
created_at: 2026-11-14T19:45:00Z
---

## Proposal: Expedited incident-ci authority binds to the attempt's genesis base, held as an ancestor of the current base within a freshness bound

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Expedited incident execution" to name the base that incident-ci authority binds to. It is the attempt's genesis base (the base recorded when the attempt was armed), not the current tip of the default branch. The admission holds while that genesis base is an ancestor of the pull request's current base tip and no more than the freshness bound behind it. It refuses, by name, when the genesis base is not an ancestor or the bound is exceeded. A busy default branch then no longer makes the incident path unavailable, and the full master run with its immediate-revert rule still judges the combined tree. Add the matching scenario steps.

Design call (A), base-commit authority (coordinator-duties §9), RULED by legacy-coordinator-agent (58d68f5e) under R301 on 2026-11-14 ~19:4xZ: option (ii) with a bound of 50 commits and 240 minutes, held as committed configuration values rather than literals a test pins (coordinator-duties §12), so they can be tuned without a test suite.

### Motivation

Work item livespec-dev-tooling-3u5rzz, filed on legacy-coordinator-agent's ruling (2026-11-13 ~03:5xZ). Measured 2026-11-13: an armed expedited pull request's incident-ci was refused because the default branch had moved between the attempt's genesis and the armed run. The earlier incident vxs7ru passed only because master did not move in that window. So the path is unavailable exactly when master is busy, which is when an incident is most likely. The interim mitigation, a corrected attempt on current master plus a merge-quiet window, holds every other merge. The ratified section binds incident item, attempt, phase, repository and base/head identity, but does not say which base the incident-ci authority binds to or how much drift it accepts. So the pre-dispatch screen holds the item at spec-change tier, verdict unstated (spec v221).

The options on record: (i) the base tip, as today: safe and simple, but unavailable on a busy master unless merges are held. (ii) the genesis base with an ancestor check and a freshness bound. (iii) the merge base of head and base, which equals (ii) for an attempt that was not rebased but can be changed by force-moving the head. Option (ii) keeps authority bound to the base the attempt was reviewed and admitted against. The ancestor check refuses any rewritten or divergent history, and the bound limits how much unreviewed drift the candidate is combined with.

### Proposed Changes

In `SPECIFICATION/contracts.md`, §"Expedited incident execution", at the end of the paragraph that begins "A trusted PR-specific label plus structured receipt MUST project mode only into the exact repair PR/head before initial CI", append:

"Incident-ci authority for an armed expedited pull request MUST bind to the attempt's genesis base, the base commit recorded for the attempt when it was armed, and not to the tip of the default branch when the run starts. The admission MUST succeed, with no corrected attempt and no hold on other merges, while the genesis base is an ancestor of the pull request's current base tip, read through the isolated object view this section requires for scope reads, and that tip is no more than the freshness bound ahead of it. The freshness bound is two committed configuration values of the controller installation, the observer role variables `incident_observer_expedited_base_max_commits` and `incident_observer_expedited_base_max_minutes` in `ansible/roles/incident_observer/defaults/main.yml`, rendered into the controller's configuration, with initial values 50 commits and 240 minutes. A change to either value MUST be a committed configuration change alone, and a test MUST NOT pin either committed value. The admission MUST refuse when the genesis base is not such an ancestor, or when either bound is exceeded. The refusal MUST name the genesis base it holds, the base the event names and each bound exceeded. A head change still invalidates earlier verdicts as this paragraph states. The merged result still runs the complete normal master CI with its immediate-revert rule."

In `SPECIFICATION/scenarios.md`, §"Scenario: an expedited PR defers coverage and spec work while master runs normally", after its last step, "And a caller that wires incident-omitted from anything other than its incident-ci job's guarded output is refused by the repository conformance check on callers.", append:

```gherkin
And when the default branch advances by commits that keep the attempt's genesis base an ancestor of the new base tip within the freshness bound, the armed pull request's incident-ci admission MUST succeed with no corrected attempt and no merge hold.
And when the genesis base is not an ancestor of the pull request's current base, or the bound is exceeded, incident-ci MUST refuse naming the genesis base, the event's base and the bound exceeded.
```

The heading set does not change, so no `tests/heading-coverage.json` row is added or removed.

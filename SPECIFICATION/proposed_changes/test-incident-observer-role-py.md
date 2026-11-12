---
topic: test-incident-observer-role-py
author: claude-opus-5-5
created_at: 2026-11-12T19:00:00Z
---

## Proposal: The committed observer role clears a tripped start limit before it restarts an observer, accepts only a not-loaded answer, and resets nothing in check mode

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds one sentence to contracts.md, section "Expedited incident execution", at the end of the paragraph that begins "A drill or proof installation whose configuration names a scratch target branch". That paragraph already names "the same committed observer role that converges production". The sentence states the role's restart behaviour, which the committed role already has (`ansible/roles/incident_observer/handlers/main.yml`):
- before it restarts an observer unit onto its installation, it clears the unit's failed and start-limit state;
- a reset answering that the unit is not loaded is accepted, and any other reset failure stops the converge;
- a check-mode run resets no real unit.

Adds one scenario to scenarios.md, after "a scratch-branch incident drill runs beside production on the full master CI graph".

### Motivation

Work item livespec-dev-tooling-xazlro (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub) was classified spec-change at dispatch at 2026-11-12T18:48:02Z (verdict partial, linked topic `test-incident-observer-role-py`). The item replaces text pins in `tests/livespec_dev_tooling/test_incident_observer_role.py` with a behavioural role-tier test. The pins are the handler's register name, the absence of a `check_mode` key, and the literal `failed_when` list. legacy-coordinator-agent ruled the replacement while grading livespec-dev-tooling#4095 (fdquen). The judgement's rationale: §"Tests never pin committed configuration values" (contracts.md:676) plausibly covers removing the pins, but nothing ratified states the handler's behaviour the new test must prove.

That behaviour is load-bearing for recovery. Once an observer unit's `StartLimitBurst` has tripped in a crash loop, systemd refuses a plain restart ("Start request repeated too quickly") until `StartLimitIntervalSec` passes. Without the reset, a converge that ships the fix within that window fails at the restart. On a first apply the unit was never loaded. `systemctl reset-failed` then exits non-zero with "not loaded" on stderr (measured), and that one answer must not stop the converge. The role states all of this in comments and code; this proposal ratifies it so a behavioural test has a clause to prove.

It adds no behaviour the committed role does not already have.

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "Expedited incident execution", append the following sentence to the end of the paragraph that begins "A drill or proof installation whose configuration names a scratch target branch MUST run side by side with the production installation", immediately after its last sentence, which ends "and the fleet audit MUST NOT read it as the running independent controller." No heading is added, removed or renamed in that file.

When that committed observer role restarts an observer unit, production's or a scratch installation's, onto its installation, it MUST first clear the unit's failed and start-limit state, so that a converge shipping a fix while the unit's start limit is tripped is not refused by systemd; a reset that answers that the unit is not loaded, as on a first install, MUST be accepted, any other failed reset MUST stop the converge before the restart, and a check-mode run MUST NOT reset a real unit.

In `SPECIFICATION/scenarios.md`, insert the following scenario immediately after the scenario "a scratch-branch incident drill runs beside production on the full master CI graph" and before the scenario "a recorded scratch-branch drill ends in drill-closed and a master incident is refused".

## Scenario: the committed observer role clears a tripped start limit before it restarts an observer

```gherkin
Given an observer unit whose systemd start limit has tripped after a crash loop
When the committed observer role converges a changed installation and restarts that unit
Then the role MUST clear the unit's failed and start-limit state before the restart, and the restart MUST succeed.
And when the reset answers non-zero with "not loaded" on stderr, as on a first install, the role MUST continue to the restart.
And when the reset answers non-zero without "not loaded", the role MUST stop the converge before the restart.
And a check-mode run of the role MUST NOT reset a real unit.
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the same commit. A spec-first `"test": "TODO"` row is acceptable when its reason names the integration tier and it carries `"work_item": "livespec-dev-tooling-xazlro"`, with the heading-coverage debt register regenerated.

---
topic: no-verb-closes-a-drill
author: claude-opus-5-5
created_at: 2026-11-11T02:02:45Z
---

## Proposal: A recorded scratch-branch drill ends through the orchestrator's drill-closed phase, and a master incident is refused

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a paragraph to contracts.md §"Expedited incident execution" and a new scenario that give a drill incident chain a way to end. It settles both spec decisions work item livespec-dev-tooling-io6hyk raised. (1) Ending a drill is the implementation orchestrator's: its owning spec governs a distinct terminal phase `drill-closed`, the verb that writes it, and that verb's fencing. No surface this repository owns writes it, and a label or mark confers nothing. (2) A drill ends in that distinct phase, never in `closed`, so a drill closure is never read as a completed incident, a completed repayment or recovery capability for `master`. This repository supplies the half of the contract it owns, the scratch-branch boundary: an item is a recorded drill only when its authority history binds at least one pull request, every carrier is bound, every bound pull request's base branch matches `incident-scratch/**`, and no landed commit is reachable from `master`. Anything else is refused by name and left unchanged.

### Motivation

Plan expedited-incident-hardening (epic livespec-dev-tooling-dh3hub), follow-up (a), work item livespec-dev-tooling-io6hyk, from the coordinator's ruling R301: 'No verb closes a drill incident chain; a drill item rests at reverting/repayment-owed forever.' Measured 2026-11-11: the four drill items livespec-dev-tooling-feh3s4, -lli7hc, -sdxw2v and -wxeybc are all at incident phase `reverting`, generation 4, with repayment owed. Their only incident labels are `incident:drill` and `incident:entry`, and their entry records carry no drill field. Their carrier pull requests livespec-dev-tooling#4052, #4054, #4058 and #4062 all MERGED into base `incident-scratch/thhgeg-proof`, so the forge already distinguishes them from a master incident without trusting a label. The orchestrator's ratified §"Expedited incident lifecycle" defines the phase table (repair through closed), says only the incident transition may establish these phases, and refuses any close or completion path that skips the normal repayment, so as ratified a drill can never end. Its `incident_authority.py` (verbs commit-transition, complete-incident, read-current and others) is the only writer of those phases. This repository's §"Expedited incident execution" says the orchestrator's owning spec governs the orchestrator lifecycle, while this repository owns the principal, the observer and the scratch-branch drill installation. Per split (iii) the realization (the phase row, the verb, its fencing, inspection and fleet-wide availability) belongs in the orchestrator's SPECIFICATION/ and needs a companion proposal and work item there. Until that companion is ratified, the orchestrator's 'Unknown phase/state combinations MUST produce a named configuration refusal' and its closure rule still forbid the phase, so this paragraph defers to it rather than restating it. This proposal records the decision and this repository's half of the boundary. Independent pre-filing review (2026-11-11) checked the discriminator against live authority records. Orchestrator recovery requests name no target branch: the drills' requests say `"surface":"trunk"`, and revert receipts hold only a receipt id and commit. A carrier's orchestrator `target_ref` is its HEAD branch, not its base. A real incident still in `repair` binds no pull request. So the test reads bound pull requests' BASE branches and master reachability, and it requires at least one bound pull request. Under that test all four live drills qualify: every carrier is pr-bound with base `incident-scratch/thhgeg-proof`, and landed commit 96f7bda is not reachable from `origin/master`.

### Proposed Changes

In `contracts.md` §"Expedited incident execution", insert the following paragraph directly after the paragraph that begins "A drill or proof installation whose configuration names a scratch target branch":

> Ending a drill incident chain belongs to the implementation orchestrator. Its owning spec governs the terminal incident phase `drill-closed`, the drill-close verb that writes it, and that verb's fencing, and this repository's contract with that verb is the scratch-branch boundary below. An incident item is a recorded drill only when an authenticated forge read, taken when the close is requested, shows that its incident authority history binds at least one carrier pull request, that every carrier in that history is bound to a pull request, that every bound pull request's base branch matches `incident-scratch/**`, and that no landed commit in that history is reachable from `master`. A label such as `incident:drill`, a title, a description or a caller's assertion alone MUST NOT make an item a recorded drill. Applied to an item that is not a recorded drill, the drill-close verb MUST refuse with the named reason `incident-not-a-recorded-drill`, naming the first carrier or landed commit that failed the test, and MUST leave the item's incident phase, generation, claim and authority history unchanged. When the forge read fails or is incomplete, the verb MUST refuse with the named reason `incident-drill-evidence-unavailable` rather than classify the item. A drill MUST end in `drill-closed` and never in `closed`. A `drill-closed` item MUST NOT satisfy incident completion and MUST NOT count as a completed repayment, as recovery capability for `master`, or as the durable observer receipt an incident merge into `master` requires, and the incident fleet audit MUST NOT read it as recovery capability for `master`. A regression attributed to a `drill-closed` item's scratch branch is drill evidence only and MUST NOT reopen the item. No surface this repository owns, including the recovery principal and the incident observer, MAY write the `drill-closed` phase.

In `scenarios.md`, add the following scenario directly after `## Scenario: a scratch-branch incident drill runs beside production on the full master CI graph`:

~~~markdown
## Scenario: a recorded scratch-branch drill ends in drill-closed and a master incident is refused

```gherkin
Given an incident item whose incident authority binds only pull-request-bound carriers, every one of whose pull requests merged into an incident-scratch/** base branch, with no landed commit reachable from master
And a second incident item whose bound carrier pull request's base branch is master
When an operator applies the implementation orchestrator's drill-close verb to each item
Then the first item reads the terminal phase drill-closed, with no repayment owed, and its incident authority history remains readable
And the first item's closure is not counted as a completed incident or as recovery capability for master
And the verb refuses the second item with incident-not-a-recorded-drill
And the second item's incident phase, generation, claim and authority history are unchanged
```
~~~

The revise commit MUST add a `tests/heading-coverage.json` row for the new heading, a spec-first `"test": "TODO"` whose reason names the integration tier or above and whose `work_item` is `livespec-dev-tooling-io6hyk`, and MUST regenerate `tests/heading-coverage-debt.json`. Work item livespec-dev-tooling-io6hyk's Definition of Done `References:` line MUST then name the new heading, and the orchestrator's companion work item carries the phase row and the verb.

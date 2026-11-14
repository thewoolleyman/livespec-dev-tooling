---
topic: the-incident-ci-inventory-renderer
author: claude-opus-5-5 (expedited-incident-response-flag)
created_at: 2026-11-14T19:45:00Z
---

## Proposal: The released incident CI inventory keys each member by job and check, and the entrance runs each check once per run

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Expedited incident execution" to state the released incident CI inventory's member identity: a member is a (job, check slug) pair. A workflow that declares one check in two jobs then renders, with one member per job, instead of being refused. The entrance runs each check slug at most once per run and attributes its outcome to every job that declares it. A member whose job carries an `if:` condition is listed as a conditional job that did not run on this event, never dropped, and the entrance parses no workflow expression to decide that. Add the matching scenario steps.

### Motivation

Work item livespec-dev-tooling-yzr6ad, found while preparing livespec's inventory entry after livespec#3196 merged. The release carries one incident CI inventory per adopting repository, rendered at build time by `render_inventory` (`livespec_dev_tooling/incident_ci_inventory.py`) from that repository's workflow and `check-targets.txt` at a recorded default-branch commit. The renderer keys members by check slug alone. livespec's `release-gate-pre-tag` job at a91c015d declares checks that another job also declares, so the render refuses, and no inventory can be released for livespec. The ratified section covers focused verification, expedited-run records, enablement reads, forge-call retries and observer installations. It says nothing about the inventory's member keying, per-run deduplication or conditional jobs. So the pre-dispatch screen holds the item at spec-change tier, verdict unstated (spec v221). The hook reader's handling of members without the `check-` prefix is a separate topic (the-incident-hook-s-inventory, livespec-dev-tooling-dixgta).

### Proposed Changes

In `SPECIFICATION/contracts.md`, §"Expedited incident execution", immediately before the paragraph that begins "An expedited pull-request CI run is a run of the incident CI job" (whose "following three paragraphs" must stay adjacent to it), insert a new paragraph:

"The release MUST carry one incident CI inventory for each adopting repository, rendered at build time from that repository's normal workflow and `check-targets.txt` at a recorded commit of its default branch, and the entrance MUST look an inventory up by the repository its authenticated pull-request read names. An inventory member MUST be keyed by its job and its check slug together, so a workflow that declares one check in two jobs renders and decodes with one member for each job. The entrance MUST execute each check slug at most once per run, however many jobs declare it, and its receipt MUST attribute that slug's outcome to every job that declares it. A member whose job carries an `if:` condition MUST appear in the receipt under a conditional-job line naming that job as not run on this event, and MUST NOT be dropped. The entrance MUST NOT parse a workflow expression to decide it. A change to the keying MUST leave this repository's own inventory byte-identical, or record and explain every difference."

In `SPECIFICATION/scenarios.md`, §"Scenario: an expedited PR defers coverage and spec work while master runs normally", after its last step, "And a caller that wires incident-omitted from anything other than its incident-ci job's guarded output is refused by the repository conformance check on callers.", append:

```gherkin
And an adopter workflow that declares one check in two jobs MUST render and decode an inventory with one member per declaring job, and the entrance MUST run that check once and attribute its outcome to both jobs in its receipt.
And a member whose job carries an if: condition MUST be listed in the receipt as a conditional job not run on this event, never dropped.
```

The heading set does not change, so no `tests/heading-coverage.json` row is added or removed.

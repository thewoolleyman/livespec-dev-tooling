---
topic: a-released-adopter-incident-ci
author: claude-opus-5-5 (expedited-incident-response-flag)
created_at: 2026-11-14T19:45:00Z
---

## Proposal: A freshness read re-renders every released adopter incident CI inventory before each release and on a schedule

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Expedited incident execution" with a freshness read over the released incident CI inventories. It re-renders every committed adopter entry from that adopter's current default-branch head, through the same `render_inventory` and timing reader the entry was built with, and compares the result with the committed entry. Before a release, any difference refuses the release by name. On a schedule, the same difference is reported to needs-attention. The read covers every file under the inventory directory, so a later entry is covered with no change. Add a scenario step.

### Motivation

Work item livespec-dev-tooling-hhxmgv, filed at legacy-coordinator-agent's direction on 2026-11-13, when it approved the per-repository inventory layout of incident livespec-dev-tooling-z5cjph. An adopter's entry is fixed at a recorded commit of its default branch. When the adopter later adds, removes, renames or reclassifies an aggregate member, the released inventory silently stops matching what its CI runs, and nothing notices until the next expedited pull request in that repository mis-selects. That is the moment an incident needs the path to work. The ratified text never mentions the per-adopter inventories, and states no read that keeps them current. So the pre-dispatch screen holds the item at spec-change tier, verdict unstated (spec v221).

### Proposed Changes

In `SPECIFICATION/contracts.md`, §"Expedited incident execution", immediately before the paragraph that begins "An expedited pull-request CI run is a run of the incident CI job" (whose "following three paragraphs" must stay adjacent to it), and after any inventory paragraphs the-incident-ci-inventory-renderer and the-incident-ci-inventory-render insert there when they are accepted, insert a new paragraph:

"Before each release of this library, and on a schedule, a freshness read MUST re-render every committed adopter incident CI inventory entry under `livespec_dev_tooling/data/incident-ci-inventory/`. It renders each one from that adopter's workflow and `check-targets.txt` at the adopter's current default-branch head, through the same renderer and timing reader the entry was built with, and compares the result with the committed entry. When any entry differs, the pre-release read MUST refuse the release, naming the repository, the entry's recorded source commit, the current head and each added, removed or reclassified member. The scheduled read MUST report the same difference to needs-attention. When every entry matches, the read MUST report each repository with its recorded source commit and current head, and refuse nothing. The read MUST cover every file under that directory, so an entry added later needs no change to it."

In `SPECIFICATION/scenarios.md`, §"Scenario: an expedited PR defers coverage and spec work while master runs normally", after its last step, append:

```gherkin
And when an adopter's default branch adds a member its released incident CI inventory entry lacks, the pre-release freshness read MUST refuse the release naming the repository, the entry's source commit, the current head and the added member.
```

The heading set does not change, so no `tests/heading-coverage.json` row is added or removed.

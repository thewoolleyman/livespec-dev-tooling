---
topic: the-incident-ci-inventory-render
author: claude-opus-5-5 (expedited-incident-response-flag)
created_at: 2026-11-14T19:45:00Z
---

## Proposal: The incident CI inventory render never truncates a committed entry and refuses a clone of the wrong repository

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Expedited incident execution" for the operator script that renders an adopter's released incident CI inventory entry (`scripts/just/render-incident-ci-inventory.sh`). A failed render leaves the previously committed entry byte-identical: the script renders to a temporary file and moves it into place only after a successful render. A clone whose origin URL does not name the repository argument is refused, naming both, and nothing is written. Each named refusal is test-driven. Add the matching scenario step.

### Motivation

Work item livespec-dev-tooling-6xd3dz. The script writes `livespec_dev_tooling/data/incident-ci-inventory/<owner>/<repo>.json` from a local clone at a named commit, and records that commit as the entry's `source`. Two failure modes were measured while preparing livespec's entry. The script redirects the render straight onto the destination, so a render that fails part-way leaves a truncated file where a good committed entry was. And the script trusts the clone it is given, so a clone of the wrong repository records a wrong `source` silently. Its own header warns of this but does not check it. The released inventory is what the entrance reads, so a bad entry that ships fails or silently mis-selects every expedited pull request of that adopter. The ratified section says nothing about the render script, so the pre-dispatch screen holds the item at spec-change tier, verdict unstated (spec v221).

### Proposed Changes

In `SPECIFICATION/contracts.md`, §"Expedited incident execution", immediately before the paragraph that begins "An expedited pull-request CI run is a run of the incident CI job" (whose "following three paragraphs" must stay adjacent to it), and after the inventory paragraph that the-incident-ci-inventory-renderer inserts there when both are accepted, insert a new paragraph:

"An adopter's released incident CI inventory entry MUST be produced only by this repository's render script, `scripts/just/render-incident-ci-inventory.sh <owner/repo> <clone-path> <commit-sha>`. The script MUST render to a temporary file and move it onto the entry's path only after the render succeeds, so a failed render leaves a previously committed entry byte-identical. It MUST refuse and write nothing, naming the fault, when the clone's origin URL does not name the repository argument (naming both), when the commit is not on the clone's default branch, or when the clone lacks the workflow or `check-targets.txt` at that commit. This repository MUST carry a test that drives each refusal and asserts its named message and that no entry file was written or changed."

In `SPECIFICATION/scenarios.md`, §"Scenario: an expedited PR defers coverage and spec work while master runs normally", after its last step, append:

```gherkin
And a render of an adopter's incident CI inventory that fails, or that is given a clone whose origin does not name the repository argument, MUST refuse by name and leave the committed entry byte-identical.
```

The heading set does not change, so no `tests/heading-coverage.json` row is added or removed.

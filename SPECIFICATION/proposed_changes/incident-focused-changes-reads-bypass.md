---
topic: incident-focused-changes-reads-bypass
author: claude-opus-5-5:expedited-incident-hardening
created_at: 2026-11-13T07:00:51Z
---

## Proposal: Focused verification reads the changed set through the isolated object view, classifies a symlinked module as the collector does, and refuses a submodule by name

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds three sentences to contracts.md §"Expedited incident execution", in the focused-verification paragraph, immediately after "Generated, deleted and non-executable paths MUST receive explicit disposition.": (1) the changed set focused verification judges MUST be read through the same isolated object view the incident's other reference-clone readers use, so replace refs, grafts and clone configuration cannot alter it; (2) a changed path under a source prefix that is a symbolic link to a Python module MUST be classified exactly as the coverage collector classifies it; (3) a changed path under a source prefix that is a submodule gitlink MUST be refused with a reason that names the submodule path, never an unrelated internal error. Adds one named scenario exercising all three. No heading is added, removed or renamed except the new scenario.

### Motivation

Work item livespec-dev-tooling-rgiufy (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub) carries non-blocking findings from the two independent reviews of livespec-dev-tooling#4086 (livespec-dev-tooling-6ou5m2) on 2026-11-11. On 2026-11-12T18:48:16Z the dispatch-stage spec-change tier held it as partial against `## Expedited incident execution`, with linked topic incident-focused-changes-reads-bypass. Its rationale: the section requires explicit disposition of generated, deleted and non-executable paths in focused verification, and it configures the target branch and requires the principal to refuse a request naming a different branch, but it does not state the isolated git object view for changed-file reads, the submodule refusal reason, or the symlinked-module classification. legacy-coordinator-agent holds the item until this topic ratifies and named this seat its owner (2026-11-13).

The defects, all in `livespec_dev_tooling/incident_focused_changes.py`:
- The changed set is read with plain `run_git` (`ls-tree`, `cat-file --batch`, `show <ref>:pyproject.toml`, and the diff in `_changed`) against the observer's reference clone. The sibling readers use `IsolatedGit` (`_incident_inverse_git.py`), which ignores replace refs, grafts and clone configuration. A clone carrying any of those can therefore change the set of paths focused verification judges.
- A `.py` under a source prefix stored as a symbolic link (tree mode 120000) is classified differently from how the coverage collector classifies it, so an honest focused-evidence record is refused.
- A submodule gitlink (tree mode 160000) under a source prefix fails with `list index out of range` rather than a reason a reader can act on.

Every one fails in the refusal direction: an honest record is refused, or a reason is unhelpful. None admits an under-covered record. That is why the item was filed as hardening. But the ratified text states none of the three behaviours, so a fix has no clause to be judged against, and the tier is right to hold it.

rgiufy's fourth Definition of Done bullet (a test drives /arm with a non-default target_branch) needs no new clause. The paragraph that configures the target branch already requires the principal to publish only on its configured branch and to refuse a request naming any other. That bullet is a test-existence assertion, which the item's Definition of Done rewrite restates as the behaviour it establishes.

### Proposed Changes

### contracts.md

In `SPECIFICATION/contracts.md`, section `## Expedited incident execution`, in the paragraph that begins "Focused verification MUST run changed/directly related tests", insert the following immediately after the sentence "Generated, deleted and non-executable paths MUST receive explicit disposition.":

> The changed set that focused verification judges MUST be read through the same isolated object view the incident's other reference-clone readers use, so that replace refs, grafts and clone configuration cannot add, drop or alter a changed path. A changed path under a source prefix that is a symbolic link to a Python module MUST be classified exactly as the coverage collector classifies it. A changed path under a source prefix that is a submodule gitlink MUST be refused with a reason that names the submodule path, never with an unrelated internal error.

No other sentence of the paragraph changes, and no heading is added, removed or renamed in contracts.md.

### scenarios.md

In `SPECIFICATION/scenarios.md`, insert this named scenario immediately after `## Scenario: incident enablement follows complete installed-fleet capability proof` and before the next `## Scenario:` heading, in the plain Given/When/Then paragraph form the neighbouring incident scenarios use:

## Scenario: incident focused verification reads its changed set through the isolated object view and disposes symlinked and submodule paths explicitly

Given an expedited incident repair whose observer reads its changed product files from a reference clone

And that clone carries a replace ref and a graft that would alter the changed set if honoured, a changed `.py` under a source prefix stored as a symbolic link to a Python module, and a changed submodule gitlink under a source prefix

When focused verification computes the changed set and classifies each changed path

Then the changed set MUST equal the set read with replace refs, grafts and clone configuration ignored

And the symbolic-link module MUST be classified exactly as the coverage collector classifies it, so an honest focused-evidence record for it is admitted

And the submodule gitlink MUST be refused with a reason that names its path

### Co-edit at revise

`tests/heading-coverage.json` gains a row for the new scenario, owned by livespec-dev-tooling-rgiufy, at the integration tier or above, and `tests/heading-coverage-debt.json` gains the matching debt entry.

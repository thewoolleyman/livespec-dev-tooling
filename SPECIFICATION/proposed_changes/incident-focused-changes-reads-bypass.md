---
topic: incident-focused-changes-reads-bypass
author: claude-opus-5-5:expedited-incident-hardening
created_at: 2026-11-13T07:00:51Z
---

## Proposal: The per-pull-request arm reads its changed set through an isolated object view against the configured target branch, disposes a symlinked .py by its in-tree target, and refuses an escaping link or a submodule by name

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph's worth of sentences to contracts.md §"Expedited incident execution", in the focused-verification paragraph, immediately after "Generated, deleted and non-executable paths MUST receive explicit disposition.". They state, for the controller's per-pull-request arm: the changed set (every path differing between the head and its merge base with the tip of the installation's configured target branch, never `master` when another branch is configured; no rename detection; moves, mode-only and type changes count); the product-path rule (a source prefix the committed configuration declares at the target-branch tip or at the head, so a head can widen but never narrow it); that every read establishing the set uses only the clone's object store under a fresh repository administration with no replace refs, grafts, shallow boundary, system, global or clone configuration or attributes; that an incompletely established set is a named refusal; that a symlinked `.py` under a source prefix is disposed as the in-tree file its target names, while an escaping or unresolvable link is refused by name; and that a submodule gitlink under a source prefix is refused by name. Adds one fenced scenario exercising them. No heading is added, removed or renamed except the new scenario.

### Motivation

Work item livespec-dev-tooling-rgiufy (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub) carries non-blocking findings from the two independent reviews of livespec-dev-tooling#4086 (livespec-dev-tooling-6ou5m2) on 2026-11-11. On 2026-11-12T18:48:16Z the dispatch-stage spec-change tier held it as partial against `## Expedited incident execution`, with linked topic incident-focused-changes-reads-bypass. Its rationale: the section requires explicit disposition of generated, deleted and non-executable paths in focused verification, and it configures the target branch and requires the principal to refuse a request naming a different branch, but it does not state the isolated git object view for changed-file reads, the submodule refusal reason, or the symlinked-module classification. legacy-coordinator-agent holds the item until this topic ratifies and named this seat its owner (2026-11-13).

The defects, all in `livespec_dev_tooling/incident_focused_changes.py`:
- The changed set is read with plain `run_git` (`ls-tree`, `cat-file --batch`, `show <ref>:pyproject.toml`, and the diff in `_changed`) against the observer's reference clone. The sibling readers use `IsolatedGit` (`_incident_inverse_git.py`), which ignores replace refs, grafts and clone configuration. A clone carrying any of those can therefore change the set of paths focused verification judges.
- A `.py` under a source prefix stored as a symbolic link (tree mode 120000) is classified differently from how the coverage collector classifies it, so an honest focused-evidence record is refused.
- A submodule gitlink (tree mode 160000) under a source prefix fails with `list index out of range` rather than a reason a reader can act on.

Every one fails in the refusal direction: an honest record is refused, or a reason is unhelpful. None admits an under-covered record. That is why the item was filed as hardening. But the ratified text states none of the three behaviours, so a fix has no clause to be judged against, and the tier is right to hold it.

rgiufy's fourth Definition of Done bullet (a test drives /arm with a non-default target_branch) rests on the per-pull-request arm sentence below. The existing target-branch paragraph binds the recovery principal's publish, merge and conflict recording, not the per-pull-request arm's changed-set base (`incident_observer_control.py:139`), which the 18:48:16Z tier rationale named.

legacy-coordinator-agent's PASS-WITH-FIXES grade of livespec-dev-tooling#4482 (2026-11-13) supplied the replacement text applied here, closing four fail-open paths the first draft left unstated: the committed-configuration read that supplies the source prefixes, the union-of-prefixes rule, the merge-base base, and an incomplete set as a named refusal. It also replaced "classified exactly as the coverage collector classifies it", which pointed at code no clause defines and which treats a dangling in-tree link as deleted (fail-open), with an explicit disposition.

### Proposed Changes

### contracts.md

In `SPECIFICATION/contracts.md`, section `## Expedited incident execution`, in the paragraph that begins "Focused verification MUST run changed/directly related tests", insert the following immediately after the sentence "Generated, deleted and non-executable paths MUST receive explicit disposition.":

> The controller's per-pull-request arm MUST judge a focused-evidence record against the changed set it reads from its own reference clone: every path that differs, listed without rename detection, between the head and the merge base of the head with the tip of the installation's configured target branch, never `master` when the installation names another branch; a moved file is both its old and its new path, and a mode-only or type change is a changed path. A changed path is a product path when it lies under a source prefix that the committed configuration declares at the target-branch tip or at the head, so a head can widen that set but never narrow it. Every read that establishes the set, including the merge base, each changed path's tree mode and content at the head, and the committed configuration at both commits, MUST use only the clone's object store under a fresh repository administration that holds no replace refs, grafts or shallow boundary and reads no system, global or clone configuration or attributes, so that none of them can add, drop or alter a changed path. A changed set the clone cannot establish completely, including one with a missing object, MUST be a named refusal, never an empty or partial set. A changed path under a source prefix whose name ends in `.py` and whose tree entry is a symbolic link MUST be disposed as the file its target names within the head's tree would be at that path; a symbolic link under a source prefix whose target leaves the repository or does not resolve within the head's tree MUST be refused with a reason that names the link's path. A changed path under a source prefix whose tree entry is a submodule gitlink MUST be refused with a reason that names the submodule path, never with an unrelated internal error.

No other sentence of the paragraph changes, and no heading is added, removed or renamed in contracts.md.

### scenarios.md

In `SPECIFICATION/scenarios.md`, insert this named scenario immediately after the scenario `## Scenario: incident enablement follows complete installed-fleet capability proof` and before the next `## Scenario:` heading. Its `## ` heading line lands outside the fence and its Given/When/Then lines inside a ```gherkin fence, as every neighbouring incident scenario does:

## Scenario: incident focused verification reads its changed set through the isolated object view and disposes symlinked and submodule paths explicitly

```gherkin
Given an installation whose configured target branch is a scratch branch other than `master`, and an expedited incident repair whose head the reference clone holds alongside a replace ref and a graft that would alter the changed set if honoured
And the head changes a `.py` under a source prefix stored as a symbolic link to an in-tree module, a second such link whose target leaves the repository, and a submodule gitlink under a source prefix
When the controller's per-pull-request arm reads the changed set and classifies each changed path
Then the changed set MUST equal the set read against the merge base with the configured scratch branch with replace refs, grafts and clone configuration ignored
And the in-tree symbolic-link module MUST be disposed as the module its target names within the head's tree
And the escaping link and the submodule gitlink MUST each be refused with a reason that names its path
```

### Co-edit at revise

`tests/heading-coverage.json` gains a `"test": "TODO"` row for the new scenario heading whose `reason` names the integration tier the owed test runs at and whose `"work_item"` is `livespec-dev-tooling-rgiufy`, and `tests/heading-coverage-debt.json` is regenerated with `just generate-heading-coverage-debt-register`, never hand-edited.

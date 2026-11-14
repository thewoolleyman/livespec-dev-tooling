---
topic: isolatedgit-s-object-view-still
author: claude-opus-5-5
created_at: 2026-11-14T03:22:43Z
---

## Proposal: Every incident scope read from a reference clone honours no commit-graph and refuses an alternates file

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

This proposal makes two changes:
- It amends contracts.md §"Expedited incident execution" with one paragraph that generalizes the isolated reads the section already requires. Every read that derives incident scope from a reference clone goes through one isolated object view: the per-pull-request arm's changed set, the recovery principal's landed scope, inverse tree entries and patch, and incident release screening. That view takes commit history only from the commit objects of the clone's own object store, so it never honours the clone's commit-graph. It refuses, naming the file, a clone whose object store names another store through objects/info/alternates or objects/info/http-alternates, before any object is read.
- It amends the body of the existing focused-verification scenario so that scenario exercises both protections.

### Motivation

Work item livespec-dev-tooling-a3xotn, filed 2026-11-14 on legacy-coordinator-agent's direction and ranked high, because it is the incident path's integrity. Its pre-dispatch screen refused it at the spec-change tier (verdict partial, generalization target ## Expedited incident execution, linked topic isolatedgit-s-object-view-still).

The gap was found while reviewing livespec-dev-tooling#4584 (rgiufy). IsolatedGit._object_view in livespec_dev_tooling/_incident_inverse_git.py makes a fresh bare administration and points GIT_OBJECT_DIRECTORY at the clone's own objects directory. That shuts out the clone's replace refs, grafts, shallow file and configuration. Two inputs live INSIDE that shared objects directory, so the view still honours them:
- objects/info/commit-graph: git takes commit parents and generation numbers from it by default, so a forged graph can feed false history to merge-base and every walk.
- objects/info/alternates and http-alternates: git resolves objects from every store they name.

The section's focused-verification paragraph already says the per-pull-request arm's reads MUST use only the clone's object store under a fresh administration with no replace refs, grafts, shallow boundary or configuration. The screen judged that this covers part of the alternates concern. It does not name the commit-graph, a refusal naming the alternates file, or the other readers that go through the same view: the recovery principal's scope and inverse reads, and release screening.

legacy-coordinator-agent's grade of livespec-dev-tooling#4631 (2026-11-14) asked for a scenario. The existing focused-verification scenario already sets up a forged clone, so its body is amended rather than a new scenario added.

### Proposed Changes

**1. One isolated view for every incident scope read (`contracts.md` §"Expedited incident execution").**

Insert the following paragraph immediately after the paragraph that begins "Focused verification MUST run changed/directly related tests":

> Every read that derives incident scope from a reference clone MUST go through one isolated object view. Those reads are the per-pull-request arm's changed set, the recovery principal's landed scope, inverse tree entries and inverse patch, and incident release screening. The view MUST take commit parents and history only from the commit objects in the clone's own object store, and MUST NOT honour the clone's commit-graph file or commit-graph chain, so a forged graph cannot change a merge base, a tree listing or a diff. When the clone's object store names another store, through `objects/info/alternates` or `objects/info/http-alternates`, the view MUST refuse before reading any object, with a reason that names that file. No object from another store may reach a scope read. Each reader MUST receive both protections from the view itself, never by opting in. These sentences are spec-first: `IsolatedGit` in `livespec_dev_tooling/_incident_inverse_git.py` still reads the clone's commit-graph and resolves objects through its alternates, and work item livespec-dev-tooling-a3xotn owns the change.

**2. The focused-verification scenario exercises both protections (`scenarios.md`).**

Replace the body of `## Scenario: incident focused verification reads its changed set through the isolated object view and disposes symlinked and submodule paths explicitly` with the following, keeping its `gherkin` fence and its heading unchanged:

```gherkin
Given an installation whose configured target branch is a scratch branch other than `master`, and an expedited incident repair whose head the reference clone holds alongside a replace ref, a graft and a forged commit-graph file that would each alter the changed set if honoured
And the head changes a `.py` under a source prefix stored as a symbolic link to an in-tree module, a second such link whose target leaves the repository, and a submodule gitlink under a source prefix
When the controller's per-pull-request arm reads the changed set and classifies each changed path
Then the changed set MUST equal the set read against the merge base with the configured scratch branch with replace refs, grafts, the commit-graph and clone configuration ignored
And the in-tree symbolic-link module MUST be disposed as the module its target names within the head's tree
And the escaping link and the submodule gitlink MUST each be refused with a reason that names its path
And when the reference clone's object store carries an `objects/info/alternates` file that names another object store, the read MUST be refused before any object is read, with a reason that names that file
```

Only the body changes. The H2 heading text stays byte-identical, so `tests/heading-coverage.json` needs no co-edit for this proposal; the heading's existing coverage row stays as it is.

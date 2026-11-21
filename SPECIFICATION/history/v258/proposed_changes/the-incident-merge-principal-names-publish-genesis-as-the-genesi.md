---
topic: the-incident-merge-principal-names-publish-genesis-as-the-genesi
author: claude-sonnet-5-5
created_at: 2026-11-19T16:41:35Z
---

## Proposal: the-incident-merge-principal-names-publish-genesis-as-the-genesis-writer

### Target specification files

- SPECIFICATION/contracts.md

### Summary

In the "Incident-merge principal" paragraph of contracts.md, replace "written by the incident authority writer's `file-incident` action" with "written by the incident authority writer's `publish-genesis` action". Every other word of the clause, including "which MUST be the sole authority for the merge", stays.

### Motivation

The released writer has two separate steps. `file-incident` is the entry: it files the backlog incident item, its claim and the deferred-admission comment, and writes no chain root. `publish-genesis` is the only action that calls the genesis publication primitive, and its request carries an attempt, a principal, the expected claim and a staged tree, none of which exist when an incident is first filed. So the spec names the wrong action for the genesis record, and an incident that went through `file-incident` alone has no genesis record, as livespec-dev-tooling-u5efoi and livespec-dev-tooling-3q3xma show. The safety direction is unchanged: the merge principal requires a genesis record, so such an item is refused rather than merged. This is a naming correction to match the shipped writer, not a change to what authorizes a merge. Recorded as a decision on livespec-dev-tooling-lf043; plan epic livespec-dev-tooling-bqnzcm.

### Proposed Changes

In SPECIFICATION/contracts.md, paragraph "**Incident-merge principal.**", change the phrase "has a genesis record in the canonical incident authority chain, written by the incident authority writer's `file-incident` action, which MUST be the sole authority for the merge" to "has a genesis record in the canonical incident authority chain, written by the incident authority writer's `publish-genesis` action, which MUST be the sole authority for the merge". No scenario changes: the paragraph's merge conditions are untouched. Any other occurrence of the same claim, if the revise pass finds one, is corrected the same way.

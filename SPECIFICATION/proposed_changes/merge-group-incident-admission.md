---
topic: merge-group-incident-admission
author: claude-opus-5-5 (bqnzcm plan seat)
created_at: 2026-11-16T02:31:08Z
---

## Proposal: The replay gate admits a rebased expedited commit in a merge group by queue-entry attribution and patch-id

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State how check-red-green-replay admits an expedited commit on a merge_group event. It resolves the queue-entry refs and attributes each commit to the first entry containing it. It reads that PR's livespec-incident-ci block and requires the block's identity to equal the forge's. It admits only on a stable patch-id match against the recorded base..head, the audited trailer, and the observer recording the head. Everything else is convicted with a named line, and a conflict-resolved rebase is named as a known limit that is always convicted. Add three scenarios.

### Motivation

livespec-dev-tooling-txon2s (split from yfrepg; throughput-plans-coordinator ruled the design and SPEC FIRST at ~01:3xZ 2026-11-16, then accepted it as the carrier for incident zq2i4c's INCIDENT-FIRST repair at 02:5xZ). On origin/master f1b5eade2, _red_green_replay_incident._pull_request returns {} unless the event is pull_request, so the merge queue convicts every expedited product-.py commit (run 43759262277 on 0fdbcc2b0). That has forced zq2i4c's FIX 1 and FIX 2, and n35tv5 a1, onto the normal lane. Reading the PR from the queue head ref is not enough: the queue rebases, so each commit is a new SHA that fails the existing is-ancestor test, and a batched group names only its last PR. Fleet scope: every repository with a required merge queue that adopts incident CI. Related: livespec-dev-tooling-72b33c (the out-of-queue merge).

### Proposed Changes

Add to `contracts.md` §"Expedited incident execution", after the paragraph on the replay gate's recorded-incident admission, a paragraph headed "Merge-queue admission of an expedited commit":

On a `merge_group` event the event carries no pull request, and the merge queue rebases each queued pull request's commits, so every commit in the range is a rebased copy whose SHA differs from the commit the incident chain recorded, and one merge group can batch several queued pull requests. `check-red-green-replay` MUST therefore admit a commit that lacks TDD evidence on a `merge_group` event only as follows, and MUST NOT admit it on any other `merge_group` path:

- It MUST resolve the merge group's queue entries from the forge, each entry being a `gh-readonly-queue/<base>/pr-<N>-<sha>` ref together with its pull request number N, read through the library's budgeted forge reader.
- It MUST attribute each commit in the range to the queued pull request of the FIRST entry ref, in queue order, whose history contains that commit.
- It MUST read the attributed pull request's body from the forge and decode its `livespec-incident-ci` block, and MUST require the block's identity to equal that pull request's forge-read number, base SHA and head SHA.
- It MUST admit the commit only when the commit's stable patch-id (`git patch-id --stable`) equals the stable patch-id of a commit in the block's recorded `base..head`, the commit carries the audited `Factory-Override` trailer naming the block's incident item, and the observer's provenance route records that head.
- Every other outcome MUST keep the commit convicted and MUST print one refusal line naming the commit and the first condition that failed: no queue entry contains it, no block, an identity mismatch, a patch-id mismatch, a missing trailer, or the observer not recording the head.
- Labels and incident environment variables MUST NOT be read. Nothing a candidate writes grants admission.

Known limit, stated so it is never read as a defect: a rebase that had to resolve a conflict changes the commit's patch-id, so such a commit matches nothing in `base..head` and MUST be convicted, never admitted. Its repair takes the normal Red-Green lane.

Add to `scenarios.md`:

## Scenario: the replay gate admits a rebased expedited commit in a merge group by its patch-id

```gherkin
Given a merge group whose queue entry for pull request N contains a rebased copy of an expedited commit that lacks TDD evidence
And pull request N's livespec-incident-ci block names its forge-read number, base and head
And the rebased copy's stable patch-id equals that of a commit in the recorded base..head, and the observer records the head
When check-red-green-replay runs on the merge_group event
Then the rebased copy is admitted
```

## Scenario: the replay gate convicts a merge-group commit whose patch-id matches nothing recorded

```gherkin
Given a merge group containing a commit that lacks TDD evidence, attributed to pull request N
And the commit's stable patch-id matches no commit in pull request N's recorded base..head, as after a conflict-resolved rebase
When check-red-green-replay runs on the merge_group event
Then the commit stays convicted
And the gate prints a line naming the commit and the patch-id mismatch
```

## Scenario: the replay gate attributes each commit of a batched merge group to its own pull request

```gherkin
Given a merge group batching two queued pull requests, each with its own queue-entry ref
When check-red-green-replay runs on the merge_group event
Then each commit is attributed to the pull request of the first entry ref that contains it
And each commit is judged against its own pull request's livespec-incident-ci block
```

The `tests/heading-coverage.json` rows for the three new scenario headings, and any debt-register entry a spec-first `TODO` row owes, MUST be co-edited in the revise commit.

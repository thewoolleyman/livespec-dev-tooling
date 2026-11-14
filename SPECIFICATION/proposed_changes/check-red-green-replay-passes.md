---
topic: check-red-green-replay-passes
author: claude-opus-5-5
created_at: 2026-11-14T01:11:54Z
---

## Proposal: Range validation refuses a trailer subject and a recorded checksum that does not match its own tree

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a bullet to contracts.md section "Suite-green replay leg", beside "Range validation collects a Red+Green commit's recorded test". It makes the commit-range validation of check-red-green-replay refuse two commit shapes it accepts today: a commit whose subject line is itself a git trailer, and a commit whose TDD-Red-Test-File-Checksum does not equal the checksum of its recorded test file on that commit's own tree. A matching scenario is added to scenarios.md.

### Motivation

Work item livespec-dev-tooling-a4w7qr was refused at the spec-change tier on 2026-11-14 (topic check-red-green-replay-passes): the spec-stated judgement found these behaviours unstated and named "## Suite-green replay leg" as the heading to generalize. The range gate judges a commit only by the presence of trailer keys, so two factory defects publish commits it accepts. (1) An aborted empty-message commit becomes trailer-only, because git runs the commit-msg hook before its empty-message abort and two hook writers append trailers in place: cc76b2c9 on livespec-dev-tooling master, and livespec-dev-tooling#3995 commits 59d64a81 and 9474e751. (2) A restored factory run rebased commits that kept their original TDD-Red-* trailers, so their recorded checksums no longer match their own trees (livespec-dev-tooling#3990). This mirrors v180's range-gate-collects-recorded-test, which stated livespec-dev-tooling-5be65c's collection rule in the same section.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Suite-green replay leg", add this bullet immediately after the bullet "Range validation collects a Red+Green commit's recorded test":

- **Range validation refuses a trailer subject and a stale recorded checksum.** The commit-range validation of `check-red-green-replay` (the no-argument path, which judges every non-merge commit in `origin/master..HEAD`) MUST apply both rules below to every commit in its range, with the same exemptions as the collection bullet above: a forge-authored revert verified under the server-side revert exemption, and an expedited commit the incident chain records. No lever, flag or subject prefix MAY exempt a commit from either rule.
  - *Trailer subject.* A commit whose subject line, the first line of its message, has the form of a git trailer (`Key: value`, where `Key` is a token of letters, digits and hyphens that contains at least one hyphen, as every trailer the fleet writes does, such as `Factory-Run-Id`, `TDD-Red-Test` and `Co-Authored-By`, followed by a colon and a space) MUST fail the range. A conventional-commit type such as `fix:` or `feat:`, which this repository's Red-Green protocol requires, is not a trailer subject. The finding MUST name the commit's sha and its subject line.
  - *Recorded checksum on its own tree.* A commit carrying a `TDD-Red-Test-File-Checksum` trailer MUST fail the range when that value does not equal the checksum, computed by the same rule the Red leg used to record it, of the bytes of the file named by the path part of its `TDD-Red-Test` value (any `::` node id dropped, as the collection bullet states) on that commit's own tree, or when that file is absent there, or when the commit carries no `TDD-Red-Test` trailer at all. The finding MUST name the commit's sha, the test file, the recorded checksum and the checksum read on the commit's tree.
  - *Finding.* Each rule's failure MUST carry its own `check_id`, distinct from the other rule's, from the missing-trailers failure and from the collection failure. The remedy each names is to rewrite the range so that every commit has a non-trailer subject and every recorded checksum matches its own tree.
  - *Passing range.* A range in which every commit has a non-trailer subject line and every recorded `TDD-Red-Test-File-Checksum` matches its commit's own tree MUST pass both rules.
  - *Fleet scope.* Every consumer whose CI runs the shared `red_green_replay` check.
  - *Spec-first.* The shipped range path checks only that the trailer keys are present. Work item livespec-dev-tooling-a4w7qr owns the change.

In SPECIFICATION/scenarios.md, add after "## Scenario: the commit-range validation fails a Red+Green commit whose recorded test cannot be collected on its own tree":

## Scenario: the commit-range validation fails a commit whose subject is a trailer or whose recorded checksum does not match its own tree

Given a branch whose range from origin/master holds a commit whose subject line is `Factory-Run-Id: c5d75329`

When check-red-green-replay validates the range

Then the check MUST fail with a finding that names that commit's sha and that subject line

And a commit whose subject is `fix: x` MUST NOT fail the trailer-subject rule

And a range holding a commit whose TDD-Red-Test-File-Checksum differs from the checksum of its TDD-Red-Test file on that commit's own tree MUST fail the check with a finding that names the commit's sha, the test file, the recorded checksum and the checksum read on the tree

And the trailer-subject finding and the checksum finding MUST each carry a check_id that differs from the other's, from the missing-trailers finding's and from the collection finding's

And a range in which every commit has a non-trailer subject line and every recorded checksum matches its own tree MUST pass both rules

## Proposal: A commit-msg trailer writer leaves an empty message empty, so git aborts the commit

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a bullet to contracts.md section "Suite-green replay leg": every commit-msg hook writer in the dev-tooling pack that appends trailers MUST leave a message with no content unchanged, so git's own empty-message abort still ends the commit with no new commit and HEAD unchanged, with or without a factory run marker. A matching scenario is added to scenarios.md.

### Motivation

This is the root of the trailer-only commits that finding 1's range rule refuses after the fact. git runs the commit-msg hook before it checks for an empty message. Two writers append trailers in place with `git interpret-trailers --in-place`: factory_provenance_gate's run-id trailer (Factory-Run-Id) and the replay leg's TDD-* trailers. An empty message therefore gains a trailer block, git no longer sees it as empty, and the commit is created with a trailer as its subject. Work item livespec-dev-tooling-a4w7qr's DoD bullet 4 asserts the abort with and without a factory run marker.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Suite-green replay leg", add this bullet after the bullet added by finding 1:

- **An empty commit message stays empty.** Every commit-msg hook writer that the dev-tooling pack installs and that appends trailers to the message file, including the replay leg's `TDD-*` trailers and the factory provenance gate's `Factory-Run-Id` trailer, MUST leave the message file unchanged when the message has no content other than whitespace and comment lines. A `git commit` attempted with an empty message in a repository whose commit-msg hooks come from the pack MUST therefore be aborted by git, with no new commit created and HEAD unchanged, both with and without a factory run marker present. A writer MUST NOT supply a subject line to make an empty message non-empty. This bullet takes precedence over every bullet of this section that requires a trailer to be recorded. Fleet scope: every consumer that installs the pack's commit-msg hooks. Spec-first: the shipped writers append their trailers to an empty message, and work item livespec-dev-tooling-a4w7qr owns the change.

In SPECIFICATION/scenarios.md, add after the scenario added by finding 1:

## Scenario: an empty-message commit is aborted even when the pack's commit-msg trailer writers are installed

Given a repository whose commit-msg hooks are installed from the dev-tooling pack, with a staged change

When a git commit is attempted with an empty message

Then git MUST abort the commit with no new commit created and HEAD unchanged

And the same MUST hold when a factory run marker is present, so that the factory provenance gate's Factory-Run-Id writer runs

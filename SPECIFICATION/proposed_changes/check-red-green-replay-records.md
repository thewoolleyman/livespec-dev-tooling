---
topic: check-red-green-replay-records
author: claude-opus-5-5
created_at: 2026-11-14T02:51:26Z
---

## Proposal: A failing test staged beside non-.py implementation is refused, never recorded as a Red, and the range fails a Red-only non-.py commit

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a bullet to contracts.md section "Suite-green replay leg", after the bullets added by check-red-green-replay-passes. It states three rules. The commit-msg replay gate refuses a commit whose staged test fails beside staged non-.py implementation, and records no TDD-Red-* trailer for it. A commit staging test modules and no implementation of any kind keeps today's Red leg. The commit-range validation of check-red-green-replay fails a commit that stages non-.py implementation and carries TDD-Red-* trailers with no TDD-Green-* trailer, under its own check_id and with the same exemptions as the other range rules. Two matching scenarios are added to scenarios.md.

### Motivation

Work item livespec-dev-tooling-kz6n3a was recorded at the spec-change tier on 2026-11-14 (verdict unstated, linked topic check-red-green-replay-records). The section states the suite-green leg, the collection rule and the Progress bound, but nothing about a staged test that fails beside non-.py implementation. The shipped hook (read at livespec-dev-tooling a8e18baf1, the same in v1.207.0) classifies only .py files as implementation, so a staged .sh leaves the impl set empty and the commit is dispatched as tests-only. The livespec-dev-tooling-9yrr carve-out stops Red intent for a non-.py-impl commit, but only when the staged-tests probe PASSES. When it fails, the Red leg runs and records TDD-Red-* trailers. The Green leg is reached only when product .py is staged, so that commit can never complete, and the range validation judges only commits that touch product .py, so CI accepts it. Measured on livespec-overseer master, PR #3018 (factory run ea54d24d3fe34cf48b7b247a1a16f4eb, pin v1.207.0): commits a8121d18 and 478ae50f each stage a .sh implementation beside a failing test and carry the five TDD-Red-* trailers and no TDD-Green-*. While one of them was master's tip, commit_pairs_source_and_test read HEAD as a Green amend in progress, so the first commit of every branch cut from master skipped the commit-pairs check. A test that fails beside its own staged implementation is a broken commit, not a Red, which is the 9yrr reasoning applied to the failing case. This proposal rides the same revise as check-red-green-replay-passes (livespec-dev-tooling#4610, legacy-coordinator-agent ruling 2026-11-14), and aligns with it: its range rule composes with #4610's two rules and takes their exemptions.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Suite-green replay leg", add this bullet immediately after the bullets added by the check-red-green-replay-passes proposal ("Range validation refuses a trailer subject and a stale recorded checksum" and "An empty commit message stays empty"). If that proposal is not accepted in the same revise, add it immediately after the bullet "Range validation collects a Red+Green commit's recorded test":

- **A Red is recorded only where a Green can follow.** Non-`.py` implementation is any staged path outside `tests/` whose name is `justfile` or ends in `.sh`, `.just`, `.yml` or `.yaml`.
  - *Commit-msg refusal.* When a commit stages at least one test module beside non-`.py` implementation, and the run of its staged test modules fails, the commit-msg replay gate MUST refuse the commit. The refusal event MUST name each failing test and each staged non-`.py` implementation path, and the commit MUST NOT record any `TDD-Red-*` trailer. A test that fails beside its own staged implementation is a broken commit, not a Red, because no Green amend can follow it: the Green leg runs only when product `.py` is staged.
  - *Tests-only Red unchanged.* A commit that stages test modules and no implementation of any kind, `.py` or non-`.py`, and whose staged test fails, MUST take the Red leg and record the `TDD-Red-*` trailers exactly as before.
  - *Range rule.* The commit-range validation of `check-red-green-replay` (the no-argument path, which judges every non-merge commit in `origin/master..HEAD`) MUST fail the range when a commit stages non-`.py` implementation and carries any `TDD-Red-*` trailer with no `TDD-Green-*` trailer, with the same exemptions as the collection bullet: a forge-authored revert verified under the server-side revert exemption, and an expedited commit the incident chain records. No lever, flag or subject prefix MAY exempt a commit from this rule. The finding MUST name the commit's sha, its subject line and its staged non-`.py` implementation paths. It MUST carry its own `check_id`, distinct from the missing-trailers, collection, trailer-subject and recorded-checksum findings. The remedy it names is to rewrite the range so that no commit carrying non-`.py` implementation rests on a Red with no Green.
  - *Fleet scope.* Every consumer whose commit-msg hook or CI runs the shared `red_green_replay` check.
  - *Spec-first.* The shipped commit-msg hook records `TDD-Red-*` trailers for a failing test staged beside non-`.py` implementation, and the shipped range path judges only commits that touch product `.py`. Work item livespec-dev-tooling-kz6n3a owns the change.

In SPECIFICATION/scenarios.md, add these two scenarios after the scenarios added by the check-red-green-replay-passes proposal, or, if that proposal is not accepted in the same revise, after "## Scenario: the commit-range validation fails a Red+Green commit whose recorded test cannot be collected on its own tree":

## Scenario: a failing test staged beside a shell implementation is refused with no Red recorded

Given a commit that stages `scripts/run.sh` and `tests/test_run.py`, and no product `.py`

And the staged test `tests/test_run.py` fails

When the commit-msg replay gate runs

Then it MUST refuse the commit with an event naming the failing test and `scripts/run.sh`

And the commit MUST NOT record any `TDD-Red-*` trailer

And a commit that stages only `tests/test_run.py`, which fails, MUST still take the Red leg and record the `TDD-Red-*` trailers

## Scenario: the commit-range validation fails a commit that stages non-.py implementation and rests on a Red with no Green

Given a branch whose range from origin/master holds a commit that stages `scripts/run.sh` and carries `TDD-Red-*` trailers and no `TDD-Green-*` trailer

When check-red-green-replay validates the range

Then the check MUST fail with a finding that names that commit's sha, its subject line and `scripts/run.sh`

And the finding MUST carry a check_id that differs from the missing-trailers, collection, trailer-subject and recorded-checksum findings' check_ids

And a range whose commits that stage non-.py implementation carry no Red-only trailer set MUST pass this rule

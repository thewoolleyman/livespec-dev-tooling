---
topic: the-ci-green-required-leg
author: claude-opus-5-5
created_at: 2026-11-13T01:36:36Z
---

## Proposal: The ci-green required-leg reader reads a block-sequence needs list and passes a job skipped by its own if

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Amend constraints.md §"CI matrix shape" with a paragraph that states, as normative behaviour, how this library's shared ci-green required-leg reader (`livespec_dev_tooling.ci_green_required_legs`) decides which legs of the aggregate gate job's needed jobs are gaps. A `needs:` written as a YAML block sequence MUST yield the same needed jobs and gaps as an inline list. A needed job that declares its own job-level `if:`, concludes `skipped`, and whose own needed jobs all concluded `success` is a designed skip and MUST NOT be a gap. A skipped job with no job-level `if:` MUST be a gap, and so MUST an `if:`-skipped job behind a needed job that did not succeed. A needed job absent from the run's job list MUST be a gap whatever its `if:`, because the forge lists a job its own condition skipped and does not list one it never created; a matrix job skipped by its own `if:` has no expanded legs, so its legs read as never created and fail closed. A needed job that concludes `skipped` in a cancelled run MUST be a gap whatever its `if:`, so a `!cancelled()` job skipped by a cancellation never passes as a designed skip. Add six scenarios to scenarios.md, one per behaviour. Work item livespec-dev-tooling-acapf4 carries the implementation.

### Motivation

No live clause in SPECIFICATION/*.md states the reader's semantics. Work item livespec-dev-tooling-acapf4 is held on a spec-change tier whose record names §"CI matrix shape" as its generalization target and finds no clause there that states these rules. master's reader still parses only the inline `[a, b]` form of `needs:` and counts every conclusion other than `success` as a gap.

The legacy-coordinator-agent routed a fleet sweep on 2026-11-10 (the homelab#1161 shape). Eight fleet ci-greens fail only on `failure` or `cancelled`, so a leg the forge never created passes them, as it passed this repository's ci-green before livespec-dev-tooling-nofeol. The fleet relay that adopts this reader in those eight ci-greens cannot adopt it as it stands, for two reasons. First, livespec-driver-claude, livespec-driver-codex and livespec-driver-pi write ci-green's `needs:` as a block sequence. The reader would read no needs there, fail closed, and redden the gate. Second, livespec's `release-gate-pre-tag` (skipped by its own `if:` on non-release pull requests) and livespec-orchestrator-beads-fabro's `check-factory-provenance` (skipped by its own `if:` on push) are designed skips. The reader counts every non-success conclusion as a gap, so it would redden them too. A job skipped by its own `if:` still appears in the Actions jobs API with conclusion `skipped`. A never-created job does not appear at all, so absence stays a gap unconditionally.

Placement. This proposal amends §"CI matrix shape" instead of adding a `##` section beside it. Three reasons: (1) acapf4's Definition of Done references `## CI matrix shape`, and its spec-change tier record names that heading as the generalization target, so stating the rules there settles the hold without rewriting the item's References line; (2) the section already owns the aggregate gate and required-check semantics that branch protection reads, and it closes by saying those semantics are unchanged by routing; (3) a new H2 would add a heading the next dispatch judgement would have to discover. The rules are a constraint whose violation a consumer observes (a red or a falsely green required check), so constraints.md is the right file under the §Boundary litmus.

### Proposed Changes

### SPECIFICATION/constraints.md §"CI matrix shape"

Append this paragraph and list at the end of the section, after the paragraph that begins "Both reverts are MANUAL and operator-driven.":

Branch protection can require the aggregate gate job (`ci-green`) as its only context, as it does in this repository, and then that job is the whole merge gate. Its verdict MUST therefore rest on the run's own job list and not only on `needs.*.result`. That expression carries one result per needed job and nothing at all for a leg the forge never created. This library's shared required-leg reader, `livespec_dev_tooling.ci_green_required_legs`, reads the workflow text the run used and the run's job list as the Actions jobs API reports it, and decides which legs of the gate job's needed jobs are gaps. The gate MUST fail when the reader reports any gap, naming each one, and MUST pass only when it reports none. The reader MUST meet all of the following:
- It MUST derive the gate job's needed jobs from a job-level `needs:` written as a YAML block sequence exactly as it does from one written as an inline flow list. The two spellings of the same list MUST yield the same needed jobs and the same gaps.
- A needed job, or a leg of one, that is absent from the run's job list MUST be a gap naming it as never created, whether or not that job declares a job-level `if:`. A job skipped by its own `if:` still appears in the run's job list with conclusion `skipped`. A job the forge never created does not appear at all, so absence MUST NOT be read as a designed skip. A matrix job is matched leg by leg, under the job name each leg reports (`${{ matrix.target }}` reports one leg per `matrix.target` entry). When a matrix job is skipped by its own `if:`, the forge does not expand its legs: the run's job list carries none of the leg names. Each leg therefore reads as never created and MUST be a gap naming it, so a matrix job skipped by its own `if:` fails closed and is never a designed skip.
- A leg that appears in the run's job list with a conclusion other than `success` or `skipped` MUST be a gap naming it.
- A needed job that concludes `skipped` and declares no job-level `if:` MUST be a gap naming it.
- A needed job that declares its own job-level `if:` and concludes `skipped` MUST NOT be a gap when every job it itself needs appears in the run's job list and concluded `success`, and the run is not cancelled under the next rule. This is a designed skip: the job's own condition chose not to run it.
- A needed job that concludes `skipped` in a cancelled run MUST be a gap naming it, whatever its own `if:` says and whatever its needs concluded. A job conditioned `if: ${{ !cancelled() }}` (as `check-metadata`, `check-metadata-batch` and `check-per-file-coverage` are) concludes `skipped` when the run is cancelled after its needs succeeded. The gate job runs under `always()`, so without this rule it could pass with that leg never executed. The reader MUST treat the run as cancelled when either of two observables holds: any job in the run's job list concluded `cancelled`, or the gate step hands it the gate job's own `cancelled()` status as true. The second observable is needed because a run cancelled before any job was in progress leaves no `cancelled` conclusion in the job list. The gate step evaluates `cancelled()` in the gate job's context and passes the value to the reader beside the job list; the shipped reader reads the job list only, so this input is spec-first.
- A needed job that declares its own job-level `if:` and concludes `skipped` while any job it itself needs is absent from the run's job list, or concluded anything other than `success`, MUST be a gap naming it. That skip can follow from the upstream job's result rather than from the job's own condition.
- A needed job whose legs the reader cannot derive MUST be a gap, and so MUST a gate job with no needs the reader can parse, so that the gate fails closed rather than checking less than it needs.

These rules leave the expedited-incident omission path passing. Under an authorized incident the member-holding jobs still run and report each omitted member through an explicit `omitted-by-incident-policy` step, so they conclude `success`. A fleet member whose ci-green adopts this reader inherits these rules. The block-sequence and designed-skip rules are spec-first: the shipped reader parses only an inline `needs:` list and counts every conclusion other than `success` as a gap. Work item livespec-dev-tooling-acapf4 owns the change.

### SPECIFICATION/scenarios.md

Add these six scenarios, in this order, directly after "## Scenario: a CI run GitHub fails at job creation with an Internal server error is re-run with backoff":

## Scenario: the ci-green required-leg reader reads a block-sequence needs list as it reads an inline one

Given a workflow whose `ci-green` job writes `needs:` as a YAML block sequence naming `check-a` and `check-b`

And a second workflow, otherwise identical, whose `ci-green` job writes `needs: [check-a, check-b]` as an inline list

And a run whose job list carries `check-a` with conclusion `success` and `check-b` with conclusion `failure`

When the required-leg reader reads each workflow against that run's job list

Then it MUST derive the needed jobs `check-a` and `check-b` from both workflows

And it MUST report the same gaps for both: one gap, naming `check-b`

## Scenario: a needed job skipped by its own if after all its needs succeeded is not a ci-green gap

Given a workflow whose `ci-green` job needs `build` and `release-gate`

And `release-gate` declares a job-level `if:` and needs `build`

And a run whose job list carries `build` with conclusion `success` and `release-gate` with conclusion `skipped`

When the required-leg reader reads that run

Then it MUST NOT report `release-gate` as a gap

And ci-green MUST pass

## Scenario: a needed job with no job-level if that concludes skipped is a ci-green gap

Given a workflow whose `ci-green` job needs `check-lint`, which declares no job-level `if:`

And a run whose job list carries `check-lint` with conclusion `skipped`

When the required-leg reader reads that run

Then it MUST report a gap naming `check-lint`

And ci-green MUST fail

## Scenario: a needed job skipped by its own if after one of its needs failed is a ci-green gap

Given a workflow whose `ci-green` job needs `check-per-file-coverage` and `check-coverage`

And `check-coverage` declares a job-level `if:` and needs `check-per-file-coverage`

And a run whose job list carries `check-per-file-coverage` with conclusion `failure` and `check-coverage` with conclusion `skipped`

When the required-leg reader reads that run

Then it MUST report a gap naming `check-coverage`, beside the gap naming `check-per-file-coverage`

And where `check-coverage` is a matrix job named `${{ matrix.target }}`, as in this repository's ci.yml, the forge reports none of its leg names, so the gap MUST name each of its legs as never created

And ci-green MUST fail

## Scenario: a needed job the forge never created is a ci-green gap whatever its if

Given a workflow whose `ci-green` job needs `check-lint` and `release-gate`

And `release-gate` declares a job-level `if:` and `check-lint` declares none

And a run whose job list carries neither `check-lint` nor `release-gate`

When the required-leg reader reads that run

Then it MUST report a never-created gap naming `check-lint` and a never-created gap naming `release-gate`

And ci-green MUST fail

## Scenario: a needed job skipped in a cancelled run is a ci-green gap even when its needs succeeded

Given a workflow whose `ci-green` job runs under `always()` and needs `check-lint` and `check-metadata`

And `check-metadata` declares the job-level `if: ${{ !cancelled() }}` and needs `check-lint`

And a run that was cancelled after `check-lint` concluded `success`, whose job list carries `check-metadata` with conclusion `skipped`

And either another job in that run's job list concluded `cancelled`, or the gate step hands the reader the gate job's `cancelled()` status as true

When the required-leg reader reads that run

Then it MUST report a gap naming `check-metadata`

And ci-green MUST fail

### Revise co-edit (outside the spec target)

The revise commit that accepts this proposal MUST add a `tests/heading-coverage.json` row for each of the six new scenario headings: `"test": "TODO"`, a `reason` naming the unit tier as the tier the owed test runs at and naming livespec-dev-tooling-acapf4 as its owner, and `"work_item": "livespec-dev-tooling-acapf4"`. It MUST also stage the regenerated `tests/heading-coverage-debt.json` from `just generate-heading-coverage-debt-register`. The constraints.md amendment adds no `## ` heading, so it owes no new row.

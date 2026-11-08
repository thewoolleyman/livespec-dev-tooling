---
topic: a-consumer-whose-pre-commit
author: claude-opus-5-5
created_at: 2026-11-08T03:36:51Z
---

## Proposal: One library entry point writes the same-tree evidence for a consumer's local pre-commit aggregate

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add to §"Suite-green replay leg" a contract for one livespec-dev-tooling entry point. A consumer's check-pre-commit recipe runs its LOCAL aggregate through it. It exits with the aggregate's status and writes the same-tree reuse evidence only when the aggregate passed on a clean worktree whose index did not change during the run. livespec-dev-tooling's own recipe uses it, consumers SHOULD, and two scenarios state the reuse and no-evidence cases.

### Motivation

The **Same-tree reuse** bullet requires the suite-green leg to reuse a passing full pre-commit aggregate on the same tree (livespec-dev-tooling-z5fwwn, PR #3203). The ratified text says nothing about WHO writes the evidence that reuse reads. It is written in exactly two places: livespec-dev-tooling's own `scripts/just/check-pre-commit.sh`, after its local aggregate, and `pre_commit_delegate`, when a gate Job delegates the aggregate. Every consumer repository runs its own fork of the pre-commit script. Each fork calls `pre_commit_delegate run`, but on the local fallback (exit 75) it runs the aggregate and writes nothing. Inside a factory sandbox that fallback is always the route, because the gates kubeconfig is unreadable there, so the whole suite runs twice for every behaviour-preserving commit.

Measured 2026-11-08 on livespec-orchestrator-beads-fabro run 01M6W3C2BBME (bd-ib-2eyiwy): the pre-commit aggregate passed (95 targets, 3728 s). The suite-green leg then re-ran the full suite with no `suite-green-reused-pre-commit-aggregate` event, and was killed after 900 s of no output. A read-only fleet survey (2026-11-08) found the same gap in nine consumer repositories: livespec, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-orchestrator-beads-fabro, livespec-orchestrator-git-jsonl, livespec-overseer, livespec-runtime and livespec-tdd-proof.

Copying the 12-line evidence tail into each fork would fix today's nine forks and leave the next fork, or the next guard change, to drift again. So the contract names one library entry point, states its guards (the ones check-pre-commit.sh applies today), and keeps the behaviour of a consumer that does not adopt it exactly as the **Scope** bullet already states. Plan implement-test-performance (epic livespec-dev-tooling-sv6m5p) files this for its assertion 2, that the whole test suite runs once against the final tree.

### Proposed Changes

Two edits. No existing sentence changes.

**1. `SPECIFICATION/contracts.md`, `## Suite-green replay leg`.** Insert this bullet immediately after the **Same-tree reuse** bullet:

> - **Local-aggregate evidence entry point.** livespec-dev-tooling MUST provide one entry point that a consumer's `check-pre-commit` recipe runs for its LOCAL pre-commit aggregate, including the local run that follows when §"Delegated pre-commit aggregate" reaches no cluster verdict. The entry point MUST run the aggregate command the recipe names and MUST exit with that command's own exit status. It MUST write the pre-commit evidence that the **Same-tree reuse** bullet consumes only when every one of these holds: the aggregate exited `0`; the working tree has no unstaged change; no untracked, non-ignored file exists; and `git write-tree` names the same tree after the aggregate as it named before the aggregate started. In every other case it MUST write no evidence. livespec-dev-tooling's own `check-pre-commit` recipe MUST run its local aggregate through this entry point, so the evidence write exists in one place. A consumer whose `check-pre-commit` recipe runs a full local aggregate SHOULD run it through this entry point. A consumer that runs its local aggregate any other way records no same-tree evidence, and its suite-green leg runs its suite in full, as the **Scope** bullet states. This bullet is spec-first: as of ratification, only livespec-dev-tooling's own `scripts/just/check-pre-commit.sh` writes this evidence after a local aggregate, and it does so inline. Work item livespec-dev-tooling-4scqti owns the change.

**2. `SPECIFICATION/scenarios.md`.** Add these two scenarios immediately after `## Scenario: a suite-green leg runs the full suite when the pre-commit aggregate judged a different tree or ran partially`. They add two `## ` headings, so the revise co-edits `tests/heading-coverage.json` with a `test: "TODO"` row for each, naming livespec-dev-tooling-4scqti as `work_item` and the integration tier, and regenerates `tests/heading-coverage-debt.json`.

```
## Scenario: a consumer's local pre-commit aggregate run through the shared entry point is reused by its suite-green leg

Given a consumer repository whose `check-pre-commit` recipe runs its local pre-commit aggregate through livespec-dev-tooling's local-aggregate entry point

And the aggregate exits `0` on tree `T` with no unstaged change and no untracked, non-ignored file, and `git write-tree` names `T` both before and after it

And `git write-tree` names tree `T` for the index when the commit-msg hook runs

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST NOT start a pytest suite run

And it MUST record its `TDD-Suite-Green-*` trailers from that aggregate run, naming that run

## Scenario: the local-aggregate entry point writes no evidence for a failed, dirty or changed tree

Given a consumer's local pre-commit aggregate run through livespec-dev-tooling's local-aggregate entry point

And the aggregate exits non-zero, or the working tree has an unstaged change or an untracked, non-ignored file, or `git write-tree` names a different tree after the aggregate than before it

When the entry point exits

Then it MUST exit with the aggregate's own exit status

And it MUST write no same-tree evidence

And the suite-green leg of that commit MUST run its suite in full
```


## Proposal: Every suite-green leg run reports whether it reused evidence or ran its suite

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every suite-green leg run emits one best-effort OTLP outcome span. The span says whether the leg REUSED pre-commit evidence or RAN its own suite, gives its outcome and duration, and names the repository and the committed tree. Inside a factory sandbox the span goes to the sandbox receiver; on a host it goes to the loopback collector. Delivery never changes the leg's verdict or exit status.

### Motivation

The cost of the double-suite class in the first proposal is invisible today. The leg's `suite-green-reused-pre-commit-aggregate` line is a structlog event on the hook's stderr, and no OTLP span is emitted. The factory's Honeycomb dataset holds only `run` and `run_turn` spans, so a re-run cannot be told apart from a legitimate full run, or from no run at all. Measured 2026-11-08 by seat token-spend-analysis: Honeycomb cannot count the class at all. The only trace is one dispatch-journal outcome (bd-ib-2eyiwy, run 01M6W3C2BBME, $32.59 whole-run loss), and that is a lower bound, because a stalled re-run whose commit later succeeds leaves no row. Without an event, the spend ranking that orders this fleet's work cannot see this class.

The emitter already exists in two shapes. `gate_outcome_telemetry` emits one best-effort outcome span per delegated gate run under §"Delegated pre-push gate" → **Telemetry**. `otel_step_timer` already emits from inside a factory sandbox to `$LIVESPEC_SANDBOX_OTEL_ENDPOINT`. This proposal applies the same best-effort rules to the suite-green leg.

### Proposed Changes

Two more edits, in addition to the first proposal's. No existing sentence changes.

**3. `SPECIFICATION/contracts.md`, `## Suite-green replay leg`.** Insert this bullet immediately after the **Local-aggregate evidence entry point** bullet that the first proposal adds:

> - **Outcome telemetry.** Every suite-green leg run MUST emit exactly one outcome event, as an OTLP span, to the fleet observability surface named in `non-functional-requirements.md` §"Runner-pool cache telemetry". The event MUST carry, as separate attributes:
>   - the repository's name;
>   - the committed tree's hash;
>   - the leg's mode: `reused` when it recorded its trailers from same-tree evidence, `ran` when it started its own suite run;
>   - its scope (`full-suite` or `staged-tests`);
>   - its outcome: `green`, `red`, or `ended`, where `ended` covers the progress bound or the optional total ceiling;
>   - its wall-clock duration in seconds.
>
>   A value the leg had not determined when it stopped MUST be absent from the event, never guessed. Inside a factory sandbox the event MUST go to the sandbox receiver at `$LIVESPEC_SANDBOX_OTEL_ENDPOINT`, the receiver `otel_step_timer` already uses. On a host it MUST go to the host's loopback collector. Emission is best-effort: when the event cannot be delivered, the leg MUST record the same trailers or refusal and exit with the same status it would have with telemetry working, and it MUST NOT wait on delivery for longer than a bounded attempt. This bullet is spec-first. Work item livespec-dev-tooling-4scqti owns the change.

**4. `SPECIFICATION/scenarios.md`.** Add this scenario immediately after the two scenarios the first proposal adds. It adds one more `## ` heading, so the revise co-edits `tests/heading-coverage.json` with a `test: "TODO"` row for it, naming livespec-dev-tooling-4scqti as `work_item` and the integration tier, and regenerates `tests/heading-coverage-debt.json`.

```
## Scenario: a suite-green leg run emits one outcome event naming whether it reused evidence

Given a commit whose suite-green leg runs, either reusing same-tree pre-commit evidence or starting its own suite run

When the leg finishes, whether green, red or ended

Then it MUST emit exactly one OTLP outcome span naming the repository, the committed tree's hash, the mode `reused` or `ran`, the scope, the outcome and the wall-clock duration

And when the observability receiver cannot be reached, the leg MUST record the same trailers or refusal and exit with the same status
```

---
proposal: detached-gate-runner.md
decision: modify
revised_at: 2026-10-26T21:08:30Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified under coordinator rulings R54, R59 and R60 (the maintainer authorized unblocking every item waiting on him; this proposal blocks livespec-dev-tooling-ycahud). The filed section stated several shipped behaviours more strongly than the shipped gate-run.sh delivers. A read-only Codex review (gpt-6-astra) checked each claim against the code over four passes, and the configured ratification reviewer (opus, one read-only review authorized by R60) returned NO BLOCKERS on the exact modified bytes.

## Modifications

The section and scenarios are kept in structure and intent, with these modifications so every non-spec-first claim matches the shipped runner: (1) Launch: setsid detaches into its own session, with a nohup fallback that stays in the caller's process group; gate-start succeeds once the wrapper publishes its pid, exits 70 when neither pid nor verdict appears in its startup wait, and a command that cannot execute is a FAILED run (127); pack materialization is a best-effort attempt only when none of the pack's members is present. (2) Run record: per-user state fallback when the shared git dir is not in a conventional primary checkout; the pid is the wrapper's. (3) Terminal states are derived from the record plus a pid liveness probe; >=128 is the runner's signal-death convention. (4) A gate may itself exit 75, so callers read the printed state to tell FAILED from DIED_WITHOUT_VERDICT. (5) The five-second gate-wait return bound moves into the spec-first Idle cost bullet, which livespec-dev-tooling-ycahud owns; the shipped waiter is described as polling every five seconds. (6) The write-watch is described as sampling, with best-effort logging (missed between-sample changes, teardown loss, holder results discarded on a /proc scan error); the digest comparison is the persistent-change guarantee; observer failure isolation is not claimed. (7) Scenario 1 is restricted to exits 1-127 and reports FAILED; Scenario 3 requires a still-observable writer, a persisting change and a gate exit of 0-127, and reads gate-status after completion. (8) Coverage: the proposal said test_gate_run.py already proves the first three scenarios, but scenario rows need integration-tier tests and it does not prove gate-wait's passthrough or the 75 case, so all four scenario rows are TODO owned by livespec-dev-tooling-ycahud (whose Definition of Done asserts all four), and the contracts heading is bound to test_a_config_flip_during_the_gate_marks_the_run_and_names_the_writer.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: opus
reviewer_identity: opus
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-26T21:08:16Z
verdict: NO BLOCKERS
proposal_stem: detached-gate-runner
content_digest: 20e9b9956e6dbc27c425890b837f2474674ff864a8ba458bb220f88ce988fe64

---
proposal: docker-engine-install-guard.md
decision: modify
revised_at: 2026-10-15T22:29:52Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies the Docker engine install guard as a non-functional-requirements section with seven scenarios, so the six factory-safe guard children (livespec-dev-tooling-ubpufs, -uhu6lm, -4dqyxj, -3ieder, -mxp5ds, -bfzrq7) and the scenario-coverage child livespec-dev-tooling-4on5pg have a governing heading for the factory's Definition-of-Done gate. The text distils docs/docker-engine-guard-design.md revisions 5-8 and the binding nine-point rider on livespec-dev-tooling-xxfqqr. The coordinator (session gitops-fleet-capacity-monitoring) authorized this revise on livespec-dev-tooling-dfixhe after its own Fable review, and accepted the modifications below without a HOLD.

## Modifications

The revise's independent Fable ratification review of the filed text returned BLOCKERS on two contradictions introduced by late tidies, and both are fixed here. (1) Scope: the sentence limiting the guarded transition to a host on which no guarded unit is installed excluded the re-run after a rollback, which never removes packages; it now applies to a host whose Docker packages and state, if any, were recorded by this guard's own runs, and refuses foreign Docker rather than adopting it. (2) The rollback-phase scenario asserted that later phases run on each firing, which contradicts the clause that a rollback-partial re-firing re-runs only failing phases; it is replaced by design G8's case, a phase that kills the rollback driver on every entry, so the run stays rolling-back, each firing restarts from the top, and the fourth firing skips the exhausted phase and runs every later one. Its heading is now 'a Docker engine install guard rollback phase that keeps killing the driver does not stop the later phases'. Clarifications taken from the review's should-fixes: the rollback path's order is stated (rollback-partial MAY become rolled-back; rolled-back is final); a retried arm keeps the first recorded deadline; the rollback path and the dispatch table's rollback row cover every install-path phase, including committed and confirmed, of a run the commit marker does not name; recover runs the operation it delegates to within its own unit; and dpkg --configure recovery covers packages in any guard run's recorded intended set (rider point 4). The tests/heading-coverage.json rows are spec-first TODO debt (the H2 owned by livespec-dev-tooling-ubpufs, the seven scenarios by livespec-dev-tooling-4on5pg), and tests/heading-coverage-debt.json is regenerated mechanically.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T22:29:19Z
verdict: NO BLOCKERS
proposal_stem: docker-engine-install-guard
content_digest: 1b8469cf4c334472860174fe997d1cb99161c9f86aa7491e8d40d94c6bd3b03b

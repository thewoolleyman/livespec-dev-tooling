---
proposal: sandbox-image-gate-one-version-flavors.md
decision: modify
revised_at: 2026-11-11T23:14:50Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:ci-runtime-and-cost
---

## Decision and Rationale

Ratified with two modifications. A consumer's ci.yml names one image repository and one release version. A flavor layered on the gate flavor is allowed only for jobs that run no `just check` aggregate target. The delegated gate runs in the gate flavor and refuses a set the check fails. The gate and the check resolve images through one shared YAML reader. Measured 2026-11-11 (plan ci-runtime-and-cost, epic livespec-dev-tooling-ib3oe3). The one-image check (livespec-dev-tooling-kzhduc, livespec-dev-tooling#4191) passes seven members and fails livespec-console-beads-fabro, whose check-fuzz job uses python-rust-fuzz-v1.197.0 beside python-rust-v1.197.0. check-fuzz is not a target of console's `just check`, so the delegated gate never replays it. legacy-coordinator-agent ruled the version rule ratification (18:27Z, 18:37Z). render-gate-job.sh's grep -A1 misses an image below comment lines (livespec-dev-tooling-op67ed).

## Modifications

Decided after the independent ratification review blocked the first draft. (a) The clause now states the gate's refusal, which the first draft did not: 'When a workflow's job container images form a set the check below fails, the delegated gate MUST refuse to render the gate Job, naming each distinct image.' Without it, scenario 3's gate outcome had no clause behind it, and two implementers could disagree on whether the gate refuses or renders. (b) Scenario 3's Given used python-rust-v1.197.0 beside python-v1.197.0. Under the clause python is a dash-prefix of python-rust, so that set PASSES, and the scenario contradicted its own clause. It now uses python-rust-v1.197.0 beside python-rust-v1.196.0, two versions of one flavor, which the clause fails. Its heading-coverage reason is updated to match. (c) A second review (2026-11-11T23:12:10Z) found that the existing scenario 'a workflow declaring two container images fails its own CI' failed ANY two distinct images, which contradicts the flavor rule for scenario 1's pass set. Its heading is kept, so no H2 heading is removed in a change that grows the debt register. Its Given now names a failing set: two image repositories, or two release versions of one image repository. The heading-coverage TODO reasons now name the integration tier or above, as §'Scenario-tier coverage' requires; the 22:27Z commit gate refused the unit-tier wording. Non-blocking review notes left to the owning items (livespec-dev-tooling-kzhduc's version-rule follow-up and livespec-dev-tooling-op67ed): how the check decides that a job runs a `just check` aggregate target, and how a tag with no `v<semver>` suffix is judged.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T23:13:57Z
verdict: NO BLOCKERS
proposal_stem: sandbox-image-gate-one-version-flavors
content_digest: c075276eaea09ab6d3ce42293fc91e2990416dba60785a8d59c919bc47edb620

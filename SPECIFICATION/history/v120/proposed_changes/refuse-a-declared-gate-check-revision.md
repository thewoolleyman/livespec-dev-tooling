---
proposal: refuse-a-declared-gate-check.md
decision: modify
revised_at: 2026-11-03T10:47:01Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified and accepted. The proposal (PR #3255) supplies the spec text that work item livespec-dev-tooling-5d3cvr was held for. It states the declared gate_check_suite key under §"Delegated pre-push gate", and it requires the shared consumer aggregates to refuse a delegated suite whose final entry, the pre-push slot, names the pre-commit aggregate. The measured cause is the 2026-11-02 silent pre-push reductions in driver-codex, driver-claude and overseer (livespec-dev-tooling-jrcp4m). Adoption was checked before arming: the rule, applied to the default-branch pyproject.toml of all 11 fleet repositories that set delegation keys, refuses none, so the check can ship armed with no adopting fix first. The first independent Sonnet review found one blocker. The proposal misstated the absent-key default as the `check` recipe, while the code falls back to GATE_CHECK_SUITE_FALL_THROUGH (`install-worktree-pack`, `install-commit-refuse-hooks`, `check-pre-push`). That sentence was corrected to cover an empty array too, and a spec-first marker naming 5d3cvr was added. A second fresh Sonnet review returned NO BLOCKERS on the final bytes. The decision was made under the project's delegated revise_decision_mode, with the coordinator's direction that this owed change is not deferred.

## Modifications

In the contracts.md bullet "Declared gate check suite": (a) the sentence "When the key is absent, the gate Job runs the `check` recipe that the local fall-through runs." became "When the key is absent or declares an empty array, the gate Job runs the shared pre-push fall-through sequence `install-worktree-pack`, `install-commit-refuse-hooks`, `check-pre-push`, whose final entry is `check-pre-push`." This matches GATE_CHECK_SUITE_FALL_THROUGH and `declared or GATE_CHECK_SUITE_FALL_THROUGH` in livespec_dev_tooling/_gate_remote_assembly.py. (b) A closing spec-first marker was appended: "The refusal is spec-first: as of ratification no shipped aggregate performs it, and work item livespec-dev-tooling-5d3cvr owns the change." The scenario, the integration-tier TODO coverage row owned by 5d3cvr, and the regenerated debt register are as proposed.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T10:45:16Z
verdict: NO BLOCKERS
proposal_stem: refuse-a-declared-gate-check
content_digest: 9400a352730afbb8598ca8de9f89fe071d9ae9054b0b1bb0dc10d6ee17e6e88e

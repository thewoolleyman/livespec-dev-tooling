---
proposal: agent-hook-foreground-gate-refusal.md
decision: modify
revised_at: 2026-10-24T19:29:39Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified, then accepted. The proposal ratifies the rule work-item livespec-dev-tooling-zlhnib implements: the agent-session PreToolUse guard refuses a FOREGROUND hook-running git commit or push and names the one-call detached gate-start && gate-wait form. Without it no heading governs that item, because §"Hooks and CI" covers lefthook ordering only. Mechanism option (a) was decided by coordinator gitops-fleet-capacity-monitoring under the maintainer's standing mandate to move gate load and verdict risk off the host (2026-10-24 ~19:1xZ); the rejected alternatives (an updatedInput rewrite, a self-detaching hook, a PATH git wrapper, a timeout) are recorded on zlhnib. MODIFICATIONS, all from the independent fable ratification review: (1) the git push --dry-run/-n exemption was REMOVED, because git 2.51.0 runs the pre-push hook on a dry-run push with the same stdin as a real push, so exempting it would leave the full gate in the foreground (the failure the section exists to prevent); its scenario was replaced by one for a repository with no installed commit hook, an exemption that genuinely runs no hook. (2) The four heading-coverage TODO reasons now name the owed integration-tier test, as the reason predicate requires; the debt register was regenerated, never hand-edited. (3) The intro is narrowed to what the guard covers. The targeting sentence states that a command without -C targets the session's working-directory repository. The background bullet no longer claims continuity with today's two-step hint. The scenarios place the session in the repository. Non-blocking notes deferred to zlhnib's implementer: hook-path resolution for linked worktrees and core.hooksPath (covered by 'cannot establish -> refuse'); gate-start runs from the justfile directory, so the hint may want git -C "$PWD"; a fresh clone without the pack has every commit refused until the hint's install line is run. A placement note for the pending detached-gate-runner proposal: it also inserts before §"Composite Actions wire contract" and will need re-anchoring. Ratification: fable, separate read-only reviewer, NO BLOCKERS on these exact bytes. Decision mode: delegated (.livespec.jsonc spec_governance).

## Modifications

Removed the git push --dry-run/-n exemption and replaced the dry-run scenario with a no-installed-commit-hook scenario; reworded all four heading-coverage TODO reasons to name the owed integration-tier test and regenerated the debt register; narrowed the intro scope, stated the working-directory default for targeting, dropped 'continue to' from the background bullet, and placed the session in the repository in scenarios 1 and 3.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-24T19:28:38Z
verdict: NO BLOCKERS
proposal_stem: agent-hook-foreground-gate-refusal
content_digest: 1ae51a446eb0b0fa2630157e86814de9b0ed80e65cfe7c12f3ff604d3913560f

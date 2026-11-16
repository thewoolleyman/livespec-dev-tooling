---
topic: queue-required-every-org-repo
author: claude-sonnet-5-5
created_at: 2026-11-16T18:38:01Z
---

## Proposal: queue-required-covers-every-livespec-ai-repository

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Make the branch_protection_alignment check treat every repository owned by the livespec-ai organization as queue-required, replacing the two-name QUEUE_REQUIRED_REPOSITORIES constant, and keep the rule that a repository cannot opt itself out.

### Motivation

Maintainer ruling on stale-base-merge-options epic livespec-dev-tooling-xowhol, 2026-11-16: "No I think we should turn on the merge queue for every repo in the org. Why wouldn't we?" The two-name constant (livespec-dev-tooling, livespec-orchestrator-beads-fabro) leaves ten organization repositories merging without the queue, so a stale-base merge is possible there. Carrier work item: livespec-dev-tooling-frkuef. In-flight survey: pending proposal SPECIFICATION/proposed_changes/merge-group-tree-equality-skip.md (branch spec/merge-group-tree-equality-skip) is independent and aligned (align). Open spec PRs on the merge queue, livespec-dev-tooling#4810 (a merge-queue rebuild cancels) and livespec-dev-tooling#4822 (incident-merge principal outside the queue), touch queue behavior but not the QUEUE_REQUIRED_REPOSITORIES rule; treated as align.

### Proposed Changes

1. In SPECIFICATION/contracts.md section 'branch_protection_alignment check', replace the bullet that begins 'The check reads the repository owner's `type`' with: 'The check reads the repository owner from `repos/{owner}/{repo}`. The repository is QUEUE-REQUIRED when the owner is the organization `livespec-ai` (owner `type` is `Organization` and owner `login` is `livespec-ai`). Every repository of that organization is queue-required; there is no per-repository name list. At the time of this revision those repositories are fleet-image-mirror, livespec, livespec-console-beads-fabro, livespec-dev-tooling, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-orchestrator-beads-fabro, livespec-orchestrator-git-jsonl, livespec-overseer, livespec-runtime and livespec-website. The `QUEUE_REQUIRED_REPOSITORIES` constant of `livespec_dev_tooling.checks.branch_protection_alignment` is removed; the owner test replaces it. The rule is deliberately not consumer configuration, because a repository must not be able to opt itself out of the queue. It changes only with a livespec specification revision. A queue-required repository with no `merge_queue` rule among its active rulesets' rules for the default branch FAILS (exit `4`, `failure_mode` `merge_queue_absent`).' Keep the rest of the bullet list unchanged, and update any sentence in that section that says the set is two repositories. The livespec core NFR section 'Merge queue on organization-owned repositories', which still requires the queue only for livespec-dev-tooling and livespec-orchestrator-beads-fabro and lets other repositories opt in, is changed by the COMPANION propose-change filed in the livespec repository (topic merge-queue-on-every-organization-owned-repository); this repository's revise cannot change it, and the two ratify together.

2. In SPECIFICATION/scenarios.md, update the scenario '## Scenario: branch_protection_alignment fails a queue-required repository whose master does not require the merge queue' (heading unchanged, so tests/heading-coverage.json needs no new row) to:

Given a repository owned by the organization livespec-ai, such as livespec-website

And no active ruleset on its default branch carries a merge_queue rule

When branch_protection_alignment runs with an admin-scoped token

Then it exits 4 with one fail finding whose failure_mode is merge_queue_absent

And the same holds for each of the twelve livespec-ai repositories named in the contract, with no per-repository name list consulted

And a repository that sets configuration to opt out of the queue is still queue-required.

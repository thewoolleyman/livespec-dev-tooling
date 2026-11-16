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

Make the branch_protection_alignment check treat every repository owned by the livespec-ai organization as queue-required, replacing the two-name QUEUE_REQUIRED_REPOSITORIES constant, and keep the rule that a repository cannot opt itself out, with ONE named exception, livespec-website (see below).

### Motivation

Maintainer ruling on stale-base-merge-options epic livespec-dev-tooling-xowhol, 2026-11-16: "No I think we should turn on the merge queue for every repo in the org. Why wouldn't we?" The two-name constant (livespec-dev-tooling, livespec-orchestrator-beads-fabro) leaves ten organization repositories merging without the queue, so a stale-base merge is possible there. Carrier work item: livespec-dev-tooling-frkuef. In-flight survey: pending proposal SPECIFICATION/proposed_changes/merge-group-tree-equality-skip.md (branch spec/merge-group-tree-equality-skip) is independent and aligned (align). Open spec PRs on the merge queue, livespec-dev-tooling#4810 (a merge-queue rebuild cancels) and livespec-dev-tooling#4822 (incident-merge principal outside the queue), touch queue behavior but not the QUEUE_REQUIRED_REPOSITORIES rule; treated as align.

### Proposed Changes

1. In SPECIFICATION/contracts.md section 'branch_protection_alignment check', replace the bullet that begins 'The check reads the repository owner's `type`' with: 'The check reads the repository owner from `repos/{owner}/{repo}`. The repository is QUEUE-REQUIRED when the owner is the organization `livespec-ai` (owner `type` is `Organization` and owner `login` is `livespec-ai`). Every repository of that organization is queue-required EXCEPT the one named exception below; there is no list of queue-required repositories. At the time of this revision the queue-required repositories are fleet-image-mirror, livespec, livespec-console-beads-fabro, livespec-dev-tooling, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-orchestrator-beads-fabro, livespec-orchestrator-git-jsonl, livespec-overseer and livespec-runtime. THE ONE EXCEPTION is `livespec-website`: its maintainer publishes edits directly from the GitHub web editor, which a required status check or a merge queue refuses ("Required status check ci-green is expected. Changes must be made through the merge queue"), so a direct commit to its default branch is a hard requirement of that repository (maintainer ruling, relayed by throughput-plans-coordinator 2026-11-16: "Livespec website is not unable to commit directly from changes to main. This is a hard requirement of that repo, it's an exception to the rule, so I can publish edits directly from the github website."). The exception is a module-level constant of `livespec_dev_tooling.checks.branch_protection_alignment`, `QUEUE_EXEMPT_REPOSITORIES`, holding exactly `livespec-website`; for a repository named in it the check runs NONE of its protection gates: it prints one informational finding naming the exemption and exits `0` without reporting `merge_queue_absent`, `protection_absent`, `enforce_admins_disabled` or any other protection-dependent failure mode, because the exempt repository's default branch is deliberately unprotected so that its maintainer can publish edits from the GitHub web editor. No check, converge or ruleset write may add a required-status-check, branch-protection or merge-queue rule to it. The `QUEUE_REQUIRED_REPOSITORIES` constant of `livespec_dev_tooling.checks.branch_protection_alignment` is removed; the owner test replaces it. The current code (`_graded_exit_code` in `_branch_protection_merge_queue.py`) tests only owner `type == "Organization"`; the revise-driven code item adds the `login == "livespec-ai"` test from the same owner object. It replaces the frozenset membership test (`QUEUE_REQUIRED_REPOSITORIES` at `branch_protection_alignment.py:188`, passed as `queue_required_names=` at line 491 and tested at `_branch_protection_merge_queue.py:221`) and updates `tests/livespec_dev_tooling/checks/test_branch_protection_merge_queue.py` (lines 4 and 499) and the `ci.yml` comment that cites the constant. The rule is deliberately not consumer configuration, because a repository must not be able to opt itself out of the queue, and the exemption is named in the specification, never read from consumer configuration. Both constants change only with a livespec specification revision. A queue-required repository with no `merge_queue` rule among its active rulesets' rules for the default branch FAILS (exit `4`, `failure_mode` `merge_queue_absent`).' Keep the rest of the bullet list unchanged, and update any sentence in that section that says the set is two repositories. The livespec core NFR section 'Merge queue on organization-owned repositories', which still requires the queue only for livespec-dev-tooling and livespec-orchestrator-beads-fabro and lets other repositories opt in, is changed by TWO companion propose-changes in the livespec repository: topic merge-queue-on-every-organization-owned-repository (merged as livespec#3272) and its follow-up topic merge-queue-exception-for-livespec-website (livespec#3274), which qualifies it with the one named exception. This repository's revise cannot change that NFR text; the three ratify together, and this proposal is not revised until the follow-up exists on livespec master.

2. In SPECIFICATION/scenarios.md, update the scenario '## Scenario: branch_protection_alignment fails a queue-required repository whose master does not require the merge queue' (heading unchanged, so tests/heading-coverage.json needs no new row) to:

Given a repository owned by the organization livespec-ai, such as livespec-runtime

And no active ruleset on its default branch carries a merge_queue rule

When branch_protection_alignment runs with an admin-scoped token

Then it exits 4 with one fail finding whose failure_mode is merge_queue_absent

And the same holds for each of the eleven queue-required livespec-ai repositories named in the contract, with no list of queue-required repositories consulted

And a repository named livespec-website, the one exception, whose default branch is unprotected and carries no ruleset, passes the check: it exits 0 with one informational finding and reports none of merge_queue_absent, protection_absent or enforce_admins_disabled

And a repository that sets configuration to opt out of the queue is still queue-required.

---
proposal: pre-push-accepts-a-same-tree-delegated-pre-commit-pass.md
decision: modify
revised_at: 2026-11-11T00:35:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in substance, per the coordinator ruling of 2026-11-10 (maintainer priority 3a): in a repository that sets both delegated_gate and delegated_pre_commit, a passing DELEGATED full pre-commit aggregate on tree T, whose gate Job reported its member list and whose verdict arrived on a clean tree with git write-tree unchanged, stands in at pre-push for the members that Job reported as run and passed when the pushed HEAD tree is T. Every member the evidence does not name, every world-reading member and every authorization-reading member still runs on the pushing host, and a LOCAL pre-commit pass never qualifies, so the pre-commit hook's local just check stops writing the green token. This removes a second full-suite run per hand-landed Green amend (about 37 minutes per Green commit in livespec-orchestrator-beads-fabro, measured on a gmktec gate: check-per-file-coverage 2,222 s). The independent reviewer answered legacy-coordinator-agent's named question (confirm Job J's verdict and member list against the cluster's record) as NOT a gate weakening and recommended not adopting it: today's green token is an equally local file, the Job's retention is one hour (ttlSecondsAfterFinished) so the record is usually gone by push time, and the member list lives only in pod logs. Per the coordinator's rule it is therefore not adopted here and is reported as a follow-up. The pre-merge doctor LLM phase found that the filed Explicit local route sentence bound every repository, so non-delegating repositories and factory sandboxes would lose pre-commit-to-pre-push green token reuse and run the full aggregate twice per push. legacy-coordinator-agent's 'a local pass never qualifies' ruling was scoped to the new delegated reuse path, so the coordinator-reported decision narrows the sentence inside this revise to repositories that set both delegated_gate and delegated_pre_commit, leaving every other repository's local token behaviour unchanged.

## Modifications

Against the filed text: (1) in Delegated pre-commit aggregate, Evidence for the pre-push gate, the doc-only and Red-leg subsets are grounded in the hook's own selections (the reduced aggregate selected when no .py file is staged, and the scoped selection made for a Red commit), and the bullet names work item livespec-dev-tooling-73ocxb; (2) in Delegated pre-push gate, Same-tree delegated pre-commit verdict, 'As of filing' reads 'As of ratification', and the filed instruction that the ratifying revise name the owning work item is replaced by naming livespec-dev-tooling-73ocxb for this repository's change, with the livespec-orchestrator-beads-fabro green-token-scope.sh adoption a separate item in that repository; (3) the sentence added to Explicit local route binds only a repository that sets both delegated_gate = true and delegated_pre_commit = true, and states that in every other repository the pre-commit hook's local aggregate records the green token as before and pre-push reuse of it is unchanged (decision by the owning seat, reported to legacy-coordinator-agent, on the pre-merge doctor finding); (4) a seventh scenario states that a repository without both keys keeps pre-commit-to-pre-push token reuse. The six filed scenarios are as filed.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T00:32:08Z
verdict: NO BLOCKERS
proposal_stem: pre-push-accepts-a-same-tree-delegated-pre-commit-pass
content_digest: 15b22bdd1321a365d73da09615b04a50f90b20f4718332f4e83eee6a4591ca77

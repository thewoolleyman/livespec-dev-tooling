---
proposal: a-repository-declares-its-gate-queue.md
decision: modify
revised_at: 2026-11-17T13:19:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Modified under delegated decision mode, carried in this pass at the gate-job-resources seat's request (2026-11-15). The proposal records legacy-coordinator-agent's A+C ruling for plan gate-job-resources item (i): a consuming repository routes its full-size gate Jobs to a declared gate LocalQueue so a 10-cpu gate is not starved inside gates-cq. The first independent sonnet review returned a BLOCKER: Lane capacity read its flavors only from cluster-queue-gates.yaml (the one packaged manifest) while the proposal let gate_queue bind to a ClusterQueue in any committed kueue manifest, so a consumer's gate client could never compare or check a queue declared elsewhere. The gate-job-resources seat chose fix (b), and a fresh sonnet review of the final bytes returned NO BLOCKERS.

## Modifications

(1) Every LocalQueue and ClusterQueue that a gate_queue may name MUST be declared in ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml; the gate ClusterQueue is the one the declared LocalQueue is bound to in that file, and a gate_queue naming no LocalQueue in that file is refused. (2) 'the gates-cq flavors' becomes 'the gate ClusterQueue's flavors' in the parse-failure sentence. (3) The no-refusal-on-missing-file sentence names none of gate_cpu, gate_memory and gate_queue, matching the comparison trigger. (4) The Spec-first sub-bullet names livespec-dev-tooling-xymcj6 as implementer of the gate_queue rules and owner of their two scenarios' tests. (5) Both scenarios' Given clauses name cluster-queue-gates.yaml instead of 'the committed Kueue manifests'.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-17T13:18:45Z
verdict: NO BLOCKERS
proposal_stem: a-repository-declares-its-gate-queue
content_digest: b77315134156d0a80192d79f2781830874edddcf8235409a185a899a045e976a

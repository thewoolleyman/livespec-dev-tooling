---
proposal: factory-sandbox-loss-drill.md
decision: modify
revised_at: 2026-11-12T09:24:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The proposal's intent and every fence legacy-coordinator-agent set on 2026-11-11 are accepted: a committed playbook applied from vps, a confirmation naming the k3s server, exactly one pod identified by a named Fabro run id in a factory namespace, refusal of any pod that is not that run's sandbox, the pod deleted and nothing else, and printed UTC times, so the orchestrator's resume-onto-a-re-acquired-sandbox proofs (bd-ib-dpsiwz, bd-ib-ljw2xg) gain a committed route. Two pre-review doctor passes walked the draft through live code (sandbox-driver-kubernetes pod.rs, sandbox.rs, labels.rs; petri run.rs; the gmktec host_vars; the sibling container-termination drill). The first found one blocker: the sandbox provider re-creates a resumed sandbox's pod under the SAME name (sandbox.rs start_inner), so the proposal's 'no longer lists that pod' wait could time out and fail on exactly the outcome the drill exists to produce. It also found that the Fabro servers and the sandbox provider are systemd units and plugin binaries, not pods, so 'a Fabro server pod, a sandbox provider pod' named nothing checkable, and that the run label, the sandbox mark and the namespace were undefined. The modifications fix each; the second pass found two nits, both applied. The independent sonnet review returned NO BLOCKERS on the exact bytes. No design record is contradicted: the container-termination drill's throwaway-namespace rule is left unchanged and explicitly does not govern this drill.

## Modifications

1. The run label and the sandbox mark are named literally: pods are listed by `petri.run` equal to the run id, compared exactly as Fabro prints it without case folding, and the one pod must carry `sandbox-driver-kubernetes/sandbox`; the example of an unlabelled pod is a workspace cleanup pod, replacing the Fabro server and provider pods that do not exist as pods. 2. The delete carries a UID precondition and the wait is on the UID: a same-named pod with a new UID is the provider's re-created sandbox, ends the wait, is never deleted, and has its UID printed; a still-listed UID after the timeout, or a refused precondition (naming both UIDs), exits non-zero without another delete. 3. The run id must be non-empty and a valid Kubernetes label value; an unconfirmed application reads nothing, changes nothing and exits 0, matching the sibling drill. 4. The namespace must be `factory` or `factory-mi-homelab` (the factory namespaces the spec already names). 5. A run holding more than one sandbox pod at once, one per lease, is refused by design. 6. The printout adds the pod's UID and states the delete time and the first-seen-gone time. 7. The new paragraph restates that the drill is committed and applied from vps with just ansible-apply and forbids a hand delete; the Scope list is reworded to three items. 8. A spec-first sentence names livespec-dev-tooling-5wybjq as the owner. 9. The scenario keeps its heading and is aligned with the clause (UID wait, printout, exit 0 when unconfirmed, the namespace and unlabelled-pod refusals). 10. Post-review, at legacy-coordinator-agent's PASS-WITH-ONE-FIX grade of livespec-dev-tooling#4295 (fix (b)): the clause and the scenario add the preserve-before-disrupt refusal, so the drill exits non-zero before any cluster write unless an operator-named origin ref carrying the run's committed tree has a non-empty diff against its merge-base with the repository's default branch. That sentence and scenario line post-date the ratification review below, whose digest binds the bytes before them.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T09:23:07Z
verdict: NO BLOCKERS
proposal_stem: factory-sandbox-loss-drill
content_digest: d50cc86ed617b71ace6fad59b0cdbc533517f358468a425e4498bbb8357f3825

---
proposal: k3s-window-drain-committed-evacuate.md
decision: modify
revised_at: 2026-11-13T19:47:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-2:homelab-k8s-worker-nodes
---

## Decision and Rationale

Accepted as written (graded PASS by legacy-coordinator-agent). It states the committed node hold, the evacuation play and the lost-node play that ansible/k3s-window-drain.yml already implements (livespec-dev-tooling#4404), and adds their four scenarios. No existing sentence changes. It was then modified in wording only, by the doctor's LLM-driven objective pass, run on this cut on legacy-coordinator-agent's grade of livespec-dev-tooling#4562 (2026-11-13): two contradictions and three ambiguities in the accepted text are resolved, and no behaviour the landed play has is changed.

## Modifications

All in non-functional-requirements.md §"Consent-gated pool-node disruption". In "**A node hold is a cordon, and it ends only by a confirmed uncordon.**": after "puts no load anywhere." one sentence is added naming the cordon's single confirmation, and the acceptance of a registered Node with no inventory entry, as the stated exceptions to "**Committed and consent-gated.**", which would otherwise contradict them; "A hold MUST NOT be lifted" and "the end of a hold" become "A node hold" and "a node hold"; and two sentences are added: the node-loss drill's configured hold is a duration and not a node hold, and a node hold does not survive a re-registration of the Node, so whoever holds the node re-applies it. In "**Clearing a lost node force-deletes the pods stranded on it, and refuses a Ready node.**": "A pod marked for deletion is cleared whatever owns it" gains "except a DaemonSet's pod and a pod in a factory namespace", which the same paragraph already forbade deleting; and "an unowned CI runner pod" becomes "a CI runner pod, whether an EphemeralRunner owns it or no controller does". No scenario changes.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T19:45:58Z
verdict: NO BLOCKERS
proposal_stem: k3s-window-drain-committed-evacuate
content_digest: d9c18c43436616d45ff3eb6b4bb0a57bd99c101205e36d65ad009f0822410195

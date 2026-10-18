---
proposal: docker-engine-guard-interfaces-preexisting-bridge.md
decision: accept
revised_at: 2026-10-18T03:20:21Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:petri-factory-on-gmktec
---

## Decision and Rationale

Accepted under the maintainer's 2026-10-18 direction to get the factory running and the 2026-10-17 petri-factory-on-gmktec ruling that a spec fix for a measured defect blocking plan work is session-ratifiable; coordinator gitops-fleet-capacity-monitoring acked this route (R140). The Interfaces probe failed every observation window on a live k3s CI node: the first attended gmktec-xubuntu converge (gate 20261018T030444Z-3778031, run r2026101803080120e0) rolled back on 18 new veths whose master is k3s's cni0, CI pods started during the window. New veths on a bridge the snapshot recorded are now allowed; Docker's own veths on docker0 and any other new interface still fail. This is the interface counterpart of the Firewall probe's existing KUBE-*/FLANNEL-* carve-out. Implementation is owned by livespec-dev-tooling-eaigbj (guard child 16). Independent read-only Fable review: NO BLOCKERS; its two minor notes (the bridge is attested by recorded name, and a bridge recreated under a recorded name would pass, which the k3s-witness probe covers) need no text change. The proposal's front-matter created_at was corrected to its real write time before the revise; no content changed.

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
reviewed_at: 2026-10-18T03:20:19Z
verdict: NO BLOCKERS
proposal_stem: docker-engine-guard-interfaces-preexisting-bridge
content_digest: 9f5b0e4f3335e928ab234b128121d369a90ee0a39491f89e40cf57b2b2837ffc

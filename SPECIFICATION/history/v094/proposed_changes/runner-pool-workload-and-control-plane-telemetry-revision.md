---
proposal: runner-pool-workload-and-control-plane-telemetry.md
decision: modify
revised_at: 2026-10-24T16:32:37Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified, then accepted. The proposal's intent stands: the maintainer direction relayed on livespec-dev-tooling-dfixhe at about 16:2xZ on 2026-10-24 ("observe everything about Kubernetes that is necessary and follows best practices to manage it") needs a governing heading for workload and control-plane health, which v090 §"Runner-pool node telemetry" does not provide. MODIFICATIONS, all from the independent fable ratification review: (1) DATASTORE CORRECTED. The proposal assumed embedded etcd. The cluster's datastore is kine over SQLite on the 2 GiB datastore-tmpfs mount at /var/lib/rancher/k3s/server/db (state.db plus WAL, k3s server without --cluster-init, verified read-only on poweredge-xubuntu 2026-10-24). /readyz prints 'etcd ok' only because kine answers the API server's etcd client. Datastore health therefore requires apiserver_storage_size_bytes, the mount's used and total bytes, and etcd_request_duration_seconds (the SQL round trip under kine), with an etcd-cutover revision clause. (2) The cluster-state dead-man is defined, with a 20-minute window, and every other emitter, the readiness probe in particular, must share its path or carry its own dead-man. (3) The conditional scenario step is split into gradable scenarios, and a quota/Kueue scenario is added (four scenarios in all). (4) Crash looping is read from the CrashLoopBackOff waiting reason, not a restart delta. (5) Event coverage is bounded to what the API server serves while the emitter runs, and the pending-pod join is named. (6) Non-collector emitters must be converged by ansible/ci-pool.yml. (7) The read-only identity may get /metrics. (8) Cluster-controller availability and PersistentVolumeClaim phase are added. SUPERSEDED FOLLOW-UP TEXT: the proposal's spec_commitments impl_followups still describe etcd; those descriptions are superseded by this record. k3s-control-plane-telemetry is now: probe /readyz?verbose, read apiserver_storage_size_bytes and etcd_request_duration_seconds from /metrics with the read-only identity, report the datastore-tmpfs mount's used and total bytes, and move ci-pool-attributed-gauges' ClusterQueue read off the admin kubeconfig onto the read-only identity with .status.flavorsUsage. Ratification: fable, separate read-only reviewer, NO BLOCKERS on these exact bytes. Non-blocking notes deferred to the child items: trigger 5's single-tick etcd-check clause may flap (align it to 3 minutes); the p99 latency calculation may need a bucket-share fallback; Cluster controllers lacks its own scenario; the dead-man drill must silence the k8s_cluster pipeline alone. Decision mode: delegated (.livespec.jsonc spec_governance), under the maintainer's standing authorization relayed by the coordinator.

## Modifications

Section and scenarios rewritten per the ratification review: kine/SQLite datastore signals, a windowed dead-man covering every emitter, gradable scenarios plus a quota/Kueue scenario, CrashLoopBackOff, bounded event wording with an explicit join, converge rule for non-collector emitters, /metrics access, controller availability and PVC phase.

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
reviewed_at: 2026-10-24T16:29:41Z
verdict: NO BLOCKERS
proposal_stem: runner-pool-workload-and-control-plane-telemetry
content_digest: b7db56bd2b2a1b95316f10e6381a99f6c751b998242637b344c9325faf6b6cf2

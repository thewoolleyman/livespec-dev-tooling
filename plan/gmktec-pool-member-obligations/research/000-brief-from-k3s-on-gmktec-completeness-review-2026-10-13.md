## The maintainer's statement of what done means

"All of the follow-up work items, existing or new, that you create should be living under epics and plans in their respective repos, either existing plans or new ones that you create. Then we will list what they are and decide whether we want to start sessions to work them or not." and "Go ahead and draft the proper definition of done in them with the context that you already have." (maintainer, 2026-10-13, on archiving the livespec repo plan k3s-on-gmktec-for-vps-usage, epic livespec-sab5gn)

## Definition of Done assertions derived from that statement

- A telemetry collector listens on gmktec-xubuntu's own pod-network gateway, provisioned from committed source by `just ansible-apply ansible/ci-pool.yml`, and a cache span emitted by a CI job pod running on gmktec-xubuntu is accepted by it and forwarded to Honeycomb.
- A runner scale set whose pods schedule only onto gmktec-xubuntu is provisioned from committed source, and a proving job routed to it by name runs on gmktec-xubuntu and finishes with a passing result.
- After both are provisioned, `just ansible-drift ansible/ci-pool.yml` reports zero changes, and after an unattended poweredge-xubuntu reboot through `just ansible-apply ansible/reboot-ci-server.yml` the collector and the scale set are serving again with no operator command run on any host.

Origin: the livespec repository's plan `k3s-on-gmktec-for-vps-usage` (epic `livespec-sab5gn`, livespec ledger), archived 2026-10-13. Its independent completeness review (evidence id k3s-on-gmktec-completeness-2026-10-13, recorded 2026-10-13T07:41:06Z) found two R5/R7 obligations that plan dropped without a carrier or hand-off; this plan holds them. The assertions were drafted by the archiving session (claude:plan-k3s-session-ae9c7217) and are open to the maintainer's revision before work starts.

## 1. gmktec-xubuntu has no telemetry collector on its own pod-network gateway (livespec-dev-tooling-xnie)

The CI cache-span emitter derives its collector endpoint from the pod's own default gateway (`ci-runner/k3s/phase2/cache-telemetry/ci-cache-span.sh publish-endpoint`), so each node needs a collector on its own cni0 gateway. poweredge-xubuntu has one (10.42.0.1:4319). flannel gives gmktec-xubuntu 10.42.1.1, and the reviewer's read-only check on 2026-10-13 found nothing listening there and `otelcol-contrib` inactive. gmktec was opened to CI on 2026-10-10, so cache telemetry from every CI job that ran there since has been dropped. livespec-dev-tooling-xnie (filed 2026-09-08 as an R5 precondition) records the full measurement and is this plan's first child.

## 2. gmktec-xubuntu cannot be targeted on its own

The livespec specification requires every runner-pool member to be separately addressable, and the archived plan's R5 called for a `gmktec-xubuntu-k3s` runner scale set and a proving job routed through it. No such scale set exists live or on livespec-dev-tooling master; gmktec's CI participation was proven by temporarily blocking poweredge from taking jobs instead (archived plan assertion 1 was proven by observing a backlog spread across both nodes). The work item filed with this plan carries it.

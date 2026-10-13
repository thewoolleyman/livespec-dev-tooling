## The maintainer's statement of what done means

"All of the follow-up work items, existing or new, that you create should be living under epics and plans in their respective repos, either existing plans or new ones that you create. Then we will list what they are and decide whether we want to start sessions to work them or not." and "Go ahead and draft the proper definition of done in them with the context that you already have." (maintainer, 2026-10-13, on archiving the livespec repo plan k3s-on-gmktec-for-vps-usage, epic livespec-sab5gn)

## Definition of Done assertions derived from that statement

- The k3s server on poweredge-xubuntu stores cluster state in embedded etcd rather than kine over SQLite, provisioned from committed source by `just ansible-apply ansible/ci-pool.yml`, and `just ansible-drift ansible/ci-pool.yml` then reports zero changes.
- The embedded etcd runs with an explicit backend quota, a compaction interval read back from the live server, a periodic defragmentation timer, and snapshots that are either disabled or written outside the tmpfs, each provisioned from committed source.
- After an unattended poweredge-xubuntu reboot issued through `just ansible-apply ansible/reboot-ci-server.yml`, gmktec-xubuntu returns to Ready, untainted and advertising its churn-slot capacity, and the churn-slot quotas and gate credential Secrets are restored, with no operator command run on any host.
- During a fleet CI backlog on the etcd datastore, runner pods run on both poweredge-xubuntu and gmktec-xubuntu and the jobs that run on gmktec-xubuntu finish with a passing result.
- No monitoring query, trigger, board or alert in the fleet keys on the SQLite-era `Slow SQL` journal signature, and an etcd-era datastore-health signal that replaced it reads healthy against the live server.

Origin: the livespec repository's plan `k3s-on-gmktec-for-vps-usage` (epic `livespec-sab5gn`, livespec ledger), archived 2026-10-13 after all six of its Definition-of-Done assertions were proven live and independently replayed. Its research notes move to `plan/archive/k3s-on-gmktec-for-vps-usage/research/` in the livespec repository. This plan was created at that archive to hold work the archived plan deferred, per the maintainer's direction quoted in the Definition of Done statement. The assertions were drafted by the archiving session (claude:plan-k3s-session-ae9c7217) from the archived plan's recorded scope and are open to the maintainer's revision before any child is admitted.

## Scope, as the archived plan recorded it

Carriers R6 and R7 of the archived plan, deferred by its 2026-10-11 scope event: "R6 (embedded-etcd datastore move and its tmpfs maintenance set) and R7 (topology-bound monitoring rewrite). The maintainer adopted the Definition of Done without them on 2026-10-11 (the broader option was declined). Reconsidered at archive time, where they are handed to a named follow-up plan."

From the archived plan's research note 006 (livespec repository): R6 replaces "the kine-over-SQLite datastore on the 2 GB tmpfs with k3s's embedded etcd, for control-plane stability under write churn rather than for speed, together with the maintenance set that etcd on a tmpfs requires — compaction interval verified, the snapshot cron disabled or pointed at durable storage, an explicit backend quota, a periodic defragmentation timer — and the monitoring rewrite that follows, because seventeen files across two repositories key on the SQLite-era `Slow SQL` journal signature that etcd does not emit." R7 is a discipline rather than a deliverable: monitoring changes in the same change as the topology change it follows, so its remaining obligation is R6's monitoring rewrite; it is folded into this plan rather than given its own.

Research note 001 of the archived plan attached a measurement rule to R6's ordering: any `Slow SQL` line observed in a fleet-wide backlog at the current admission capacity is a signal to start R6. Nothing watches for it.

## Constraints learned on the archived plan

- The datastore is tmpfs, so every poweredge boot rebuilds the cluster from empty: ServiceAccounts, their tokens, the node-status and gates credentials are re-minted by `converge-ci-stack.service`, and the agent and vps credentials self-refresh on first rejection. Any datastore change must keep that unattended recovery (archived plan assertion 2).
- The only sanctioned reboot is `just ansible-apply ansible/reboot-ci-server.yml -e ci_server_reboot_confirm=poweredge-xubuntu` (livespec-dev-tooling PRs #2409, #2412). The Driver's `fleet_host_guard.py` refuses hand changes to fleet hosts.
- The boot converge must not need the internet (livespec-dev-tooling-tb2az6, PR #2399): Kueue and ARC artifacts are host-held.
- Where the Honeycomb triggers and boards live as code was ruled to be the otel-collector repository, which carries no livespec ledger; work landing there is outside the factory.

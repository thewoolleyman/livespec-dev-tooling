<!-- Captured by throughput-plans-coordinator on the maintainer's word, 2026-11-17 ~10:0xZ, and landed by the stale-base-merge-options seat (epic livespec-dev-tooling-xowhol). Maintainer direction, verbatim: "Write this to the retrospective as well. This is a good one, one for the record books" and "The retrospective is on the stale merge base options plan". Source text below is unaltered. -->

# Retro: a repro run waited on one node while four nodes had room, 2026-11-17

Captured by throughput-plans-coordinator on the maintainer's word, 2026-11-17 ~10:0xZ: "Write this to the retrospective as well. This is a good one, one for the record books". Before that he asked, verbatim: "Why would anything be blocked on a slot on just HP when we literally have five fucking Kubernetes worker nodes?", and then: "Why are you so fucking stupid? Why can't you realize these sorts of things on your own?"

## What happened

All times UTC.

- 07:14Z: this seat read the cluster's nodes. gamingpc-xubuntu 100%, gmktec-xubuntu 66%, poweredge-xubuntu 25%, hp-xubuntu 0%, macbook-m4-max-homelab-worker 0% (tainted). poweredge had about three quarters of its 72 cores free.
- ~07:5xZ: gate-job-resources applied the repro lane (livespec-dev-tooling-cwrg3v) through its single converge. It gave the repro queue (`gates-repro-cq`) quota on ONE node: `gates-repro-hp-flavor` at 5 cpu / 8Gi. The other three repro flavors stayed at 0. hp was chosen because it was idle after CI moved off it.
- 08:05Z: the first identical-image repro (release-please branch, run 20261117T080502Z-1740961) took hp's only unit. It found the cause of the release-branch slowdown: the flake-retry plugin re-ran a git diff, two git show reads and four TOML parses for every collected test.
- 08:17Z: the master contrast repro (run 20261117T081729Z-1890567) was submitted. gate-job-resources told this seat it "queues behind the first if it cannot fit". This seat accepted that, and had itself written "if the second can't fit, queue it, but don't wait to submit".
- ~08:47Z: the master contrast run waited 1800 s for admission, was abandoned, and never ran. The release-vs-master comparison was missing for about 1.5 h.
- 09:46Z: the master run was relaunched on hp, after the first run ended.
- ~09:5xZ: the maintainer asked the question above. Only then was quota routed to poweredge and gmktec.

## Cause

1. **The lane was built with one node's worth of capacity.** The repro queue's design has a flavor per node, but only one flavor got quota. Nothing about the work required hp: any amd64 node runs the identical image. A node pin is only needed for a node-specific failure.
2. **The coordinator accepted a queue as normal.** This seat had the node read showing idle capacity and the report saying a job would queue, and never compared them. STRANDED-CAPACITY (coordinator-duties §10) covers "a binding cap beside an idle node". This was that case, on a new queue the tick did not look at.
3. **No mechanical check watched this queue.** `scripts/coordinator/fleet-utilization.sh` STRANDED-CAPACITY reads factory and CI caps, not Kueue queues whose quota sits on one node while other nodes are idle.

## Fixes and owners

- **Arm repro quota on more nodes.** poweredge-xubuntu and gmktec-xubuntu each get one 5 cpu / 8Gi repro unit through the committed values and the single converge (revert: set back to 0). Owner: gate-job-resources (livespec-dev-tooling-ukoeah), with the cwrg3v helper.
- **`just gate-repro` picks any node with free repro quota by default.** It renders no nodeSelector unless `--node` is given; `--node` stays for node-specific failures. Owner: gate-job-resources.
- **Mechanical check.** STRANDED-CAPACITY in `scripts/coordinator/fleet-utilization.sh` (and its top5 line) flags any Kueue ClusterQueue with pending workloads whose admitting flavors sit on one node while another node reads idle. Red case: gates-repro-cq on 2026-11-17. Owner: legacy-coordinator-agent (epic livespec-dev-tooling-6tgd2z); item livespec-dev-tooling-war5ld.
- **Coordinator tick, until the check ships.** Every report that work is "queued", "waiting for admission" or "behind" something is checked against idle nodes before it is accepted. A queue with only one node behind it is fixed, not accepted. Owner: this seat.
- **Rule.** No repro or diagnostic run serializes on one node. legacy-coordinator-agent ports it into `.ai/coordinator-duties.md` in its next docs PR.

## Lesson

A capacity decision made for one reason (hp was idle) set a limit for a different purpose (all repro work). The coordinator held both facts and did not compare them. A queue is a capacity read: before accepting "it will wait", ask what it is waiting on and whether that resource is actually scarce.

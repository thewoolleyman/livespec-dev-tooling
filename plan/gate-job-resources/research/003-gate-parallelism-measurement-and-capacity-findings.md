# 003 — gate parallelism measurement, and two capacity findings

Recorded 2026-11-12 by the gate-job-resources seat (session 2c835b). This note
holds three things the handoffs said to record at the next repo change:

1. the measurement for plan assertion 4;
2. the gates-hp-flavor STRANDED read, where admission counts requests rather
   than use;
3. the gamingpc-xubuntu root cause behind livespec-dev-tooling-ddy5xu.

## 1. Assertion 4: orchestrator coverage at 8 and 12 test workers

### Method

The gate client changes were all released by the time of the measurement:

- C1, c3nd2h: declared gate resources reach the gates Job.
- C1b, yznwz7: Lane capacity.
- C2, lfkkaf: Replay Job size.

livespec-orchestrator-beads-fabro master pins livespec-dev-tooling v1.199.0.

Each run went through the normal gate client and touched nothing on orchestrator
master. The setup:

- An orchestrator worktree at master 418677ec4, holding ONE uncommitted line in
  `pyproject.toml` `[tool.livespec_dev_tooling]`: `gate_parallelism = 8`, then
  `= 12`.
- The command was `just gate-start -- mise exec -- just check`. The client
  selected `cluster_job` (eligible full-suite command), pushed the working tree
  to the gate mirror, and submitted the Job to `gates-cq`.
- Only the worker count moved. Each Job requested cpu 5 and memory 6Gi, with a
  6Gi memory limit and NO cpu limit, so CFS throttling was structurally zero
  (`cpu.max` read `max`, `nr_throttled` 0). The binding term is node
  contention.
- Placement was not steered. Raising `gate_cpu` past 15 would have forced
  poweredge, but under contention a pod's `cpu.weight` follows its request, so
  forcing the node would have added a second confound. That was
  legacy-coordinator-agent's ruling, ~07:05Z.

The node reads follow `.ai/ci-node-capacity-reads.md`. Each is idle % from two
`/proc/stat` samples plus `cpu.pressure`, read on the node for the host, the
`kubepods-burstable.slice` that holds the gate pods, and the
`kubepods-besteffort.slice`. Each read is one literal `cat` per ssh, because
`fleet_host_guard` refuses an scp'd read script and an ssh command built from
shell variables. Per-pod CPU and memory come from Honeycomb, dataset `metrics`,
`k8s.pod.cpu.usage` and `k8s.pod.memory.working_set`, filtered by pod name.

### Results

| | baseline | p8 | p12 |
|---|---|---|---|
| node | gmktec-xubuntu | poweredge-xubuntu | poweredge-xubuntu |
| workers | 4 | 8 | 12 |
| coverage target wall | 2,222 s (target) | 1,072.1 s | 918.8 s |
| test-run wall | 2,174 s / 14,969 tests | 929.22 s / 15,291 items | 796.70 s / 15,291 items |
| pod cpu AVG / P50 / P90 / MAX | not measured | 5.46 / 6.43 / 9.19 / 12.87 | 6.69 / 9.89 / 12.11 / 13.13 |
| pod working set MAX | not measured | 4.10 GiB of 6Gi | 5.22 GiB of 6Gi |
| node idle, start → end | not measured | 3.3% → 0.6% | 0.5% → 27.8% |
| host PSI some avg60, start → end | not measured | 11.6 → 37.2 | 39.7 → 8.2 |
| burstable slice avg60, start → end | not measured | 9.0 → 20.1 | 21.1 → 6.2 |
| node cpu busy over the coverage window, P50 / AVG of 72 | not measured | 68.8 / 66.1 | 70.4 / 66.7 |

Gate runs: p8 `20261112T065825Z-1535720`, Job
`gate-livespec-orchestrator-beads-fabro-jmg2d`, 06:58:26Z-07:18:59Z, PASSED,
98 targets. p12 `20261112T072042Z-1846220`, Job
`gate-livespec-orchestrator-beads-fabro-wfj8q`, 07:20:43Z-07:39:41Z, PASSED, 98 targets.

### What it shows, and what it does not

- **The baseline is not comparable to either run.** It was taken on a
  different node (gmktec-xubuntu) on another day, with no node read. The
  2.3x drop from 2,174 s to 929 s is therefore not attributed to the worker
  count alone.
- **p8 and p12 ran on the same node under comparable load.** The PSI
  snapshots point in opposite directions: p12 started at host avg60 39.7
  against p8's 11.6, and ended at 8.2 against 37.2. Snapshots at the two ends
  do not say what happened in between. Honeycomb's `k8s.node.cpu.usage` for
  poweredge-xubuntu over each coverage window does: P50 68.8 of 72 CPUs for p8
  (bUwoqZnCMVz) and 70.4 for p12 (yaXEVT9DLdf). Both ran on a node 95-98% busy,
  under close to the same load. On that node, 12 workers cut the test run from
  929.22 s to 796.70 s (-14%), and the coverage target from 1,072.1 s to
  918.8 s.
- **The gain holds only on a saturated node.** With the node at its CPU
  ceiling, the extra workers bought only part of their share. On an idle node
  the step from 8 to 12 could be larger, and these two runs cannot say how much
  larger. The ranking of 12 over 8 is sound only for a busy node, which is the
  case that matters for the fleet's gates.
- **12 workers leave thin memory headroom under the default 6Gi.** p12's
  working set peaked at 5.22 GiB, 87% of the limit, with RSS at 4.35 GiB. p8
  peaked at 4.10 GiB. Committing 12 workers on the 6Gi default risks an OOM
  kill as the suite grows, so the commit for assertion 5 carries a memory
  declaration with it.
- **The request is far below use.** At 8 workers the pod used 5.46 cpus on
  average and up to 12.87, against a 5-cpu request. A request is a
  reservation, not a ceiling, so the scheduler packs gates onto a node by a
  number well under what they burn. That is the poweredge 0.5-3% idle seen in
  both runs. Any change to the default request has to be sized from these
  per-pod figures, not from the worker count.
- **The check aggregate's own fan-out did not move.** Its parallel target
  dispatcher logged `"workers": 8` in BOTH runs, so `gate_parallelism` sets only
  the pytest-xdist worker count. The aggregate's other targets run 8-wide
  beside it whatever is declared. (This corrects a reading reported to
  legacy-coordinator-agent after p8 alone.)
- **The yljbpf PASS line was not met at 8.** The line is "orchestrator
  janitor full suite at or under 900 s at the committed gate_parallelism", and
  the 8-worker test run took 929.22 s. At 12 workers it took 796.70 s,
  under the line, so the yljbpf scope event's condition 2 does NOT fire: no
  orchestrator janitor-timeout item is owed. The gate's test run stands in for
  the janitor's full suite here. Both run the same suite on the same worker
  count, but the janitor runs in the factory sandbox, not a gates Job.

## 2. gates-hp-flavor STRANDED: admission counts requests

legacy-coordinator-agent asked about this at 03:09Z on 2026-11-12. hp-xubuntu
looked idle by CPU use while gates queued. Kueue admission and the scheduler
both count REQUESTS. hp had 0.80 cpu free by requests with two gates in, so a
5-cpu gate could not be placed at any quota, whatever the node's idle.

The disposition was no quota change, and it was accepted. The lever is a
smaller, measured per-gate request (assertions 4 and 5), sized from section 1.
The coordinator is fixing the STRANDED check in `fleet-utilization.sh`, which
read CPU idle where it should have read requests. That bears on assertion 6.

## 3. gamingpc-xubuntu: AppArmor denies signals inside the gate container

livespec-dev-tooling-ddy5xu carries the full evidence; this is a summary. On
gamingpc-xubuntu (kernel 7.0.0-43, AppArmor parser 5.0.2) the kernel logs
`apparmor="DENIED" operation="signal"` for sends between processes inside a
gate container. The profile is `cri-containerd.apparmor.d` and the peer is
`cri-containerd.apparmor.d//&unconfined`. There were 233 lines from
2026-11-11.

- gmktec (7.0.0-31) and poweredge (7.0.0-38) logged none. Per
  homelab-k8s-worker-nodes, poweredge, gmktec and hp all have -43 installed and
  not booted, so the fault can reach them on their next reboot.
- No test helper can stop a child it started. Bounded waits run to their bound.
  One unbounded wait in the orchestrator's `bd-guard/test/run-tests.sh`
  (`start_capture` and `stop_capture`) never returns, so the full-suite gate
  reached no verdict in 3 of 3 runs.
- The gate pod has no AppArmor annotation or `appArmorProfile`, an empty
  securityContext and no `hostUsers`, so containerd's default profile applies.
- The node fix is owned by homelab-k8s-worker-nodes. The likely route is the
  `apparmor_profile` role in `ci-pool.yml`, for every node on -43 or 5.0.2.
  gamingpc has been cordoned since 04:48:00Z. The gamingpc gate lane is held
  at 0/0Gi (livespec-dev-tooling#4210). This seat lifts it after one
  `just gate-repro` full suite there ends in under 3600 s with no new DENIED
  lines.
- The harness side is bd-ib-w4bbbd, held at the spec-change tier. Its proposal
  is livespec-orchestrator-beads-fabro#5009, topic
  `bd-guard-harness-start-capture`: a failed probe is not an exit, every wait
  on the capture server is bounded, and a server that cannot be stopped is
  named as a failed case.

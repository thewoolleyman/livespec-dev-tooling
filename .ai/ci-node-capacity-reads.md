# CI node capacity reads — CPU, load, the control plane, and the traps

Read this before raising or lowering the churn-slot cap `C`, before diagnosing
"the node is slow" or "load is huge", and before proposing CPU protection for
k3s or disabling a k3s component. It is agent-facing operational guidance; the
cap's arithmetic lives in `ci-runner/k3s/phase2/kueue/DERIVATION.md` and the
tiers in `.ai/ci-node-storage-tiers.md`. Every entry is drawn from the first
hour at `C = 64` on the two-NVMe host, 2026-09-06 (livespec epic
`livespec-g52yrb`, child `livespec-e2vcqf`).

## Utilization is not the target; throughput is

The maintainer's rule: a higher queue throughput beats a tidy CPU number.
Running more runners than cores is RIGHT while jobs have phases that wait
rather than compute (clone, dependency fetch, container start); those phases
are short now that iowait is ~0, but they exist. CPU-bound phases (`rustc`,
`cc1`, `clippy`, pytest) are zero-sum: past saturation every extra runner
lengthens every job without adding throughput and pushes long jobs toward
their timeouts. So the cap is set where **p95 job duration still grows about
linearly with concurrency and the control plane stays responsive** — never at
"100 % busy", and never at "leave headroom". 64 is in that regime today;
96 is out (no CPU for it, and `max-pods = 200` cannot hold `2 × 96` plus
helpers and system pods).

## Load average is not CPU busy — sample `mpstat`, and mind the buckets

Load 96 with 134 runnable threads on 72 read as "saturated"; `mpstat 5 6` in
the same minute read 84 % busy with an idle floor of 6–8 %. Ninety seconds
later, at 14 runners, the same box was 31 % busy while the 1-minute load still
said 67 — load decays slowly. Read `mpstat` (or `top`'s `%Cpu(s)` line) for
"how busy", `/proc/stat` `procs_running` for "how contended", and the load
average only for trend. `sar` collects every TEN minutes on this host
(`sysstat-collect.timer` `OnCalendar=*:00/10`), so a 3-minute burst that
peaks at load 120 averages down to 48 in its bucket; when the maintainer says
"there was a spike", believe the maintainer and read live, not `sar`.

## `k3s-server` at 120 % is not the problem; starving it would be

120 % of one core is 1.7 % of a 72-thread box, spread across ~20 goroutine
threads at 3–6 % each: the API server fanning watches to 11 ARC listeners,
Kueue, the provisioner and the ARC controller; the kubelet's cgroup stats and
pod churn; scheduler, kine, networking. That is k3s's AVERAGE draw, and it is
not the risk. The risk is the SHARE k3s keeps when the node saturates. Never
reach for `--reserved-cpus` (a cpuset pin), and do not use `--kube-reserved` or
`--system-reserved` as the lever: each needs a k3s restart and only trims
allocatable.

- At the cgroup root the pod slice and `system.slice` are NOT peers at weight
  100. Under the systemd cgroup driver, kubelet weights `kubepods.slice` from
  allocatable CPU: on 72-CPU `poweredge-xubuntu`, 72000m becomes 73728 shares
  and `cpu.weight` 2813, against `system.slice` at 100 (measured 2026-11-05
  23:52Z; `/sys/fs/cgroup/kubepods` does not exist there). At full contention
  all of `system.slice` (k3s with its embedded containerd and kubelet, plus
  every other unit) was therefore entitled to about 100/3113 x 72, or 2.3 CPUs.
  From 20:25Z to 21:25Z that day the node sat at 72.98 of 72 CPUs with load1 up
  to 231, and the API server's datastore p99 reached 7 s with 463 kine
  `Slow SQL` lines in that hour, while kine itself stayed healthy (WAL
  constant, checkpoints running; orchestrator item `bd-ib-yqmnvi`). The earlier
  "load 96 produced 0 `Slow SQL`" reading predates the pool packing this many
  pods onto the server.
- The committed protection is `k3s_config_system_slice_cpu_weight` (role
  `k3s_config`, HOST_VARS.md "system.slice CPU weight",
  `livespec-dev-tooling-cetudy`). `poweredge-xubuntu` declares 1000, which
  entitles `system.slice` to about 1000/4013 x 72, or 17.9 CPUs, under full
  contention. A daemon-reload applies it with no k3s restart, and an empty
  value removes it. `k3s_config_cpu_weight` cannot do this, because a unit's
  weight only orders units inside `system.slice`.
- CFS weights and kubelet reservations are SHARES: they only decide who wins
  when demand exceeds cores and never hold a core idle. The maintainer's
  worry ("cores kept idle because they are allocated to kube") applies only
  to a cpuset pin (`--reserved-cpus`), which nobody should add.
- Runner pods request no CPU (only `ci-runner.io/churn-slot: 1`), so
  lowering allocatable CPU would change no scheduling decision.

## `metrics-server` is not an observability dependency — leave it anyway

Honeycomb's k3s telemetry comes from the host OTel collector's `kubeletstats`
(scrapes the kubelet directly) and `k8s_cluster` (watches the API server)
receivers, not from the Metrics API (`metrics.k8s.io`) that `metrics-server`
serves; the cluster has zero HPAs and nobody runs `kubectl top` in
automation. Disabling it would be safe for telemetry, and is still not worth
doing: its cost is a rounding error and "safe as far as I can see" is not a
reason to remove a component for no gain. Maintainer-confirmed 2026-09-06.

## The memory lever is cache hit rate, not tiering

~143 GiB free cannot create CPU cycles. It CAN stop CPU work from being
repeated: the top consumers are compilers, so the question is `sccache`'s hit
rate (the converge stands up `sccache-redis`; a larger `maxmemory` and a high
hit rate turn `rustc` CPU into cache reads) and the per-repo Rust target-dir /
cargo registry caching owned by the ci-runner-cache-tiers plan. A RAM disk
for work volumes buys nothing: the NVMe work-volume tier already runs at
1–3 ms with iowait ~0.

## Host CPU pressure counts throttle stall — split it by cgroup

`/proc/pressure/cpu` `some` counts every runnable task that is not running, and
that includes a task held back by its own cgroup's CFS quota (`cpu.max`). On a
node that carries Guaranteed, quota-limited factory sandboxes beside the CI
pool, the host figure therefore rises with sandbox throttling even while cores
sit idle. Measured 2026-11-04 14:24Z on `poweredge-xubuntu`: host PSI `some`
avg60 88.7 with 39.3 % idle, about 47 of 72 cores busy (`kubepods.slice` 44.3,
`system.slice` 2.3). The 4-CPU sandboxes were throttled in 30-84 % of their CFS
periods (one reached its own `cpu.pressure` avg60 92.3), while the BestEffort CI
pods' pressure read about 1-1.7. Reading the host figure as saturation cost a
cap decision that day. The 13:16Z revert of per-job test parallelism was real
saturation (0.24 % idle); the later readings of 75-91 were mostly throttle
stall.

So never take host PSI alone as a saturation signal or a revert trigger on a
mixed node. Read:

- **idle %** from `/proc/stat`, or `top`'s `%Cpu(s)` line, for "is there CPU
  left";
- **`usage_usec`** of `kubepods.slice` and `system.slice`, sampled twice a few
  seconds apart, for who is using it;
- **`cpu.pressure`** of the BestEffort slice that holds the CI pods
  (`kubepods.slice/kubepods-besteffort.slice`), for whether CI is actually
  waiting on CPU;
- **`cpu.stat` `nr_throttled` / `nr_periods`** per Guaranteed sandbox, for
  whether a sandbox is limit-bound.

A node is saturated when idle % is under about 5 AND the CI slice's pressure
avg60 is above about 30 (`legacy-coordinator-agent` ruling, 2026-11-04,
recorded on `livespec-dev-tooling-6e5pyj`). Sandbox throttling with idle cores
is a sizing question for the sandbox limit, not a sign the node is full.

## Two instruments that lied, and one that only looked like it

- **`iostat -dx` column offsets.** In sysstat 12.x the write columns are
  `w/s`=$8, `wkB/s`=$9, `wrqm/s`=$10, `%wrqm`=$11, **`w_await`=$12**,
  `wareq-sz`=$13, `aqu-sz`=$22, `%util`=$23. An awk that printed `$11` as
  `w_await` reported "75 ms" on an NVMe that was at 2 ms and fired a false
  soak alarm. Print the header once before trusting a column number.
- **`ssh host 'cut -d" " ...'` quoting.** A double quote inside a
  single-quoted remote command is fine; the same command pasted into a
  double-quoted local wrapper is not. Put multi-line remote scripts in a
  file and `scp` it, as `/tmp/iostat-read.sh` was.
- **`scan-runner-pod-lifecycle.service` in `failed` state.** Exit 1 is its
  REPORT (a lifecycle class fired, e.g. `pvc-pending` when work PVCs sat
  165–182 s at a 51-runner burst); `systemctl --failed` counting 1 is the
  signal working, not a unit to repair. Read its journal for the class and
  whether it cleared.

## `Slow SQL` tracks the backlog's depth, not the cap

kine (the SQLite-on-tmpfs datastore behind the k3s API) logs `Slow SQL`
for any statement over one second. On this host it is CPU and write-volume
queueing, never disk: the datastore is in RAM. Read the two apart:

- `mpstat` at 90 % with `Slow SQL` at zero — the cap is the lever (the
  first hour at C = 64 looked like this).
- `Slow SQL` climbing while the running count is flat — the backlog is the
  lever. At the first fleet-wide backlog on the tiered host (2026-09-06
  07:38Z, C = 32) 119 pending Kueue workloads and 122 gated runner objects
  produced 11 `Slow SQL` in ten minutes, MORE than the 64-slot burst two
  hours earlier, because every gated pod is an `EphemeralRunner`, a pod, a
  `Workload` and events rewritten every reconcile. The fix was bounding ARC
  `maxRunners` to `max(2 x nominalQuota, 6)` so the surplus stays queued on
  GitHub (`ci-runner/k3s/phase2/kueue/DERIVATION.md` "
Bounding maxRunners to the quota (2026-09-06)"). Check the ceilings before blaming the cap:
  `kubectl get autoscalingrunnerset -n arc-runners -o custom-columns=NAME:.metadata.name,MAX:.spec.maxRunners,CUR:.status.currentRunners,PEND:.status.pendingEphemeralRunners`.
- A job mix matters more than a job count. 32 running jobs read 73 % busy at
  one backlog and 91–98 % at the next, because the second was dominated by
  heavier matrices plus the per-job overhead (the node container hook at one
  to two cores per runner, `cp` volume seeding, `rm` teardown, namespace and
  veth churn showing as 17–20 % system time). Derive the cap at the heavy
  mix; the light one flatters it.

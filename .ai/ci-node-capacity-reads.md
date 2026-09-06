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
pod churn; scheduler, kine, networking. Do NOT reach for `CPUWeight`,
`--kube-reserved`, `--system-reserved`, or `--reserved-cpus`:

- At the cgroup root the pod slice (`/sys/fs/cgroup/kubepods`) and
  `system.slice` are peers at `cpu.weight` 100, so under full contention the
  host side may take half the machine; k3s wants 1.7 %. Load 96 produced
  0 `Slow SQL`. It is already protected.
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

# `k3s_config` — per-node values a pool agent's profile declares

`k3s_config` renders each pool agent's own k3s start configuration from that
node's committed phase0 profile (`ci-runner/k3s/phase0-bare-metal/profiles/`).
It restarts nothing; `ansible/restart-k3s-agent.yml` is the one sanctioned way
to make a rendered change take effect. The values live in the profiles, never
here. This file records only the arithmetic that a value cannot carry itself.

## hp-xubuntu factory-worker kubelet budget

**What the budget is for.** `hp-xubuntu` runs a k3s agent as a factory-only node:
it is closed to CI, and Kubernetes factory pods are placed on it. The kubelet
must hold back what the host itself needs, so that pods cannot starve k3s, `sshd`
or the page cache. The rest it offers to factory pods. The records live in **one**
place: `KUBELET_ARGS` in `ci-runner/k3s/phase0-bare-metal/profiles/hp-xubuntu.env`.
The `k3s_config` role renders them, as an APPEND (`kubelet-arg+`), into
`/etc/rancher/k3s/config.yaml.d/`. This section is the arithmetic, not a second
copy of the data.

**What changed, and why.** Until 2026-11-02, hp's reservations were sized to
coexist with the Docker sandbox slice (`docker_sandbox_slice`: a `24G` / `1400%`
ceiling). That slice dominated `system-reserved` and left pods only `500m` CPU and
about `3Gi` of memory. The slice was retired on hp on 2026-11-02 through the
committed apply (`docker_sandbox_slice_state: absent` for hp, PR #3078; plan
gmktec-factory-placement, item `livespec-dev-tooling-2yn4yb`). hp's Docker
sandboxes are gone, so that capacity is released to the pod-allocatable line,
where the factory's Kubernetes pods run.

**The reservations, as `hp-xubuntu`'s profile declares them.**

```text
system-reserved=cpu=1000m,memory=2048Mi
kube-reserved=cpu=500m,memory=1024Mi
eviction-hard=memory.available<512Mi,nodefs.available<10%,imagefs.available<10%
```

| term | memory | CPU | what it covers |
| --- | --- | --- | --- |
| node capacity | 32176236Ki (~30.7Gi) | 16000m | read from the API on 2026-11-02 (`.status.capacity`) |
| `system-reserved` | 2048Mi | 1000m | `sshd`, the host's own daemons, the retained read-only Fabro instance files, and the Docker daemon that still serves `sccache-redis` |
| `kube-reserved` | 1024Mi | 500m | `k3s-agent`: the kubelet and the bundled containerd |
| `eviction-hard` | 512Mi | — | the headroom the kubelet keeps so it evicts before the kernel OOM-kills |
| **pod-allocatable** | **~27.2Gi** (`28506220Ki`) | **14500m** | what is left for pods |

**Measured before the change (2026-11-02, read-only).** With no pods on hp, `free -m` reported 2717Mi used of 31422Mi, and `sccache-redis`, the only remaining Docker container, used 21Mi against its own 5GiB container limit. That limit is a ceiling, not a reservation. If `sccache-redis` ever grows toward it, `system-reserved` no longer covers it and condition 2 below applies.

**What that funds.** One factory pod requests and limits `4` CPU and `7630Mi`.
Three of them take `12000m` and `22890Mi` (~22.4Gi), which fits inside `14500m`
and ~27.2Gi with room for the cluster's own DaemonSet pods. A fourth does not fit
on CPU. Confirm the live figures after the apply with
`kubectl describe node hp-xubuntu` rather than from this table: the kubelet's
own arithmetic is the authority, and `ansible/restart-k3s-agent.yml` prints
capacity beside allocatable for exactly this purpose.

**Why `ADMISSION_CAPACITY_C` stays `0`.** That key counts CI churn slots, not
factory pods. hp stays closed to CI, and `profile.sh` refuses a non-zero value on
a node whose `CI_NODE_FACILITIES=none`. The allocatable line above is for factory
pods, which the `factory` namespace's ResourceQuota bounds
(`ci-runner/k3s/phase2/factory/DERIVATION.md`), not for runner pods.

**When this budget is revisited.** Revisit it in any of these three cases:

1. **hp's `ADMISSION_CAPACITY_C` becomes non-zero.** Opening the node to CI means
   runner and workflow pods, which this table does not fund beside three factory
   pods. A profile edit that opens the node without revisiting this table
   produces work that Kueue admits and the scheduler then cannot place.
2. **A workload outside Kubernetes returns to hp.** A Docker sandbox slice, a
   live Fabro server, or anything else that runs beside the kubelet must come
   back out of `system-reserved` first. The reservations and that workload are
   two halves of one budget, and they move together.
3. **The factory pod's declared resources change.** The three-pod fit above is
   computed from `4` CPU and `7630Mi`.

## Single-process OOM kill

**What it is for.** Orchestrator work-item `bd-ib-3kdjct` (plan epic
`bd-ib-nmuyjc`) requires that one runaway command fails only that command and
does not destroy the sandbox. On cgroup v2 the kubelet sets `memory.oom.group=1`
on every container cgroup by default, so when one process hits the container's
memory limit the kernel kills every process in the container.

**What broke, measured 2026-11-02.** In factory pod
`petri-01m6dp57ek5q0p8arn07bgwad8-l0` (7630 MB limit, on poweredge-xubuntu), the
agent's own pytest reached about 7.5 GB at 08:44:35Z. The group kill took the
codex agent with it. Every uncommitted change was lost, and the run's checkpoint
found the sandbox unreachable.

**What the role does.** On every node, server and agent alike, it installs
`<data-dir>/agent/etc/kubelet.conf.d/50-single-process-oom-kill.conf`. `<data-dir>`
is the profile's `NODE_DATA_DIR`, or `/var/lib/rancher/k3s` when that is empty.
The file carries `singleProcessOOMKill: true` (KubeletConfiguration, Kubernetes
1.32+), and k3s's kubelet merges it over its own `00-k3s-defaults.conf` through
`--config-dir`. The kubelet then leaves `memory.oom.group` unset, and the kernel
kills only the process it selects, usually the largest.

| variable | default | meaning |
| --- | --- | --- |
| `k3s_config_single_process_oom_kill` | `true` | install the drop-in; `false` removes it |
| `k3s_config_single_process_oom_kill_drop_in` | `50-single-process-oom-kill.conf` | the drop-in's file name |
| `k3s_config_default_data_dir` | `/var/lib/rancher/k3s` | k3s's data directory when the profile names none |

**Scope.** Node-wide: it applies to every container on the node, ARC runner
and gate pods included.

**When it takes effect.** On the next k3s start, and only for containers created
after it; a running container keeps the `memory.oom.group` value it was created
with. Reach that start on an agent through `ansible/restart-k3s-agent.yml`. On
the server, use a coordinated `k3s` restart. Check a new pod's container cgroup
with `cat .../memory.oom.group`; it reads `0` once the drop-in is in force.

**Rollback.** Set `k3s_config_single_process_oom_kill: false` for the node,
re-apply `ansible/ci-pool.yml`, and restart k3s on that node.

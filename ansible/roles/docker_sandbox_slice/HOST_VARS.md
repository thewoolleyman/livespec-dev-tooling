# `docker_sandbox_slice` — per-host values for the inventory's `host_vars`

The aggregate resource envelope a Fabro factory host puts around its sandbox
containers: a systemd slice carrying memory and CPU limits, named as the Docker
daemon's default `cgroup-parent` so every container the daemon starts joins it.

**Why it exists, and why it is interim.** The Petri-era candidate engine starts
its Docker sandboxes with `CpuQuota 0` and `Memory 0` — no per-run limits at
all — so a single run can take the whole host. Until the Kubernetes sandbox
backend restores per-run limits, the only available protection is a ceiling on
the containers *together*. See "Expiry" below for what retires this role.

**Measured on `hp-xubuntu`, 2026-10-10:** 16 CPUs, 30 GB RAM, cgroup v2 with the
systemd cgroup driver, and no `/etc/docker/daemon.json` at all (so no
`default-cgroup-parent` and no existing keys). The non-Fabro `sccache-redis`
container (5 GB limit) runs on the same daemon.

## The variables

Every one of these equals this role's default, so **`hp-xubuntu` needs no
`host_vars` entry at all**. They are listed so the next host's values have
something to differ from — and so the sizing rationale is not lost.

| variable | default | what it is |
| --- | --- | --- |
| `docker_sandbox_slice_name` | `fabro-sandbox.slice` | the slice every sandbox container joins, and the value written as `cgroup-parent` |
| `docker_sandbox_slice_unit_dir` | `/etc/systemd/system` | where the slice unit is installed |
| `docker_sandbox_slice_memory_high` | `22G` | the slice's throttling watermark |
| `docker_sandbox_slice_memory_max` | `24G` | the slice's hard memory ceiling |
| `docker_sandbox_slice_cpu_quota` | `1400%` | the slice's CPU ceiling, in whole-core percent |
| `docker_sandbox_slice_daemon_config` | `/etc/docker/daemon.json` | the daemon configuration the role edits |
| `docker_sandbox_slice_daemon_service` | `docker.service` | the unit a drained restart restarts |
| `docker_sandbox_slice_pending_restart_marker` | `/var/lib/docker-sandbox-slice/restart-pending` | where a converge records that the running daemon has not loaded the envelope |
| `docker_sandbox_slice_state` | `present` | `present` installs and holds the envelope. `absent` RETIRES it on a host that keeps its daemon; see "Retiring the envelope on one host" below. Any other value is refused before anything is written |
| `docker_sandbox_slice_docker_engine_state_root` | `/var/lib/docker-engine-guard` | the docker_engine guard's state root. Where it exists without its `confirmed` marker the guard has not committed (or rolled back, leaving `dockerd` on disk), so the role treats the host as having no daemon and leaves the daemon configuration to the guard |

```yaml
# hp-xubuntu — every value is the role default; shown, not required.
docker_sandbox_slice_memory_high: 22G
docker_sandbox_slice_memory_max: 24G
docker_sandbox_slice_cpu_quota: "1400%"
```

**Where the three numbers come from.** `24G` of the host's 30 GB leaves 6 GB for
the host itself, the Fabro servers (which run *outside* this slice) and the page
cache. `22G` sits below it so reclaim pressure arrives before the OOM killer
does: a slice over `MemoryHigh` is throttled, and only a slice that cannot be
reclaimed below `MemoryMax` loses a process. `1400%` is 14 of the 16 cores,
leaving two for the Fabro servers, `sshd` and the janitor steps.

**What else lands in the slice.** `cgroup-parent` is the daemon's *default*
parent, so `sccache-redis` joins it too. The ceiling is therefore shared between
the sandboxes and that cache, which is deliberate — both are container-layer
load on the same host, and the number worth protecting is the host's. If that
cache ever needs to sit outside the envelope, give its unit its own
`--cgroup-parent`; do not narrow this role.

## Coexistence with the k3s agent

**Why this section is here and not somewhere else.** Since
`livespec-dev-tooling-7we6po`, `hp-xubuntu` also runs a **k3s agent** — it joins
the CI pool as a factory-only node, closed to CI by its own committed profile.
The kubelet must hold capacity back from the pods it would otherwise schedule, or
the first node-pressure eviction takes a running factory dispatch with it. The
numbers it holds back are computed almost entirely from the three slice limits
above, so the budget is recorded beside them rather than in a file of its own.
The values themselves live in **one** place — `KUBELET_ARGS` in
`ci-runner/k3s/phase0-bare-metal/profiles/hp-xubuntu.env` — and the `k3s_config`
role renders them into `/etc/rancher/k3s/config.yaml.d/`. This section is the
arithmetic, not a second copy of the data.

**What is on this host at once.** The Docker sandbox slice (ceiling
`docker_sandbox_slice_memory_max` `24G` / `docker_sandbox_slice_cpu_quota`
`1400%`, with `docker_sandbox_slice_memory_high` `22G` as its throttling
watermark, holding every sandbox container and `sccache-redis`); two running
Fabro server instances and one stopped one, which run *outside* the slice;
`sshd`, the host's own daemons and the page cache; and now a k3s agent —
`k3s-agent` itself (the kubelet plus the bundled containerd) and whatever pods it
is allocated for.

**The reservations, as `hp-xubuntu`'s profile declares them.**

```text
system-reserved=cpu=14500m,memory=25088Mi
kube-reserved=cpu=1000m,memory=1024Mi
eviction-hard=memory.available<512Mi,nodefs.available<10%,imagefs.available<10%
```

| term | memory | CPU | what it covers |
| --- | --- | --- | --- |
| node capacity | ~29Gi (30 GB) | 16000m | measured 2026-10-13 |
| `system-reserved` | 25088Mi (24.5Gi) | 14500m | the slice's hard ceiling (`24G` / `1400%`) **plus** 512Mi and 500m for the two Fabro servers, `sshd` and the host's daemons |
| `kube-reserved` | 1024Mi | 1000m | `k3s-agent`: the kubelet and the bundled containerd |
| `eviction-hard` | 512Mi | — | the headroom the kubelet keeps so it evicts before the kernel OOM-kills |
| **pod-allocatable** | **~3Gi** | **500m** | what is left for pods |

**Read the two allocatable figures as a consequence, not a target.** `500m` and
`~3Gi` are what the subtraction leaves, and they are deliberately not inflated:
this node admits **no CI churn** (`ADMISSION_CAPACITY_C=0`) and the pods it is
expected to carry are the cluster's own small system pods plus, later, whatever
the Kubernetes sandbox backend places on it. A factory dispatch on this host runs
in a **Docker** sandbox inside the slice, not in a pod, so it is funded by the
`system-reserved` line and not by the allocatable one. Confirm the live figures
with `kubectl describe node hp-xubuntu` after the apply rather than from this
table — the capacity figure above is approximate, and the kubelet's own
arithmetic is the authority.

**The conditions under which this is revisited.** Two, and the first is this
role's own "Expiry" below:

1. **When the Kubernetes sandbox backend cutover steps the slice budget down.**
   The sandbox containers move into pods, `docker_sandbox_slice` is retired, and
   the `24G`/`1400%` that dominates `system-reserved` is released to the
   allocatable line. The reservations and the slice limits are two halves of one
   budget and move together — do not lower one without the other.
2. **When `hp-xubuntu`'s `ADMISSION_CAPACITY_C` becomes non-zero.** Opening this
   node to CI means runner and workflow pods, which `500m`/`3Gi` cannot fund. A
   profile edit that opens the node without revisiting this table produces work
   Kueue admits and the scheduler then cannot place.

## The drained restart

**`cgroup-parent` is not reloadable.** `systemctl reload docker` re-reads only a
subset of `daemon.json` and this key is not in it, so the converge's write takes
effect on the daemon's *next start* and on nothing else. A converge therefore
never restarts `dockerd`: it leaves the host configured and records the pending
restart at `/var/lib/docker-sandbox-slice/restart-pending`.

**Restarting the daemon kills every running sandbox container**, which on a
factory host means destroying every in-flight run and discarding the warm
`sccache-redis` cache. So the restart is the operator's, taken inside a window
they have drained:

1. Read the drift report first, as the play requires:
   `just ansible-drift ansible/fabro-hosts.yml --tags docker_sandbox_slice`.
2. Converge the envelope: `just ansible-apply ansible/fabro-hosts.yml --tags
   docker_sandbox_slice`. This installs the slice, writes `cgroup-parent`, and
   records the pending restart. It does **not** restart anything.
3. Drain the host. For each instance in this host's `fabro_server_instances`,
   stop dispatching to it and wait for its active runs to finish — the Fabro
   server's own `ps` is the reader
   (`HOME=<instance home_env> <instance binary_path> --json ps`). A run killed
   mid-flight is a lost run, not a retried one.
4. Inside that window, take the restart by naming its tag:
   `just ansible-apply ansible/fabro-hosts.yml --tags
   docker_sandbox_slice_drained_restart`. That tag is the only thing that
   restarts `dockerd` and the only thing that clears the marker file.
5. Verify: `systemctl show fabro-sandbox.slice -p MemoryMax -p CPUQuota` reports
   the configured limits, and a freshly started container's cgroup path is
   under `/sys/fs/cgroup/fabro.slice/fabro-sandbox.slice/`. The marker file is
   gone.

**Why the tag and not a handler.** A handler notified by the `daemon.json` write
would fire on exactly the converge that must not restart. And the `never` tag
alone is not enough: `roles:`-level tagging puts `docker_sandbox_slice` on every
task in the role, and Ansible runs a `never`-tagged task whenever any other tag
it carries is selected — so each gated task also carries
`when: 'docker_sandbox_slice_drained_restart' in ansible_run_tags`. Both halves
are load-bearing.

## Rollback

1. Remove the `cgroup-parent` key from `/etc/docker/daemon.json`, leaving every
   other key as it stands. Removing the role from the play does **not** remove
   the key — a converge that no longer runs cannot undo what a previous one
   wrote.
2. Restart `docker.service` inside a drained window, by the same drain procedure
   as "The drained restart" steps 3-5 above. Until that restart the daemon keeps
   placing containers in the slice, so the rollback is not in effect.
3. Optionally remove `/etc/systemd/system/fabro-sandbox.slice` and
   `systemctl daemon-reload`. An orphaned slice with no members bounds nothing
   and costs nothing, so this step is housekeeping rather than part of the
   rollback.

Rolling back returns the host to **no per-container and no aggregate limits at
all**, which is the state that motivated this role. Prefer raising
`docker_sandbox_slice_memory_max` / `docker_sandbox_slice_cpu_quota` in this
host's `host_vars` to removing the envelope.

## Retiring the envelope on one host

Set `docker_sandbox_slice_state: absent` in that host's `host_vars`. The role
then runs `tasks/retire.yml` and ends, and never reaches the install half. The
same one rule holds: a converge never restarts `dockerd`.

1. Read the drift: `just ansible-drift ansible/fabro-hosts.yml --limit <host>
   --tags docker_sandbox_slice`. It shows `cgroup-parent` leaving `daemon.json`,
   with every other key kept, and the pending-restart marker being written.
2. Converge it: `just ansible-apply ansible/fabro-hosts.yml --limit <host>
   --tags docker_sandbox_slice`. Running containers stay in the slice, because
   the running daemon loaded the key when it started.
3. Drain the host as in "The drained restart" step 3. Then take the restart:
   `just ansible-apply ansible/fabro-hosts.yml --limit <host> --tags
   docker_sandbox_slice_drained_restart`. That run restarts `dockerd`, stops the
   slice, removes its unit, reloads systemd and clears the marker. The slice
   cannot be stopped before the restart, because stopping a slice kills every
   process in it.
4. Verify:
   - `daemon.json` names no `cgroup-parent`;
   - `systemctl status fabro-sandbox.slice` reports the unit not found;
   - the marker file is gone.

A host that later leaves `sandbox_hosts` keeps this state, because no further
converge reaches it. Measured first on hp-xubuntu, 2026-11-02 (plan
gmktec-factory-placement, item livespec-dev-tooling-2yn4yb). That host leaves
the factory role and is being reworked into a Kubernetes factory worker.

## Expiry

**Retire this role when the Kubernetes sandbox backend enforces per-run limits.**
The envelope is an aggregate stand-in for limits that belong on each run: it
cannot stop one run from starving its neighbours inside the slice, only from
taking the host. Once a sandbox backend sets per-run CPU and memory on each
container, this role's reason to exist is gone — remove it from
`ansible/fabro-hosts.yml`, perform the "Rollback" above, and delete the role.

Until then it is live and load-bearing, and a host carrying it by hand rather
than through the play is drift to be expressed in the play, never an accepted
exception.

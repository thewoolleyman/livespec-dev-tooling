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

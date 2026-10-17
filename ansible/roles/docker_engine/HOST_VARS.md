# `docker_engine` — per-host values for the inventory's `host_vars`

Installs the Docker engine (`docker.io`, `containerd`, `runc`) on a factory host
that **already runs k3s and Tailscale**, without risking the host's network
access. Every step that could cut the host off runs behind the Docker engine
install guard, `/usr/local/libexec/docker-engine-guard`, whose source is this
repository's `livespec_dev_tooling/fleet/docker_engine_guard.py` and its
`_docker_engine_guard_*.py` siblings.

**Why it exists.** gmktec-xubuntu carries a k3s agent (CI pods) and the fleet's
local LLM service, and its only remote access is Tailscale SSH plus the direct-LAN
fallback (`lan_ssh_fallback`). Installing Docker as packaged changes FORWARD to
DROP and inserts `DOCKER-USER` and `DOCKER-FORWARD` (measured on hp-xubuntu), and
the packages' postinst starts the daemons at once. Nobody can reach the host
physically. Governing specification: `## Docker engine install guard` and
`## Fabro factory host provisioning` in `SPECIFICATION/non-functional-requirements.md`.
Governing design: `docs/docker-engine-guard-design.md` (revisions 5 to 8 and the
implementation rider). Work-item `livespec-dev-tooling-xxfqqr`.

## Guard dependencies

The role drives the guard and does not restate it, so it can complete a run only
once the guard is whole. These guard children of
`livespec-dev-tooling-xxfqqr` are what it relies on:

| child | what the role needs from it | state when this role was drafted (2026-10-16) |
| --- | --- | --- |
| `livespec-dev-tooling-23e3c5` | `_docker_engine_guard_aptlock.py` (the dpkg frontend-lock helper the fence runs), `docker_engine_guard_budgets.py` (the budgets and deadline the role's unit timeouts are read from), and the guard's own maintainer-script-set refusal | not merged |
| `livespec-dev-tooling-bfzrq7` | the guard's preflight (the bridge-overlap refusal, the k3s resync window) and the observation `sample` probes | not merged |
| `livespec-dev-tooling-p4clqz` | the remaining `RealHost` seams in `_docker_engine_guard_host.py` | not merged |

**The role cannot complete a run until all three are merged.** Before then a
converge fails closed: the budgets lookup fails before the host is touched, or
`reserve` refuses having changed nothing.

## How a converge keeps the host reachable

| when | what holds the host safe |
| --- | --- |
| before `reserve` | the preflight refuses an unhealthy or foreign host, having written nothing |
| packages installed, not started | each guarded unit's drop-in `ConditionPathExists=|` pair: no unit can start without the tmpfs start permission or the commit marker, so the postinst start is skipped |
| after `arm` | a transient dead-man timer rolls the run back at its deadline, and every 60 s after, unless `confirm` stops it; it needs no controller |
| a reboot before the commit | `/run` is tmpfs, the permission is gone, nothing can start, Docker's rules are not persisted |
| a controller-observed failure | the role's rescue runs the guard's `rollback` (a no-op once the run is committed) |
| apt during the run | the apt timers are stopped and a helper holds the dpkg frontend lock around the install; a host-side backstop restores the timers if the controller is lost |

The role never starts, stops, enables or disables `containerd.service`,
`docker.service` or `docker.socket` itself. On systemd 259 a `Restart=` respawn
does **not** re-evaluate `ConditionPathExists` (rider point 1), so the only thing
that keeps a respawning `dockerd` down once the permission is revoked is the
guard's rollback stopping `docker.socket` before `docker.service`. The disposable
VM acceptance carries the respawn test.

## The variables

| variable | default | where set | what it is |
| --- | --- | --- | --- |
| `docker_engine_llm_health_url` | `""` (refused) | host_vars | the local LLM service's health endpoint across the tailnet; the controller requires HTTP 200 |
| `docker_engine_dpkg_config_digests` | `{}` (refused) | host_vars | every apt/dpkg configuration file mapped to its committed SHA256 (see "The audit") |
| `docker_engine_must_stay_running` | `[]` | host_vars | further units that must be active before, during and after |
| `docker_engine_window_seconds` | `420` | host_vars if the host's k3s resync periods differ | the observation window W; sizes `observe`'s budget and the deadline |
| `docker_engine_packages` | the three pinned versions, `scripts: {}` | defaults (audit commits the scripts) | the allowlist: package, version, maintainer-script SHA256s |
| `docker_engine_deb_arch` | `amd64` | defaults | the architecture in each `.deb` name |
| `docker_engine_deb_cache` | `/var/cache/docker-engine-guard/debs` | defaults | where the role and the guard download the `.deb` files |
| `docker_engine_dpkg_config_dirs` | `/etc/apt/apt.conf.d`, `/etc/dpkg/dpkg.cfg.d` | defaults | directories every file of which a digest must cover |
| `docker_engine_daemon_config` | the design's eight owned keys | defaults | written into `/etc/docker/daemon.json`, every other key preserved |
| `docker_engine_daemon_config_path` | `/etc/docker/daemon.json` | defaults | |
| `docker_engine_bridge_cidr` | `172.17.0.0/16` | defaults | passed to the guard, whose preflight refuses an overlap with an address, a route or a reserved CIDR |
| `docker_engine_reserved_cidrs` | `100.64.0.0/10`, `10.42.0.0/16`, `10.43.0.0/16` | defaults | the tailnet range and k3s's pod and service CIDRs, passed to the guard in `probes.json` |
| `docker_engine_sandbox_slice` | `fabro-sandbox.slice` | defaults | must be loaded and active before the first start; equals `cgroup-parent` |
| `docker_engine_tailscale_unit` | `tailscaled.service` | defaults (VM: a stub) | must be active |
| `docker_engine_k3s_agent_unit` | `k3s-agent.service` | defaults (VM: a stub) | must be active |
| `docker_engine_tailscale_ssh_argv` | `ssh -o BatchMode=yes … -o ControlMaster=no -o ControlPath=none <user>@<host> true` | defaults (VM: override) | the controller's new Tailscale SSH session |
| `docker_engine_lan_fallback_port` | `22022` | defaults | the `lan_ssh_fallback` port |
| `docker_engine_lan_fallback_ssh_argv` | `ssh … -p 22022 <host>-lan true` | defaults (VM: override) | the controller's LAN-fallback login |
| `docker_engine_probe_timeout_seconds` | `15` | defaults | the health read's timeout |
| `docker_engine_k3s_node` | `inventory_hostname` | defaults | the k3s node name the observer's node-Ready and DNS-placement probes read (gmktec: `gmktec-xubuntu`, measured 2026-10-16) |
| `docker_engine_k3s_server` | none, REFUSED while empty | host_vars | the k3s server the DNS-placement probe asks where CoreDNS runs (gmktec: `poweredge-xubuntu`, the control plane) |
| `docker_engine_k3s_server_argv` | `[]` | host_vars | the command prefix that reaches that server with `k3s kubectl` rights (guard child 9, livespec-dev-tooling-tceepc); gmktec: `[sudo, -u, cwoolley, -H, ssh, -o, BatchMode=yes, poweredge-xubuntu, sudo]`, node_status_credential's proven route |
| `docker_engine_canary_name` / `docker_engine_canary_image` | `docker-engine-guard-canary` / busybox 1.37.0 by digest | defaults | the ONE canary container run between `start` and `observe` and removed after `confirm` |
| `docker_engine_probe_parameters` | the guard's ProbeParameters: node, k3s_server, `10.43.0.10`, `kubernetes.default.svc.cluster.local`, `10.43.0.1:443`, canary | defaults | uploaded as the run's `inputs/probes.json`, with `must_stay_running` and any `k3s_server_argv` merged in |
| `docker_engine_postinst_started_units` | the three guarded units | defaults | units whose condition-skip the post-install check requires in the journal |
| `docker_engine_apt_timers` | `apt-daily.timer`, `apt-daily-upgrade.timer` | defaults | stopped for the run, restored to their prior state |
| `docker_engine_lock_wait_seconds` | `600` | defaults | bound on the apt/dpkg lock wait |
| `docker_engine_guard_source_root` | the repository root, from `role_path` | defaults | where the guard modules are copied from on the control node |
| `docker_engine_guard_install_root` | `/usr/local/lib/docker-engine-guard` | defaults | |
| `docker_engine_guard_executable` | `/usr/local/libexec/docker-engine-guard` | defaults | fixed by the guard's `GUARD_EXECUTABLE`; not a knob |
| `docker_engine_state_root` / `docker_engine_runtime_root` | `/var/lib/docker-engine-guard` / `/run/docker-engine-guard` | defaults | fixed by the guard; not knobs |
| `docker_engine_acknowledge_run` | `""` | `-e` only | acknowledges a `rollback-partial` run; runs the guard's `verify` |
| `docker_engine_recover` | `""` | `-e` only | names the current unfinished run for the guard's `recover` |

```yaml
# gmktec-xubuntu
docker_engine_must_stay_running:
  - local-homelab-llama-server.service
docker_engine_llm_health_url: http://<gmktec tailnet address>:<port>/health
docker_engine_dpkg_config_digests:
  /etc/apt/apt.conf.d/20apt-esm-hook.conf: <sha256>
  # ... every file in /etc/apt/apt.conf.d and /etc/dpkg/dpkg.cfg.d,
  # and /etc/dpkg/dpkg.cfg
```

**For the disposable VM acceptance run**, which has no Tailscale, k3s or LLM,
override `docker_engine_tailscale_unit`, `docker_engine_k3s_agent_unit` and
`docker_engine_must_stay_running` with stub units, `docker_engine_llm_health_url`
with a stub `/health` server, `docker_engine_tailscale_ssh_argv` and
`docker_engine_lan_fallback_ssh_argv` with logins to the VM's forwarded SSH port,
and `docker_engine_probe_parameters` with the stubs the harness serves.

## The audit

Two values are committed only after a human has read what they vouch for, and
the role refuses to converge without them:

1. **Maintainer scripts.** For each package, download the pinned `.deb` on a host
   of the same release (`apt-get download <pkg>=<version>`), list its scripts
   (`dpkg-deb -e <deb> <dir>`; the scripts are `preinst`, `postinst`, `prerm`,
   `postrm`, `config`), read every one, and commit
   `dpkg-deb -I <deb> <script> | sha256sum` for each under that package's
   `scripts` in `defaults/main.yml`. The guard's audit refuses a `.deb` whose
   script set differs from the committed keys, and a script whose bytes differ
   from its digest. Record who read them and when here, under this
   heading.
2. **apt and dpkg configuration.** On the target host, `sha256sum` every file in
   `/etc/apt/apt.conf.d/` and `/etc/dpkg/dpkg.cfg.d/`, and `/etc/dpkg/dpkg.cfg`,
   read each apt hook, and commit the map as `docker_engine_dpkg_config_digests`
   in that host's host_vars.

### The maintainer-script audit (2026-10-16)

Read by the session `petri-factory-on-gmktec` (session c06a2db3) on
2026-10-16. The `.deb` files came from the Ubuntu 26.04 archive, downloaded
inside the disposable acceptance VM with `apt-get download`. Each script was
extracted with `dpkg-deb -e` and hashed with `sha256sum`; those are the same
bytes `dpkg-deb -I` prints. Every script was read in full.

- **containerd 2.2.2-0ubuntu1.1**: `postinst`, `prerm` and `postrm`.
  - `postinst` unmasks and enables `containerd.service`, runs
    `systemctl daemon-reload`, then `deb-systemd-invoke start`.
  - `prerm` stops the unit on remove.
  - `postrm` reloads on remove and purges the unit state on purge.
- **runc 1.4.0-0ubuntu1**: no maintainer script.
- **docker.io 29.1.3-0ubuntu4.1**: `preinst`, `postinst`, `prerm` and `postrm`.
  - `preinst` refuses only when `/var/lib/docker/aufs` exists.
  - `postinst` does four things. It creates the `docker` system group on a
    first install. That group is why `arm` repeats the docker-group check
    (design I4). It reloads the AppArmor profile. It unmasks and enables
    `docker.service` and `docker.socket`. Finally it runs
    `invoke-rc.d docker start`.
  - A ZFS migration branch in `postinst` runs only on a ZFS root, and a
    debconf restart prompt runs only on upgrade. Neither applies to a fresh
    install on ext4.
  - `prerm` stops `docker.socket` then `docker.service` on remove, and copies
    `nuke-graph-directory.sh` into `/var/lib/docker`.
  - `postrm` reloads on remove and runs that script on PURGE only. Purge is a
    path the role never takes: design Mechanism 6 never erases.

What this means for Mechanism 1 is that every start a maintainer script
attempts meets the guard's start condition. docker.io's `postinst` issues
`invoke-rc.d docker start` WITHOUT a `daemon-reload` of its own, and it is
covered two ways:

- `dpkg -i` on the audited set unpacks all three packages before configuring
  any. So containerd's `postinst`, configured first, has already reloaded
  systemd with docker's unit files and the guard's drop-ins in place.
- systemd loads a never-loaded unit's drop-ins from disk on its first start in
  any case.

The disposable-VM acceptance run is what proves this, not this reading: after
`publish`, all three units must be inactive with their condition unmet
(`FAULTS.md`, H-01).

## Operator procedure

Preconditions (the work-item's convergence gates): the LAN SSH fallback applied
and demonstrated on the host; the disposable-VM acceptance passed; the attended
converge announced to gitops-fleet-capacity-monitoring and the k3s sessions; the
host in the `docker_engine_hosts` group, which no host joins by default.

```bash
just ansible-drift ansible/docker-engine.yml   # classifies, compares the guard; changes nothing
just ansible-apply ansible/docker-engine.yml   # one guarded run, attended
```

A run takes, at the defaults: reserve, the drop-in proof, the download and
scratch-root proof, the fenced audited install (up to 30 minutes), arm, start,
a seven-minute observation, the controller probes and confirm. Every operation
runs as its own transient unit (`docker-engine-guard-<op>-<run>-<seq>`, or the
fixed `docker-engine-guard-start` / `docker-engine-guard-observe`); its verdict
is in the play output and in `journalctl -u <unit>`.

What a converge does with what it finds:

| found | the role |
| --- | --- |
| nothing, or the last run `rolled-back` | a new guarded run |
| the commit marker | the post-commit path: validates the drop-ins, the units (enabled and active) and the owned keys; a changed owned key goes through the guard's `reconfigure`, which records a pending drained restart; nothing is reserved |
| an unfinished run | refuses with its id, phase and deadline; `-e docker_engine_recover=<run>` has the guard recover it |
| a `rollback-partial` run | refuses; after repairing what its record names, `-e docker_engine_acknowledge_run=<run>` runs `verify`, which marks it `rolled-back` only if every postcondition holds |
| a guard unit active or queued | refuses |
| Docker packages or state no guard run recorded | refuses; foreign Docker is never adopted or erased |

## Rollback

**Automatic.** Any failure the controller observes after `reserve` runs the
guard's `rollback <run>`; a failed observation sample makes the guard start it
itself; a lost controller is covered by the dead-man from `arm` on. The rollback
removes the start permission, stops `docker.socket` before `docker.service`,
cancels the guarded units' queued jobs, restores each family's FORWARD policy,
kills and stops the guarded units and `fabro-sandbox.slice` by cgroup, disables
the units, removes exactly Docker's firewall footprint, deletes `docker0` and
its veths, and compares the sysctls; it ends `rolled-back` only if every
postcondition holds. It never touches `k3s-agent.service` or its containerd, and
never erases `/var/lib/docker`, `/var/lib/containerd` or the packages.

**By hand**, only if the guard itself cannot run:

```bash
sudo rm -f /run/docker-engine-guard/allow-start
sudo systemctl stop docker.socket docker.service containerd.service
sudo systemctl disable docker.socket docker.service containerd.service
sudo iptables -P FORWARD <policy before>; sudo ip6tables -P FORWARD <policy before>
```

then remove Docker's chains by full rule specification as the guard does. Never
remove `/var/lib/docker-engine-guard/confirmed` on a committed host: after the
commit it is the only thing that lets the units start.

**Retiring the installation** on a committed host is not this role's: stop and
purge the three packages inside a drained window, remove the three drop-ins and
`/var/lib/docker-engine-guard`, and daemon-reload.

## Retirement

Retire the guarded transition when no factory host still needs Docker installed
beside a live k3s agent — when the Kubernetes sandbox backend runs the factory's
sandboxes as pods (the same condition that retires `docker_sandbox_slice`) — or
when the home-lab hosts move to the Talos fleet (the header of
`inventory/legacy.yml`). Until then a host that carries Docker installed by hand
rather than through this role is foreign to it, and is drift to be expressed in
the play.

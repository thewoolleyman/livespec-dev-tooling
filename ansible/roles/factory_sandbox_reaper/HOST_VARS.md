# `factory_sandbox_reaper` — per-host values for the inventory's `host_vars`

A periodic reaper for the Kubernetes sandboxes of Fabro runs that ended long ago.
Work-item `bd-ib-u5facl` (livespec-orchestrator-beads-fabro ledger).

**Why it exists.** Petri calls the kubernetes provider's `stop` (the pod is
deleted) at run end but never `delete`. The sandbox-driver-kubernetes record
store therefore keeps a `stopped` / `no-pod` record per run, and each run's node
workspace directory under `/srv/factory-workspaces` (about 0.5 G each) is never
removed. Measured on the cluster's server node: 170 such directories, 107 G free,
about 100 runs a day ending at the new cap, so roughly two days of runway. The
driver's own `lithos-sandbox --provider kubernetes sandbox delete <id>` clears
pod, workspace and record; this role runs it on a timer.

**Scope: the fleet instance only.** The reaper reads `fabro ps` from the
`fabro-server` instance (loopback `:32276`) and the `kubernetes` provider profile
of the Fabro account's HOME. The mi-homelab instance (`:32277`, namespace
`factory-mi-homelab`, its own `STATE_DIR` and `KUBECONFIG`), the candidate
instance and the `kubernetes-rust` provider kind (its own record store) are NOT
reaped by this role. Reaping them is a separate change.

## Retention rule (coordinator ruling, binding)

No ledger is reachable from the sandbox host, so retention is AGE-ONLY plus an
evidence guard. A sandbox is deleted only when every line holds; any doubt keeps
it, and every keep names its reason in the journal.

1. State is `stopped` (never running or starting).
2. The run is found in `fabro ps -a`. An unknown run is KEPT and reported.
3. The run is terminal (`succeeded` or `failed`) with a known end time
   (`start_time + wall_time_ms`).
4. The run ended at least `factory_sandbox_reaper_min_age_hours` (24) ago.
5. Origin holds no `refs/heads/needs-human/<livespec.dispatch.id>` for the run
   (one `git ls-remote <repo_origin_url> 'refs/heads/needs-human/*'` per
   repository). If that call fails, EVERY sandbox of that repository is kept
   and the failure is reported. A run with no `livespec.dispatch.id` label is
   kept.
6. At most `factory_sandbox_reaper_max_deletions` (50) deletions per pass,
   oldest-ended first; the rest wait for the next pass.

## Dry-run toggle

DRY-RUN IS THE DEFAULT. The hourly timer runs a report-only pass and writes
`DRY-RUN DELETE|KEEP <sandbox> run=<run> <reason>` lines plus a summary to the
journal. To enable deletion, set in the host's `host_vars` and apply:

```yaml
factory_sandbox_reaper_apply: true
```

The converge's own verification pass always runs report-only, whatever this is.

## Variables

| variable | default | meaning |
| --- | --- | --- |
| `factory_sandbox_reaper_enabled` | `false` | install the reaper on this host |
| `factory_sandbox_reaper_apply` | `false` | `true` makes the timer's pass delete; otherwise report-only |
| `factory_sandbox_reaper_min_age_hours` | `24` | age since the run ended before its sandbox is eligible |
| `factory_sandbox_reaper_max_deletions` | `50` | deletions per pass |
| `factory_sandbox_reaper_user` / `_group` | the Fabro host user and group | the account the pass runs as |
| `factory_sandbox_reaper_instance_unit` | `fabro-server` | which declared Fabro instance is reaped |
| `factory_sandbox_reaper_provider` | `kubernetes` | the `lithos-sandbox` provider profile |
| `factory_sandbox_reaper_on_calendar` | `hourly` | timer schedule |

```yaml
factory_sandbox_reaper_enabled: true
factory_sandbox_reaper_apply: false   # flip to true to delete
```

## Operator procedure

```bash
just ansible-drift ansible/fabro-hosts.yml --limit <host>
just ansible-apply ansible/fabro-hosts.yml --limit <host> --tags factory_sandbox_reaper
journalctl -u livespec-factory-sandbox-reaper.service --since -2h
```

Arming the timer restarts no Fabro server and touches no sandbox. Before setting
`apply: true`, read a few passes of `DRY-RUN DELETE` lines against `fabro ps -a`
and confirm every listed run is one you would remove. An `ERROR:` line (sandbox
list or `fabro ps` failed, or a delete failed) exits non-zero and shows as a
failed unit.

## Rollback

```bash
sudo systemctl disable --now livespec-factory-sandbox-reaper.timer
sudo rm -f /etc/systemd/system/livespec-factory-sandbox-reaper.{service,timer} \
           /usr/local/sbin/livespec-factory-sandbox-reaper
sudo systemctl daemon-reload
```

A deleted sandbox cannot be recovered; that is why deletion is off by default.

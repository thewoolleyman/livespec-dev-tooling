# reconcile_runs — the livespec `reconcile-runs` host timer, every tenant

The role is the one committed owner of the `reconcile-runs` timer on each host
that dispatches factory runs. It replaces the hand-run
`livespec-orchestrator-beads-fabro orchestrator-image/services/reconcile-runs/install.sh`.

## What it installs

- One service per tenant, `<unit>.service`, rendered from
  livespec-orchestrator-beads-fabro's committed `reconcile-runs.service`. The
  role reads that text from the host's own checkout
  (`reconcile_runs_orchestrator_checkout`). It substitutes `@PLUGIN_ROOT@`,
  `@PRIMARY_REPO@` and `@RUN_AS_USER@`. It puts
  `/usr/local/libexec/livespec-tenant-wrap.sh --` in place of the wrapper the
  unit text names, and sets `TW_FAMILY_WRAPPER` to
  `reconcile_runs_family_wrapper`.
- `/usr/local/libexec/livespec-tenant-wrap.sh`
  (`reconcile_runs_tenant_wrap_bin`), from `files/livespec-tenant-wrap.sh`. See
  "The tenant credential wrapper, read at run time" below.
- A dry-run twin per tenant, `<unit>-dry-run.service`, with the same user,
  checkout, wrapper and plugin root plus `--dry-run`. It has no timer.
- A drop-in per tenant service with the pass bound (`TimeoutStartSec`), the
  ordering after the previous tenant, and the dead-man marker (`ExecStartPost`
  touches `<reconcile_runs_state_dir>/<name>.last-success`). The role creates
  that marker when it enables a tenant, so telemetry that reads the markers
  never reports a newly enabled tenant `missing`. It never refreshes a marker
  that already exists.
- `reconcile-runs-sweep.service`, which `Wants=` and is ordered `After=` every
  enabled tenant's service. Starting it runs the enabled passes one at a time,
  in list order.
- `reconcile-runs.timer`, rendered from the orchestrator's committed
  `reconcile-runs.timer`, with `Unit=` pointed at the sweep. A drop-in sets
  `OnBootSec` and `OnUnitInactiveSec` from this role's variables.
- `reconcile-runs-staleness.{service,timer}` and
  `/usr/local/libexec/livespec-reconcile-runs-staleness`. Every five minutes
  the check journals `reconcile-runs-stale tenant=<name> age_seconds=<n>` for
  each enabled tenant whose marker is missing or older than
  `reconcile_runs_stale_after_seconds`.
  - With `reconcile_runs_staleness_on_failure` set (the dev host:
    `host-unit-alert@%n.service`), the unit fails, and so alerts, only when
    the stale set changes or the last alert is a day old.
  - With it empty (a host whose own telemetry reads the markers, such as
    hetzner-xubuntu), the unit fails on every stale check.

This role's drop-in is `10-reconcile-runs-role.conf`. The role also deletes
`60-tenant-wrap.conf` from each tenant's drop-in directory. That is the override
installed by hand on vmi3006760 on 2026-11-15 (livespec-dev-tooling-xowhol), and
the rendered unit now does the same job. The role deletes it in the same
converge that renders the unit, so no pass ever runs without the tenant
wrapper. On the dev host, role
`dev_host_memory_bounds` also places
`reconcile-runs.service.d/50-livespec-memory-bounds.conf`. That file sorts later,
so its memory bounds win over the unit text's `MemoryHigh` and `MemoryMax`. The
two roles write different files and leave each other's alone.

## The tenant credential wrapper, read at run time

Every tenant's ExecStart is

```text
/usr/local/libexec/livespec-tenant-wrap.sh -- /usr/bin/python3 <plugin_root>/scripts/bin/dispatcher.py reconcile-runs --repo <repo> --invoker timer:reconcile-runs --json
```

The script reads the tenant's committed `.livespec.jsonc` `credential_wrapper`
each time a pass starts. The tenant is `$TW_REPO`, or else the unit's
`WorkingDirectory`, which is the tenant's checkout. The script picks one of
three routes:

| Committed `credential_wrapper` | The pass runs as |
|---|---|
| none | `<family> -- <command>` |
| first element resolves (`realpath -e`) to the family wrapper's own file | `<argv...> <command>`, exactly as committed |
| anything else | `<family> -- env -u BEADS_DOLT_PASSWORD <argv...> <command>` |

`<family>` is `reconcile_runs_family_wrapper`, which defaults to
`/usr/local/bin/with-livespec-env.sh`. A relative first element resolves
against the checkout.

The match is by resolved path, not by name. A tenant's own
`./with-livespec-env.sh`, or a vendored copy, is a different file, so it
runs nested like any other tenant wrapper.

A family wrapper therefore runs with every hop it commits after its `--`. One
example is livespec-orchestrator-beads-fabro's route C, which re-exports the
livespec-ai organization App's credentials through `/bin/sh -c ... sh`
(orchestrator PR 5361). After the organization transfer, a bare family wrapper
mints the personal GitHub App, and livespec-ai repositories refuse that App
(bd-ib-ft426g).

The script never falls back to the family wrapper when it cannot use the
committed one. It exits 78 and runs nothing in two cases: the `.livespec.jsonc`
is unreadable, or its `credential_wrapper` is not a non-empty array of
non-empty strings. It also exits 78 when a wrapper it would run is not an
executable file. A failed pass then leaves the dead-man marker to age, so the
staleness check reports the tenant.

The role used to keep a copy of each tenant's argv here and asserted that the
copy ended in `--`. A copy goes stale as soon as the tenant changes its
wrapper, and route C ends in `sh`. A tenant entry that still carries
`credential_wrapper` is refused.

Read a tenant's route without running anything:

```bash
cd <repo> && /usr/local/libexec/livespec-tenant-wrap.sh --resolve
```

## Why one sweep instead of one timer per tenant

`dispatcher.py reconcile-runs` takes a single `--repo`. Its claim lane reads
only that repository's ledger, so each tenant needs its own pass, run against
its own checkout, through its own credential wrapper. A pass peaked at about
3.5 GB on the dev host (2026-11-11), so passes run one after another, never in
parallel.

A failed or timed-out pass is not restarted inside the sweep. The
orchestrator's unit text keeps `Restart=no`, and the next sweep, one interval
after this one ends, retries the tenant. With restarts, one hung tenant would
hold every later tenant for several 1800 s bounds instead of one.

## One enabled host at a time

Only the reconciler's CLAIM lane is host-fenced. A claim stamped by another
host is held as `owner-elsewhere`, and this host never releases it.

The RUN lane has no host fence. Orphan export and terminate, the
sandbox-container sweep and the ended-run collection all act on every run the
shared factories list, whichever host dispatched it. If two hosts reconcile at
once, both can take the same terminal action on the same run.

`reconcile_runs_enabled` MUST therefore stay `false` on every host but one,
until livespec-orchestrator-beads-fabro's bd-ib-mnkasb fences the run lane by
dispatching host. Lifting hetzner-xubuntu's hold for the dispatcher move waits
on that item.

## Variables

```yaml
# The hold: the only switch that starts the timers. With false, every service
# is installed, and reconcile-runs.timer and reconcile-runs-staleness.timer
# are disabled and inactive. Drift shows a timer someone enabled by hand.
reconcile_runs_enabled: false

# The tenants, in sweep order. No credential_wrapper: each pass reads the
# tenant's committed one at run time.
reconcile_runs_tenants:
  - name: livespec-orchestrator-beads-fabro
    unit: reconcile-runs            # optional; default reconcile-runs-<name>
    repo: /home/ubuntu/workspace/livespec-orchestrator-beads-fabro
  - name: hetzner-xubuntu-info
    repo: /home/ubuntu/workspace/hetzner-xubuntu-info
    enabled: false                  # optional per-tenant hold
    # plugin_root: <dir>            # optional; default reconcile_runs_plugin_root

reconcile_runs_orchestrator_checkout: /home/ubuntu/workspace/livespec-orchestrator-beads-fabro
reconcile_runs_plugin_root: "{{ reconcile_runs_orchestrator_checkout }}/.claude-plugin"
reconcile_runs_interval: 10min           # OnUnitInactiveSec: idle gap between sweeps
reconcile_runs_boot_delay: 5min
reconcile_runs_timeout_seconds: 1800     # one pass's bound
reconcile_runs_stale_after_seconds: 14400
reconcile_runs_staleness_on_failure: ""   # e.g. host-unit-alert@%n.service
reconcile_runs_family_wrapper: /usr/local/bin/with-livespec-env.sh
reconcile_runs_tenant_wrap_bin: /usr/local/libexec/livespec-tenant-wrap.sh
```

Use the explicit `/home/ubuntu/...` paths. These are system units, and in a
system unit `%h` names root's home. On the dev host, `/home/ubuntu/workspace`
is a link to `/data/projects`. The reconciler resolves both paths to the same
registered project.

Size `reconcile_runs_stale_after_seconds` to the sweep. It must cover every
enabled tenant's pass, plus the interval, plus one timed-out pass.

## Preconditions (asserted before any change)

The family wrapper (`reconcile_runs_family_wrapper`) must be an executable
file. Each declared tenant must have all of the following, held tenants
included:

- its checkout;
- its `.livespec.jsonc`;
- `<plugin_root>/scripts/bin/dispatcher.py`;
- a committed `credential_wrapper` that `livespec-tenant-wrap.sh --resolve`
  accepts. The role runs the script from its own copy, as the service account,
  in the tenant's checkout, so the wrapper is checked against what the
  checkout holds at converge time. A wrapper committed later is checked only
  when a pass runs. Use the dry-run twin to prove it then.

The orchestrator unit text must still carry every substitution point the role
rewrites. Without its wrapper, a timer would run `bd` with no
`BEADS_DOLT_PASSWORD`. Every pass would then fail as an absent tenant rather
than as an absent credential.

## Verify

```bash
systemctl list-timers reconcile-runs.timer reconcile-runs-staleness.timer --no-pager
systemctl show reconcile-runs-sweep.service -p Wants -p After
journalctl -u 'reconcile-runs*' -n 100 --no-pager
ls -l /var/lib/livespec/reconcile-runs/
```

Prove a held tenant would run. A dry run terminates and releases nothing, but
it does append one dry-run `reconcile-runs-pass` record to the tenant's
dispatch journal:

```bash
sudo systemctl start --wait <unit>-dry-run.service
journalctl -u <unit>-dry-run.service -n 50 --no-pager
```

## Out-of-band

- **Converging after a template change.** The unit text comes from the host's
  orchestrator checkout. After that checkout advances past a change to
  `orchestrator-image/services/reconcile-runs/`, run the drift report and
  converge again. If the change moves a substitution point, the converge
  refuses at its assert until this role is updated.
- **A tenant taken out of the list.** Its service, its dry-run twin and its
  marker stay on the host until an operator removes them. The sweep no longer
  wants it, so it never runs.
- **The OnFailure= alert unit.** On the dev host this is
  `host-unit-alert@.service`, from role `host_unit_alert`. The role
  refuses to install the staleness unit when the named alert unit is missing.
- **First sweep.** If a converge changes the timer or its interval on a host
  that is already enabled, the role starts one sweep. Without that sweep, a
  timer that was already running would never elapse again.

Converge on the dev host with:

```bash
/usr/local/bin/with-livespec-env.sh -- just ansible-drift ansible/dev-host.yml --tags reconcile_runs
/usr/local/bin/with-livespec-env.sh -- just ansible-apply ansible/dev-host.yml --tags reconcile_runs
```

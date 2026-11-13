# reconcile_runs — the livespec `reconcile-runs` host timer, every tenant

The role is the one committed owner of the `reconcile-runs` timer on each host
that dispatches factory runs. It replaces the hand-run
`livespec-orchestrator-beads-fabro orchestrator-image/services/reconcile-runs/install.sh`.

## What it installs

- One service per tenant, `<unit>.service`, rendered from
  livespec-orchestrator-beads-fabro's committed `reconcile-runs.service`. The
  role reads that text from the host's own checkout
  (`reconcile_runs_orchestrator_checkout`). It substitutes `@PLUGIN_ROOT@`,
  `@PRIMARY_REPO@` and `@RUN_AS_USER@`, and puts the tenant's committed
  `credential_wrapper` in place of the wrapper the unit text names.
- A dry-run twin per tenant, `<unit>-dry-run.service`, with the same user,
  checkout, wrapper and plugin root plus `--dry-run`. It has no timer.
- A drop-in per tenant service with the pass bound (`TimeoutStartSec`), a
  bounded restart on failure, the ordering after the previous tenant, and the
  dead-man marker (`ExecStartPost` touches
  `<reconcile_runs_state_dir>/<name>.last-success`).
- `reconcile-runs-sweep.service`, which `Wants=` and is ordered `After=` every
  enabled tenant's service. Starting it runs the enabled passes one at a time,
  in list order.
- `reconcile-runs.timer`, rendered from the orchestrator's committed
  `reconcile-runs.timer`, with `Unit=` pointed at the sweep. A drop-in sets
  `OnBootSec` and `OnUnitInactiveSec` from this role's variables.
- `reconcile-runs-staleness.{service,timer}` and
  `/usr/local/libexec/livespec-reconcile-runs-staleness`. Every five minutes the
  staleness unit fails, and journals `reconcile-runs-stale tenant=<name>
  age_seconds=<n>`, when an enabled tenant's marker is missing or older than
  `reconcile_runs_stale_after_seconds`.

## Why one sweep instead of one timer per tenant

`dispatcher.py reconcile-runs` takes a single `--repo`. Its claim lane reads
only that repository's ledger, so each tenant needs its own pass, run against
its own checkout, through its own credential wrapper. A pass peaked at about
3.5 GB on the dev host (2026-11-11), so passes run one after another, never in
parallel. A tenant that keeps failing uses up its start limit
(`reconcile_runs_start_limit_burst` starts in
`reconcile_runs_start_limit_interval`), and the sweep then moves on to the
next tenant.

Each host acts only on the claims it stamped itself. The reconciler holds a
claim stamped by another host as `owner-elsewhere`. So during a migration
overlap, both hosts run this role, and each one reconciles its own claims.

## Variables

```yaml
# The hold: the only switch that starts the timers. With false, every service
# is installed, and reconcile-runs.timer and reconcile-runs-staleness.timer
# are disabled and inactive. Drift shows a timer someone enabled by hand.
reconcile_runs_enabled: false

# The tenants, in sweep order. credential_wrapper is the tenant's committed
# .livespec.jsonc credential_wrapper argv, verbatim. A relative first element
# resolves against repo.
reconcile_runs_tenants:
  - name: livespec-orchestrator-beads-fabro
    unit: reconcile-runs            # optional; default reconcile-runs-<name>
    repo: /home/ubuntu/workspace/livespec-orchestrator-beads-fabro
    credential_wrapper: [/usr/local/bin/with-livespec-env.sh, "--"]
  - name: hetzner-xubuntu-info
    repo: /home/ubuntu/workspace/hetzner-xubuntu-info
    credential_wrapper: [./with-hetzner-xubuntu-credentials.sh, "--"]
    enabled: false                  # optional per-tenant hold
    # plugin_root: <dir>            # optional; default reconcile_runs_plugin_root

reconcile_runs_orchestrator_checkout: /home/ubuntu/workspace/livespec-orchestrator-beads-fabro
reconcile_runs_plugin_root: "{{ reconcile_runs_orchestrator_checkout }}/.claude-plugin"
reconcile_runs_interval: 10min           # OnUnitInactiveSec: idle gap between sweeps
reconcile_runs_boot_delay: 5min
reconcile_runs_timeout_seconds: 1800     # one pass's bound
reconcile_runs_stale_after_seconds: 14400
```

Use the explicit `/home/ubuntu/...` paths. These are system units, and in a
system unit `%h` names root's home. On the dev host, `/home/ubuntu/workspace`
is a link to `/data/projects`. The reconciler resolves both paths to the same
registered project.

Size `reconcile_runs_stale_after_seconds` to the sweep. It must cover every
enabled tenant's pass, plus the interval, plus one timed-out pass.

## Preconditions (asserted before any change)

Each declared tenant must have all of the following, held tenants included:

- its checkout;
- its `.livespec.jsonc`;
- an executable first element of its credential wrapper;
- `<plugin_root>/scripts/bin/dispatcher.py`.

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
- **First sweep.** If a converge changes the timer or its interval on a host
  that is already enabled, the role starts one sweep. Without that sweep, a
  timer that was already running would never elapse again.

Converge on the dev host with:

```bash
/usr/local/bin/with-livespec-env.sh -- just ansible-drift ansible/dev-host.yml --tags reconcile_runs
/usr/local/bin/with-livespec-env.sh -- just ansible-apply ansible/dev-host.yml --tags reconcile_runs
```

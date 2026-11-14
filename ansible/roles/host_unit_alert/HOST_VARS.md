# host_unit_alert — the OnFailure= alert for units this repository's roles install

A unit that a livespec-dev-tooling role installs names
`OnFailure=host-unit-alert@%n.service`. When it fails, the alert names that unit
and the host, and never calls it a backup failure.

It replaces dolt-server's `dolt-backup-alert@`, which these units used to
share. That handler reports every failure as a dolt backup failure. On
2026-11-14 at 12:12:34Z a stale reconcile pass reached the operator as
"dolt-backup run failed" while every backup was succeeding
(livespec-dev-tooling-l7f72q).

## What it installs

- `/usr/local/libexec/host-unit-alert` (`host_unit_alert_bin`). Given the
  failed unit's name, it sends:
  - one Honeycomb event to `HONEYCOMB_DATASET`: `name=host-unit-failure`,
    `source=host-unit-alert`, `outcome=unit_failure`, `unit`, `host`, `ts`;
  - one ntfy push titled `<host>: <unit> failed`, carrying the unit's last 30
    journal lines.

  It exits 1 when no channel accepted the alert, so an alert that reached nobody
  shows as a failed `host-unit-alert@` unit in the journal. Secrets reach `curl`
  on stdin, never in its argv.
- `/etc/systemd/system/host-unit-alert@.service`. It runs as root, so it can
  read the failed unit's journal, and reads its channels from
  `host_unit_alert_env_file`. It has no `[Install]` section, and nothing starts
  it except `OnFailure=`.

`dev-host.yml` runs this role before `honeycomb_trigger_recipients_check` and
`reconcile_runs`. Both check that their alert unit is installed.

## Preconditions

`host_unit_alert_env_file` MUST exist, and it MUST set `HONEYCOMB_INGEST_KEY` or
`ALERT_NTFY_TOPIC`. On the dev host it is dolt-server's
`/etc/doltdb/alert.env.local`, which that repository's
`scripts/setup-backup-alerts.sh` installs. The role cannot create it. Without
it every alert would exit 1 and reach nobody, so the role's first task checks
it. The check counts only the key names and reads no value. When it fails, the
apply stops naming the file, before any task changes the host.

## The Honeycomb trigger

Created 2026-11-14 through the v1 triggers API, in the dataset
`dolt-backup`, with the Configuration key that
`honeycomb_trigger_recipients_check` uses. dolt-server's
`runbooks/alerting.md` creates its triggers the same way.

| Trigger | ID | Query | Window (`query.time_range`) | Threshold | Freq |
|---|---|---|---|---|---|
| host unit failed | `2PdsuwyiqqL` | `COUNT where source=host-unit-alert AND outcome=unit_failure` | 900 s | `> 0` | 300 s |

Its recipients are the same operator emails as `dolt-backup run failed`
(`9HKs4W3UYN8`). That trigger counts `source in (backup-sync, onfailure)` and
never counts these events.

## Units routed here

- `reconcile-runs-staleness.service` (role `reconcile_runs`, through
  `reconcile_runs_staleness_on_failure` in the dev host's host variables).
- `honeycomb-trigger-recipients-check.service` (role
  `honeycomb_trigger_recipients_check`, `..._alert_target`).

dolt-server's own units (`dolt-backup`, `doltdb`,
`dolt-backup-oversized-verify`) keep `dolt-backup-alert@`. They belong to
dolt-server.

## Variables

```yaml
host_unit_alert_unit: host-unit-alert@.service
host_unit_alert_unit_dir: /etc/systemd/system
host_unit_alert_bin: /usr/local/libexec/host-unit-alert
# The channels' configuration. The dev host reuses dolt-server's alert file
# (Honeycomb ingest key, dataset `dolt-backup`, ntfy topic). A missing file is
# not fatal to the unit; every alert then exits 1.
host_unit_alert_env_file: /etc/doltdb/alert.env.local
```

## Converge and verify

```bash
/usr/local/bin/with-livespec-env.sh -- just ansible-drift ansible/dev-host.yml --tags host_unit_alert
/usr/local/bin/with-livespec-env.sh -- just ansible-apply ansible/dev-host.yml --tags host_unit_alert,honeycomb_trigger_recipients_check,reconcile_runs
systemctl show -p OnFailure reconcile-runs-staleness.service honeycomb-trigger-recipients-check.service
sudo systemctl start host-unit-alert@host-unit-alert-probe.service   # one event and one push
```

The probe's event must be counted by `2PdsuwyiqqL` and not by `9HKs4W3UYN8`.

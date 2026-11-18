# breakage_pass — the host timer for `dispatcher.py breakage-pass`

The role installs one `livespec-breakage-pass-<name>.service` and
`.timer` per entry of `breakage_pass_repos`. Each service runs the orchestrator's
`dispatcher.py breakage-pass --repo <repo>` from the orchestrator's own checkout
(`breakage_pass_plugin_root`), through role `reconcile_runs`'s
`livespec-tenant-wrap.sh`, so the pass runs under the repository's committed
`credential_wrapper`. The work item is `bd-ib-voazyv` (orchestrator tenant), slice
S3 of plan `ci-runtime-and-cost`.

## What the journal shows

`dispatcher.py breakage-pass` prints one verdict line per watched workflow and
prints nothing when the repository watches none. The runner
`/usr/local/libexec/livespec-breakage-pass` adds one closing line either way:

```text
breakage-pass-result repo=<name> rc=<n>
```

A pass that exits 0 refreshes `/var/lib/livespec/breakage-pass/<name>.last-success`.
Read the journal with:

```bash
journalctl -u 'livespec-breakage-pass-*.service' --since '-2h'
systemctl list-timers 'livespec-breakage-pass-*'
```

## Schedule

`OnUnitInactiveSec` is `breakage_pass_interval_minutes` (15) and the pass is bound
to `breakage_pass_timeout_seconds` (600), so two starts are never more than 25
minutes apart. The role refuses an interval plus timeout above 30 minutes.

## The hold, and what it does not cover

`breakage_pass_enabled` defaults to false: the units are installed and the timers
are left disabled and stopped. The host variables enable it; merging does not
apply it.

A repository is read only for the workflows it declares in
`.livespec.jsonc` `dispatcher.breakage_workflows`. A repository that declares
none prints no verdict line, only the closing result line. The role does not
declare any workflow for a repository.

The role needs `livespec-tenant-wrap.sh`, installed by `reconcile_runs`, and
refuses to run without it.

## Apply and revert

Apply through the drift-gated route, then read the first verdict back from the
journal:

```bash
just ansible-drift dev-host.yml --tags breakage_pass
just ansible-apply dev-host.yml --tags breakage_pass
journalctl -u 'livespec-breakage-pass-*.service' --since '-1h'
```

Revert by setting `breakage_pass_enabled: false` and applying again, or by
`systemctl disable --now livespec-breakage-pass-<name>.timer`.

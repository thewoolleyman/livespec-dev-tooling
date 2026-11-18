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

`OnUnitInactiveSec` is `breakage_pass_interval_minutes` (15). A pass is bound to
`breakage_pass_timeout_seconds` (600) and gets `breakage_pass_stop_timeout_seconds`
(90) to stop, so two starts are never more than 26.5 minutes apart. The role
refuses an interval plus timeout plus stop timeout above 30 minutes.

## Staleness

`livespec-breakage-pass-staleness.timer` runs every five minutes and reports a
repository with no successful pass within `breakage_pass_stale_after_seconds`
(3600). It runs role `reconcile_runs`'s staleness check, so the journal line reads
`reconcile-runs-stale tenant=<name> age_seconds=<n>`, where `<name>` is a watched
repository. With `breakage_pass_staleness_on_failure` set (the dev host:
`host-unit-alert@%n.service`) the unit fails, and so alerts, once per stale
episode. A new install seeds each marker so a repository is not reported missing
before its first pass.

## The hold, and what it does not cover

`breakage_pass_enabled` defaults to false, and false is the revert: no breakage
pass unit is left installed. The host variables enable it; merging does not apply
it.

A repository is read only for the workflows it declares in
`.livespec.jsonc` `dispatcher.breakage_workflows`. A repository that declares
none prints no verdict line, only the closing result line. The role does not
declare any workflow for a repository.

## The reader must carry the fix: COMMITTED IS NOT CONVERGED

The pass runs `dispatcher.py` from the orchestrator's own checkout
(`breakage_pass_orchestrator_checkout`) and reads the watched repository's committed
`.livespec.jsonc` from its checkout (`repo`). Nothing else advances either one: no unit,
timer, role or script on the host updates them, and `reconcile-runs.service` runs from
the same orchestrator checkout. Only a person's or a session's `git pull` does. A merge
to the orchestrator's master is therefore not a running fix.

So the runner syncs both before every pass: it fetches `origin/<branch>`
(`breakage_pass_branch`, `master`) and fast-forwards the checkout, and it FAILS CLOSED.
It refuses with exit 70, journals `breakage-pass-sync-refused ... reason=<reason>` and
the closing `breakage-pass-result ... rc=70` line, and writes no success marker (so the
staleness alert fires after an hour), when the path is not a git checkout
(`not-a-git-checkout`), is on a branch other than the configured one
(`on-branch-<name>`; a detached HEAD is the usual state), has modified tracked files
(`modified-tracked-files`; untracked files do not count), cannot fetch (`fetch-failed`),
holds commits `origin/<branch>` lacks (`not-fast-forward`), or cannot fast-forward
(`ff-failed`). A pass never runs on a stale or foreign reader. A successful sync journals
`breakage-pass-sync repo=<name> path=<path> head=<sha> origin=<sha> action=<current|advanced>`.

### A live dispatcher holds the pass back

The orchestrator checkout is also the dispatcher's launcher tree. A launcher past launch,
or a sourced lib (`config.sh`, `launch-lib.sh`), may not survive an in-place edit, because
bash reads a script incrementally. So a fast-forward under a running launcher is unsafe.
A pre-launch fast-forward is tolerated: `dispatch-dual.sh` detects a changed script and
re-execs keeping its ticket.

While any `dispatch-dual.sh` or `resume-capped.sh` process has the orchestrator checkout
as its cwd or its script path, the runner skips the WHOLE pass: no fetch, no
fast-forward, no pass. It does not run read-only on the current HEAD, because that HEAD
may predate a fix the pass depends on. It journals

```
breakage-pass-skipped repo=<name> reason=dispatcher-live pid=<pid> script=<basename> detail=<script-path|cwd|cwd-unreadable>
```

exits 0, writes no success marker and does not trip `OnFailure=`. The marker stops
advancing, so a skip that lasts past `breakage_pass_stale_after_seconds` (3600 s, about
four consecutive skips at the 15 minute interval) is reported by the staleness unit as
`reconcile-runs-stale`. A dispatcher that runs for hours therefore alerts after an hour.
That is deliberate: the pass is not running, and the alert says so.

Detection reads `/proc/<pid>/cmdline` and `/proc/<pid>/cwd` for every process; it never
uses `pgrep -f`, whose own argv would name the pattern. A process matches when one of its
first four argv words is named `dispatch-dual.sh` or `resume-capped.sh` and that script
path, or its cwd, lies under the checkout. A process whose cwd cannot be read and whose
script path does not name the checkout is treated as live (`cwd-unreadable`): the runner
cannot rule the tree out, so it fails closed. A process that vanishes mid-scan, or whose
cmdline cannot be read, names nothing and does not match. Only the orchestrator checkout is
guarded; the watched repository's checkout is not a launcher tree.
`LIVESPEC_BREAKAGE_PROC_ROOT` (default `/proc`) exists for tests only.

### Acceptance before the timer is enabled

After the converge and before `breakage_pass_enabled` is true, on the host, both of these
must exit 0 (substitute the orchestrator's merge commits for the fixes the pass depends on):

```bash
C=/home/ubuntu/workspace/livespec-orchestrator-beads-fabro
git -C "$C" fetch origin master
git -C "$C" merge-base --is-ancestor 5b2161340 origin/master    # #5513: breakage items file with manual admission
git -C "$C" merge-base --is-ancestor <#5518 merge commit> origin/master   # ci.yml is a watched workflow
```

The first runner pass then advances the checkout, and its `breakage-pass-sync` line names
`head` equal to `origin`. Read that line back before trusting the timer, and repeat the
two `merge-base --is-ancestor` checks against `HEAD` instead of `origin/master`.

## Apply order: `reconcile_runs` FIRST

`livespec-tenant-wrap.sh` and the staleness check are NOT currently installed on
the host. Role `reconcile_runs` installs them, and this role refuses to run without
them. So `reconcile_runs` must be reviewed and applied first, as its own step
(`just ansible-drift`, then `just ansible-apply`, with its own second look), and
only then `breakage_pass`. The role also refuses a repository whose checkout,
`.livespec.jsonc`, `dispatcher.py` or committed credential wrapper is unusable.

## Apply and revert

After `reconcile_runs` is applied, apply through the drift-gated route and read
the first verdict back from the journal:

```bash
just ansible-drift dev-host.yml --tags breakage_pass
just ansible-apply dev-host.yml --tags breakage_pass
journalctl -u 'livespec-breakage-pass-*.service' --since '-1h'
```

### Revert

Set `breakage_pass_enabled: false` and apply, or drop a repository from
`breakage_pass_repos` and apply. The role stops and disables each breakage pass
timer it no longer wants, removes every breakage pass unit file (the services, the
timers and the staleness pair), and reloads systemd. It does this by finding the
installed `livespec-breakage-pass-*` units, so a repository removed from the list is
cleaned up too. A second run changes nothing. The revert needs neither
`reconcile_runs` nor a usable repository.

It does not remove the runner script or the state directory, and it does not stop a
pass that is already running: that pass ends at its own bound, at most 10 minutes
plus the 90 s stop timeout. For an immediate stop on the host, as the role would
do, `systemctl disable --now livespec-breakage-pass-<name>.timer`.

## DoD status

The Definition of Done asks the journal to show each pass's verdict line. That is
unmet until a repository declares `dispatcher.breakage_workflows` in its committed
`.livespec.jsonc`; until then a pass prints only the closing result line.

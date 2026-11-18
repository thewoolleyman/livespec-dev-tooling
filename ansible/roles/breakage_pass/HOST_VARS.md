# breakage_pass — the host timer for `dispatcher.py breakage-pass`

The role installs one `livespec-breakage-pass-<name>.service` and
`.timer` per entry of `breakage_pass_repos`. Each service runs the orchestrator's
`dispatcher.py breakage-pass --repo <repo>` from the orchestrator's DEDICATED clone
(`breakage_pass_plugin_root`, inside `breakage_pass_orchestrator_checkout`), through role `reconcile_runs`'s
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

The pass runs `dispatcher.py` from, and reads the orchestrator's committed
`.livespec.jsonc` in, a DEDICATED clone of the orchestrator
(`breakage_pass_orchestrator_checkout`, default
`/home/ubuntu/.local/share/breakage-pass/livespec-orchestrator-beads-fabro`, set in
`host_vars/vps.yml`). The role creates it; only the runner advances it. It is NEVER the
shared workspace checkout (`breakage_pass_shared_checkout`,
`/home/ubuntu/workspace/livespec-orchestrator-beads-fabro`), which the factory's
dispatcher launches from: a launcher past launch, or a sourced lib (`config.sh`,
`launch-lib.sh`), may not survive an in-place edit because bash reads a script
incrementally, so a fast-forward under it is unsafe. Never sharing the tree satisfies the
dispatcher's earlier "skip the fast-forward while a launcher is live" ask more strongly
than a guard would, and without one: a guard would skip the pass nearly always, since the
factory keeps a launcher live most of each hour. The role refuses a clone that is, holds
or sits inside the shared checkout, and a watched repository that is the shared checkout
(`The dedicated orchestrator clone ... must be its own directory`).

Merging to the orchestrator's master is therefore not a running fix until the runner's
next pass advances the dedicated clone.

The runner syncs before every pass: it fetches `origin/<branch>`
(`breakage_pass_branch`, `master`) and fast-forwards the dedicated clone, and each other
watched repository's checkout (a repository that is not the orchestrator), and it FAILS
CLOSED. It refuses with exit 70, journals `breakage-pass-sync-refused ... reason=<reason>`
and the closing `breakage-pass-result ... rc=70` line, and writes no success marker (so
the staleness alert fires after an hour), when the path is not a git checkout
(`not-a-git-checkout`), is on a branch other than the configured one
(`on-branch-<name>`; a fresh clone is on it, a detached HEAD is also accepted), has
modified tracked files (`modified-tracked-files`; untracked and ignored files do not
count), cannot fetch (`fetch-failed`), holds commits `origin/<branch>` lacks
(`not-fast-forward`), or cannot fast-forward (`ff-failed`). A pass never runs on a stale or
foreign reader. A successful sync journals
`breakage-pass-sync repo=<name> path=<path> head=<sha> origin=<sha> action=<current|advanced>`.

### How the role creates the clone

On a converge with `breakage_pass_enabled: true` the role, before it checks the pass's
inputs: reads the origin URL (`breakage_pass_orchestrator_origin_url`, or the `origin`
remote of the shared checkout when that is empty) and refuses a URL that embeds a
password or token; creates the parent directory; and runs `git clone` as the pass's user
with `GIT_TERMINAL_PROMPT=0`. The clone authenticates with what that user already has (the
host's `gh auth git-credential` helper or an ssh key); nothing is embedded. It is never
re-cloned (`creates:`), so a second converge changes nothing. With no access, it fails with
`Could not clone <url> ... Check gh auth status`. It never runs `bd init`.

A clone lacks the gitignored `.beads/metadata.json` (measured: a fresh clone answers
`bd list` with "no beads database found"; with the file copied in, `bd list` reads the
right tenant). The role copies it from `breakage_pass_beads_metadata_source` (default the
shared checkout's) with `force: false`, mode 0600, so an existing file is never
overwritten, and refuses a missing source or one holding a key that names a secret (the
file holds backend, database name, host, port and user, no password). It also sets
`.beads` to mode 0700, which `bd` recommends. Everything else the pass needs is tracked:
`.livespec.jsonc`, the vendored `_vendor` libraries and the plugin scripts. The clone
needs no `.venv`: the pass runs under `/usr/bin/python3`.

Under `just ansible-drift` (check mode) the clone is only planned, so the preflight checks
that read the clone's inputs are skipped while it does not exist yet; drift reports the
creation instead.

### Acceptance before the timer is enabled

After the converge and before `breakage_pass_enabled` is true on the host, both of these
must exit 0 against the DEDICATED clone, never the shared checkout:

```bash
C=/home/ubuntu/.local/share/breakage-pass/livespec-orchestrator-beads-fabro
git -C "$C" fetch origin master
git -C "$C" merge-base --is-ancestor 5b2161340be4e875050b6866805967e8bfaeec52 origin/master  # #5513: breakage items file with manual admission
git -C "$C" merge-base --is-ancestor b1f671938a9745962d6046e2c1bed5621fa66908 origin/master  # #5518: ci.yml is a watched workflow
```

The first runner pass then advances the clone, and its `breakage-pass-sync` line names
`head` equal to `origin`. Read that line back before trusting the timer, and repeat the
two `merge-base --is-ancestor` checks against `HEAD` instead of `origin/master`. This
read-back supersedes the text of livespec-dev-tooling#5021, which names the shared path.

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

# incident_observer

Converges one fleet host to a running **independent released incident
observer** — the controller process `docs/incident-observer-service.md`
specifies, whose `/current` and `/admitted` answer the incident CI entrance's
read-only query (`docs/incident-ci-entry.md`). Work item
`livespec-dev-tooling-w7n3ad`, plan `expedited-incident-response-flag`.

```bash
/usr/local/bin/with-livespec-env.sh -- just ansible-drift ansible/dev-host.yml --tags incident_observer,tailscale_serve
/usr/local/bin/with-livespec-env.sh -- just ansible-apply ansible/dev-host.yml --tags incident_observer,tailscale_serve
```

Both run under the credential wrapper, because the role writes the three secret
files from the control node's projected environment (below). A bare run refuses
at its first task and names the variables; nothing is written.

## The host, and why

The role runs on the `dev_hosts` group, whose one member is **`vps`**. Of the
four inventory hosts it is the only one that already runs always-on fleet
control services behind a tailnet TLS front — `tailscale serve` publishes its
two Fabro servers and two further loopback services at `vps.perch-rudd.ts.net`
— and that is in neither `ci_pool` (the k3s CI nodes, whose runners are the
observer's callers) nor `sandbox_hosts` (the Fabro factory host `gmktec-xubuntu`,
which runs the petri server but executes candidate code in its sandboxes).
The controller's directory must live outside candidate checkouts, the tenant,
credential projection, factory and gates namespaces (`docs/incident-observer.md`),
which rules out every CI node and every sandbox host whatever their TLS posture.

## Which URL is tailnet-internal and which must be public

| Route | Caller | Reach |
| --- | --- | --- |
| `POST /current`, `POST /admitted` (query token) | the incident CI job on a self-hosted k3s runner | **tailnet-internal**: `https://vps.perch-rudd.ts.net:8765`, the `tailscale serve` mapping `vps` declares in `host_vars` (`:8765 -> http://127.0.0.1:8765`). The runners sit inside the tailnet, so nothing here needs a public address. |
| `POST /arm`, `/bind`, `/invalidate-ci` (control token) | the maintainer's independent host | tailnet-internal, the same mapping. |
| `POST /callback` (GitHub HMAC) | GitHub's `workflow_job` webhook delivery | **must be public**: `https://vps.perch-rudd.ts.net:10000/callback`, a path-scoped Tailscale Funnel the role publishes (`tailscale funnel --bg --https=10000 --set-path=/callback http://127.0.0.1:8765/callback`). Only that path is public; a request to any other path on port 10000 is not proxied, and the tailnet-only mapping above is untouched. Funnel admits ports 443, 8443 and 10000 only, and 8443 is already served here. |

## What the apply converges

- the system account `livespec-incident` (home `/var/lib/livespec-incident`,
  no login), distinct from the candidate account whose uid controller.json
  names (`incident_observer_candidate_user`, `ubuntu` on `vps`);
- `/opt/livespec-incident/venv` on the system interpreter, with the **released**
  `livespec-dev-tooling` tag installed from GitHub (`incident_observer_release`),
  never from a checkout on the host, re-installed only when the venv serves a
  different version;
- `/opt/livespec-incident/reader`: the orchestrator plugin at its released tag
  (`incident_observer_reader_release`), whose `incident_authority.py` is the
  canonical `read-current` reader the manifest names;
- `/var/lib/livespec-incident/reference`: the independent reference clone of the
  observed repository at the released tag, owned by the controller account and
  held at mode 0750 (the loader refuses a group- or other-writable repository,
  and the account's own umask would leave the clone 0775), with
  a `livespec-incident-reference-fetch.timer` (every 5 min) keeping its objects
  current for the inverse. Its `.beads/` directory is held at 0700 and carries
  the gitignored `.beads/metadata.json` ledger pointer, rendered by the role
  from the clone's committed `.beads/config.yaml` plus the tenant's
  server-stable `project_id` (`incident_observer_tenant_project_id`): `bd`
  resolves its workspace from that pointer, not from `config.yaml`, and the
  first `POST /arm` (2026-11-06, 16:27Z) refused `canonical pre-merge authority
  unavailable` because the clone had no pointer and the reader's first `bd
  show` answered `no beads database found`. The port is written as a JSON
  integer: without it `bd` dials port 0;
- `/var/lib/livespec-incident/receipts` (mode 0700, outside the clone) with the
  recovery journal directories beneath it;
- the three secret files (`/etc/livespec-incident/{webhook,control,query}-secret`,
  mode 0600, owned by the controller account), written from the control node's
  environment under `no_log` — see the first maintainer step;
- `/etc/livespec-incident/reader.env` (mode 0600, owned by the controller
  account): `BEADS_DOLT_PASSWORD=…`, the canonical reader's tenant credential,
  written under `no_log` from the same wrapper-projected variable the control
  node already carries, and loaded by the unit's `EnvironmentFile=`. The reader
  subprocess inherits it, so it reads the tenant with credential projection
  inside the controller's own account — the shape the spec allows under
  `NoNewPrivileges`; the sudo wrapper is refused by the loader and the unit
  alike. The tenant's host and port (`127.0.0.1:3307`, the dolt-server on this
  host) come from the reference clone's committed `.beads/config.yaml`, not
  from this role;
- `/etc/livespec-incident/controller.json` with exactly the nine keys the loader
  demands, every value a host fact (paths from the role's layout, the candidate
  uid from `getent`, the repository and port from the role's defaults), plus the
  optional tenth key `target_branch` only when `incident_observer_target_branch`
  is set (empty by default, so production keeps master and an unchanged file);
- `/etc/livespec-incident/released-installation.json`, rendered **on the host by
  the serving interpreter** with `files/render_released_installation.py`: the
  package digest over every installed `.py` in the loader's own order, the
  released tag and its commit (read from the reference clone), the reader and
  principal argv, the SHA256 of every executable they name plus the resolved
  interpreter, and the required master leaf jobs: every leaf job and matrix leg
  `ci-green` needs, spelled as the `workflow_job` event reports it, then
  `ci-green` itself (`incident_observer_required_jobs`; the revert fires at the
  first failing leaf, not when the aggregate concludes). The repository's
  `tests/livespec_dev_tooling/test_incident_observer_role.py` holds the renderer
  to the loader's algorithm, and
  `tests/livespec_dev_tooling/test_incident_observer_job_universe.py` holds the
  job list to `ci-green`'s `needs:`;
- an isolated `ControllerInstallation.load` of the whole installation **as the
  controller account** before the unit is written, so a refusal names the apply
  rather than a unit exiting 2;
- `livespec-incident-observer.service`: the packaged provisioning template with
  `NoNewPrivileges=true`, `ProtectSystem=strict`, `ProtectHome=true`,
  `PrivateTmp=true`, `UMask=0077`, the cleared injection variables and a fixed
  `PATH`, executing
  `/opt/livespec-incident/venv/bin/python -I -m livespec_dev_tooling.incident_observer_service --config /etc/livespec-incident/controller.json`
  on loopback port 8765;
- a probe that `POST /current` without the query token is refused (403), which
  is also the proof the unit passed its installation check and bound its socket;
- the path-scoped Funnel for `/callback` (above), published only when the
  node's funnel status does not already carry it **and the tailnet grants this
  node the `funnel` attribute**. The role reads the grant from the node's own
  capability map first. Without it `tailscale funnel` exits 0 and publishes
  nothing (measured on `vps`, 2026-11-06), so the role withholds the publish,
  says in the run output that the path is not public and whose step that is,
  and still converges the listener and its tailnet front. After a publish it
  reads the funnel status back and refuses an apply whose path is not there.

A second apply over a converged host reports no change: the install is gated on
the served version, both clones sit at tags, every file is compared by content,
the manifest is rendered to a register and installed only when its bytes differ,
and every restart lives in a handler. A `--check` on a host the role has never
reached writes nothing and says which steps an apply would perform.

The principal the manifest names is the packaged
`incident_recovery_principal_service.py`, the live recovery principal
(`docs/incident-recovery-principal.md`, work item `livespec-dev-tooling-7536jf`).
It acts on the forge only as the dedicated recovery GitHub App, and it reads that
App's credential from `/etc/livespec-incident/recovery-app.json` (mode 0600, owned
by the controller account). The role writes that file at apply, under `no_log`,
when the control node's wrapper projects both `LIVESPEC_RECOVERY_APP_ID` and
`LIVESPEC_RECOVERY_APP_PRIVATE_KEY`. When either is missing, the role writes
nothing and says so in the run output. The principal then refuses every forge
operation as `recovery-app-credential-absent`, while `lookup` and `conflict`
still answer. The observer process reads the same file for its own forge reads
and mints only a `contents: read` token (`docs/incident-observer-service.md`). The
canonical reader never holds the key.

## Running the operator entrance on this host

`incident_original_run_entry` needs no extra provisioning. It runs as the controller
account from the installed venv, and reads everything from the protected files this
role already writes: `controller.json`, the manifest's reader, `reader.env` and
`recovery-app.json`.

```bash
sudo -u livespec-incident -H /opt/livespec-incident/venv/bin/python -I \\
  -m livespec_dev_tooling.incident_original_run_entry collect \\
  --config /etc/livespec-incident/controller.json \\
  --revert-sha SHA --expected-graph /path/readable/by/that/account.json
```

## What a first apply does that later applies do not

A first apply creates the account, the venv and the release, and only then can
it render the manifest, load the installation and import the service module.
The role re-reads "is it installed" after it installs, so all three run on the
first apply and the unit starts verified; a dry run creates nothing and keeps
its pre-read answer. The role installs the release and nothing beside it: the
released distribution declares the two packages its vendored `returns` imports
from outside itself (`typing-extensions` and `anyio`), so the release is
installed with its declared dependencies. The incident CI job installs it the
same way.

## Maintainer-only steps

Each is outside what a committed, reversible change can do; the reason follows.
Steps 2 and 3 were performed by the maintainer on 2026-11-05 against exactly the
values this role renders; they are recorded here so the next host or rotation
knows what to redo.

1. **Create the three secrets in 1Password, environment
   `fufpvkvatwkmqjzvilvfnemsue` (the livespec environment the installed
   `/usr/local/bin/with-livespec-env.sh` projects), named
   `LIVESPEC_INCIDENT_WEBHOOK_SECRET`, `LIVESPEC_INCIDENT_CONTROL_SECRET` and
   `LIVESPEC_INCIDENT_QUERY_SECRET`, each at least 32 bytes and all three
   distinct, then run the apply through the wrapper** (the two commands at the
   top). Reason: the secrets must never exist in this repository, and only that
   environment is what the wrapper delivers to the control node, so that is the
   one place the apply can read them from. The reader's `BEADS_DOLT_PASSWORD`
   is already in that environment; nothing new is created for it.
2. **Done 2026-11-05 — the GitHub `workflow_job` webhook on
   `thewoolleyman/livespec-dev-tooling`**, delivering to
   `https://vps.perch-rudd.ts.net:10000/callback` with the webhook secret and
   JSON content type. Reason it is maintainer-held: a webhook subscription is a
   repository GitHub setting an agent never writes. The public ingress itself
   is the role's funnel task. **Not done as of 2026-11-06 on `vps`: the
   tailnet policy does not grant this node the `funnel` attribute**, so the
   role publishes nothing and says so (above), and GitHub's deliveries to that
   URL fail until it is granted. Granting it (a `nodeAttrs` entry giving this
   node `funnel` in the tailnet policy file) is a tailnet-admin step an agent
   never takes; run the apply again afterwards and it publishes the path.
3. **Done 2026-11-05 — the repository variable `LIVESPEC_INCIDENT_OBSERVER_URL`
   = `https://vps.perch-rudd.ts.net:8765` and the repository secret
   `LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN` = the query secret's exact bytes.**
   Reason: the trusted workflow supplies both to the incident CI job
   (`docs/incident-ci-entry.md`), and repository variables and secrets are
   maintainer-held GitHub settings this repository's tooling never writes.

4. **Not done — provision the recovery GitHub App (plan note 006, GO-1).**
   Create a GitHub App used only for incident recovery, never the
   factory/publishing bot. Give it `contents: write` on
   `thewoolleyman/livespec-dev-tooling` and install it there. Put its numeric id
   and private key in the livespec 1Password environment as
   `LIVESPEC_RECOVERY_APP_ID` and `LIVESPEC_RECOVERY_APP_PRIVATE_KEY`. Add a
   master ruleset whose bypass list names only that App, then run the apply
   again. Reason it is maintainer-held: it grants a principal unchecked writes
   to master, and App, secret and ruleset settings are GitHub and 1Password
   state that this repository never writes. Rollback: delete the ruleset or its
   bypass entry, or suspend the installation. Classic protection is untouched
   throughout.

No separate step remains for the canonical reader's credential: the role
projects it at apply (`reader.env` above). Until step 1's apply has run, the
observer does not exist and the incident CI job's reads refuse, which is the
safe state: an observer that is not reachable admits nothing.

## What the role asserts and never provisions

- The three secret environment variables and `BEADS_DOLT_PASSWORD` on the
  control node (step 1).
- A declared `incident_observer_candidate_user` for the host.
- The host's `tailscale serve` mapping is converged by the `tailscale_serve`
  role from the same `host_vars`, not here; `dev-host.yml` runs it right after
  this role so one apply brings the listener up and fronts it.
- The GitHub webhook, the repository variable and secret (steps 2–3) and the
  tailnet policy's `funnel` grant are named, never faked as checks.

## The scratch-branch instance

A host proof that must exercise the recovery principal off master (the thhgeg
moved-head and restart proofs) needs a SECOND observer installation bound to a
scratch branch, while production stays on master. The principal takes no
branch argument: it reads `target_branch` from the controller.json its
observer's manifest names as the principal argv's last element. So the scratch
instance is the same role applied with another variable set,
`vars/scratch.yml`, through `ansible/incident-observer-scratch.yml`
(livespec-dev-tooling-32qdja):

- its own `/etc/livespec-incident/controller-scratch-<name>.json`, with
  `target_branch: incident-scratch/<name>-proof`, in production's directory
  because the principal reads `recovery-app.json` from the config's parent;
- its own `released-installation-scratch-<name>.json`, whose principal argv
  ends in the scratch controller.json;
- its own state directory and reference clone under
  `/var/lib/livespec-incident/scratch-<name>/`, loopback port 8766, and units
  `livespec-incident-observer-scratch` and
  `livespec-incident-reference-fetch-scratch` (service and timer).

`<name>` defaults to `thhgeg`; `-e incident_observer_scratch_name=<name>` moves
every path and the branch together, and `-e
incident_observer_target_branch=incident-scratch/<x>` names the branch alone.
The name must be one segment of lowercase letters, digits and hyphens, and
every path and unit name is FIXED by it: an override of a single path refuses.

### Separation from production is enforced by code, not by the OS

Both instances run as the same controller account, and the scratch unit's
`ReadWritePaths` is the controller's home, which holds production's receipts.
Nothing in systemd or the filesystem stops the scratch process, or a mistyped
override, from reaching production's state. `tasks/scratch_preflight.yml` is
what does, and both the apply and the teardown run it before they write, stop
or remove anything:

- scratch mode is on, the name is one safe segment, the branch starts with
  `incident-scratch/`, and the port is not production's;
- every shared value (home, configuration directory, `/opt` install, venv and
  reader directories, account, the three secret files, `reader.env`,
  `recovery-app.json`, repository) is exactly production's;
- every per-instance path is exactly the layout the name fixes;
- after `realpath` normalization (a trailing slash, `..`), no scratch path is,
  sits inside or contains any path production owns. Production's home and
  configuration directory are parents a scratch path may sit inside, never be
  or contain;
- on the host, read as root without following links, no scratch path is a
  symbolic link. The control node's `realpath` runs as the operator, who
  cannot enter production's 0750 home, so it cannot see a link planted there.

Each assert spells production's paths and the scratch layout inline, from
fixed literals plus the validated name. An `-e` override outranks every
variable a play, a vars file or a fact can set, so no intermediate variable
stands between an override and a verdict.

The role runs the preflight whenever ANY scratch-identifying variable is set:
the scratch flag, the name, or a target branch. Its first assert refuses
scratch variables without scratch mode, so `-e incident_observer_scratch=false`
on the scratch playbook cannot fall through to production's path. Both scratch
playbooks also refuse, as their first task (`pre_tasks`), unless scratch mode is
on and a scratch name and an `incident-scratch/` branch are set.

**Operator boundary: `--start-at-task`.** Ansible cannot stop an operator from
starting a play past its refusals. Never pass `--start-at-task` to either
scratch playbook. What still holds when one is passed: every production-shared
write (apt, the account, the shared directories, the venv, the release
install, the reader clone, the secrets, `reader.env`, `recovery-app.json`, the
manifest renderer) and every funnel task carries its own guard on the task
itself. That guard refuses whenever the scratch flag, the scratch name or a
target branch is set, so production's public `/callback` funnel is never
re-pointed and no shared file is written. The scratch instance's own writes are
then unvalidated, which is why the flag is forbidden. The teardown's stops and
removals depend on facts only its preflight sets, so starting past them fails
on an undefined variable before acting.

The scratch apply then writes none of production's shared installation: no
apt package, account, shared directory, venv, release install, reader clone,
manifest renderer, secret, `reader.env` or `recovery-app.json`. It publishes no
funnel and never restarts production's unit. It also refuses when the shared
venv does not already serve `incident_observer_release` (converge production
first). Every refusal comes before the scratch apply's first write, so its
"Nothing has been written" is true. The observer and its principal then refuse
every action whose registered branch is not the scratch branch
(livespec-dev-tooling-thhgeg).

### How the scratch instance binds and observes: no webhook

Only production has the public funnel, so GitHub's one webhook delivers every
`workflow_job` event, scratch-branch runs included, to PRODUCTION. Production
answers each scratch job `ignored` and writes nothing, because its
controller.json names no target branch and so serves master
(`tests/livespec_dev_tooling/test_incident_observer_role_production_ignores_scratch.py`).
The scratch observer receives no delivery at all.

- **Binding works without a webhook.** `POST /bind` on the scratch loopback
  port is called by the operator with the merge sha and the id of `ci.yml`'s
  push run on the scratch branch. The observer then reads `pulls/<n>` and
  `actions/runs/<id>` from GitHub itself, as the recovery App, through
  `recovery-app.json` beside the scratch controller.json. That push run exists
  only once `ci.yml` runs on `incident-scratch/**` pushes
  (livespec-dev-tooling-7w757z).
- **Recovery works without a webhook.** `POST /recover` and `POST /reconcile`
  are operator-called on the loopback port and drive the scratch principal.
- **First-failure observation is MISSING.** The observer has no forge-polling
  path for `workflow_job` outcomes: only a `/callback` delivery starts the
  revert of a failing leaf. A scratch observer therefore never acts on a
  failing scratch CI job by itself. The thhgeg proofs do not need it, because
  they trigger recovery through `/recover`, but a proof of first-failure
  recovery on a scratch branch would need a polling path built first.

```bash
/usr/local/bin/with-livespec-env.sh -- just ansible-drift ansible/incident-observer-scratch.yml
/usr/local/bin/with-livespec-env.sh -- just ansible-apply ansible/incident-observer-scratch.yml
```

A drift run before the first apply has no scratch reference clone yet. It
withholds the clone's reads and says so, rather than failing, and the apply
clones it.

The committed teardown is `ansible/incident-observer-scratch-teardown.yml`
(`tasks/scratch_teardown.yml`). It runs the same preflight first. Then it:

- stops and disables the scratch observer and its fetch timer;
- removes their unit files, the timer's stamp, the scratch controller.json and
  the scratch manifest, then reloads systemd and clears any failed state for
  the scratch units;
- reads back production's unit, controller.json, manifest, fetch service and
  timer, `recovery-app.json`, `reader.env`, the three secrets, its main
  directories and the full listing (with checksums) of its state directory.
  It fails loudly if any moved.

It keeps `/var/lib/livespec-incident/scratch-<name>/` as the evidence store
unless run with `-e incident_observer_scratch_teardown_purge=true`. A purge
removes only `<production home>/scratch-<name>`, spelled from the validated
name, never from a path an override could move. The teardown loads
`vars/scratch.yml`, so run it BEFORE a change that removes that file merges.

```bash
/usr/local/bin/with-livespec-env.sh -- just ansible-apply ansible/incident-observer-scratch-teardown.yml
```

With the scratch instance absent, the production apply renders controller.json,
the manifest's renderer argv, the observer unit and the fetch service and timer
byte-identical to the role before the instance existed;
`tests/livespec_dev_tooling/test_incident_observer_role_production_unchanged.py`
holds that against fixtures matching ansible-core 2.21.4's own output.

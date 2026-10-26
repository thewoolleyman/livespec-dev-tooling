# `fabro_server` host variables

The per-host and per-instance values this role needs, transcribed from
`fabro-hosts` `services/fabro-server/hosts/*.env` and reconciled against the
live hosts on 2026-09-09. **These are not merged into the inventory yet** —
this file exists so the role can be reviewed without touching
`ansible/inventory/legacy.yml`, which another agent owns. Merge each block
below into that host's `host_vars` entry.

Four of the five instances here are the four `hosts/*.env` files: two hosts, two
instances each. The fifth is `hp-xubuntu`'s `fabro-server-candidate`, which never
had a values file — it was hand-installed for the fabro-currency cutover and is
declared here so the play owns it. Nothing else in the role needs configuring.

## Targeting

`hp-xubuntu` is in the inventory's `sandbox_hosts` group and `vps` is in
`dev_hosts`, so a playbook that installs every Fabro instance has to name both
groups (`hosts: dev_hosts:sandbox_hosts`) or the inventory needs a group that
holds exactly these two. That is an inventory decision, not a role one.

Note that `vps`'s inventory name is its **tailnet label**; its kernel hostname
is `vmi3006760`. The shell installer had to know both, because it compared the
values file's canonical host against `hostname -s` and against
`tailscale status --self --json`. No task in this role reads either name: the
values reach the right host because they are that host's `host_vars`.

## The playbook

The role installs one instance per invocation, so the play loops it:

```yaml
---
- name: Install the Fabro dark-factory servers
  hosts: dev_hosts:sandbox_hosts
  gather_facts: true
  tasks:
    - name: Install every Fabro instance on this host
      ansible.builtin.include_role:
        name: fabro_server
      loop: "{{ fabro_server_instances }}"
      loop_control:
        loop_var: fabro_server_instance
        label: "{{ fabro_server_instance.unit_name }}"
```

`include_role` rather than a `roles:` entry, because the role has to run once
per instance and a `roles:` entry runs once per host.

## Optional per-instance axes

Every other key of an instance mapping must be spelled out — the role refuses a
mapping that misses one, because an instance that inherited `unit_name`,
`home_dir` or `port` would silently share the fleet server's state. These eight
are the exception, and they are safe to default for one reason: omitting one
cannot make two instances collide. It only keeps the behaviour the instance had
before the axis existed.

| axis | default | what naming it does |
|---|---|---|
| `binary_path` | `fabro_server_host_home` + `/.fabro/bin/fabro` | the Fabro binary this instance's unit starts. Naming one runs a **different build** from the instance's siblings on the same host, which is what a cutover rehearsal is. The role never builds it; the preflight stats whatever this axis resolves to, so a declared-but-absent binary is refused before any file is written — unless `binary_source` below tells the role to install one. |
| `binary_source` | empty — the role leaves whatever is at `binary_path` alone | an **absolute control-node path** holding the build this instance should run. Declared, the role installs that file at `binary_path`; omitted, the instance's binary is out-of-band state the role only ever reads. |
| `binary_sha256` | empty — the role leaves whatever is at `binary_path` alone | the sha256 `binary_source` must hash to. Declared together with `binary_source` or not at all; the role refuses the pair half-spelled, and refuses a source that does not hash to this digest **before** it reads the factory host. |
| `home_env` | `fabro_server_host_home` | the unit's `Environment=HOME`. Independent of `home_dir`: `home_dir` is the state root the server is POINTED at with `--storage-dir` and `--config`, while this is the `HOME` its process and its CLI resolve `~/.fabro` against. |
| `environments` | `[]` — the role leaves whatever the instance's server holds alone | the instance's **sandbox environment catalog**: a list of entries, each spelling an `id`, a docker `image`, a `cpu` count and a `memory` size. The one axis that is not a file this role renders — a sandbox environment is server-managed state behind the instance's `/api/v1/environments` API. See "The sandbox environment catalog" below. |
| `vault_secrets` | `[]` — the role leaves the instance's vault alone | vault entries the instance must hold: a list, each spelling a `name`, a `type` (`token` or `file`), an optional `description`, and either `from_controller_env` (the control-node variable a real credential is read from) or `value` (a committed non-secret placeholder). Each name the vault lacks is created once the server answers; a name it holds is never read, compared or overwritten. See "State the role provisions on a host that has none" below. |
| `service_state` | `running` | `stopped` parks the instance in version control — unit, drop-in, `settings.toml` and state directory all KEPT on the host, the unit stopped and disabled, the restart handler never fired for it and the running-server verification skipped. Bring it back by flipping the word and re-applying. Refused while the instance is carrying runs, by the quiet-server guard that gates a restart. |
| `sandbox_providers` | `{}` — the role renders no `[server.sandbox.providers]` table, so settings.toml is byte-identical to its pre-axis render | the third-party **sandbox-driver plugins** this instance may launch: a mapping from a provider kind (a lower-case name that is not `local`, `docker` or `daytona`) to that plugin's absolute `path`, its 64-hex-digit `sha256`, optional `args` and `inherit_env` lists, an optional `env` mapping of variables set for the plugin process, and the `process_spec` the plugin's sandboxes are built from (`image`, `cpu_cores`, `memory_mb`). Each becomes one `[server.sandbox.providers.<kind>]` table with `enabled = true`. Rendered only when settings.toml is written (`fabro_server_manage_settings`). An `environments` entry may then name that kind as its optional `provider`, which otherwise defaults to `docker`. See "Sandbox-driver plugin providers" below. |

An instance that omits `binary_path` and `home_env` renders a unit **byte-identical**
to the unit this role rendered before the two axes existed — asserted against a
captured pre-axis unit by
`tests/consumer/test_fabro_instance_axes_scenario.py`. That is the property that
makes them safe to add: declaring a second instance that needs its own build
does not rewrite the live fleet factory's unit as a side effect.

### How the binary install actually behaves

`binary_source` and `binary_sha256` are the axes that let the play express a
build placement. They do not make the role a builder: it still never compiles or
downloads anything. What it will do is **carry a build the operator has already
staged on the control node**, which is what makes a by-hand `scp` to a factory
host unnecessary rather than merely discouraged.

For an instance that declares the pair, one apply does this and only this:

1. Reads the control-node file's sha256, **on the control node**, and refuses
   the run if the file is absent or hashes to anything but `binary_sha256`.
   Nothing on the factory host has been read at this point, let alone written.
2. Compares `binary_sha256` against the digest of whatever the host holds at
   `binary_path`. Equal means the host already runs that build and steps 3–5 are
   all skipped — a converged host reports no change.
3. Stages a copy at `<binary_path>.incoming`, owned by the instance's service
   user with mode `0755`.
4. Keeps the outgoing binary at `<binary_path>.<first-12-of-its-sha256>.bak`, so
   a rollback can name the build it is returning to. Skipped on a first install,
   where there is nothing to keep.
5. Renames the staged copy onto `binary_path` — `rename(2)` within one
   directory, so the binary is either the old build or the new one and never a
   half-written file. `binary_path` is what a running server's `ExecStart` named
   and what `Restart=always` re-execs, which is why nothing is ever written to it
   directly.

A replacement notifies the same `Fabro instance files changed` handler a changed
unit file does, so it obeys the same two refusals: the handler does nothing
unless `fabro_server_restart_allowed` is set, and whenever that flag IS set the
carrying-runs preflight has already halted the play if the instance is carrying
runs.

**Replacing a binary therefore never interrupts a live factory.** Note the one
case the two refusals do not cover and why it is still safe: with the default
`fabro_server_restart_allowed` false, the carrying-runs probe is skipped
entirely, so the binary is replaced under a busy factory. `rename(2)` does not
touch the inode a running process already execs — the server keeps serving its
runs from the old build, the new one sits at `binary_path` waiting for the next
start, and the handler says out loud in the run output that it did not restart.
Picking up the new build is then an operator's deliberate act: quiesce the
instance and re-run with `-e fabro_server_restart_allowed=true`, or restart it by
hand. That re-run works because the refusing run RECORDED the deferral on the
host — see "The deferred restart" below for what it wrote and what the re-run
does with it.

**Quiesce means cancel the runs, then re-dispatch them — never wait for them to
end.** A factory run is restartable, so the carrying-runs refusal means "cancel to
idle", not "wait for idle". List the instance's active runs with
`fabro ps --server <instance>`, cancel each through the server's own
`POST /api/v1/runs/{id}/cancel` (it cancels a pending, runnable or running run
and answers 409 for one already finished; neither the 0.254 nor the 0.382 client
has a `cancel` verb, and `fabro rm --force` is NOT a cancel — it deletes the run's
record), confirm `fabro ps` shows none active, then re-run the play with the flag
true. As soon as the instance is back, re-dispatch every cancelled item, or route
it to another factory. The guard itself is honoured, never bypassed: the play
still refuses while any run is active. Holding the fleet cap at 0 until runs end
naturally cost about 1 h 50 min of factory time on 2026-10-23/24 (22:5xZ to
00:4xZ) on an under-used account.

On a host with several instances, that re-run probes EVERY instance it visits,
so a busy sibling refuses it even when the instance you want is idle. Narrow it
with the playbook's `fabro_server_target_units`, passed as JSON:
`-e '{"fabro_server_target_units": ["fabro-server-candidate"]}'
-e fabro_server_restart_allowed=true`. See the header of
`ansible/fabro-hosts.yml` for why the probe stays broad and the loop is narrowed
instead.

Rollback is step 4 in reverse and needs no role change: move the `.bak` over
`binary_path` by hand, or point `binary_source` at the build you want and declare
its digest. Both the `.incoming` and `.bak` siblings are left on the host
deliberately; nothing in the role reaps them.

## The checkout the server runs in

`fabro_server_host_checkout` is a **per-host** value, not a per-instance axis:
every instance on a host runs from one checkout, which is the `WorkingDirectory`
of every unit this role renders. Two optional per-host axes say where a host that
does not have it yet gets it from:

| variable | default | what declaring it does |
|---|---|---|
| `fabro_server_host_checkout_remote` | **empty** — the role leaves this host's checkout alone, exactly as it did before the axis existed | the git remote `fabro_server_host_checkout` is cloned from. Declared on a host whose checkout directory is **absent**, the role clones it there as the instance's service user, before the preflight that requires it. |
| `fabro_server_host_checkout_ref` | `HEAD` | the ref a fresh clone is left on. `HEAD` is git's own word for the remote's default branch, so the default names no branch of its own. Read **only** by a clone. |

**An existing checkout is never reset.** A host whose checkout directory is
already there keeps that checkout's working tree and its HEAD across a converge,
whatever the two axes say — a live factory's checkout carries uncommitted work
and a branch somebody chose, and it is the working directory of a server that is
carrying runs while this role runs against it. Two separate guards say so: the
clone's `when:` fires only on an absent directory, and the clone passes
`update: false` because `ansible.builtin.git` DEFAULTS to `update: true`, which
would reset that working tree hard onto `version`. The second is not redundant —
it is what happens if the first is ever wrong.

A host that declares **no** remote is refused by the checkout preflight exactly
as it was before: the role has never created this directory for such a host and
still does not.

Why the role clones at all, having refused to create every other piece of
out-of-band state: each of those stands in for a step only an operator can take
— a `SESSION_SECRET` Fabro itself generates, a GitHub App private key held in the
instance's own vault, a `tailscale serve` mapping that lives in the
`tailscale-admin` repository, a Fabro binary this role will never build. A git
clone is none of those; it is derivable from one URL. On a new factory host the
old refusal left exactly one way through — a hand clone — and a service placed on
a factory host by hand is drift to be expressed in the play, never an accepted
exception.

**Operator notes.** The parent directory of `fabro_server_host_checkout` must
exist and be writable by `fabro_server_host_user`, or the clone fails naming it;
the role deliberately does not create or re-own it, because that path is shared
(`/data/projects` on `vps`) and re-owning a shared parent is a bigger change than
the clone it would enable. Under `--check` the clone is **reported and not
performed** — `just ansible-drift ansible/fabro-hosts.yml` against a host with no
checkout names the clone it would make and changes nothing, and the checkout
preflight stands aside for that run rather than failing the drift read of the one
host the axis was added for.

## The sandbox environment catalog

The `environments` axis is the one per-instance axis that is **not a file this role
renders**. A Fabro sandbox environment is server-managed state: it lives in the
instance's own store, is read and written through
`GET`/`POST /api/v1/environments` and `GET`/`PUT /api/v1/environments/{id}`, and a
`workflow.toml` `[environments.*]` table is never selected on this engine. So the
only way version control reaches a catalog is a request the converge makes.

This section exists because the alternative was somebody remembering to POST one.
Measured on `hp-xubuntu` 2026-10-11 (work-item `livespec-dev-tooling-fe62lh`): the
`fabro-server-candidate` canary run passed its start node and failed at run
preparation with `mise: not found`, because the instance's catalog held only the
server's seeded `default` entry — `buildpack-deps:noble`, 2 CPU, 4GB — and the
factory's own `livespec-ci` environment did not exist there at all. **Nothing
errored on the server.** A run placed in the wrong environment is a run that looks
dispatched and cannot work.

### What a declaration says

Four fields, all required, each refused before the host is read:

```yaml
    environments:
      - id: livespec-ci
        image: ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.93.5
        cpu: 4
        memory: 8GB
```

`id` is the key the catalog is keyed by — two declarations on one instance may not
share one. `image` is a docker image. `cpu` is an integer above zero. `memory` is
an integer followed by one of `B`, `KB`, `MB`, `GB`, `TB`, `KiB`, `MiB`, `GiB`,
`TiB`.

**Declare the memory size the way Fabro renders it.** Fabro stores a size and
re-renders it in the largest decimal unit that divides it exactly, so `8GB`
round-trips as `8GB` and compares equal on every later run. A value spelled some
other way for the same size — `8000MB`, or a binary unit — converges on the first
run and is then reported as changed on every run after it, because the string the
catalog returns is no longer the string version control declares.

### The image tag follows the orchestrator workflow pin

The `image` of the factory's own environment is **not an independent choice**. It
must be the tag that
`livespec-orchestrator-beads-fabro`'s
`.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml` pins — today
`python-agent-v1.93.5`. Bump the two together. A tag declared here that the
workflow does not pin is an environment the factory never dispatches into, and a
tag the workflow pins that no instance declares is the canary failure above.

### Which runs write, and which run writes nothing

Per declared environment, one `GET /api/v1/environments/{id}` decides everything:

| what the catalog holds | what the converge does |
|---|---|
| the declared image, cpu and memory | nothing — **no change is reported for that environment** |
| the id, with other settings | `PUT /api/v1/environments/{id}` with the `If-Match` revision the read returned; the environment is **replaced** |
| no entry for that id (404) | `POST /api/v1/environments`; the environment is **created** |
| nothing — the server does not answer | neither, and the run says so by name rather than skipping silently |

The comparison is **field by field, on the declared fields only**. A whole-settings
comparison would report drift for everything the server defaults or normalises,
which would make a converged instance report a change forever — and a converge
that always writes is a converge whose report says nothing.

Both writes carry the server's own concurrency check where it has one: the replace
sends `If-Match` with the revision that same read returned, so a change made
between the read and the write is refused rather than overwritten. The header is
required by the API, so there is no form of that request that skips it.

### The body is DERIVED from the catalog, not spelled in the role

A create or replace request requires **every** field the server's build knows and
refuses **any** field it does not. This repository cannot know which fields a given
factory host's Fabro build has — `hp-xubuntu` runs two instances on two different
builds on purpose, which is what the cutover rehearsal IS. So the request body is
the catalog entry **the server itself returned**, with the declared image and
resource envelope combined onto it, and `id` and `revision` dropped because the API
carries both outside the settings.

That has a second property worth as much as the first: a converge never resets a
field version control does not declare. An environment's network policy, its
labels and its `env` map survive a converge untouched.

For an environment the catalog already holds, that entry is its own base. For one
it does not, `fabro_server_environment_template_id` names the entry to derive
from — `default`, the docker environment `fabro install` seeds. It is a role
default rather than a per-instance axis because an instance that needed a
different base would be declaring a second environment, which the axis already
expresses.

Only `fabro install` seeds `default`; the server never seeds on startup, and this
role writes `server.env` itself rather than running install. So a server the role
brings up from nothing has no `default` — measured 2026-10-18 on gmktec-xubuntu's
first converge, whose catalog held `local` alone. For that case
`fabro_server_environment_fallback_template_id` names the entry to fall back to,
`local`: still the server's own answer, so its fields carry the build's schema,
with only its provider set to `docker`, which the declaration already implies by
naming a docker image. If none of the declared id, the template and the fallback
is in the catalog, the role refuses and writes nothing.

### The credential, and why these tasks are not hidden

The API authenticates with the instance's `FABRO_DEV_TOKEN`, which Fabro generates
into `<home_dir>/storage/server.env` at mode 0600 — the file the role's preflight
already requires. Every request reads it **in the host-side shell** and pipes it to
curl as a whole header line on standard input (`--header @-`). Ansible therefore
never holds the value: it is in no variable, no `set_fact`, no message and no
module argument, so there is nothing for `-v` output or an invocation record to
carry. Because the header arrives on stdin rather than as an argument, it is not in
the host's process table either.

That is also why these tasks carry no `no_log`. There is no value in them to hide,
and hiding them would hide the API's own error body — which is the entire
diagnostic for a refused write.

### Reading a catalog by hand

The same two requests the role makes, for an operator checking a host:

```bash
# on the factory host, as root
token=$(sed -n 's/^FABRO_DEV_TOKEN=//p' /home/cwoolley/.fabro-candidate/storage/server.env | tail -n 1)
printf 'Authorization: Bearer %s\n' "$token" | curl -sS -H @- http://127.0.0.1:32278/api/v1/environments
printf 'Authorization: Bearer %s\n' "$token" | curl -sS -H @- http://127.0.0.1:32278/api/v1/environments/livespec-ci
```

A dry run (`just ansible-drift ansible/fabro-hosts.yml`) reports each declared
environment's disposition without writing: the reads run under `--check`, and the
two writes are `shell` tasks, which Ansible skips there.

## The deferred restart

A run that changes an instance's files with `fabro_server_restart_allowed` false
does not restart the server, and it does not drop the restart either: it writes a
**restart-pending marker** for that instance on the host. A later run with the
flag true reads the marker, re-checks the carrying-runs refusal, restarts the
instance, and removes it.

This section exists because the paragraph above used to end at "re-run with
`-e fabro_server_restart_allowed=true`" and that instruction did not work.
Measured on `hp-xubuntu` 2026-10-11 (work-item `livespec-dev-tooling-vmeiv6`):
pass 1, with the flag false, installed the v0.382 carrier at the candidate
instance's `binary_path`, changed its unit, and reported that
`fabro-server-candidate` was not restarted. Pass 2, with the flag true against
that instance alone, passed the carrying-runs refusal ("this instance has no
active runs"), changed nothing, never notified the restart handler, and left the
candidate serving `0.378.0-nightly.0` with 72 hours of uptime. **Nothing
errored.** A handler notification lives only inside the run that raised it, so
pass 2 arrived with nothing to act on — and its output was indistinguishable
from a converged host's.

### Where the record lives

`fabro_server_restart_pending_dir` defaults to
`/var/lib/fabro-server/restart-pending`, and the role resolves one file inside it
per instance as `fabro_server_restart_pending_marker`, named for the instance's
`unit_name`. `unit_name` is the identifier the role already refuses to let two
instances share, so two instances on one host can never collide on one marker.
`/var/lib` rather than `/run` because the record must survive a reboot: a reboot
starts each instance from its new unit file, which silently resolves some
deferrals and not others, and a record a reboot forgot would leave no way to tell
which.

Read the host's standing deferrals directly — this is a plain file, and
inspecting it before opening a quiesced window is how you tell a standing
deferral from a converged instance:

```bash
ls -l /var/lib/fabro-server/restart-pending/
cat /var/lib/fabro-server/restart-pending/fabro-server-candidate
```

The file's contents name the instance, the binary path it is waiting on, and the
invocation that applies it. The bytes are deliberately CONSTANT for an instance —
no timestamp, no list of what changed — so two consecutive refused runs write
identical bytes and the second reports no change. One standing deferral reads as
one fact rather than as a fresh event per converge; what changed on a given run
is in that run's output, not in the file.

### Which runs write it, and which run applies it

| run | what happens to the marker |
|---|---|
| files change, `fabro_server_restart_allowed` false | written, and the run says the restart is still pending |
| nothing changes, flag false, marker present | kept — rewritten identically, reported as still pending |
| flag true, marker present (or the running server executes a file other than `binary_path`) | the instance is restarted and the marker is **removed** |
| instance parked (`service_state: stopped`) | nothing; a parked instance has no running server to be out of date |

The third row is the one that makes the first two worth doing, and it is reached
two ways. The marker is the record of a restart an earlier run refused. The
running-binary check is the independent, self-healing half: the role reads
`/proc/<pid>/exe` of the supervised process BEFORE it installs anything, and a
link target that is not exactly `binary_path` — including the
`<path> (deleted)` the kernel reports once a new build has been renamed over
that path — means the running server is not the one version control names. That
catches a drifted instance even if its marker was never written or was removed
by hand.

Both halves fail toward NOT restarting. An unreadable `/proc/<pid>/exe`, or a
unit reporting pid 0, is treated as carrying nothing: a restart that really was
owed is re-detected on the next run from the marker, whereas a restart invented
from an unreadable probe would kill the runs a live factory is carrying and
nothing would re-create them.

Nothing but the restart removes the marker. There is no flag, tag or override
that clears it without restarting — a deferral that could be dismissed is a
deferral that would be, which is the failure this whole section exists to end.

## `host_vars/hp-xubuntu.yml`

```yaml
# The service account is cwoolley, NOT ubuntu: the tailnet ACL rejects the
# ubuntu account on this host, and the checkout root is under $HOME rather
# than /data/projects.
fabro_server_host_user: cwoolley
fabro_server_host_group: cwoolley
fabro_server_host_home: /home/cwoolley
fabro_server_host_checkout: /home/cwoolley/repos/livespec-orchestrator-beads-fabro

fabro_server_instances:
  - unit_name: fabro-server
    home_dir: /home/cwoolley/.fabro
    port: 32276
    canonical_host: hp-xubuntu.perch-rudd.ts.net:32276
    cli_target_url: http://127.0.0.1:32276
    # 15 = the core count minus one, reserved for the server, janitor steps
    # and host overhead. A maintainer instruction of 2026-08-21, not a copy of
    # vps's 10: hp earns a higher over-subscription factor (3.75x against
    # vps's 2.2x) by being a dedicated factory host at load 1.36, where vps is
    # a shared box carrying dozens of user sessions.
    max_concurrent_runs: 15
    github_app_id: "3668528"
    # Live on the host since 2026-08-21.
    otel_dropin: present
    # The SAME build this instance has run since 2026-10-01 — fabro 0.254.0 at
    # 8869e88 (tag carrier-8869e88-pre-rebuild-2026-10-10 on
    # thewoolleyman/fabro) — rebuilt 2026-10-16 with NODE_ENV=production
    # exported, because fabro-web's build.ts never sets it and every earlier
    # build embedded React's DEVELOPMENT build in the web console. Engine source
    # is identical; only the SPA differs. STAGED, NOT RESTARTED: this instance is
    # never idle, so an apply with fabro_server_restart_allowed false swaps the
    # file atomically under the running server and records the deferred restart.
    # The new console goes live at the next restart: a zero-live window, or the
    # fabro-currency cutover (gitops-fleet-capacity-monitoring ruling R80). The
    # path is shared with fabro-server-mi-homelab, which names no binary_path and
    # is stopped. Provenance is in BUILD_INFO beside the binary.
    binary_source: /home/ubuntu/.local/state/fabro-web-prod/v0254-8869e88/fabro
    binary_sha256: 199407cec8119735fc0751407272ba3282703bd45ada87d34a89cc8f62a22421

  - unit_name: fabro-server-mi-homelab
    home_dir: /home/cwoolley/.fabro-mi-homelab
    port: 32277
    canonical_host: hp-xubuntu.perch-rudd.ts.net:32277
    cli_target_url: http://127.0.0.1:32277
    # A chosen value, not an observation: the host's 16 cores are already
    # over-subscribed by the fleet instance's 15, and the org factory serves
    # one repository. Raise it deliberately, with the fleet instance's number
    # in view, never by copying the entry above.
    max_concurrent_runs: 5
    github_app_id: "4688510"
    # Live on the host since 2026-08-22.
    otel_dropin: present
    # STOPPED 2026-09-12 by maintainer instruction: the homelab project is on
    # hold. The unit, its drop-in, settings.toml and the state directory under
    # home_dir are all KEPT — nothing is deleted — so the instance comes back
    # by flipping this one word to running and re-applying. The role stops and
    # disables the unit, never restarts it, and skips the running-server
    # verification for it. vps's mi-homelab instance is untouched by this.
    service_state: stopped

  # The fabro-currency cutover candidate. Hand-installed on 2026-10-08 and
  # reported by every drift read since, because the role could not express an
  # instance that runs its own build: expressing it here is the fix, not a
  # second exception. It carries the Petri-era build production moves onto,
  # beside the fleet instance above still carrying the current one, and
  # publishes as the SAME fleet App — it is the fleet factory, pre-cutover,
  # not a second project.
  - unit_name: fabro-server-candidate
    home_dir: /home/cwoolley/.fabro-candidate
    port: 32278
    canonical_host: hp-xubuntu.perch-rudd.ts.net:32278
    cli_target_url: http://127.0.0.1:32278
    # Chosen deliberately and small, with the fleet instance's 15 in view: the
    # host's 16 cores are already over-subscribed by that instance, and this
    # one carries rehearsal dispatches rather than the fleet's traffic. Raise
    # it AT the cutover, when the fleet instance's number comes down.
    max_concurrent_runs: 2
    github_app_id: "3668528"
    # A decision, not a default: this instance becomes hp's production factory
    # at the cutover, and both instances above export, so a candidate that did
    # not would blind the factory telemetry for exactly the window in which it
    # is being proven. Setting `present` ADDS the drop-in if the hand-install
    # left none — read the drift report before applying, as the play requires.
    otel_dropin: present
    # Its own build, beside its own state root — the two axes this instance
    # exists to exercise. HOME is the state root rather than the account home,
    # which is how it was hand-installed.
    binary_path: /home/cwoolley/.fabro-candidate/bin/fabro
    home_env: /home/cwoolley/.fabro-candidate
    # The v0.382 carrier build, staged on the control node (vps) and carried
    # from there. Measured 2026-10-11: the host's candidate instance was
    # running fabro 0.378.0-nightly.0 (64b9d88), so the first apply after this
    # lands REPLACES that binary. The digest is the gate — the source path is
    # inside a mutable state tree, so a declaration without one would install
    # whatever is there on the day it runs. The replacement does not restart
    # the instance: fabro_server_restart_allowed is false by default and the
    # carrying-runs refusal gates it even when it is true.
    #
    # Rebuilt 2026-10-16 from the SAME commit (adeefec4c) with
    # NODE_ENV=production exported. fabro-web's build.ts never sets NODE_ENV,
    # so every earlier build, including effe9d03, embedded React's DEVELOPMENT
    # build in the web console. The engine source is identical; only the SPA
    # differs. A rebuild without NODE_ENV=production regresses the console to
    # the dev UI. Provenance is in BUILD_INFO beside the binary.
    binary_source: /home/ubuntu/.local/state/fabro-web-prod/v0382-adeefec/fabro
    binary_sha256: 26872440c75c50edfd59a0d33f1401baf70a9e5de81fb65192a1f7042817f7c1
    # The sandbox environment the factory's own runs are prepared in. Measured
    # 2026-10-11: this instance's catalog held only the server's seeded `default`
    # entry — buildpack-deps:noble, 2 CPU, 4GB — so the canary run dispatched to
    # it was prepared in that image and failed at run preparation with
    # `mise: not found`. The image tag FOLLOWS THE ORCHESTRATOR WORKFLOW PIN:
    # `.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml` in
    # livespec-orchestrator-beads-fabro, today python-agent-v1.93.5. Bump the
    # two together — a tag here that the workflow does not pin is an
    # environment the factory never dispatches into. The envelope is the one
    # the factory's runs are sized for, against the fleet instance's 15 slots
    # and this instance's 2.
    environments:
      - id: livespec-ci
        image: ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.93.5
        cpu: 4
        memory: 8GB
    # STOPPED 2026-10-18 (livespec-dev-tooling-hkf457, plan bd-ib-fyozyd): the
    # maintainer ruled that gmktec-xubuntu replaces hp as the Petri-era
    # factory's home, so the current Fabro server now serves from gmktec and
    # this hp instance is parked. Unit, drop-in, settings.toml, binary and
    # state directory are all KEPT; the role stops and disables the unit and
    # never restarts it. Bring it back by flipping this word to running.
    service_state: stopped
```

## `host_vars/vps.yml`

```yaml
fabro_server_host_user: ubuntu
fabro_server_host_group: ubuntu
fabro_server_host_home: /home/ubuntu
fabro_server_host_checkout: /data/projects/livespec-orchestrator-beads-fabro

fabro_server_instances:
  - unit_name: fabro-server
    home_dir: /home/ubuntu/.fabro
    port: 32276
    canonical_host: vps.perch-rudd.ts.net:32276
    cli_target_url: http://127.0.0.1:32276
    # vps sets this explicitly in its live, hand-maintained settings.toml.
    max_concurrent_runs: 10
    github_app_id: "3668528"
    # THE OPEN DECISION, and it is now exactly this one line. Measured
    # 2026-09-09: this is the only one of the four instances with no OTLP
    # drop-in on disk. fabro-hosts' README asks for the call to be made
    # deliberately, because installing the drop-in here newly adds OTLP export
    # from the fleet's fallback factory — a behaviour change, not a
    # transcription. `unmanaged` leaves the host as it is and says so in the
    # run output. Setting `present` turns export on; `absent` decides against
    # it. Do not leave it undecided indefinitely; do not decide it by default.
    otel_dropin: unmanaged

  - unit_name: fabro-server-mi-homelab
    home_dir: /home/ubuntu/.fabro-mi-homelab
    port: 32277
    canonical_host: vps.perch-rudd.ts.net:32277
    cli_target_url: http://127.0.0.1:32277
    # Chosen, not observed: vps is a shared box already carrying the fleet
    # instance's 10, and the org factory is the fallback, not the default.
    max_concurrent_runs: 3
    github_app_id: "4688510"
    # Live on the host since 2026-08-23.
    otel_dropin: present
```

## Values the role defaults rather than reading from `host_vars`

`fabro_server_web_verify_attempts` defaults to 300, which is what all four
values files set. It is a per-host variable if a host ever needs a different
budget; see the defaults file for why the default is 300 and not the
verifier's own 60.

`fabro_server_restart_allowed`, `fabro_server_manage_settings` and
`fabro_server_settings_mode` are deliberately not host variables. The first
two are per-run decisions an operator makes with `-e`, not standing
configuration; making either a committed host variable would turn a
deliberate act into a default.

`fabro_server_restart_pending_dir` is not a host variable either, for close to
the opposite reason: it is where the role records a restart it refused, and an
operator free to relocate it per host could split one host's deferrals across
two directories — or, after changing it, leave standing deferrals at the old
path where no later run would look for them. See "The deferred restart" above
for the record's shape and lifecycle.

## The `ansible_managed` banner

`templates/fabro-server.service.j2` carries `# {{ ansible_managed }}` as its
first line. `templates/settings.toml.j2` deliberately does **not**, and neither
do `files/otel.conf` or `files/fabro-server-verify-web`.

The unit is a file this role genuinely owns and rewrites on every run, so
stamping it is honest and useful — this whole repository exists because
hand-edited copies of these files drifted invisibly. `settings.toml` is the
opposite: by default the role only reports drift and never writes it, so a
banner claiming Ansible manages the file would be false in the default case
and true only under an opt-in flag. The two `files/` copies are byte-fidelity
artifacts shared with the shell installer and are copied, not templated, so
they could not carry it anyway.

The measured cost of the banner is exactly one line, and the dry run isolates
it: on the two `fabro-server-mi-homelab` instances, which the shell renderer
installed on 2026-08-23, the entire reported unit diff is `+# Ansible managed`
and nothing else. Without the banner those two instances report a zero diff.

## What the first run will report

Measured, not predicted: the role was run against **both** live hosts with
`--check --diff` on 2026-09-09 through the real `inventory/legacy.yml`.

| Host | Result |
|---|---|
| `hp-xubuntu` | ok=56 changed=3 failed=0 |
| `vps` | ok=55 changed=4 failed=0 |

Every one of those seven changes is listed below and every one is drift the
role finds rather than drift it introduces.

**That measurement predates `fabro-server-candidate` and says nothing about
it.** The candidate instance was hand-installed on 2026-10-08, after the dry run
above, so its first `just ansible-drift ansible/fabro-hosts.yml` is unmeasured
and its result is NOT recorded here. Read that drift report before applying: the
candidate's hand-installed unit, its `settings.toml` and whether it carries the
OTLP drop-in are all unknown from version control, and its `binary_path` is the
path declared for it rather than one this repository has observed — the role's
preflight refuses the host, before writing anything, if no executable binary is
there. Record the measured result here once it exists.

### `vps` / `fabro-server` — the pre-parameterization unit (2 changes)

Its installed unit predates the whole template. The render adds the
`Description` instance suffix, `FABRO_WEB_VERIFY_ATTEMPTS=300`,
`FABRO_CANONICAL_HOST`, `FABRO_BASE_URL`, the explicit `--storage-dir` and
`--config`, and the banner. The second change removes the hand-made
`verify-timeout-override.conf` drop-in, which is where that host's 300
currently lives; the resulting value is the same 300, now in the unit where a
rebuild cannot lose it.

### `hp-xubuntu` / `fabro-server` — three lines and a mode (2 changes)

The unit differs by exactly the three lines `fabro-hosts` recorded on
2026-08-23 — `Description` suffix, `FABRO_BASE_URL`, and the explicit
`--storage-dir` / `--config` — plus the banner. It already carries
`FABRO_WEB_VERIFY_ATTEMPTS` and `FABRO_CANONICAL_HOST`. Its `settings.toml`
content is **byte-identical** to the render; the only difference is mode 0644
against the role's 0600.

### Both `fabro-server-mi-homelab` instances — the banner only (2 changes)

One line each, `+# Ansible managed`. Nothing else. These were installed by the
shell renderer on 2026-08-23 and this role reproduces their unit, drop-in and
`settings.toml` byte for byte, which is the transcription's own proof.

### `vps` / `fabro-server` `settings.toml` — comments only, and this is the one to read carefully (1 change)

**The hand-maintained `max_concurrent_runs = 10` is untouched.** The reported
diff is three comment blocks and nothing else: every value line matches. That
file is the fleet's fallback factory's real configuration and overwriting its
deliberate 10 would be a regression, so the fact that the diff contains no
value line is the result worth checking on every future run. The role does not
write it in any case — the reporting task is pinned to check mode
independently of the command line.

The comments come from `settings.toml.in`, which `render-settings.sh`
preserved and this template preserves too. `fabro-hosts` recorded this render
as "identical, comments stripped"; the dry run is that same finding with the
comments left in.

Note that a mode change is not visible in Ansible's diff text, which shows
content only. The contrast between the two hosts demonstrates it: `hp` has no
content difference so its mode diff is all that prints, while `vps` has a
content difference so its mode is folded into the same reported change without
appearing.

## Out-of-band state the role asserts on and never creates

Per instance, unless noted:

1. The built Fabro binary the instance's `binary_path` resolves to, which is
   `<host_home>/.fabro/bin/fabro` — **shared by every instance that does not
   name one** — and otherwise the instance's own build. The preflight stats
   whichever path the axis resolves to; the role never builds or downloads it.
2. The GitHub App private key in that instance's own Fabro vault, for an
   instance that does not declare it under `vault_secrets` (below).
3. A `tailscale serve` mapping for the port, which lives in the
   `tailscale-admin` repository. The role cannot see it at all — see the note
   in `tasks/main.yml`.
4. `<home_dir>/settings.toml`, unless `fabro_server_manage_settings` is set.

## State the role provisions on a host that has none

Each of these used to be a refusal whose only way through was a step by hand,
which the fleet host guard denies. On a host that already has them, every task
is a no-op (hp-xubuntu and vps drift reads, 2026-10-18: no change).

- **The state root, `<home_dir>/storage`, and the binary's directory**, owned by
  the service account. The mode only adds the owner's bits, so an existing
  directory keeps its mode.
- **`<home_dir>/storage/server.env`**, mode 0600, generated ON THE HOST when it
  is absent: `SESSION_SECRET` is 64 hex characters and `FABRO_DEV_TOKEN` is
  `fabro_dev_` plus 64 hex characters, Fabro's own formats. An existing file is
  never touched, because the running server's dev token is what the Dispatcher
  and the catalog requests authenticate with.
- **Docker group membership** for the service account. Added only where the
  host's Docker is ready: a `docker` group exists AND either the host has no
  docker_engine guard state root (`fabro_server_docker_engine_state_root`,
  default `/var/lib/docker-engine-guard`; its Docker predates the guard) or that
  guard's `confirmed` marker is present. Before its commit point the
  docker_engine guard refuses a host on which any account is in the group, so a
  running instance on a host whose Docker is not ready is REFUSED, naming
  `ansible/docker-engine.yml` as the step to converge first.
- **Vault entries an instance declares** (the optional `vault_secrets` axis).
  After the server answers its health endpoint, the role lists the vault's
  NAMES and creates each declared name that is missing. It never reads,
  compares or overwrites a value it finds. Each entry spells `name`, `type`
  (`token` or `file`), an optional `description`, and either
  `from_controller_env` — the control-node environment variable the value is
  read from, which the credential wrapper supplies — or `value`, for a committed
  non-secret placeholder. A missing entry whose variable is unset is refused
  before anything is written, so run the apply under `with-livespec-env.sh`.
  The write task is `no_log`, and on the host the value and the dev token travel
  on standard input and a pipe, never as arguments.

## `fabro_server_interrupt_runs_allowed` (per-invocation only)

Default `false`. With `fabro_server_restart_allowed=true` (or `service_state: stopped`),
setting `-e fabro_server_interrupt_runs_allowed=true` waives the carrying-runs refusal:
the play still probes and reports how many runs are active, then restarts or stops the
instance anyway, killing them. It exists because a busy factory never becomes quiet
during a play (other sessions' dispatchers keep admitting runs), so without it the role
had no way to stop or restart a busy instance, and the fleet host guard forbids doing it
by hand. Never put it in host_vars.

## `host_vars/gmktec-xubuntu.yml`

The current Fabro server's host (plan `petri-factory-on-gmktec`). The fleet
factory runs here as two instances under the `cwoolley` account: `fabro-server`
on port 32276 under `/home/cwoolley/.fabro`, and the registered-provider carrier
canary `fabro-server-candidate` on port 32278 under
`/home/cwoolley/.fabro-candidate`. The canary runs the next carrier BESIDE the
fleet instance rather than in place of it — its own unit, port, state root and
`binary_path` — and is retired (`service_state: stopped`) once the fleet
instance carries the build it proved; its own `max_concurrent_runs` is 2 because
it shares this host with the fleet instance's runs. The org-owned
`fabro-server-mi-homelab` on port 32277 is declared beside them and belongs to a
different project, not to the fleet factory.

Both are pinned to Fabro `0.393.0-nightly.1` at commit `9f6c38f` — the
registered-provider carrier, `thewoolleyman/fabro`
`carrier-candidate-registered-20261023` with Petri `e92b191`, staged on the
control node and carried from there by `binary_source` and `binary_sha256`. It
replaces the v0.382 carrier the fleet instance ran while this host was being
stood up. The rollback target is named in `host_vars` beside the pin and never
here, because that is the file an operator rolling back edits.

`fabro_server_host_checkout_remote` is declared because the host had no
checkout, and `fabro_server_manage_settings` is true because a fresh instance
has no settings.toml to preserve. The fleet instance's `max_concurrent_runs` is
12 (coordinator ruling R50, 2026-10-26, on the maintainer's direction to max
out the Kubernetes capacity). Its environments run as Kubernetes pods, so the
bound that moves with this number is now the `factory-runs` ResourceQuota
(`ci-runner/k3s/phase2/factory/DERIVATION.md` "The quota, raised to twelve
runs"), not the Docker slice. Only `livespec-ci-rust` still lands in the 36G-high
/ 40G-max sandbox slice, where maintainer directive R259 (2026-10-19) had sized
eight runs from the petri capacity sampler: every run's sandbox anon peaked at
2.61-2.64 GB, so the slice holds twelve even if every run chose it. Change the
number together with the quota, and read any sandbox OOM on this host as an
INFRASTRUCTURE ending (ruling R235).

That instance's catalog declares `livespec-ci`, `livespec-ci-rust` and
`livespec-ci-k8s`, each 4 CPU and 8GB. `livespec-ci` and `livespec-ci-k8s` run
on the `kubernetes` provider and so declare no image; `livespec-ci-rust` keeps a
docker image — the `python-rust-agent` layer, following the pin of the one
repository that builds Rust rather than the orchestrator's. A dispatch reaches
an environment only through a factory entry that names it, so a cutover between
two of them is pointing that entry, and the rollback is pointing it back.

`sandbox_providers` on that instance declares the `kubernetes` kind at the
plugin digest the `sandbox_driver_kubernetes` role pins — the same `sha256` that
role stages `/usr/local/bin/sandbox-driver-kubernetes` at, so the two move
together and the instance never launches a plugin binary the role did not put on
the host. `inherit_env` passes `HOME` and `PATH` through the cleared plugin
environment, and this instance's `HOME` is `/home/cwoolley`, which
`sandbox_driver_kubernetes_config_homes` lists.

`vault_secrets` declares the App key, from the wrapper's
`GITHUB_PRIVATE_KEY`, and the `OPENAI_API_KEY` placeholder an ACP-only graph
needs to pass `fabro.model.no_ready_provider` admission. Its Docker comes from
`ansible/docker-engine.yml`, which must be confirmed before this play installs
the server.

## Sandbox-driver plugin providers

`sandbox_providers` is how version control tells an instance to launch a
third-party sandbox-driver plugin, the Kubernetes plugin
(`thewoolleyman/sandbox-driver-kubernetes`, installed by the
`sandbox_driver_kubernetes` role) being the first. It is two halves, and both
are needed before a run can use the plugin:

1. The provider table in `settings.toml`. The plugin is launched by the
   instance's workers with a CLEARED environment (sandbox-driver protocol v2), so
   `inherit_env` must name every host variable the plugin reads: at least `HOME`,
   which is where the plugin finds its `~/.config/sandbox-driver-kubernetes/config.toml`,
   and `PATH`. `HOME` is the instance's `home_env`, so the
   `sandbox_driver_kubernetes` role must render its plugin config into that
   directory too (`sandbox_driver_kubernetes_config_homes`).
2. A catalog environment whose `provider` names the kind. The derivation still
   starts from a docker base entry, and the declared provider replaces the
   base's. Such an entry declares NO `image`, and the role writes it with a null
   docker image: Petri builds a registered provider's sandboxes from the
   provider's `process_spec`, and refuses a run whose environment names an image
   ("is a registered provider; `image` applies to `docker` and `daytona` only",
   measured on the gmktec canary 2026-10-23). An environment naming a kind the
   instance does not declare, and a registered-provider entry that does declare
   an image, are both refused before the host is read.

Declaring a provider requires a Fabro build that registers an unbundled kind as a
Petri registered provider (plan `kubernetes-sandbox-backend`; Petri PRs #122 and
#131). The deployed one is the carrier `0.393.0-nightly.1` (`9f6c38f`), which
every Fabro instance on `gmktec-xubuntu` is pinned to. Such a build requires a
`process_spec`, the sandbox-driver `SandboxSpec` every sandbox of that kind is
built from, and refuses the provider without one. The role renders it from three keys: `image`
(the OCI reference), `cpu_cores` and `memory_mb`. Petri lays each run's own
environment resources over the template, so these are the fallback size; keep
them equal to the matching environment's, in mebibytes as Fabro lowers them
(`8GB` is `memory_mb: 7629`). `host_address` is refused: a registered
provider's sandboxes have no route back to the host, and Fabro's provider table
rejects the key as unknown. A build that predates registered providers (the
0.389 carrier) has no `process_spec` key and needed `host_address` instead, so
this declaration and the carrier move together.

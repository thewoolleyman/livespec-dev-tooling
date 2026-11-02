# `sandbox_image_warm` — per-host values for the inventory's `host_vars`

The host-side warm that keeps a docker Fabro factory host's local image store
ahead of the sandbox image tag its runs are about to need: a oneshot unit that
reads the fleet's current sandbox image version and pulls the corresponding tag
under a per-reference lock, armed by a systemd timer.

The same role also fills a k3s factory node's **containerd** store, the one a
Kubernetes factory pod is pulled into; see [The containerd store](#the-containerd-store)
below. Everything above that section describes the docker warm.

**Why it exists.** On 2026-10-20 at 08:09:51-52Z two runs started within one
second on `hp-xubuntu` and both needed
`ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.118.5`, a tag the
host did not hold (it held `v1.118.4` and older). Each run's pull tore down the
other's containerd leases and both died in sandbox init with
`Failed to pull Docker image ... causes=[Docker stream error]` in 0.8 s and
3.3 s. The tag was in the registry throughout: neither auth nor network.
Nothing serialized the FIRST pull of a new sandbox image tag, so every image
bump re-armed that race, and it fired hardest when the fleet was busiest
(work-item `livespec-dev-tooling-dq3km7`; hold R286 of the coordinator plan
`gitops-fleet-capacity-monitoring`).

**The two properties that close it.** The pull is serialized per reference under
`flock`, and the lock holder RE-CHECKS the local image store inside the lock.
Both are load-bearing: a lock without the re-check serializes two pulls instead
of preventing one, and the second pull is exactly as able to tear down a lease
as the first.

**Why the timer, and not a playbook step.** The acceptance condition is that the
host holds a new tag before the first run that needs it reaches sandbox init
*with no operator command run by hand*. A warm armed only when someone applies
a playbook lags the pin exactly as the gate renderer lagged the gate client
(work-item `livespec-dev-tooling-vurvjl`), so the converge enables AND starts
the timer and the host re-reads the pin on its own cadence from then on.

**Why the tag is derived and not declared.** The tag a repository dispatches on
is `<layer>-v<version>`, where the version is this repository's released
version: the sandbox image layers are built and published from here, and the
release fan-out rewrites every consumer's `docker =` pin to the new tag
(`livespec_dev_tooling/cross_repo/fabro_image_pin_rewrite.py`, whose `bump_pin`
preserves the layer prefix and moves only the version). Reading that version
from `.release-please-manifest.json` on this repository's master therefore names
the tag the fleet is about to dispatch on, and names it no later than the pin
bump that makes a repository dispatch on it. A tag written into `host_vars`
would only ever name the tag whose bump an operator last applied.

## The variables

Every one of these equals this role's default, so **a docker factory host needs
no `host_vars` entry at all**. They are listed so the next host's values have
something to differ from.

| variable | default | what it is |
| --- | --- | --- |
| `sandbox_image_warm_store` | `docker` | which image store this warm fills: `docker` or `containerd`. A play passes it as a role parameter, never through host_vars (see the containerd section) |
| `sandbox_image_warm_state` | `present` | `present` installs and arms the warm; `absent` retires it (see Rollback) |
| `sandbox_image_warm_name` | `livespec-sandbox-image-warm`, plus `-containerd` for the containerd store | the stem every name below is derived from, so the two warms on one host are disjoint |
| `sandbox_image_warm_bin` | `/usr/local/sbin/<name>` | where the warm runner is installed |
| `sandbox_image_warm_unit_dir` | `/etc/systemd/system` | where the two units are installed |
| `sandbox_image_warm_service` | `<name>.service` | the oneshot unit the timer triggers |
| `sandbox_image_warm_timer` | `<name>.timer` | the timer the converge enables and starts |
| `sandbox_image_warm_image` | `ghcr.io/thewoolleyman/livespec-fabro-sandbox` | the image whose tags are warmed |
| `sandbox_image_warm_tag_prefixes` | `[python-agent]` | the layer prefixes to warm; one reference per prefix, `<image>:<prefix>-v<version>` |
| `sandbox_image_warm_pin_url` | this repository's `.release-please-manifest.json` on `master` | where the version is read from |
| `sandbox_image_warm_lock_dir` | `/run/<name>` | where the per-reference lock files live; on tmpfs, because a lock has no meaning across a reboot |
| `sandbox_image_warm_lock_timeout_seconds` | `1800` | how long a warm waits for a concurrent warm's pull before giving up; a warm that hits the ceiling exits non-zero and pulls NOTHING |
| `sandbox_image_warm_on_boot_sec` | `2min` | the first warm after a boot |
| `sandbox_image_warm_on_unit_active_sec` | `5min` | the cadence thereafter |
| `sandbox_image_warm_randomized_delay_sec` | `30` | jitter, so two factory hosts do not pull the same new tag in the same second |
| `sandbox_image_warm_timeout_start_sec` | `45min` | bounds ONE warm, layer download included |
| `sandbox_image_warm_crictl` | `/usr/local/bin/k3s crictl` | containerd store only: the CRI client the warm reads and pulls through |
| `sandbox_image_warm_host_vars_base_url` | this repository's `ansible/inventory/host_vars` on `master` | containerd store only: where the committed host_vars files are read from |
| `sandbox_image_warm_process_spec_urls` | one URL per `sandbox_hosts` member, for the containerd store; `[]` for docker | containerd store only: the files whose `process_spec.image` values the warm pulls, re-read every tick |
| `sandbox_image_warm_inventory_process_spec_images` | every `fabro_server_instances[].sandbox_providers.<kind>.process_spec.image` in the inventory | containerd store only: read by the converge alone, which refuses to arm a containerd warm when it is empty |

```yaml
# A host that serves a workflow pinned to a second sandbox layer.
sandbox_image_warm_tag_prefixes:
  - python-agent
  - python-rust-agent
```

## Operator procedure

The converge is the whole procedure, and it restarts nothing:

```bash
just ansible-drift ansible/fabro-hosts.yml --limit <host>
just ansible-apply ansible/fabro-hosts.yml --limit <host> --tags sandbox_image_warm
```

Arming the timer touches neither `dockerd` nor any Fabro server, so this role
needs no drained window — unlike `docker_sandbox_slice`, whose setting takes
effect only on a daemon restart.

To read what the host has warmed, and when it last tried:

```bash
systemctl list-timers livespec-sandbox-image-warm.timer
journalctl -u livespec-sandbox-image-warm.service --since -1h
docker image inspect ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v<version>
```

A warm that could not read the pin exits NON-ZERO and pulls nothing, so a failed
timer run in the journal means the host is still exposed to the first-pull race
and the pin read is what to fix. Silence is not success: the unit logs one line
per reference per tick, `already held` included.

To run one warm by hand — the same thing the timer does, because the script's
built-in defaults are the fleet's current values:

```bash
sudo /usr/local/sbin/livespec-sandbox-image-warm
```

## Rollback

Through the committed apply, because the fleet host guard refuses a by-hand
`systemctl disable` on a factory host: set `sandbox_image_warm_state: absent`
on the `sandbox_image_warm` entry in `ansible/fabro-hosts.yml`, then

```bash
just ansible-drift ansible/fabro-hosts.yml --limit <host> --tags sandbox_image_warm
just ansible-apply ansible/fabro-hosts.yml --limit <host> --tags sandbox_image_warm
```

That stops and disables `livespec-sandbox-image-warm.timer` and removes the
runner and both units. Reverting the role alone would NOT remove them, because
a converge never removes what it no longer declares.

Nothing else on the host changes: the warm holds no state but the tmpfs lock
files, and the images it pulled are ordinary images the existing
`docker-prune.timer` and `disk-guard` reclaim on their own terms.

## The containerd store

**Why it exists.** A Kubernetes factory pod is pulled by its k3s node's kubelet
into that node's containerd store (namespace `k8s.io`), which the docker warm
above never touches. Measured 2026-10-26 at the twelve-run cap: all 11 live
factory pods ran on `poweredge-xubuntu` and none on `gmktec-xubuntu`, whose
containerd held `python-agent-v1.93.5` and not the `python-agent-v1.114.1` the
pods ran (work-item `bd-ib-kogktm` in the livespec-orchestrator-beads-fabro
tenant, child of plan epic `bd-ib-nmuyjc`). Step 1 of that item's plan is to
hold the image in every factory node's containerd and then re-measure
placement.

**Where it runs.** `ansible/ci-pool.yml` includes this role with the role
parameter `sandbox_image_warm_store: containerd`, gated
`when: ci_pool_factory_node == 'true'`: every `ci_pool` node whose committed
profile declares `FACTORY_NODE=true`, the same key the `ci-runner.io/factory`
node label the factory pods select on is rendered from. Today that is all three
pool nodes. It is a role parameter, not a host_vars value, because
`gmktec-xubuntu` and `hp-xubuntu` are in both plays and carry both warms: a
host_vars value would flip the docker warm too. Every name is derived from the
store (`livespec-sandbox-image-warm-containerd.{service,timer}`,
`/usr/local/sbin/livespec-sandbox-image-warm-containerd`,
`/run/livespec-sandbox-image-warm-containerd`), so the two warms on one host
share nothing on disk.

**Which images, and why they re-pull with no apply.** A Kubernetes sandbox is
built from the registered provider's `process_spec.image` in the Fabro server's
host_vars (`sandbox_providers.kubernetes.process_spec.image` and
`sandbox_providers.kubernetes-rust.process_spec.image` in
`inventory/host_vars/gmktec-xubuntu.yml`). That tag moves on its own schedule,
not with this repository's release, so the docker warm's release-pin read would
name a tag no pod is built from. Instead, every tick re-reads the committed
host_vars file of every `sandbox_hosts` member on `master` and pulls every
`image:` inside a `process_spec:` mapping that lies in
`sandbox_image_warm_image`. Comment lines are skipped, so a commented-out
rollback image is never pulled. A pin bump merged to `master` is therefore
pulled on every factory node within one timer interval (5 minutes, plus up to
30 s of jitter, plus the CDN's cache of a few minutes), with nobody applying
anything. That is ahead of the fabro-hosts apply that makes the server dispatch
on it, the same ordering the docker warm keeps.

**Failure is loud.** A tick that cannot fetch ANY of those files, or finds no
`process_spec` image in them, exits non-zero and pulls nothing: a partial read
could omit the very pin that moved. It never falls back to the release pin.

**The pull.** `k3s crictl pull`, through the CRI, so the image is one kubelet
sees; a bare `ctr images pull` would not carry the CRI's labels. It goes through the
cluster's registry mirror exactly as a pod's own pull does. The same per-reference
`flock` and in-lock re-check as the docker warm serialize two ticks.

**What it restarts: nothing.** It restarts no k3s server or agent, no
`dockerd` and no Fabro server, and it drains and cordons nothing. The unit
orders `After=` k3s but `Wants=` only `network-online.target`, so it can never
start a stopped `dockerd` or k3s. A pull runs beside live pods exactly as
kubelet's own pulls do, at `Nice=10` and idle I/O priority.

### Operator procedure (the host window)

From the control node `vps`, in this repository's primary checkout on `master`:

```bash
just ansible-drift ansible/ci-pool.yml --tags sandbox_image_warm_containerd
just ansible-apply ansible/ci-pool.yml --tags sandbox_image_warm_containerd
```

No `--limit` is needed: the play targets `ci_pool`, and the `FACTORY_NODE` gate
selects the factory nodes inside it (add `--limit <host>` to converge one node
at a time). The role escalates with `become: true` per task, so the apply needs
no `-b` and no credential wrapper. The apply itself takes about 1 to 3 minutes
for the three nodes: fact gathering plus about a dozen file, unit and timer
tasks. Arming the timer fires its first tick at once, because its `OnBootSec`
is long past and the timer is `Persistent`. The pulls then run in the
background, an estimated 2 to 15 minutes per node depending on how many layers the node
already holds. The apply does not wait for them.

To verify, on each factory node (read-only):

```bash
systemctl list-timers livespec-sandbox-image-warm-containerd.timer
journalctl -u livespec-sandbox-image-warm-containerd.service --since -1h
sudo k3s crictl images | grep livespec-fabro-sandbox
```

The journal carries one line per image per tick, `already held` included, so
silence is not success.

### Rollback (the containerd store)

Set `sandbox_image_warm_state: absent` on the containerd `sandbox_image_warm`
entry in `ansible/ci-pool.yml` (or revert this role's change and add that line),
merge, then:

```bash
just ansible-drift ansible/ci-pool.yml --tags sandbox_image_warm_containerd
just ansible-apply ansible/ci-pool.yml --tags sandbox_image_warm_containerd
```

That stops and disables the containerd timer and removes its runner and units
on every factory node. The docker warm on the same host is untouched. Removing
the entry outright, or reverting alone, would leave the installed timer running,
because a converge never removes what it no longer declares.

The images already pulled stay. They are ordinary CRI images: on the server,
`prune-sandbox-images` keeps the newest releases and anything a committed
manifest pins, and on every node kubelet's image GC reclaims unused images under
disk pressure. If an image must go sooner, `sudo k3s crictl rmi <reference>`
removes it, in a maintainer-approved window, because it is a by-hand host
change. Know first that the CRI's `RemoveImage` deletes every reference of the
image record it resolves, so removing one tag can take a byte-identical sibling
tag with it (`ci-runner/k3s/phase2/warm-cache/README.md`). A pod that needs a
removed image simply pulls it again.

### Expiry (the containerd store)

Retired when the Kubernetes sandbox backend pre-pulls its own image on every
factory node, for example a DaemonSet the sandbox-driver plugin owns, or when
factory pod placement no longer depends on which node already holds the image.

## Expiry

This control is retired when a first pull can no longer race — when the
dispatcher serializes the pull of a run's image before it creates the run (the
coordinator's second named remedy, which belongs to
`livespec-orchestrator-beads-fabro` because only the dispatcher knows a run's
image before the run exists), or when the Kubernetes sandbox backend replaces
the docker image store on factory hosts with a cluster-side pull that is already
serialized. Until one of those lands, the warm is what keeps the window between
a tag bump and a dispatch from coinciding.

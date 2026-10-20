# `sandbox_image_warm` — per-host values for the inventory's `host_vars`

The host-side warm that keeps a docker Fabro factory host's local image store
ahead of the sandbox image tag its runs are about to need: a oneshot unit that
reads the fleet's current sandbox image version and pulls the corresponding tag
under a per-reference lock, armed by a systemd timer.

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
| `sandbox_image_warm_bin` | `/usr/local/sbin/livespec-sandbox-image-warm` | where the warm runner is installed |
| `sandbox_image_warm_unit_dir` | `/etc/systemd/system` | where the two units are installed |
| `sandbox_image_warm_service` | `livespec-sandbox-image-warm.service` | the oneshot unit the timer triggers |
| `sandbox_image_warm_timer` | `livespec-sandbox-image-warm.timer` | the timer the converge enables and starts |
| `sandbox_image_warm_image` | `ghcr.io/thewoolleyman/livespec-fabro-sandbox` | the image whose tags are warmed |
| `sandbox_image_warm_tag_prefixes` | `[python-agent]` | the layer prefixes to warm; one reference per prefix, `<image>:<prefix>-v<version>` |
| `sandbox_image_warm_pin_url` | this repository's `.release-please-manifest.json` on `master` | where the version is read from |
| `sandbox_image_warm_lock_dir` | `/run/livespec-sandbox-image-warm` | where the per-reference lock files live; on tmpfs, because a lock has no meaning across a reboot |
| `sandbox_image_warm_lock_timeout_seconds` | `1800` | how long a warm waits for a concurrent warm's pull before giving up; a warm that hits the ceiling exits non-zero and pulls NOTHING |
| `sandbox_image_warm_on_boot_sec` | `2min` | the first warm after a boot |
| `sandbox_image_warm_on_unit_active_sec` | `5min` | the cadence thereafter |
| `sandbox_image_warm_randomized_delay_sec` | `30` | jitter, so two factory hosts do not pull the same new tag in the same second |
| `sandbox_image_warm_timeout_start_sec` | `45min` | bounds ONE warm, layer download included |

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

```bash
sudo systemctl disable --now livespec-sandbox-image-warm.timer
sudo rm -f /etc/systemd/system/livespec-sandbox-image-warm.{service,timer} \
           /usr/local/sbin/livespec-sandbox-image-warm
sudo systemctl daemon-reload
```

Nothing else on the host changes: the warm holds no state but the tmpfs lock
files, and the images it pulled are ordinary images the existing
`docker-prune.timer` and `disk-guard` reclaim on their own terms.

## Expiry

This control is retired when a first pull can no longer race — when the
dispatcher serializes the pull of a run's image before it creates the run (the
coordinator's second named remedy, which belongs to
`livespec-orchestrator-beads-fabro` because only the dispatcher knows a run's
image before the run exists), or when the Kubernetes sandbox backend replaces
the docker image store on factory hosts with a cluster-side pull that is already
serialized. Until one of those lands, the warm is what keeps the window between
a tag bump and a dispatch from coinciding.

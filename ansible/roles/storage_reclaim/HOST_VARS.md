# storage_reclaim — per-host values for the inventory

These are the values that genuinely vary by machine, lifted from the
`fabro-hosts` files this role replaces:
`services/storage-reclaim/hosts/hp-xubuntu.env` and
`services/storage-reclaim/hosts/vps.env`, both measured on the live hosts on
2026-08-22. Merge each block into that host's `host_vars` in
`ansible/inventory/legacy.yml`.

Everything the two hosts agree on stays in `defaults/main.yml` and is not
repeated here: the 14-day artifact horizon, the 30-day orphan horizon, and the
daily schedule are fleet defaults. `storage_reclaim_service_group`,
`storage_reclaim_worktree_root` and `storage_reclaim_checkout_roots` are
defaulted as derivations of the service user and home, so each block below sets
one only where that derivation is wrong for the host.

```yaml
# hp-xubuntu
storage_reclaim_canonical_host: hp-xubuntu.perch-rudd.ts.net
storage_reclaim_system_hostname: hp-xubuntu
storage_reclaim_service_user: cwoolley
storage_reclaim_home: /home/cwoolley
# storage_reclaim_worktree_root defaults to /home/cwoolley/.worktrees, which
# DOES NOT EXIST on this host and is not expected to. hp is a dedicated factory
# running sandboxed dispatches rather than interactive sessions, so the worktree
# layer that dominates the vps has never appeared here. The reclaimer treats a
# missing root as an empty inventory, and the role reports it rather than
# failing, so the mechanism is armed and reporting if the layer ever appears.
# storage_reclaim_checkout_roots defaults to /home/cwoolley/repos, which is
# correct here: 3 clones, measured 2026-08-22.
```

```yaml
# vps
storage_reclaim_canonical_host: vps.perch-rudd.ts.net
# NOT the tailnet label. Tailscale serves vps.perch-rudd.ts.net, but
# `hostname -s` on this machine reports the Contabo-assigned vmi3006760. The
# reclaimer compares this value against the running host's own hostname, so a
# value derived from the tailnet name would refuse to run on the host it
# targets.
storage_reclaim_system_hostname: vmi3006760
storage_reclaim_service_user: ubuntu
storage_reclaim_home: /home/ubuntu
# OVERRIDE REQUIRED. The default derives this from the home directory, which
# would give /home/ubuntu/repos; the vps keeps its clones on the data volume.
# A wrong value here does not fail — it reports live worktrees as orphans,
# because orphan detection differences the on-disk worktrees against the
# worktrees registered by the clones under these roots.
storage_reclaim_checkout_roots: /data/projects
```

## hp's storage problem is not this service's

hp's disk filled to zero bytes on 2026-08-22 because of its CONTAINER layer,
which is the `container_reclaim` role's subject, not this one's. Do not widen
this role's host_vars to cover it.

## Values that are fleet defaults today but were measured per host

Recorded so a future divergence is a change to a known number rather than a
discovery. Neither host currently needs an override.

| Variable | hp-xubuntu | vps | Basis |
|---|---|---|---|
| `storage_reclaim_artifact_idle_days` | 14 | 14 | Measured on the vps across all 574 worktrees: 30 days reclaims 101.9 GB, 21 days 120.6 GB, 14 days 165.3 GB, 10 days 165.5 GB, 7 days 174.7 GB. The curve is flat between 10 and 14 days, so 14 is free against 10 and four days more conservative. hp's worktree layer is empty, so there is no hp measurement to derive a different value from. |
| `storage_reclaim_orphan_idle_days` | 30 | 30 | Removal is deliberately far more conservative than artifact reclamation: an artifact regenerates, an orphaned worktree holding unpushed work does not. The orphan report is unconditional and ignores this value. |
| `storage_reclaim_on_calendar` | daily | daily | The vps accumulated roughly 232 GB over about two months of session activity, and a daily pass holds the steady state well below the roughly 110 GB of headroom it had when this was measured. |
| `storage_reclaim_service_group` | cwoolley | ubuntu | Both hosts use a user-private group, which is what the default derives. |

## What the vps measurement actually found

Recorded because it is the reason this service exists: on 2026-08-22 the vps
held 574 worktrees under `~/.worktrees` carrying 231.7 GB of build artifacts.
That was 95% of the tree and 41% of a 678 GB disk which was 84% full with no
reclamation of any kind.

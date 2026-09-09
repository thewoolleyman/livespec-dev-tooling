# container_reclaim — per-host values for the inventory

These are the values that genuinely vary by machine, lifted from the
`fabro-hosts` files this role replaces:
`services/container-reclaim/hosts/hp-xubuntu.env` and
`services/container-reclaim/hosts/vps.env`, both measured on the live hosts on
2026-08-22. Merge each block into that host's `host_vars` in
`ansible/inventory/legacy.yml`.

Everything the two hosts agree on stays in `defaults/main.yml` and is not
repeated here: the service account (`root`), the 48-hour container horizon, the
72-hour image horizon, and the hourly schedule are fleet defaults, not per-host
values. Only override one of those in `host_vars` when a measurement on that
host justifies a different number.

```yaml
# hp-xubuntu
container_reclaim_canonical_host: hp-xubuntu.perch-rudd.ts.net
container_reclaim_system_hostname: hp-xubuntu
```

```yaml
# vps
container_reclaim_canonical_host: vps.perch-rudd.ts.net
# NOT the tailnet label. Tailscale serves vps.perch-rudd.ts.net, but
# `hostname -s` on this machine reports the Contabo-assigned vmi3006760. The
# reclaimer compares this value against the running host's own hostname, so a
# value derived from the tailnet name would refuse to run on the host it
# targets.
container_reclaim_system_hostname: vmi3006760
```

## Values that are fleet defaults today but were measured per host

Recorded so a future divergence is a change to a known number rather than a
discovery. Neither host currently needs an override.

| Variable | hp-xubuntu | vps | Basis |
|---|---|---|---|
| `container_reclaim_container_idle_hours` | 48 | 48 | The vps's bimodal writable-layer population has an empty middle between 12 hours and four days, so any horizon inside it reclaims the same 20652 MB. hp's own reclaimable total was never measured, so 48 is the vps derivation applied to hp, not an hp measurement. `docker ps -as` on hp settles it. |
| `container_reclaim_image_idle_hours` | 72 | 72 | The hp incident accumulated 28 unreferenced tags holding roughly 390 GB, about 14 GB per tag, against a ~2.3 GB re-pull. 72 hours bounds unreferenced tags to roughly three at the observed release cadence. |
| `container_reclaim_on_calendar` | hourly | hourly | hp accumulates about 4 GB/hour, so a daily pass would let roughly 100 GB build up between runs. The vps accumulates far more slowly, but its store shares the disk the worktree layer nearly filled, so the cost of being late there is paid by an unrelated subsystem. |
| `container_reclaim_service_user` / `_group` | root | root | Every action is a call to the container daemon over a root-owned socket, and the store roots are unreadable otherwise: measured on the vps at 1 MB as a normal user against 17163 MB as root. |

## Layout note, for whoever reads a size and doubts it

The two hosts INVERT their container store layout. hp keeps about 49 GB in
`/var/lib/containerd` with 3 MB in `/var/lib/docker`; the vps is the mirror
image, with about 43 GB in `/var/lib/docker`. Nothing in this role or in the
reclaimer is keyed on either path — the store is resolved from the daemon —
and that is why. A path-keyed mechanism measures a few megabytes on one of the
two hosts and reports success.
